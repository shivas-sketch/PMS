"""Prepare datasets for training.

Two datasets are needed:
1. Detection dataset: full vehicle images + YOLO bbox annotations
2. Recognition dataset: cropped plate images + text labels

This script:
- Scans raw/ recursively for images and inline XML annotations
- Parses PASCAL VOC XML annotations and converts to YOLO format
- Extracts plate text from <name> tag (plate number is the class name)
  or from <attributes><number_plate_text> (Datacluster format)
- Crops plates from full images using bbox annotations (for recognition)
- Splits data into train/val/test (80/10/10)
- Generates YOLO dataset YAML for detection training

Supports two annotation styles:
- Style A (State-wise_OLX / google_images): <name>DL10CG4693</name> — plate text is the class
- Style B (Datacluster): <name>number_plate</name> + <attributes><number_plate_text>KL34A465</number_plate_text>

Usage:
    python training/prepare_dataset.py
"""
from __future__ import annotations

import random
import re
import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.config import (
    ANNOTATIONS_DIR,
    AUGMENTED_DIR,
    DATA_DIR,
    LABELS_FILE,
    PLATES_DIR,
    RAW_DIR,
)

SPLIT_RATIOS = (0.8, 0.1, 0.1)  # train, val, test
DETECTION_CLASSES = ["license_plate"]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# Names that are generic class labels, not plate text
GENERIC_CLASS_NAMES = {"number_plate", "license_plate", "plate", "dog", "person",
                       "cat", "tv", "car", "meatballs", "marinara sauce",
                       "tomato soup", "chicken noodle soup", "french onion soup",
                       "chicken breast", "ribs", "pulled pork", "hamburger", "cavity"}

# Plate text pattern: starts with 2 letters, then digits/letters (max 10 chars
# total, matching LPR_MAX_LABEL_LEN in training/config.py)
PLATE_TEXT_RE = re.compile(r"^[A-Z]{2}[\dA-Z]{2,8}$")


@dataclass
class VocObject:
    """Single object from a PASCAL VOC annotation."""
    name: str
    xmin: float
    ymin: float
    xmax: float
    ymax: float
    plate_text: Optional[str] = None


@dataclass
class VocAnnotation:
    """Parsed PASCAL VOC XML annotation."""
    filename: str
    width: int
    height: int
    objects: List[VocObject]


def _extract_plate_text(name: str, obj_elem: ET.Element) -> Optional[str]:
    """Extract plate text from a VOC object.

    Style A: <name> is the plate text itself (e.g., "DL10CG4693")
    Style B: <name> is "number_plate" and text is in <attributes>
    """
    name_upper = name.upper().strip()

    # Style A: name is the plate text
    if name_upper not in {n.upper() for n in GENERIC_CLASS_NAMES}:
        if PLATE_TEXT_RE.match(name_upper):
            return name_upper
        # Even if it doesn't match the strict regex, if it's not a generic
        # class name and looks alphanumeric, treat it as plate text.
        # Enforce max length so corrupted/placeholder names (e.g. duplicated
        # or malformed strings from source datasets) don't leak into training
        # and overflow LPR_MAX_LABEL_LEN.
        if (
            name_upper
            and 4 <= len(name_upper) <= 10
            and name_upper[0].isalpha()
            and any(c.isdigit() for c in name_upper)
        ):
            return name_upper

    # Style B: check attributes for number_plate_text
    attrs = obj_elem.find("attributes")
    if attrs is not None:
        for attr in attrs.findall("attribute"):
            attr_name = attr.findtext("name", "")
            if attr_name == "number_plate_text":
                text = attr.findtext("value", "")
                if text:
                    return text.upper().strip()

    return None


def parse_voc_xml(xml_path: Path) -> Optional[VocAnnotation]:
    """Parse a PASCAL VOC XML annotation file."""
    try:
        tree = ET.parse(str(xml_path))
    except ET.ParseError:
        print(f"  ERROR: failed to parse {xml_path}")
        return None

    root = tree.getroot()

    size_elem = root.find("size")
    if size_elem is None:
        print(f"  ERROR: no <size> in {xml_path}")
        return None

    width = int(float(size_elem.findtext("width", "0")))
    height = int(float(size_elem.findtext("height", "0")))
    if width == 0 or height == 0:
        print(f"  ERROR: invalid size in {xml_path}")
        return None

    filename = root.findtext("filename", xml_path.stem + ".jpg")

    objects: List[VocObject] = []
    for obj in root.findall("object"):
        name = obj.findtext("name", "unknown")
        bndbox = obj.find("bndbox")
        if bndbox is None:
            continue
        xmin = float(bndbox.findtext("xmin", "0"))
        ymin = float(bndbox.findtext("ymin", "0"))
        xmax = float(bndbox.findtext("xmax", "0"))
        ymax = float(bndbox.findtext("ymax", "0"))

        plate_text = _extract_plate_text(name, obj)

        objects.append(VocObject(
            name=name, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax,
            plate_text=plate_text,
        ))

    return VocAnnotation(
        filename=filename, width=width, height=height, objects=objects,
    )


