# Hospital Valet Parking - Backend (FastAPI)

Vehicle recognition (YOLO + plate detection + OCR, **100% in-memory**) and
Firestore-backed parking capacity management, kept as two independent
APIs.

## Architecture

```
backend/
├── app/
│   ├── main.py                 FastAPI app, startup model loading, error handlers
│   ├── api/
│   │   ├── recognition.py      POST /api/vehicle-recognition
│   │   └── parking.py          /api/parking/*
│   ├── services/
│   │   ├── vehicle_detection_service.py       YOLO vehicle detection
│   │   ├── vehicle_classification_service.py Car -> Hatchback/Sedan/SUV refinement (pluggable)
│   │   ├── plate_detection_service.py         YOLO plate detector + OpenCV heuristic fallback
│   │   ├── ocr_service.py                     PaddleOCR (preferred) / EasyOCR (fallback)
│   │   ├── recognition_service.py             Orchestrates the full pipeline
│   │   └── parking_service.py                 Parking business logic
│   ├── repositories/
│   │   └── parking_repository.py   Firestore transactions (capacity/vehicles/sessions)
│   ├── schemas/            Pydantic request/response models (camelCase JSON)
│   ├── config/             settings.py (env-driven config), firebase.py (Firestore client)
│   └── utils/
│       ├── image_processing.py    in-memory decode/crop/enhance, never touches disk
│       └── vehicle_number.py      Indian plate normalization
├── models/                 optional local weights (vehicle_model/, plate_model/)
├── tests/
├── requirements.txt
└── .env.example
```

## No image storage - by design

- The upload is read into a `bytes` buffer, decoded straight into an OpenCV
  `numpy` array (`cv2.imdecode`), processed, and explicitly `del`eted /
  garbage-collected before the response is returned (`app/services/recognition_service.py`,
  `app/utils/image_processing.py::discard`).
- Nothing under `app/` calls `open(...)` for writing, `cv2.imwrite(...)`, or
  `shutil.copy(...)` on the uploaded image, and no `/uploads`, `/images`, or
  `/temp-images` directory exists or is created.
- The recognition response never contains the image, a Base64 payload, or
  an image URL.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit as needed
```

`paddlepaddle`/`paddleocr` wheels can lag behind the newest CPython
release. If they fail to install, either use Python 3.11/3.12 for this
venv, or simply skip them - `OCRService` automatically falls back to
`easyocr`, and if neither is installed the API still runs (recognition
responses will just carry an "OCR unavailable" style low-confidence
result instead of crashing).

Similarly, `ultralytics`/plate detection: if `ultralytics` isn't
installed or `yolov8n.pt` can't be downloaded (no internet), vehicle
detection degrades to "no vehicle found" per request rather than
crashing the app - `VehicleDetectionService`/`NumberPlateDetectionService`
load lazily and log a warning instead of raising on startup.

### Firestore credentials

Pick one:

1. **Service account (real Firestore)** - Firebase Console -> Project
   Settings -> Service accounts -> Generate new private key -> set
   `FIREBASE_CREDENTIALS_PATH=/path/to/key.json` and
   `FIREBASE_PROJECT_ID=smart-hospital-parking` in `.env`.
2. **Local emulator (no real credentials needed)**:
   ```bash
   firebase emulators:start --only firestore
   ```
   then set `FIRESTORE_EMULATOR_HOST=localhost:8080` in `.env`.

> The Firebase config you shared (`apiKey`, `authDomain`, ...) is the
> **web SDK** config used by client apps; `firebase-admin` on the backend
> needs a **service account key** or the emulator instead - it does not
> use the web `apiKey`.

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Docs: `http://localhost:8000/docs`

## Firestore schema

```
parking_config/main            { totalCapacity, availableSlots, occupiedSlots, sessionCounter }
vehicles/{vehicleNumber}        { vehicleNumber, wheelCategory, vehicleType, createdAt, updatedAt, activeSessionId, lastSessionId }
parking_sessions/{sessionId}    { sessionId, vehicleNumber, wheelCategory, vehicleType, status, entryTime, exitTime }
```

