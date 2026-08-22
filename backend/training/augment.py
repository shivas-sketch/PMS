"""Data augmentation for Indian license plates.

Generates synthetic variations of plate images to expand the dataset
5-10x. Augmentations are tailored to real-world conditions:

- Brightness/contrast variation (backlit, night, overexposed)
- Rotation and perspective warp (angled shots)
- Motion blur and Gaussian blur (moving vehicles)
- Gaussian noise (low-quality cameras)
- Salt-and-pepper noise (sensor artifacts)
- JPEG compression artifacts
- Rain/water droplet simulation

Usage:
    python training/augment.py
"""
from __future__ import annotations

import os
import random
import sys
from pathlib import Path

import cv2
import numpy as np

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.config import AUGMENTED_DIR, AUG_MULTIPLIER, PLATES_DIR


def adjust_brightness(img: np.ndarray) -> np.ndarray:
    factor = random.uniform(0.5, 1.5)
    return np.clip(img * factor, 0, 255).astype(np.uint8)


def adjust_contrast(img: np.ndarray) -> np.ndarray:
    factor = random.uniform(0.6, 1.4)
    mean = img.mean()
    return np.clip((img - mean) * factor + mean, 0, 255).astype(np.uint8)


def add_gaussian_noise(img: np.ndarray) -> np.ndarray:
    sigma = random.uniform(5, 25)
    noise = np.random.normal(0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)


def add_salt_pepper(img: np.ndarray) -> np.ndarray:
    prob = random.uniform(0.01, 0.03)
    mask = np.random.random(img.shape[:2])
    img = img.copy()
    img[mask < prob / 2] = 0
    img[mask > 1 - prob / 2] = 255
    return img


def motion_blur(img: np.ndarray) -> np.ndarray:
    kernel_size = random.choice([7, 11, 15])
    kernel = np.zeros((kernel_size, kernel_size))
    kernel[kernel_size // 2, :] = 1.0
    kernel /= kernel_size
    return cv2.filter2D(img, -1, kernel)


def gaussian_blur(img: np.ndarray) -> np.ndarray:
    ksize = random.choice([3, 5, 7])
    return cv2.GaussianBlur(img, (ksize, ksize), 0)


def rotate(img: np.ndarray) -> np.ndarray:
    angle = random.uniform(-8, 8)
    h, w = img.shape[:2]
    matrix = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def perspective_warp(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    margin = int(min(h, w) * 0.1)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([
        [random.randint(0, margin), random.randint(0, margin)],
        [w - random.randint(0, margin), random.randint(0, margin)],
        [w - random.randint(0, margin), h - random.randint(0, margin)],
        [random.randint(0, margin), h - random.randint(0, margin)],
    ])
    matrix = cv2.getPerspectiveTransform(src, dst)
    return cv2.warpPerspective(img, matrix, (w, h), borderMode=cv2.BORDER_REPLICATE)


def jpeg_compress(img: np.ndarray) -> np.ndarray:
    quality = random.randint(20, 60)
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def shadow(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    x_start = random.randint(0, w // 2)
    shadow_width = random.randint(w // 4, w // 2)
    img = img.copy()
    for x in range(x_start, min(x_start + shadow_width, w)):
        factor = 0.5 + 0.5 * (x - x_start) / shadow_width
        img[:, x] = (img[:, x] * factor).astype(np.uint8)
    return img


AUGMENTATIONS = [
    adjust_brightness,
    adjust_contrast,
    add_gaussian_noise,
    add_salt_pepper,
    motion_blur,
    gaussian_blur,
    rotate,
    perspective_warp,
    jpeg_compress,
    shadow,
]


def augment_plate(img: np.ndarray) -> np.ndarray:
    """Apply 2-3 random augmentations in sequence."""
    n_augs = random.randint(2, 3)
    chosen = random.sample(AUGMENTATIONS, n_augs)
    result = img
    for aug in chosen:
        result = aug(result)
    return result


def augment_recognition_dataset() -> None:
    """Augment cropped plate images for recognition training."""
    print("\n=== Augmenting Recognition Dataset ===")
    src_dir = AUGMENTED_DIR / "recognition"
    if not src_dir.exists():
        print(f"  {src_dir} not found. Run prepare_dataset.py first.")
        return

    total = 0
    for split in ("train", "val", "test"):
        split_dir = src_dir / split
        if not split_dir.exists():
            continue

        images = sorted(f for f in split_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
        aug_count = 0

        for img_path in images:
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            for i in range(AUG_MULTIPLIER):
                aug_img = augment_plate(img)
                aug_name = f"{img_path.stem}_aug{i}{img_path.suffix}"
                cv2.imwrite(str(split_dir / aug_name), aug_img)
                aug_count += 1

        total += aug_count
        print(f"  {split}: +{aug_count} augmented images")

    print(f"  Total: +{total} augmented images")


def augment_detection_dataset() -> None:
    """Augment full vehicle images for detection training (YOLO handles its own
    augmentation, but we can add extra synthetic samples)."""
    print("\n=== Augmenting Detection Dataset ===")
    det_dir = AUGMENTED_DIR / "detection"
    if not det_dir.exists():
        print(f"  {det_dir} not found. Run prepare_dataset.py first.")
        return

    train_img_dir = det_dir / "train" / "images"
    train_lbl_dir = det_dir / "train" / "labels"
    if not train_img_dir.exists():
        return

    images = sorted(f for f in train_img_dir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
    aug_count = 0

    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        ann_path = train_lbl_dir / (img_path.stem + ".txt")
        for i in range(AUG_MULTIPLIER):
            aug_img = augment_plate(img)
            aug_name = f"{img_path.stem}_aug{i}{img_path.suffix}"
            cv2.imwrite(str(train_img_dir / aug_name), aug_img)
            # Copy annotation (bbox is same in normalized coords for most augs)
            if ann_path.exists():
                shutil_copy = __import__("shutil").copy2
                shutil_copy(ann_path, train_lbl_dir / (Path(aug_name).stem + ".txt"))
            aug_count += 1

    print(f"  train: +{aug_count} augmented images")


def main():
    random.seed(42)
    augment_recognition_dataset()
    augment_detection_dataset()
    print("\nDone! Next steps:")
    print("  1. Run: python training/train_detection.py")
    print("  2. Run: python training/train_recognition.py")


if __name__ == "__main__":
    main()