def voc_to_yolo(ann: VocAnnotation) -> List[str]:
    """Convert VOC annotation to YOLO format lines.

    All objects are class 0 (license_plate).
    YOLO format: class x_center y_center width height (all normalized 0-1)
    """
    lines: List[str] = []
    w, h = ann.width, ann.height
    for obj in ann.objects:
        xc = (obj.xmin + obj.xmax) / 2.0 / w
        yc = (obj.ymin + obj.ymax) / 2.0 / h
        bw = (obj.xmax - obj.xmin) / w
        bh = (obj.ymax - obj.ymin) / h
        xc = max(0.0, min(1.0, xc))
        yc = max(0.0, min(1.0, yc))
        bw = max(0.0, min(1.0, bw))
        bh = max(0.0, min(1.0, bh))
        if bw <= 0 or bh <= 0:
            continue
        lines.append(f"0 {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}")
    return lines


def find_all_images(root: Path) -> List[Path]:
    """Recursively find all image files under root."""
    return sorted(
        f for f in root.rglob("*") if f.suffix.lower() in IMAGE_EXTS
    )


def find_all_xml(root: Path) -> List[Path]:
    """Recursively find all XML annotation files under root."""
    return sorted(
        f for f in root.rglob("*") if f.suffix.lower() == ".xml"
    )


def match_images_to_xml(
    images: List[Path], xml_files: List[Path]
) -> List[Tuple[Path, Path]]:
    """Match images to their XML annotations by filename stem.

    Searches both ANNOTATIONS_DIR and inline (next to image) XMLs.
    """
    xml_by_stem = {x.stem: x for x in xml_files}
    paired: List[Tuple[Path, Path]] = []
    for img in images:
        ann = xml_by_stem.get(img.stem)
        if ann:
            paired.append((img, ann))
    return paired


def prepare_detection_dataset() -> List[Tuple[Path, VocAnnotation]]:
    """Convert VOC XML to YOLO format and split into train/val/test.

    Returns list of (image_path, parsed_annotation) for use by recognition prep.
    """
    print("\n=== Preparing Detection Dataset ===")

    images = find_all_images(RAW_DIR)
    # Search both ANNOTATIONS_DIR and RAW_DIR for XMLs (inline annotations)
    xml_files = find_all_xml(ANNOTATIONS_DIR) + find_all_xml(RAW_DIR)

    print(f"  Found {len(images)} images, {len(xml_files)} XML annotations")

    if not images:
        print(f"No images found under {RAW_DIR}. Place vehicle images there first.")
        return []

    paired = match_images_to_xml(images, xml_files)
    unannotated = len(images) - len(paired)
    if unannotated:
        print(f"  WARNING: {unannotated} images have no XML annotation (skipped)")

    if not paired:
        print("No paired image+annotation found. Cannot prepare detection dataset.")
        return []

    print(f"  Matched {len(paired)} image+annotation pairs")

    parsed_pairs: List[Tuple[Path, VocAnnotation]] = []

    for img_path, ann_path in paired:
        ann = parse_voc_xml(ann_path)
        if ann is None or not ann.objects:
            print(f"  WARNING: no valid objects in {ann_path.name}")
            continue
        parsed_pairs.append((img_path, ann))

    print(f"  Parsed {len(parsed_pairs)} valid annotations")

    if not parsed_pairs:
        return []

    random.shuffle(parsed_pairs)
    n = len(parsed_pairs)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])

    splits = {
        "train": parsed_pairs[:n_train],
        "val": parsed_pairs[n_train:n_train + n_val],
        "test": parsed_pairs[n_train + n_val:],
    }

    for split, items in splits.items():
        img_dst = AUGMENTED_DIR / "detection" / split / "images"
        lbl_dst = AUGMENTED_DIR / "detection" / split / "labels"
        img_dst.mkdir(parents=True, exist_ok=True)
        lbl_dst.mkdir(parents=True, exist_ok=True)

        for img_path, ann in items:
            shutil.copy2(img_path, img_dst / img_path.name)
            yolo_lines = voc_to_yolo(ann)
            lbl_path = lbl_dst / (img_path.stem + ".txt")
            lbl_path.write_text("\n".join(yolo_lines) + "\n" if yolo_lines else "")

        print(f"  {split}: {len(items)} images")

    yaml_path = AUGMENTED_DIR / "detection" / "dataset.yaml"
    yaml_path.write_text(
        f"path: {AUGMENTED_DIR / 'detection'}\n"
        f"train: train/images\n"
        f"val: val/images\n"
        f"test: test/images\n"
        f"nc: {len(DETECTION_CLASSES)}\n"
        f"names: {DETECTION_CLASSES}\n"
    )
    print(f"  Dataset YAML: {yaml_path}")

    return parsed_pairs


