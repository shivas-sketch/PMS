# End-to-End License Plate Recognition Training

Train a custom LPR (License Plate Recognition) model for Indian license plates.

## Architecture

```
Input Image → YOLOv8 (plate detection) → LPRNet (character recognition) → Plate Text
```

- **YOLOv8**: Fine-tuned for Indian license plate detection (bounding box)
- **LPRNet**: Lightweight CNN + CTC loss for character-by-plate recognition (no OCR engine needed)

## Directory Structure

```
training/
├── README.md                  # This file
├── requirements.txt           # Training-specific dependencies
├── config.py                  # Training configuration (hyperparams, paths)
├── prepare_dataset.py         # Convert raw images + annotations to training format
├── augment.py                 # Data augmentation for Indian plates
├── train_detection.py         # YOLOv8 plate detection training
├── train_recognition.py       # LPRNet character recognition training
├── export_model.py            # Export trained models for inference
├── models/
│   ├── lprnet.py              # LPRNet model architecture
│   └── __init__.py
├── data/
│   ├── raw/                   # Put raw plate images here
│   ├── annotations/           # YOLO format annotations
│   ├── plates/                # Cropped plate images (for recognition training)
│   ├── labels.txt             # Plate text labels (for recognition training)
│   └── augmented/             # Augmented dataset (auto-generated)
└── output/
    ├── detection/             # Trained YOLO weights
    └── recognition/           # Trained LPRNet weights
```

## Quick Start

### 1. Install training dependencies

```bash
pip install -r training/requirements.txt
```

### 2. Prepare your dataset

Place raw vehicle images in `training/data/raw/` and create YOLO-format
annotations in `training/data/annotations/` (one `.txt` per image with
`class x_center y_center width height` per line, normalized 0-1).

For recognition training, place cropped plate images in
`training/data/plates/` and create `training/data/labels.txt` with
one `filename,PLATE_TEXT` per line.

```bash
python training/prepare_dataset.py
```

### 3. Augment data

Generates synthetic variations (brightness, rotation, blur, noise, perspective)
to expand the dataset 5-10x.

```bash
python training/augment.py
```

### 4. Train plate detection (YOLOv8)

```bash
python training/train_detection.py
```

Output: `training/output/detection/best.pt`

### 5. Train character recognition (LPRNet)

```bash
python training/train_recognition.py
```

Output: `training/output/recognition/lprnet_best.pth`

### 6. Export & integrate

```bash
python training/export_model.py
```

Copies trained models to `models/` and updates the inference pipeline.

## Indian License Plate Character Set

```
0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ
```

States: AN AP AR AS BR CH CG DD DH DL GA GJ HP HR JH JK KA KL LA LD MH ML MN MP MZ NL OD PB PY RJ SK ST TN TS TR UK UP WB
```

## Dataset Sources

- **OpenALPR benchmark**: https://openalpr.com/faq.html (sample images)
- **AOLP benchmark**: Academia Sinica license plate dataset
- **Custom collection**: Use the recognition page to capture plates, then
  manually verify and save crops with labels
- **Synthetic generation**: Use `augment.py` to create variations from
  existing plates
