"""One-off diagnostic: evaluate the best recognition checkpoint on ONLY the
original (non-augmented) validation crops, to isolate whether augmentation
noise or dataset size/diversity is the dominant cause of low val accuracy.

Usage:
    python training/diagnose_recognition.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import numpy as np
import torch

from training.config import (
    AUGMENTED_DIR,
    IDX_TO_CHAR,
    LPR_INPUT_HEIGHT,
    LPR_INPUT_WIDTH,
    NUM_CLASSES,
    RECOGNITION_OUTPUT,
)
from training.models.lprnet import LPRNet


def ctc_decode_one(logits: torch.Tensor) -> str:
    pred = logits.argmax(dim=-1)
    chars = []
    prev = -1
    for t in range(pred.shape[0]):
        idx = pred[t].item()
        if idx != prev and idx < NUM_CLASSES:
            chars.append(IDX_TO_CHAR.get(idx, ""))
        prev = idx
    return "".join(chars)


def main() -> None:
    labels: dict[str, str] = {}
    labels_file = AUGMENTED_DIR / "recognition" / "labels.txt"
    for line in labels_file.read_text().strip().splitlines():
        parts = line.split(",", 1)
        if len(parts) == 2:
            labels[parts[0]] = parts[1]

    val_dir = AUGMENTED_DIR / "recognition" / "val"
    orig_images = [
        f for f in val_dir.iterdir()
        if f.suffix.lower() in (".jpg", ".jpeg", ".png")
        and "_aug" not in f.name
        and f.name in labels
    ]
    print(f"Original (non-augmented) val images with labels: {len(orig_images)}")

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    model = LPRNet(num_classes=NUM_CLASSES, input_h=LPR_INPUT_HEIGHT, input_w=LPR_INPUT_WIDTH).to(device)
    model.load_state_dict(torch.load(RECOGNITION_OUTPUT / "lprnet_best.pth", map_location=device))
    model.eval()

    correct = 0
    results = []
    with torch.no_grad():
        for f in orig_images:
            img = cv2.imread(str(f))
            img = cv2.resize(img, (LPR_INPUT_WIDTH, LPR_INPUT_HEIGHT))
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            img = np.transpose(img, (2, 0, 1))
            x = torch.from_numpy(img).unsqueeze(0).to(device)
            logits = model(x)[0].cpu()
            pred = ctc_decode_one(logits)
            target = labels[f.name]
            results.append((f.name, target, pred))
            if pred == target:
                correct += 1

    acc = correct / len(orig_images) if orig_images else 0.0
    print(f"Accuracy on original val images: {correct}/{len(orig_images)} = {acc:.2%}")
    print("Sample predictions:")
    for name, target, pred in results[:20]:
        mark = "OK" if target == pred else ""
        print(f"  target={target:12s} pred={pred:12s} {mark}")


if __name__ == "__main__":
    main()
