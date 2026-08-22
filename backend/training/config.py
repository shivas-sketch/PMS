"""Training configuration for end-to-end LPR.

All hyperparameters and paths are centralized here so you can tune
without editing training scripts.
"""
from __future__ import annotations

from pathlib import Path

# --- Paths ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"
MODELS_DIR = BASE_DIR.parent / "models"

RAW_DIR = DATA_DIR / "raw"
ANNOTATIONS_DIR = DATA_DIR / "annotations"
PLATES_DIR = DATA_DIR / "plates"
AUGMENTED_DIR = DATA_DIR / "augmented"
LABELS_FILE = DATA_DIR / "labels.txt"

DETECTION_OUTPUT = OUTPUT_DIR / "detection"
RECOGNITION_OUTPUT = OUTPUT_DIR / "recognition"

# --- Character set for Indian plates -------------------------------------
# 36 characters: 0-9 + A-Z
CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CHAR_TO_IDX = {c: i for i, c in enumerate(CHARS)}
IDX_TO_CHAR = {i: c for i, c in enumerate(CHARS)}
NUM_CLASSES = len(CHARS)  # 36 + 1 (CTC blank is auto-added by loss)

# --- LPRNet hyperparameters ----------------------------------------------
LPR_INPUT_HEIGHT = 48
LPR_INPUT_WIDTH = 144
LPR_MAX_LABEL_LEN = 10  # max plate chars (e.g. TN09BK1883 = 10)
LPR_BATCH_SIZE = 32
LPR_LEARNING_RATE = 0.001
LPR_EPOCHS = 100
LPR_WEIGHT_DECAY = 5e-4

# --- YOLO detection hyperparameters --------------------------------------
YOLO_BASE_MODEL = "yolo11n.pt"  # YOLO11 nano for speed; use yolo11s.pt for accuracy
YOLO_EPOCHS = 100
YOLO_IMG_SIZE = 640
YOLO_BATCH_SIZE = 16

# --- Augmentation --------------------------------------------------------
AUG_MULTIPLIER = 5  # generate 5x augmented samples per original
