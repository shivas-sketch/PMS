"""Train YOLOv8 for license plate detection.

Fine-tunes a YOLOv8 model on the prepared detection dataset. The model
learns to detect license plate bounding boxes in vehicle images.

Usage:
    python training/train_detection.py [--epochs N] [--batch B] [--model yolov8s.pt]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.config import (
    AUGMENTED_DIR,
    DETECTION_OUTPUT,
    MODELS_DIR,
    YOLO_BASE_MODEL,
    YOLO_BATCH_SIZE,
    YOLO_EPOCHS,
    YOLO_IMG_SIZE,
)


def train(epochs: int, batch: int, base_model: str) -> None:
    import torch
    from ultralytics import YOLO

    if torch.cuda.is_available():
        device = "0"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"

    dataset_yaml = AUGMENTED_DIR / "detection" / "dataset.yaml"
    if not dataset_yaml.exists():
        print(f"Dataset not found: {dataset_yaml}")
        print("Run `python training/prepare_dataset.py` first.")
        return

    DETECTION_OUTPUT.mkdir(parents=True, exist_ok=True)

    print(f"Loading base model: {base_model}")
    model = YOLO(base_model)

    print(f"Training for {epochs} epochs, batch={batch}, imgsz={YOLO_IMG_SIZE}")
    results = model.train(
        data=str(dataset_yaml),
        epochs=epochs,
        batch=batch,
        imgsz=YOLO_IMG_SIZE,
        project=str(DETECTION_OUTPUT),
        name="plate_detection",
        save=True,
        save_period=10,
        patience=20,  # early stopping
        device=device,
        augment=True,
        fliplr=0.0,  # don't flip plates horizontally
        mosaic=0.5,
        mixup=0.1,
        degrees=10.0,
        translate=0.1,
        scale=0.3,
        shear=2.0,
        perspective=0.0,
        hsv_h=0.015,
        hsv_s=0.5,
        hsv_v=0.3,
    )

    # Copy best model to models directory
    best_pt = DETECTION_OUTPUT / "plate_detection" / "weights" / "best.pt"
    if best_pt.exists():
        target = MODELS_DIR / "plate_model" / "license_plate.pt"
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(best_pt, target)
        print(f"\nBest model copied to: {target}")
        print("Update .env: LICENSE_PLATE_MODEL_PATH=models/plate_model/license_plate.pt")
    else:
        print(f"\nWARNING: best.pt not found at {best_pt}")

    print(f"\nTraining complete. Results: {DETECTION_OUTPUT / 'plate_detection'}")


def main():
    parser = argparse.ArgumentParser(description="Train YOLO11 for plate detection")
    parser.add_argument("--epochs", type=int, default=YOLO_EPOCHS)
    parser.add_argument("--batch", type=int, default=YOLO_BATCH_SIZE)
    parser.add_argument("--model", type=str, default=YOLO_BASE_MODEL)
    args = parser.parse_args()
    train(args.epochs, args.batch, args.model)


if __name__ == "__main__":
    main()
