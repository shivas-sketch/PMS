"""Train LPRNet for license plate character recognition.

Trains the LPRNet model on cropped plate images with text labels using
CTC (Connectionist Temporal Classification) loss.

Dataset format:
    training/data/augmented/recognition/
        train/   — plate image crops (.jpg)
        val/     — plate image crops (.jpg)
        test/    — plate image crops (.jpg)
    labels.txt   — filename,PLATETEXT (one per line)

Usage:
    python training/train_recognition.py [--epochs N] [--batch B] [--lr LR]
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

# MPS (Apple GPU) does not implement the CTC loss op; fall back to CPU for
# unsupported ops only, while the rest of the model still runs on MPS.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

import cv2
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from training.config import (
    AUGMENTED_DIR,
    MODELS_DIR,
    CHAR_TO_IDX,
    CHARS,
    IDX_TO_CHAR,
    LABELS_FILE,
    LPR_BATCH_SIZE,
    LPR_EPOCHS,
    LPR_INPUT_HEIGHT,
    LPR_INPUT_WIDTH,
    LPR_LEARNING_RATE,
    LPR_MAX_LABEL_LEN,
    LPR_WEIGHT_DECAY,
    NUM_CLASSES,
    RECOGNITION_OUTPUT,
)
from training.models.lprnet import LPRNet


# Matches the "_augN" suffix appended by augment.py before the extension,
# e.g. "plate0_aug3.jpg" -> "plate0.jpg"
_AUG_SUFFIX_RE = re.compile(r"_aug\d+(?=\.[^.]+$)")


def _base_label_key(filename: str) -> str:
    """Strip an augmentation suffix (if any) to find the original label key."""
    return _AUG_SUFFIX_RE.sub("", filename)


class PlateDataset(Dataset):
    """Dataset for license plate recognition training."""

    def __init__(self, split_dir: Path, labels: dict[str, str], is_train: bool = True):
        self.split_dir = split_dir
        self.labels = labels
        self.is_train = is_train
        all_images = sorted(
            f for f in split_dir.iterdir()
            if f.suffix.lower() in (".jpg", ".jpeg", ".png")
        )
        # Only keep images that resolve to a known plate text label (via base
        # name for augmented files). Unlabeled images would otherwise train
        # the model to predict an empty string, corrupting CTC loss/accuracy.
        self.images = [
            f for f in all_images if _base_label_key(f.name) in labels
        ]
        skipped = len(all_images) - len(self.images)
        if skipped:
            print(f"  {split_dir}: skipping {skipped}/{len(all_images)} images with no label")

    def __len__(self) -> int:
        return len(self.images)

    def __getitem__(self, idx: int):
        img_path = self.images[idx]
        img = cv2.imread(str(img_path))
        if img is None:
            # Return a dummy sample if image can't be loaded
            img = np.zeros((LPR_INPUT_HEIGHT, LPR_INPUT_WIDTH, 3), dtype=np.uint8)

        # Resize to LPRNet input size
        img = cv2.resize(img, (LPR_INPUT_WIDTH, LPR_INPUT_HEIGHT))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Normalize to [0, 1] and convert to CHW
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC → CHW

        # Get label (resolve augmented filenames back to their base label key)
        label_text = self.labels.get(_base_label_key(img_path.name), "")
        label_indices = [CHAR_TO_IDX[c] for c in label_text.upper() if c in CHAR_TO_IDX]
        label_len = len(label_indices)

        # Pad to max length
        if len(label_indices) < LPR_MAX_LABEL_LEN:
            label_indices += [0] * (LPR_MAX_LABEL_LEN - len(label_indices))

        return (
            torch.from_numpy(img),
            torch.tensor(label_indices, dtype=torch.long),
            torch.tensor(label_len, dtype=torch.long),
            img_path.name,
        )


def load_labels() -> dict[str, str]:
    """Load plate text labels from labels.txt."""
    labels: dict[str, str] = {}
    labels_file = AUGMENTED_DIR / "recognition" / "labels.txt"
    if not labels_file.exists():
        labels_file = LABELS_FILE
    if not labels_file.exists():
        print(f"WARNING: labels file not found at {labels_file}")
        return labels

    for line in labels_file.read_text().strip().splitlines():
        parts = line.strip().split(",", 1)
        if len(parts) == 2:
            labels[parts[0]] = parts[1]
    print(f"Loaded {len(labels)} plate labels")
    return labels


def ctc_decode(logits: torch.Tensor, blank: int = NUM_CLASSES) -> list[str]:
    """Greedy CTC decode: merge consecutive duplicates, remove blanks."""
    pred = logits.argmax(dim=-1)  # (B, T)
    results = []
    for b in range(pred.shape[0]):
        chars = []
        prev = -1
        for t in range(pred.shape[1]):
            idx = pred[b, t].item()
            if idx != prev and idx != blank:
                chars.append(IDX_TO_CHAR.get(idx, ""))
            prev = idx
        results.append("".join(chars))
    return results


def evaluate(model: LPRNet, loader: DataLoader, device: torch.device) -> tuple[float, float]:
    """Evaluate model on a dataset. Returns (accuracy, avg_loss)."""
    model.eval()
    correct = 0
    total = 0
    total_loss = 0.0
    ctc_loss = nn.CTCLoss(blank=NUM_CLASSES, zero_infinity=True)

    with torch.no_grad():
        for images, labels, label_lens, filenames in loader:
            images = images.to(device)
            labels = labels.to(device)
            label_lens = label_lens.to(device)

            logits = model(images)  # (B, T, C)
            B, T, C = logits.shape

            # CTC loss expects (T, B, C) logits, (B, S) targets, (B,) input lengths, (B,) target lengths
            log_probs = nn.functional.log_softmax(logits, dim=-1).permute(1, 0, 2)  # (T, B, C)
            input_lens = torch.full((B,), T, dtype=torch.long, device=device)

            # Flatten labels to 1D for CTC
            flat_labels = []
            for i in range(B):
                n = label_lens[i].item()
                flat_labels.append(labels[i, :n])
            if flat_labels:
                flat_labels = torch.cat(flat_labels)
            else:
                flat_labels = torch.tensor([], dtype=torch.long, device=device)

            loss = ctc_loss(log_probs, flat_labels, input_lens, label_lens)
            total_loss += loss.item()

            # Decode predictions
            preds = ctc_decode(logits.cpu())
            for i, pred in enumerate(preds):
                n = label_lens[i].item()
                target = "".join(IDX_TO_CHAR.get(labels[i, j].item(), "") for j in range(n))
                if pred == target:
                    correct += 1
                total += 1

    accuracy = correct / total if total > 0 else 0.0
    avg_loss = total_loss / len(loader) if len(loader) > 0 else 0.0
    return accuracy, avg_loss


def train(epochs: int, batch_size: int, lr: float) -> None:
    """Train LPRNet on the plate recognition dataset."""
    if torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"Device: {device}")

    # Load labels
    labels = load_labels()
    if not labels:
        print("No labels found. Prepare the dataset first.")
        print("Run: python training/prepare_dataset.py")
        return

    # Create datasets
    train_dir = AUGMENTED_DIR / "recognition" / "train"
    val_dir = AUGMENTED_DIR / "recognition" / "val"

    if not train_dir.exists():
        print(f"Training data not found: {train_dir}")
        print("Run: python training/prepare_dataset.py first.")
        return

    train_ds = PlateDataset(train_dir, labels, is_train=True)
    val_ds = PlateDataset(val_dir, labels, is_train=False) if val_dir.exists() else None

    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True, num_workers=0, drop_last=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False, num_workers=0) if val_ds else None

    print(f"Train: {len(train_ds)} samples, Val: {len(val_ds) if val_ds else 0} samples")

    # Create model
    model = LPRNet(num_classes=NUM_CLASSES, input_h=LPR_INPUT_HEIGHT, input_w=LPR_INPUT_WIDTH)
    model = model.to(device)

    # Optimizer and scheduler
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=LPR_WEIGHT_DECAY)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=10)
    ctc_loss = nn.CTCLoss(blank=NUM_CLASSES, zero_infinity=True)

    RECOGNITION_OUTPUT.mkdir(parents=True, exist_ok=True)
    best_val_acc = 0.0
    best_model_path = RECOGNITION_OUTPUT / "lprnet_best.pth"

    for epoch in range(1, epochs + 1):
        model.train()
        epoch_loss = 0.0
        n_batches = 0

        for images, label_tensors, label_lens, _ in train_loader:
            images = images.to(device)
            label_tensors = label_tensors.to(device)
            label_lens = label_lens.to(device)

            optimizer.zero_grad()
            logits = model(images)  # (B, T, C)
            B, T, C = logits.shape

            log_probs = nn.functional.log_softmax(logits, dim=-1).permute(1, 0, 2)
            input_lens = torch.full((B,), T, dtype=torch.long, device=device)

            flat_labels = []
            for i in range(B):
                n = label_lens[i].item()
                flat_labels.append(label_tensors[i, :n])
            flat_labels = torch.cat(flat_labels) if flat_labels else torch.tensor([], dtype=torch.long, device=device)

            loss = ctc_loss(log_probs, flat_labels, input_lens, label_lens)
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            n_batches += 1

        avg_train_loss = epoch_loss / n_batches if n_batches > 0 else 0.0

        # Validation
        val_acc, val_loss = 0.0, 0.0
        if val_loader:
            val_acc, val_loss = evaluate(model, val_loader, device)
            scheduler.step(val_loss)

        lr_current = optimizer.param_groups[0]["lr"]
        print(
            f"Epoch {epoch}/{epochs} | train_loss={avg_train_loss:.4f} | "
            f"val_loss={val_loss:.4f} val_acc={val_acc:.2%} | lr={lr_current:.6f}"
        )

        # Save best model
        if val_acc > best_val_acc:
            best_val_acc = val_acc
            torch.save(model.state_dict(), best_model_path)
            print(f"  → Saved best model (val_acc={val_acc:.2%})")

        # Always save latest checkpoint so progress isn't lost if interrupted
        torch.save(model.state_dict(), RECOGNITION_OUTPUT / "lprnet_latest.pth")

    print(f"\nTraining complete. Best val accuracy: {best_val_acc:.2%}")
    print(f"Best model: {best_model_path}")

    # Also save final model
    final_path = RECOGNITION_OUTPUT / "lprnet_final.pth"
    torch.save(model.state_dict(), final_path)
    print(f"Final model: {final_path}")

    # Copy best model to models directory for the app to pick up
    if best_model_path.exists():
        target = MODELS_DIR / "plate_model" / "lprnet.pth"
        target.parent.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(best_model_path, target)
        print(f"\nBest model copied to: {target}")
        print("Update .env: LPRNET_MODEL_PATH=models/plate_model/lprnet.pth")


def main():
    parser = argparse.ArgumentParser(description="Train LPRNet for plate recognition")
    parser.add_argument("--epochs", type=int, default=LPR_EPOCHS)
    parser.add_argument("--batch", type=int, default=LPR_BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=LPR_LEARNING_RATE)
    args = parser.parse_args()
    train(args.epochs, args.batch, args.lr)


if __name__ == "__main__":
    main()