def prepare_recognition_dataset(
    parsed_pairs: List[Tuple[Path, VocAnnotation]],
) -> None:
    """Crop plates from annotated images and build labels.txt for LPRNet.

    Only objects with plate_text are included in the recognition dataset.
    """
    print("\n=== Preparing Recognition Dataset ===")

    PLATES_DIR.mkdir(parents=True, exist_ok=True)

    # Clear old plate crops to avoid stale data
    for old in PLATES_DIR.iterdir():
        if old.suffix.lower() in IMAGE_EXTS:
            old.unlink()

    labels: dict[str, str] = {}
    if LABELS_FILE.exists():
        for line in LABELS_FILE.read_text().strip().splitlines():
            parts = line.strip().split(",", 1)
            if len(parts) == 2:
                labels[parts[0]] = parts[1]
        print(f"  Loaded {len(labels)} existing labels from {LABELS_FILE}")

    cropped = 0
    with_text = 0
    new_labels: dict[str, str] = {}

    for img_path, ann in parsed_pairs:
        img = cv2.imread(str(img_path))
        if img is None:
            print(f"  WARNING: cannot read {img_path}")
            continue

        # Use actual image dimensions (XML size may differ from actual)
        h_actual, w_actual = img.shape[:2]
        w, h = ann.width, ann.height
        scale_x = w_actual / w if w > 0 else 1.0
        scale_y = h_actual / h if h > 0 else 1.0

        for idx, obj in enumerate(ann.objects):
            x1 = int(max(0, obj.xmin * scale_x))
            y1 = int(max(0, obj.ymin * scale_y))
            x2 = int(min(w_actual, obj.xmax * scale_x))
            y2 = int(min(h_actual, obj.ymax * scale_y))
            if x2 <= x1 or y2 <= y1:
                continue

            crop = img[y1:y2, x1:x2]
            crop_name = f"{img_path.stem}_plate{idx}.jpg"
            crop_path = PLATES_DIR / crop_name
            cv2.imwrite(str(crop_path), crop)
            cropped += 1

            if obj.plate_text:
                new_labels[crop_name] = obj.plate_text.upper()
                with_text += 1

    print(f"  Cropped {cropped} plate images to {PLATES_DIR}")
    print(f"  {with_text} crops have plate text labels (from XML <name> or attributes)")

    # Replace old labels with new ones (old crops were deleted)
    labels = new_labels

    plate_images = sorted(
        f for f in PLATES_DIR.iterdir() if f.suffix.lower() in IMAGE_EXTS
    )
    if not plate_images:
        print("  No plate images found.")
        return

    unlabeled = [p.name for p in plate_images if p.name not in labels]
    if unlabeled:
        print(f"  WARNING: {len(unlabeled)} plates have no text label:")
        for name in unlabeled[:10]:
            print(f"    {name}")
        if len(unlabeled) > 10:
            print(f"    ... and {len(unlabeled) - 10} more")
        print(f"  Add labels to {LABELS_FILE} as: filename,PLATETEXT")

    random.shuffle(plate_images)
    n = len(plate_images)
    n_train = int(n * SPLIT_RATIOS[0])
    n_val = int(n * SPLIT_RATIOS[1])

    splits = {
        "train": plate_images[:n_train],
        "val": plate_images[n_train:n_train + n_val],
        "test": plate_images[n_train + n_val:],
    }

    for split, items in splits.items():
        dst = AUGMENTED_DIR / "recognition" / split
        dst.mkdir(parents=True, exist_ok=True)
        for old in dst.iterdir():
            if old.suffix.lower() in IMAGE_EXTS:
                old.unlink()
        for img_path in items:
            shutil.copy2(img_path, dst / img_path.name)
        print(f"  {split}: {len(items)} plate images")

    labels_path = AUGMENTED_DIR / "recognition" / "labels.txt"
    with open(labels_path, "w") as f:
        for name, text in sorted(labels.items()):
            f.write(f"{name},{text}\n")
    print(f"  Labels: {labels_path} ({len(labels)} entries)")

    with open(LABELS_FILE, "w") as f:
        for name, text in sorted(labels.items()):
            f.write(f"{name},{text}\n")
    print(f"  Labels also saved to: {LABELS_FILE}")

    labeled_count = sum(1 for p in plate_images if p.name in labels)
    print(f"\n  Summary: {labeled_count}/{len(plate_images)} plates have text labels")
    if labeled_count < len(plate_images):
        print(f"  NOTE: Manually add missing labels to {LABELS_FILE}")
        print(f"  Format: filename,PLATETEXT (e.g. img001_plate0.jpg,TN09BK1883)")


def main():
    random.seed(42)
    AUGMENTED_DIR.mkdir(parents=True, exist_ok=True)

    # Clear old augmented detection data
    det_dir = AUGMENTED_DIR / "detection"
    if det_dir.exists():
        shutil.rmtree(det_dir)

    parsed_pairs = prepare_detection_dataset()
    prepare_recognition_dataset(parsed_pairs)

    print("\nDone! Next steps:")
    if parsed_pairs:
        print("  1. Check labels.txt — add missing plate text labels")
        print("  2. Run: python training/augment.py")
        print("  3. Run: python training/train_detection.py")
        print("  4. Run: python training/train_recognition.py")
    else:
        print("  Fix data issues above before proceeding.")


if __name__ == "__main__":
    main()