Storing `activeSessionId` on the vehicle document means duplicate/active
and double-exit checks are single-document reads inside the transaction -
**no composite Firestore indexes need to be provisioned** for this POC.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/vehicle-recognition` | Analyze an uploaded image in memory. Never touches Firestore. |
| POST | `/api/parking/vehicles` | Register a vehicle entry (decrements `availableSlots`). |
| GET | `/api/parking/vehicles?status=ACTIVE\|EXITED\|ALL` | List sessions. |
| GET | `/api/parking/vehicles/{vehicleNumber}` | Current/most recent session for a plate. |
| POST | `/api/parking/vehicles/{vehicleNumber}/exit` | Mark exit (increments `availableSlots`). |
| GET | `/api/parking/capacity` | `{ totalCapacity, availableSlots, occupiedSlots }` |

```bash
curl -X POST -F "image=@car.jpg" http://localhost:8000/api/vehicle-recognition

curl -X POST http://localhost:8000/api/parking/vehicles \
  -H "Content-Type: application/json" \
  -d '{"vehicleNumber":"TS09AB1234","wheelCategory":4,"vehicleType":"SUV"}'

curl -X POST http://localhost:8000/api/parking/vehicles/TS09AB1234/exit
```

### Error shapes

Every domain error returns `{"error": "<CODE>", "message": "..."}` (see
`app/exceptions.py`):

| Code | HTTP | When |
|---|---|---|
| `INVALID_IMAGE` | 400 | Unsupported content-type or file too large |
| `VEHICLE_RECOGNITION_FAILED` | 422 | No vehicle and no plate/registration could be determined at all |
| `VEHICLE_ALREADY_ACTIVE` | 409 | Vehicle already has an ACTIVE session |
| `PARKING_FULL` | 409 | `availableSlots == 0` |
| `VEHICLE_ALREADY_EXITED` | 409 | Exit called on a vehicle with no active session |
| `VEHICLE_NOT_FOUND` | 404 | No parking record for that plate |

## Configuration (`.env`)

See `.env.example` for the full list: model paths
(`VEHICLE_MODEL_PATH`, `LICENSE_PLATE_MODEL_PATH`,
`VEHICLE_CLASSIFIER_MODEL_PATH`), OCR engine selection, confidence
thresholds (`VEHICLE_CONFIDENCE_THRESHOLD`, `PLATE_CONFIDENCE_THRESHOLD`,
`OCR_CONFIDENCE_THRESHOLD`), upload limits, and the wheel-category
mapping (`app/config/settings.py::Settings.WHEEL_MAPPING`).

## Confidence calculation

`app/services/recognition_service.py::_combine_confidence`: average of
whatever sub-confidences (vehicle/plate/OCR) were actually produced; a
flat penalty is subtracted when plate detection or OCR didn't run at all,
so an incomplete read is never reported as confidently as a complete one.
This is an explicit, documented policy - not a fabricated number.

## Tests

```bash
pytest -v
```

All tests substitute the heavy ML services (YOLO/OCR) with lightweight
stubs (`tests/test_recognition_service.py`) and Firestore with an
in-memory fake repository that has identical method signatures/exceptions
(`tests/fakes.py`), so the full suite runs fast with no GPU, model
weights, or live GCP project required. Coverage includes:

- Recognition: valid car/bike image, plate detected, no plate detected,
  OCR failure, unsupported file type, oversized image, low-confidence
  result, nothing-detected (422).
- Parking: 100->99->98 on entry, duplicate keeps capacity unchanged,
  exit 98->99, double-exit keeps 99 (409), full parking rejects entry,
  concurrent entries never overbook (threaded test against a shared
  fake repository lock).

  # run front end

  cd /Users/satyasivasundarsalagrama/projects/DG/pms/frontend
  npm install
  npm run dev

  # run backend
cd /Users/satyasivasundarsalagrama/projects/DG/pms/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

cd /Users/satyasivasundarsalagrama/projects/DG/pms/backend
firebase emulators:start --only firestore


