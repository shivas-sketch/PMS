import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid2 as Grid,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import AddOutlinedIcon from '@mui/icons-material/AddOutlined';
import DeleteOutlineOutlinedIcon from '@mui/icons-material/DeleteOutlineOutlined';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import LayersOutlinedIcon from '@mui/icons-material/LayersOutlined';
import DirectionsWalkOutlinedIcon from '@mui/icons-material/DirectionsWalkOutlined';
import { del, get, patch, post, ApiError } from '../api/client';
import type { ParkingArea, ParkingAreaList, ParkingSlot, ParkingSlotList, AreaType, BulkCreateSlotsResponse, SlotStatus } from '../types';

const AREA_TYPES: AreaType[] = ['BASEMENT', 'GROUND', 'SIDE', 'OUTSIDE', 'ROOFTOP', 'OTHER'];

const AREA_TYPE_COLORS: Record<AreaType, 'primary' | 'secondary' | 'success' | 'warning' | 'info' | 'default'> = {
  BASEMENT: 'primary',
  GROUND: 'success',
  SIDE: 'info',
  OUTSIDE: 'warning',
  ROOFTOP: 'secondary',
  OTHER: 'default',
};

export function ParkingLayoutPage() {
  const [areas, setAreas] = useState<ParkingArea[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [areaDialogOpen, setAreaDialogOpen] = useState(false);
  const [selectedArea, setSelectedArea] = useState<ParkingArea | null>(null);
  const [slots, setSlots] = useState<ParkingSlot[]>([]);
  const [slotsLoading, setSlotsLoading] = useState(false);
  const [slotFilter, setSlotFilter] = useState<'all' | 'regular' | 'corridor'>('all');

  const filteredSlots = useMemo(() => {
    if (slotFilter === 'corridor') return slots.filter((s) => s.isCorridorSlot);
    if (slotFilter === 'regular') return slots.filter((s) => !s.isCorridorSlot);
    return slots;
  }, [slots, slotFilter]);
  const [slotDialogOpen, setSlotDialogOpen] = useState(false);
  const [bulkSlotDialogOpen, setBulkSlotDialogOpen] = useState(false);
  const [editingSlot, setEditingSlot] = useState<ParkingSlot | null>(null);
  const [corridorDialogArea, setCorridorDialogArea] = useState<ParkingArea | null>(null);
  const [busy, setBusy] = useState<string>();

  const loadAreas = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const data = await get<ParkingAreaList>('/parking/areas');
      setAreas(data.areas);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load parking areas.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAreas();
  }, [loadAreas]);

  const loadSlots = useCallback(async (areaId: string) => {
    setSlotsLoading(true);
    try {
      const data = await get<ParkingSlotList>(`/parking/areas/${areaId}/slots`);
      setSlots(data.slots);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load slots.');
    } finally {
      setSlotsLoading(false);
    }
  }, []);

  const handleAreaClick = (area: ParkingArea) => {
    setSelectedArea(area);
    void loadSlots(area.areaId);
  };

  const handleDeleteArea = async (areaId: string) => {
    setBusy(`area-${areaId}`);
    setError(undefined);
    try {
      await del(`/parking/areas/${areaId}`);
      if (selectedArea?.areaId === areaId) {
        setSelectedArea(null);
        setSlots([]);
      }
      await loadAreas();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to delete area.');
    } finally {
      setBusy(undefined);
    }
  };

  const handleDeleteSlot = async (slotId: string) => {
    setBusy(`slot-${slotId}`);
    setError(undefined);
    try {
      await del(`/parking/slots/${slotId}`);
      if (selectedArea) {
        await loadSlots(selectedArea.areaId);
        await loadAreas();
      }
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to delete slot.');
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4">Parking Layout</Typography>
          <Typography color="text.secondary">
            Manage parking areas (basement, side, outside) and individual slots.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <IconButton onClick={() => void loadAreas()} aria-label="Refresh areas">
            <RefreshOutlinedIcon />
          </IconButton>
          <Button
            startIcon={<AddOutlinedIcon />}
            variant="contained"
            onClick={() => setAreaDialogOpen(true)}
          >
            Add Area
          </Button>
        </Stack>
      </Stack>

      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 5 }}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" gutterBottom>
              Parking Areas
            </Typography>
            <Stack spacing={1.5}>
              {areas.length === 0 && (
                <Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                  No areas yet. Create one to get started.
                </Typography>
              )}
              {areas.map((area) => (
                <Paper
                  key={area.areaId}
 variant="outlined"
                  sx={{
                    p: 1.5,
                    cursor: 'pointer',
                    borderColor: selectedArea?.areaId === area.areaId ? 'primary.main' : 'divider',
                    bgcolor: selectedArea?.areaId === area.areaId ? 'action.selected' : 'transparent',
                  }}
                  onClick={() => handleAreaClick(area)}
                >
                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography fontWeight={700}>{area.name}</Typography>
                        <Chip
                          size="small"
                          label={area.areaType}
                          color={AREA_TYPE_COLORS[area.areaType]}
                          variant="outlined"
                        />
                        {area.corridorCapacity > 0 && (
                          <Tooltip title="Corridor parking (unnumbered overflow slots)">
                            <Chip
                              size="small"
                              icon={<DirectionsWalkOutlinedIcon />}
                              label={`${area.corridorOccupied}/${area.corridorCapacity} corridor`}
                              color="secondary"
                              variant="outlined"
                            />
                          </Tooltip>
                        )}
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {area.occupiedSlots}/{area.totalSlots} occupied
                        {area.description ? ` · ${area.description}` : ''}
                      </Typography>
                    </Box>
                    <Stack direction="row" spacing={0}>
                      <Tooltip title="Configure corridor parking">
                        <IconButton
                          size="small"
                          color="secondary"
                          onClick={(e) => {
                            e.stopPropagation();
                            setCorridorDialogArea(area);
                          }}
                        >
                          <DirectionsWalkOutlinedIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Delete area">
                        <span>
                          <IconButton
                            size="small"
                            color="error"
                            disabled={busy === `area-${area.areaId}` || area.occupiedSlots > 0 || area.corridorOccupied > 0}
                            onClick={(e) => {
                              e.stopPropagation();
                              void handleDeleteArea(area.areaId);
                            }}
                          >
                            {busy === `area-${area.areaId}` ? (
                              <CircularProgress size={18} />
                            ) : (
                              <DeleteOutlineOutlinedIcon fontSize="small" />
                            )}
                          </IconButton>
                        </span>
                      </Tooltip>
                    </Stack>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 7 }}>
          {selectedArea ? (
            <Paper sx={{ p: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                <Box>
                  <Typography variant="h6">{selectedArea.name} — Slots</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {selectedArea.availableSlots} available · {selectedArea.occupiedSlots} occupied · {selectedArea.totalSlots} total
                  </Typography>
                  {selectedArea.corridorCapacity > 0 && (
                    <Typography variant="body2" color="text.secondary">
                      Corridor: {selectedArea.corridorAvailable} available · {selectedArea.corridorOccupied} occupied · {selectedArea.corridorCapacity} total
                    </Typography>
                  )}
                </Box>
                <Stack direction="row" spacing={1}>
                  <Button
                    startIcon={<LayersOutlinedIcon />}
                    variant="outlined"
                    size="small"
                    onClick={() => setBulkSlotDialogOpen(true)}
                  >
                    Add Bulk Slots
                  </Button>
                  <Button
                    startIcon={<AddOutlinedIcon />}
                    variant="outlined"
                    size="small"
                    onClick={() => setSlotDialogOpen(true)}
                  >
                    Add Slot
                  </Button>
                </Stack>
              </Stack>

              {slotsLoading ? (
                <LinearProgress />
              ) : (
                <>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                    <ToggleButtonGroup
                      value={slotFilter}
                      exclusive
                      size="small"
                      onChange={(_, value) => value && setSlotFilter(value)}
                      aria-label="slot filter"
                    >
                      <ToggleButton value="all" aria-label="all slots">All</ToggleButton>
                      <ToggleButton value="regular" aria-label="regular slots">Slots</ToggleButton>
                      <ToggleButton value="corridor" aria-label="corridor slots">Corridor</ToggleButton>
                    </ToggleButtonGroup>
                    <Typography variant="caption" color="text.secondary">
                      Showing {filteredSlots.length} of {slots.length}
                    </Typography>
                  </Stack>
                  {filteredSlots.length === 0 ? (
                    <Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                      {slotFilter === 'corridor'
                        ? 'No corridor slots in this area.'
                        : slotFilter === 'regular'
                          ? 'No regular slots in this area.'
                          : 'No slots in this area yet.'}
                    </Typography>
                  ) : (
                    <Box
                      sx={{
                        display: 'flex',
                        flexWrap: 'wrap',
                        gap: 1,
                      }}
                    >
                      {filteredSlots.map((slot) => (
                        <Tooltip
                      key={slot.slotId}
                      title={
                        slot.isCorridorSlot
                          ? slot.status === 'OCCUPIED'
                            ? `Corridor slot occupied by ${slot.vehicleNumber}`
                            : 'Corridor parking (unnumbered)'
                          : slot.status === 'OCCUPIED'
                            ? `Occupied by ${slot.vehicleNumber}`
                            : slot.status === 'AVAILABLE'
                              ? 'Available'
                              : slot.status
                      }
                    >
                      <Paper
                        variant="outlined"
                        sx={{
                          width: 80,
                          height: 70,
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderColor:
                            slot.isCorridorSlot ? 'secondary.main' :
                            slot.status === 'AVAILABLE' ? 'success.main' :
                            slot.status === 'OCCUPIED' ? 'error.main' : 'divider',
                          bgcolor:
                            slot.isCorridorSlot ? 'secondary.lighter' :
                            slot.status === 'AVAILABLE' ? 'success.lighter' :
                            slot.status === 'OCCUPIED' ? 'error.lighter' : 'action.hover',
                          position: 'relative',
                        }}
                      >
                        <Typography
                          fontWeight={700}
                          fontSize={slot.isCorridorSlot ? 12 : 14}
                          color={slot.isCorridorSlot ? 'secondary.main' : 'text.primary'}
                        >
                          {slot.isCorridorSlot ? `C-${slot.slotNumber}` : slot.slotNumber}
                        </Typography>
                        <Chip
                          size="small"
                          label={
                            slot.isCorridorSlot
                              ? slot.status === 'OCCUPIED'
                                ? slot.vehicleNumber
                                : 'Corridor'
                              : slot.status === 'AVAILABLE'
                                ? 'Free'
                                : slot.status === 'OCCUPIED'
                                  ? slot.vehicleNumber
                                  : slot.status
                          }
                          color={slot.isCorridorSlot ? 'secondary' : undefined}
                          sx={{ mt: 0.5, fontSize: 10, maxWidth: 72 }}
                        />
                        {!slot.isCorridorSlot && slot.status === 'AVAILABLE' && (
                          <IconButton
                            size="small"
                            sx={{ position: 'absolute', top: -8, right: -8, bgcolor: 'background.paper' }}
                            disabled={busy === `slot-${slot.slotId}`}
                            onClick={() => void handleDeleteSlot(slot.slotId)}
                          >
                            {busy === `slot-${slot.slotId}` ? (
                              <CircularProgress size={14} />
                            ) : (
                              <DeleteOutlineOutlinedIcon sx={{ fontSize: 14 }} />
                            )}
                          </IconButton>
                        )}
                        {!slot.isCorridorSlot && (
                          <IconButton
                            size="small"
                            sx={{ position: 'absolute', bottom: -8, right: -8, bgcolor: 'background.paper' }}
                            onClick={() => setEditingSlot(slot)}
                          >
                            <EditOutlinedIcon sx={{ fontSize: 14 }} />
                          </IconButton>
                        )}
                      </Paper>
                        </Tooltip>
                      ))}
                    </Box>
                  )}
                </>
              )}
            </Paper>
          ) : (
            <Paper sx={{ p: 4, textAlign: 'center' }}>
              <Typography color="text.secondary">
                Select an area to view and manage its slots.
              </Typography>
            </Paper>
          )}
        </Grid>
      </Grid>

      <CreateAreaDialog
        open={areaDialogOpen}
        onClose={() => setAreaDialogOpen(false)}
        onCreated={() => {
          setAreaDialogOpen(false);
          void loadAreas();
        }}
      />

      {corridorDialogArea && (
        <EditCorridorDialog
          area={corridorDialogArea}
          onClose={() => setCorridorDialogArea(null)}
          onUpdated={(updated) => {
            setCorridorDialogArea(null);
            if (selectedArea?.areaId === updated.areaId) {
              setSelectedArea(updated);
            }
            void loadAreas();
          }}
        />
      )}

      {selectedArea && (
        <CreateSlotDialog
          open={slotDialogOpen}
          areaName={selectedArea.name}
          onClose={() => setSlotDialogOpen(false)}
          onCreated={() => {
            setSlotDialogOpen(false);
            void loadSlots(selectedArea.areaId);
            void loadAreas();
          }}
          areaId={selectedArea.areaId}
        />
      )}

      {selectedArea && (
        <BulkCreateSlotsDialog
          open={bulkSlotDialogOpen}
          areaName={selectedArea.name}
          onClose={() => setBulkSlotDialogOpen(false)}
          onCreated={() => {
            setBulkSlotDialogOpen(false);
            void loadSlots(selectedArea.areaId);
            void loadAreas();
          }}
          areaId={selectedArea.areaId}
        />
      )}

      {editingSlot && selectedArea && (
        <EditSlotDialog
          slot={editingSlot}
          onClose={() => setEditingSlot(null)}
          onUpdated={() => {
            setEditingSlot(null);
            void loadSlots(selectedArea.areaId);
            void loadAreas();
          }}
        />
      )}
    </Stack>
  );
}

function CreateAreaDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [name, setName] = useState('');
  const [areaType, setAreaType] = useState<AreaType>('BASEMENT');
  const [description, setDescription] = useState('');
  const [corridorCapacity, setCorridorCapacity] = useState('0');
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError(undefined);
    try {
      await post('/parking/areas', {
        name,
        areaType,
        description: description || undefined,
        corridorCapacity: parseInt(corridorCapacity, 10) || 0,
      });
      setName('');
      setAreaType('BASEMENT');
      setDescription('');
      setCorridorCapacity('0');
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to create area.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add Parking Area</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            required
            label="Area Name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            helperText="e.g. Basement 1, Side Parking, Outside Lot"
          />
          <TextField
            select
            label="Area Type"
            value={areaType}
            onChange={(e) => setAreaType(e.target.value as AreaType)}
            fullWidth
          >
            {AREA_TYPES.map((t) => (
              <MenuItem key={t} value={t}>
                {t}
              </MenuItem>
            ))}
          </TextField>
          <TextField
            label="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            helperText="e.g. Near emergency entrance"
          />
          <TextField
            label="Corridor Parking Slots (optional)"
            type="number"
            value={corridorCapacity}
            onChange={(e) => setCorridorCapacity(e.target.value)}
            helperText="Unnumbered overflow slots, e.g. corridor space (0 = none)"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void submit()} disabled={!name || saving}>
          {saving ? 'Creating…' : 'Create Area'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function EditCorridorDialog({
  area,
  onClose,
  onUpdated,
}: {
  area: ParkingArea;
  onClose: () => void;
  onUpdated: (updated: ParkingArea) => void;
}) {
  const [corridorCapacity, setCorridorCapacity] = useState(String(area.corridorCapacity));
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const capacityNum = parseInt(corridorCapacity, 10);
  const isInvalid = Number.isNaN(capacityNum) || capacityNum < area.corridorOccupied;

  const submit = async () => {
    if (isInvalid) return;
    setSaving(true);
    setError(undefined);
    try {
      const updated = await patch<ParkingArea>(`/parking/areas/${area.areaId}/corridor`, {
        corridorCapacity: capacityNum,
      });
      onUpdated(updated);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update corridor capacity.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Corridor Parking — {area.name}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info" sx={{ py: 0.5 }}>
            {area.corridorOccupied} corridor slot(s) currently occupied
          </Alert>
          <TextField
            autoFocus
            label="Corridor Parking Slots"
            type="number"
            value={corridorCapacity}
            onChange={(e) => setCorridorCapacity(e.target.value)}
            error={isInvalid}
            helperText={
              isInvalid
                ? `Cannot be less than ${area.corridorOccupied} (currently occupied)`
                : 'Unnumbered overflow slots, e.g. corridor space'
            }
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void submit()} disabled={isInvalid || saving}>
          {saving ? 'Saving…' : 'Save Changes'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function CreateSlotDialog({
  open,
  onClose,
  onCreated,
  areaId,
  areaName,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  areaId: string;
  areaName: string;
}) {
  const [slotNumber, setSlotNumber] = useState('');
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError(undefined);
    try {
      await post(`/parking/areas/${areaId}/slots`, { slotNumber });
      setSlotNumber('');
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to create slot.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Add Slot to {areaName}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            required
            label="Slot Number"
            value={slotNumber}
            onChange={(e) => setSlotNumber(e.target.value)}
            helperText="e.g. A1, B12, O-05"
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void submit()} disabled={!slotNumber || saving}>
          {saving ? 'Adding…' : 'Add Slot'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function BulkCreateSlotsDialog({
  open,
  onClose,
  onCreated,
  areaId,
  areaName,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  areaId: string;
  areaName: string;
}) {
  const [count, setCount] = useState('10');
  const [prefix, setPrefix] = useState('');
  const [startIndex, setStartIndex] = useState('1');
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const preview = (() => {
    const n = parseInt(count, 10) || 0;
    const start = parseInt(startIndex, 10) || 1;
    const p = prefix.trim();
    if (n <= 0) return '';
    const first = `${p}${start}`;
    const last = `${p}${start + n - 1}`;
    return `${first} … ${last}`;
  })();

  const submit = async () => {
    const n = parseInt(count, 10);
    if (!n || n < 1) return;
    setSaving(true);
    setError(undefined);
    try {
      await post<BulkCreateSlotsResponse>(`/parking/areas/${areaId}/slots/bulk`, {
        count: n,
        prefix: prefix.trim() || undefined,
        startIndex: parseInt(startIndex, 10) || 1,
      });
      setCount('10');
      setPrefix('');
      setStartIndex('1');
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to create slots.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Add Bulk Slots to {areaName}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            required
            label="Number of Slots"
            type="number"
            value={count}
            onChange={(e) => setCount(e.target.value)}
            helperText="How many slots to create (1–500)"
          />
          <TextField
            label="Prefix (optional)"
            value={prefix}
            onChange={(e) => setPrefix(e.target.value)}
            helperText="e.g. 'A' → A1, A2, A3…  (leave empty for plain numbers)"
          />
          <TextField
            label="Start Index"
            type="number"
            value={startIndex}
            onChange={(e) => setStartIndex(e.target.value)}
            helperText="First number in the sequence"
          />
          {preview && (
            <Alert severity="info" sx={{ py: 0.5 }}>
              Preview: <strong>{preview}</strong>
            </Alert>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={!count || saving}
        >
          {saving ? 'Creating…' : `Create ${count || ''} Slots`}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function EditSlotDialog({
  slot,
  onClose,
  onUpdated,
}: {
  slot: ParkingSlot;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const [slotNumber, setSlotNumber] = useState(slot.slotNumber);
  const [status, setStatus] = useState<SlotStatus>(slot.status);
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const isOccupied = slot.status === 'OCCUPIED';

  const submit = async () => {
    setSaving(true);
    setError(undefined);
    try {
      const body: Record<string, unknown> = {};
      if (slotNumber !== slot.slotNumber) body.slotNumber = slotNumber;
      if (status !== slot.status) body.status = status;
      if (Object.keys(body).length === 0) {
        onClose();
        return;
      }
      await patch(`/parking/slots/${slot.slotId}`, body);
      onUpdated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update slot.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>Edit Slot {slot.slotNumber}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            label="Slot Number"
            value={slotNumber}
            onChange={(e) => setSlotNumber(e.target.value)}
            disabled={isOccupied}
            helperText={isOccupied ? 'Cannot rename an occupied slot' : 'e.g. A1, B12, O-05'}
          />
          <TextField
            select
            label="Status"
            value={status}
            onChange={(e) => setStatus(e.target.value as SlotStatus)}
            disabled={isOccupied}
            helperText={isOccupied ? 'Cannot change status of an occupied slot' : undefined}
          >
            {(['AVAILABLE', 'RESERVED', 'MAINTENANCE'] as SlotStatus[]).map((s) => (
              <MenuItem key={s} value={s}>{s}</MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" onClick={() => void submit()} disabled={saving}>
          {saving ? 'Saving…' : 'Save Changes'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
