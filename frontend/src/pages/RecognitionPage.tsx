import { useCallback, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Grid2 as Grid,
  IconButton,
  InputAdornment,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import CloudUploadOutlinedIcon from '@mui/icons-material/CloudUploadOutlined';
import CameraAltOutlinedIcon from '@mui/icons-material/CameraAltOutlined';
import LocalParkingOutlinedIcon from '@mui/icons-material/LocalParkingOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import CheckOutlinedIcon from '@mui/icons-material/CheckOutlined';
import CloseOutlinedIcon from '@mui/icons-material/CloseOutlined';
import { post, postForm, ApiError } from '../api/client';
import type { RecognitionResult, ParkingSession, AddVehicleRequest } from '../types';
import { HOSPITAL_SIDES } from '../types';

const VEHICLE_TYPES = ['Bike', 'Scooter', 'Auto Rickshaw', 'Hatchback', 'Sedan', 'SUV', 'Car', 'Van', 'Pickup', 'Truck', 'Bus', 'Other'];
const WHEEL_OPTIONS = [2, 3, 4, 6, 8, 10];

export function RecognitionPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [result, setResult] = useState<RecognitionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [parkingStatus, setParkingStatus] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [addingToParking, setAddingToParking] = useState(false);
  const [editingNumber, setEditingNumber] = useState(false);
  const [editedVehicleNumber, setEditedVehicleNumber] = useState('');
  const [hospitalSide, setHospitalSide] = useState('');

  const handleFileSelect = useCallback((file: File | null) => {
    setSelectedFile(file);
    setResult(null);
    setError(undefined);
    setParkingStatus(null);
    setEditingNumber(false);
    setEditedVehicleNumber('');
    setHospitalSide('');
    if (file) {
      setPreviewUrl(URL.createObjectURL(file));
    } else {
      setPreviewUrl(null);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      const file = e.dataTransfer.files?.[0] ?? null;
      if (file && file.type.startsWith('image/')) {
        handleFileSelect(file);
      }
    },
    [handleFileSelect],
  );

  const submit = async () => {
    if (!selectedFile) return;
    setLoading(true);
    setError(undefined);
    setResult(null);
    setParkingStatus(null);
    setEditingNumber(false);
    setEditedVehicleNumber('');
    setHospitalSide('');
    try {
      const formData = new FormData();
      formData.append('image', selectedFile);
      setResult(await postForm<RecognitionResult>('/vehicle-recognition', formData));
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Recognition request failed.');
    } finally {
      setLoading(false);
    }
  };

  const confidencePct = (v: number | null) => (v == null ? '—' : `${Math.round(v * 100)}%`);

  const currentVehicleNumber = editingNumber ? editedVehicleNumber : (result?.vehicleNumber ?? '');

  const startEdit = () => {
    setEditedVehicleNumber(result?.vehicleNumber ?? '');
    setEditingNumber(true);
  };

  const cancelEdit = () => {
    setEditingNumber(false);
    setEditedVehicleNumber('');
  };

  const saveEdit = () => {
    if (result && editedVehicleNumber.trim()) {
      setResult({ ...result, vehicleNumber: editedVehicleNumber.trim() });
    }
    setEditingNumber(false);
    setEditedVehicleNumber('');
  };

  const addToParking = async () => {
    const vehicleNumber = editingNumber ? editedVehicleNumber.trim() : result?.vehicleNumber;
    if (!vehicleNumber) return;
    setAddingToParking(true);
    setParkingStatus(null);
    try {
      const body: AddVehicleRequest = {
        vehicleNumber,
        wheelCategory: result!.wheelCategory,
        vehicleType: result!.vehicleType,
        hospitalSide: hospitalSide || undefined,
      };
      const session = await post<ParkingSession>('/parking/vehicles', body);
      setParkingStatus({
        type: 'success',
        message: `${session.vehicleNumber} added to parking (Session: ${session.sessionId})`,
      });
    } catch (cause) {
      setParkingStatus({
        type: 'error',
        message: cause instanceof ApiError ? cause.message : 'Failed to add vehicle to parking.',
      });
    } finally {
      setAddingToParking(false);
    }
  };

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">Vehicle Recognition</Typography>
        <Typography color="text.secondary">
          Upload a photo of a vehicle. The system detects the vehicle, reads the plate, and classifies the type — all in memory.
        </Typography>
      </Box>

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 7 }}>
          <Card
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            sx={{ border: '2px dashed', borderColor: 'divider', cursor: 'pointer' }}
            onClick={() => fileInputRef.current?.click()}
          >
            <CardContent>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp"
                hidden
                onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)}
              />
              {previewUrl ? (
                <Box sx={{ textAlign: 'center' }}>
                  <Box
                    component="img"
                    src={previewUrl}
                    alt="Vehicle preview"
                    sx={{ maxWidth: '100%', maxHeight: 360, borderRadius: 2 }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                    {selectedFile?.name} — Click to change
                  </Typography>
                </Box>
              ) : (
                <Stack alignItems="center" spacing={2} sx={{ py: 6 }}>
                  <CloudUploadOutlinedIcon sx={{ fontSize: 64, color: 'text.secondary' }} />
                  <Typography variant="h6" color="text.secondary">
                    Drop an image here or click to browse
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    JPG, PNG, or WebP — max 10 MB
                  </Typography>
                </Stack>
              )}
            </CardContent>
          </Card>

          <Stack direction="row" spacing={2} sx={{ mt: 2 }}>
            <Button
              variant="contained"
              startIcon={<CameraAltOutlinedIcon />}
              disabled={!selectedFile || loading}
              onClick={() => void submit()}
            >
              Recognize Vehicle
            </Button>
            {selectedFile && !loading && (
              <Button variant="outlined" onClick={() => handleFileSelect(null)}>
                Clear
              </Button>
            )}
          </Stack>
        </Grid>

        <Grid size={{ xs: 12, md: 5 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Result
              </Typography>
              <Divider sx={{ mb: 2 }} />
              {loading && (
                <Stack alignItems="center" spacing={2} sx={{ py: 4 }}>
                  <CircularProgress />
                  <Typography color="text.secondary">Analyzing image…</Typography>
                </Stack>
              )}
              {error && <Alert severity="error">{error}</Alert>}
              {!loading && !result && !error && (
                <Typography color="text.secondary" sx={{ py: 4, textAlign: 'center' }}>
                  Upload an image and click "Recognize Vehicle" to see results.
                </Typography>
              )}
              {result && !loading && (
                <Stack spacing={2}>
                  <Box>
                    <Typography variant="overline" color="text.secondary">
                      Vehicle Number
                    </Typography>
                    {editingNumber ? (
                      <TextField
                        fullWidth
                        autoFocus
                        size="small"
                        value={editedVehicleNumber}
                        onChange={(e) => setEditedVehicleNumber(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void saveEdit();
                          if (e.key === 'Escape') cancelEdit();
                        }}
                        InputProps={{
                          endAdornment: (
                            <InputAdornment position="end">
                              <IconButton size="small" onClick={saveEdit} disabled={!editedVehicleNumber.trim()}>
                                <CheckOutlinedIcon fontSize="small" />
                              </IconButton>
                              <IconButton size="small" onClick={cancelEdit}>
                                <CloseOutlinedIcon fontSize="small" />
                              </IconButton>
                            </InputAdornment>
                          ),
                        }}
                        helperText="Press Enter to save, Esc to cancel"
                      />
                    ) : (
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="h5" fontWeight={700}>
                          {result.vehicleNumber ?? 'Not detected'}
                        </Typography>
                        {result.vehicleNumber && (
                          <IconButton size="small" onClick={startEdit} aria-label="Edit vehicle number">
                            <EditOutlinedIcon fontSize="small" />
                          </IconButton>
                        )}
                      </Stack>
                    )}
                  </Box>
                  <Stack direction="row" spacing={2}>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="overline" color="text.secondary">
                        Vehicle Type
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        size="small"
                        value={result.vehicleType}
                        onChange={(e) => setResult({ ...result, vehicleType: e.target.value })}
                      >
                        {VEHICLE_TYPES.map((t) => (
                          <MenuItem key={t} value={t}>{t}</MenuItem>
                        ))}
                        {!VEHICLE_TYPES.includes(result.vehicleType) && (
                          <MenuItem value={result.vehicleType}>{result.vehicleType}</MenuItem>
                        )}
                      </TextField>
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="overline" color="text.secondary">
                        Wheels
                      </Typography>
                      <TextField
                        select
                        fullWidth
                        size="small"
                        value={result.wheelCategory}
                        onChange={(e) => setResult({ ...result, wheelCategory: parseInt(e.target.value, 10) })}
                      >
                        {WHEEL_OPTIONS.map((w) => (
                          <MenuItem key={w} value={w}>{w}</MenuItem>
                        ))}
                      </TextField>
                    </Box>
                  </Stack>
                  <Box>
                    <Typography variant="overline" color="text.secondary">
                      Overall Confidence
                    </Typography>
                    <LinearProgress
                      variant="determinate"
                      value={result.confidence * 100}
                      sx={{ height: 10, borderRadius: 5, mt: 0.5 }}
                    />
                    <Typography variant="caption" color="text.secondary">
                      {Math.round(result.confidence * 100)}%
                    </Typography>
                  </Box>
                  <Box>
                    <Typography variant="overline" color="text.secondary">
                      Detection Details
                    </Typography>
                    <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                      <DetailRow label="Vehicle Detection" value={confidencePct(result.details.vehicleDetectionConfidence)} />
                      <DetailRow label="Plate Detection" value={confidencePct(result.details.plateDetectionConfidence)} />
                      <DetailRow label="OCR" value={confidencePct(result.details.ocrConfidence)} />
                    </Stack>
                  </Box>
                  {result.warnings.length > 0 && (
                    <Box>
                      <Typography variant="overline" color="text.secondary">
                        Warnings
                      </Typography>
                      <Stack spacing={0.5} sx={{ mt: 0.5 }}>
                        {result.warnings.map((w, i) => (
                          <Chip key={i} label={w} size="small" color="warning" variant="outlined" />
                        ))}
                      </Stack>
                    </Box>
                  )}
                  {currentVehicleNumber && (
                    <>
                      <Divider sx={{ my: 1 }} />
                      <Box>
                        <Typography variant="overline" color="text.secondary">
                          Hospital Side / Gate
                        </Typography>
                        <TextField
                          select
                          fullWidth
                          size="small"
                          value={hospitalSide}
                          onChange={(e) => setHospitalSide(e.target.value)}
                          helperText="Where the vehicle was received (optional)"
                        >
                          <MenuItem value="">— Not specified —</MenuItem>
                          {HOSPITAL_SIDES.map((side) => (
                            <MenuItem key={side} value={side}>
                              {side}
                            </MenuItem>
                          ))}
                        </TextField>
                      </Box>
                      <Button
                        variant="contained"
                        color="success"
                        startIcon={<LocalParkingOutlinedIcon />}
                        disabled={addingToParking || (editingNumber && !editedVehicleNumber.trim())}
                        onClick={() => void addToParking()}
                        fullWidth
                      >
                        {addingToParking ? <CircularProgress size={20} /> : 'Add to Parking'}
                      </Button>
                      {parkingStatus && (
                        <Alert severity={parkingStatus.type} sx={{ mt: 1 }}>
                          {parkingStatus.message}
                        </Alert>
                      )}
                    </>
                  )}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Stack>
  );
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <Stack direction="row" justifyContent="space-between">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body2" fontWeight={600}>
        {value}
      </Typography>
    </Stack>
  );
}
