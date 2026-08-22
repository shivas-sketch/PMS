"""Export trained models for production inference.

Copies trained model weights to the models/ directory and prints
instructions for updating the .env configuration.

Usage:
    python training/export_model.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.config import DETECTION_OUTPUT, MODELS_DIR, RECOGNITION_OUTPUT


def export_detection_model() -> None:
    """Copy best YOLO detection weights to models/."""
    src = DETECTION_OUTPUT / "plate_detection" / "weights" / "best.pt"
    if not src.exists():
        print(f"Detection model not found: {src}")
        print("Run: python training/train_detection.py first.")
        return

    dst = MODELS_DIR / "plate_model" / "license_plate.pt"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Detection model exported: {dst}")


def export_recognition_model() -> None:
    """Copy best LPRNet weights to models/."""
    src = RECOGNITION_OUTPUT / "lprnet_best.pth"
    if not src.exists():
        print(f"Recognition model not found: {src}")
        print("Run: python training/train_recognition.py first.")
        return

    dst = MODELS_DIR / "plate_model" / "lprnet.pth"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Recognition model exported: {dst}")


def main():
    print("=== Exporting Trained Models ===\n")
    export_detection_model()
    export_recognition_model()
    print("\n=== Update .env ===")
    print("LICENSE_PLATE_MODEL_PATH=models/plate_model/license_plate.pt")
    print("LPRNET_MODEL_PATH=models/plate_model/lprnet.pth")
    print("\nRestart the backend to use the new models.")


if __name__ == "__main__":
    main()
