import { useEffect, useState } from 'react';
import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
} from '@mui/material';
import { get, patch, ApiError } from '../api/client';
import type { ParkingArea, ParkingAreaList, ParkingSession, ParkingSlot, ParkingSlotList } from '../types';

type Props = {
  session: ParkingSession;
  onClose: () => void;
  onAssigned: () => void;
};

export function AssignSlotDialog({ session, onClose, onAssigned }: Props) {
  const [areas, setAreas] = useState<ParkingArea[]>([]);
  const [selectedAreaId, setSelectedAreaId] = useState('');
  const [slots, setSlots] = useState<ParkingSlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState('');
  const [useCorridor, setUseCorridor] = useState(false);
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void get<ParkingAreaList>('/parking/areas')
      .then((data) => {
        setAreas(data.areas);
        if (session.areaId) {
          setSelectedAreaId(session.areaId);
        } else if (data.areas.length > 0) {
          setSelectedAreaId(data.areas[0].areaId);
        }
      })
      .catch(() => {});
  }, [session.areaId]);

  useEffect(() => {
    setSelectedSlotId('');
    setUseCorridor(false);
    if (selectedAreaId) {
      void get<ParkingSlotList>(`/parking/areas/${selectedAreaId}/slots`)
        .then((data) => setSlots(data.slots.filter((s) => s.status === 'AVAILABLE')))
        .catch(() => setSlots([]));
    } else {
      setSlots([]);
    }
  }, [selectedAreaId]);

  const selectedArea = areas.find((a) => a.areaId === selectedAreaId);

  const submit = async () => {
    if (!useCorridor && !selectedSlotId) return;
    if (useCorridor && !selectedAreaId) return;
    setSaving(true);
    setError(undefined);
    try {
      const body = useCorridor
        ? { useCorridor: true, areaId: selectedAreaId }
        : { slotId: selectedSlotId };
      await patch<ParkingSession>(
        `/parking/vehicles/${encodeURIComponent(session.vehicleNumber)}/slot`,
        body,
      );
      onAssigned();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to assign slot.');
    } finally {
      setSaving(false);
    }
  };

  const dialogTitle = session.slotNumber ? `Change Slot — ${session.vehicleNumber}` : `Select Slot — ${session.vehicleNumber}`;
  const submitLabel = session.slotNumber ? 'Change Slot' : 'Select Slot';

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{dialogTitle}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info" sx={{ py: 0.5 }}>
            Current slot: <strong>{session.slotNumber || 'None'}</strong>
            {session.areaName ? ` in ${session.areaName}` : ''}
          </Alert>
          <TextField
            select
            label="Parking Area"
            value={selectedAreaId}
            onChange={(e) => setSelectedAreaId(e.target.value)}
            helperText="Select the area to find an available slot"
          >
            {areas.map((area) => (
              <MenuItem key={area.areaId} value={area.areaId}>
                {area.name} ({area.areaType}) — {area.availableSlots}/{area.totalSlots} free
              </MenuItem>
            ))}
          </TextField>
          {selectedArea && selectedArea.corridorCapacity > 0 && (
            <FormControlLabel
              control={
                <Switch
                  checked={useCorridor}
                  onChange={(e) => setUseCorridor(e.target.checked)}
                  disabled={selectedArea.corridorAvailable <= 0}
                />
              }
              label={`Park in corridor (${selectedArea.corridorAvailable}/${selectedArea.corridorCapacity} free, unnumbered)`}
            />
          )}
          {!useCorridor && (
            <TextField
              select
              label="Available Slot"
              value={selectedSlotId}
              onChange={(e) => setSelectedSlotId(e.target.value)}
              helperText={
                selectedArea?.corridorCapacity && selectedArea.corridorAvailable > 0
                  ? 'Or enable corridor parking above'
                  : slots.length === 0
                    ? 'No available slots in this area'
                    : 'Select a new slot'
              }
              disabled={slots.length === 0}
            >
              {slots
                .filter((slot) => !slot.isCorridorSlot)
                .sort((a, b) => a.slotNumber.localeCompare(b.slotNumber, undefined, { numeric: true }))
                .map((slot) => (
                  <MenuItem key={slot.slotId} value={slot.slotId}>
                    {slot.slotNumber}
                  </MenuItem>
                ))}
            </TextField>
          )}
          {useCorridor && (
            <Alert severity="info" sx={{ py: 0.5 }}>
              Vehicle will be parked in the corridor of {selectedArea?.name}.
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={(!useCorridor && !selectedSlotId) || saving}
        >
          {saving ? 'Saving…' : submitLabel}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
