import { useCallback, useEffect, useState } from 'react';
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
  Divider,
  FormControlLabel,
  Grid2 as Grid,
  IconButton,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material';
import AddOutlinedIcon from '@mui/icons-material/AddOutlined';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';
import SwapHorizOutlinedIcon from '@mui/icons-material/SwapHorizOutlined';
import HistoryOutlinedIcon from '@mui/icons-material/HistoryOutlined';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import WarningAmberOutlinedIcon from '@mui/icons-material/WarningAmberOutlined';
import EditOutlinedIcon from '@mui/icons-material/EditOutlined';
import { get, patch, post, ApiError } from '../api/client';
import type {
  ParkingSession,
  UpdateSessionRequest,
  VehicleList,
  ParkingArea,
  ParkingAreaList,
  ParkingSlot,
  ParkingSlotList,
  ParkingTimelineEvent,
  ParkingTimelineList,
} from '../types';
import { HOSPITAL_SIDES, TIMELINE_STAGE_DISPLAY_NAMES } from '../types';
import { VALET_DRIVERS, type ValetIdentity } from '../roles';

const NEXT_STAGE_ACTION: Record<string, { label: string; endpoint: string }> = {
  ASSIGNED_FOR_PARKING: { label: 'Accept Parking Request', endpoint: 'accept-parking-request' },
  PARKING_REQUEST_ACCEPTED: { label: 'Mark as Parked', endpoint: 'mark-parked' },
  PARKED: { label: 'Request Delivery', endpoint: 'request-delivery' },
  REQUESTED_FOR_DELIVERY: { label: 'Assign for Delivery', endpoint: 'assign-for-delivery' },
  ASSIGNED_FOR_DELIVERY: { label: 'Accept Delivery Request', endpoint: 'accept-delivery' },
  DELIVERY_REQUEST_ACCEPTED: { label: 'Mark Picked Up', endpoint: 'picked-up' },
  PICKED_UP: { label: 'Mark Arrived', endpoint: 'arrived' },
  ARRIVED: { label: 'Deliver Vehicle', endpoint: 'delivered' },
};

type DriverAssignMode = 'parking' | 'delivery';

const STATUS_FILTERS = ['ACTIVE', 'EXITED', 'ALL'] as const;

export function ParkingPage() {
  const [sessions, setSessions] = useState<ParkingSession[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>('ACTIVE');
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [reassignSession, setReassignSession] = useState<ParkingSession | null>(null);
  const [postReassignAction, setPostReassignAction] = useState<string | undefined>();
  const [timelineSession, setTimelineSession] = useState<ParkingSession | null>(null);
  const [confirmOverride, setConfirmOverride] = useState<ParkingSession | null>(null);
  const [editSession, setEditSession] = useState<ParkingSession | null>(null);
  const [assignDriverSession, setAssignDriverSession] = useState<ParkingSession | null>(null);
  const [assignDriverMode, setAssignDriverMode] = useState<DriverAssignMode>('parking');
  const [busy, setBusy] = useState<string>();

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const query = statusFilter === 'ALL' ? '' : `?status=${statusFilter}`;
      const data = await get<VehicleList>(`/parking/vehicles${query}`);
      setSessions(data.vehicles);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load parking sessions.');
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void load();
  }, [load]);

  const handleExit = async (vehicleNumber: string) => {
    setBusy(vehicleNumber);
    setError(undefined);
    try {
      await post(`/parking/vehicles/${encodeURIComponent(vehicleNumber)}/exit`);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to process vehicle exit.');
    } finally {
      setBusy(undefined);
    }
  };

  const runStageAction = async (session: ParkingSession, endpoint: string, body?: Record<string, unknown>) => {
    setBusy(session.vehicleNumber);
    setError(undefined);
    try {
      // Forward the driver already assigned to this session so later stages
      // (accept, mark-parked, picked-up, ...) keep the same valet identity
      // unless the caller explicitly supplies a different one (e.g. a fresh
      // driver assignment).
      const payload = {
        valetId: session.currentValetId ?? undefined,
        valetName: session.currentValetName ?? undefined,
        ...body,
      };
      await post(`/parking/sessions/${encodeURIComponent(session.sessionId)}/${endpoint}`, payload);
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update vehicle stage.');
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" spacing={2}>
        <Box>
          <Typography variant="h4">Parking Operations</Typography>
          <Typography color="text.secondary">Manage vehicle entry, exit, and active sessions.</Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          <Select
            size="small"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            sx={{ minWidth: 120 }}
          >
            {STATUS_FILTERS.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </Select>
          <IconButton onClick={() => void load()} aria-label="Refresh sessions">
            <RefreshOutlinedIcon />
          </IconButton>
          <Button
            startIcon={<AddOutlinedIcon />}
            variant="contained"
            onClick={() => setDialogOpen(true)}
          >
            New Entry
          </Button>
        </Stack>
      </Stack>

      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      <Grid container spacing={2}>
        <Grid size={{ xs: 12, lg: 8 }}>
          <Paper>
            <Box sx={{ px: 2.5, py: 2 }}>
              <Typography variant="h6">
                {statusFilter === 'ALL' ? 'All Sessions' : `${statusFilter.charAt(0) + statusFilter.slice(1).toLowerCase()} Sessions`}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {sessions.length} vehicle(s) listed
              </Typography>
            </Box>
            <Divider />
            <TableContainer sx={{ overflowX: 'auto' }}>
              <Table size="small" sx={{ minWidth: 1050 }}>
              <TableHead>
                <TableRow>
                  <TableCell>Vehicle Number</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Wheels</TableCell>
                  <TableCell>Hospital Side</TableCell>
                  <TableCell>Area</TableCell>
                  <TableCell>Slot</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Stage</TableCell>
                  <TableCell>Driver</TableCell>
                  <TableCell>Entry Time</TableCell>
                  <TableCell>Exit Time</TableCell>
                  <TableCell align="right">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {sessions.map((session) => {
                  const stageAction = session.currentStage ? NEXT_STAGE_ACTION[session.currentStage] : undefined;
                  const needsParkingDriver =
                    session.currentStage === 'ASSIGNED_FOR_PARKING' && !session.currentValetId;
                  const isBusy = busy === session.vehicleNumber;
                  return (
                    <TableRow key={session.sessionId} hover>
                      <TableCell>
                        <Typography fontWeight={700}>{session.vehicleNumber}</Typography>
                      </TableCell>
                      <TableCell>{session.vehicleType}</TableCell>
                      <TableCell>{session.wheelCategory}</TableCell>
                      <TableCell>{session.hospitalSide || '—'}</TableCell>
                      <TableCell>{session.areaName || '—'}</TableCell>
                      <TableCell>
                        {session.isCorridorParking ? (
                          <Chip size="small" color="secondary" variant="outlined" label="Corridor" />
                        ) : (
                          session.slotNumber || '—'
                        )}
                      </TableCell>
                      <TableCell>
                        <Chip
                          size="small"
                          label={session.status}
                          color={session.status === 'ACTIVE' ? 'success' : 'default'}
                        />
                      </TableCell>
                      <TableCell>
                        {session.currentStage ? (
                          <Chip size="small" variant="outlined" label={TIMELINE_STAGE_DISPLAY_NAMES[session.currentStage]} />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>
                        {session.currentValetName ? (
                          session.currentValetName
                        ) : needsParkingDriver ? (
                          <Chip size="small" color="warning" variant="outlined" label="Unassigned" />
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell>{formatTime(session.entryTime)}</TableCell>
                      <TableCell>{session.exitTime ? formatTime(session.exitTime) : '—'}</TableCell>
                      <TableCell align="right">
                        <Stack direction="row" spacing={0.5} alignItems="center" justifyContent="flex-end">
                          <Tooltip title="View timeline">
                            <IconButton size="small" onClick={() => setTimelineSession(session)}>
                              <HistoryOutlinedIcon fontSize="small" />
                            </IconButton>
                          </Tooltip>
                          {session.status === 'ACTIVE' && (
                            <Tooltip title="Edit entry">
                              <IconButton
                                size="small"
                                color="info"
                                disabled={isBusy}
                                onClick={() => setEditSession(session)}
                              >
                                <EditOutlinedIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                          )}
                          {session.status === 'ACTIVE' && (
                            <>
                              {needsParkingDriver ? (
                                <Tooltip title="Assign Driver for Parking">
                                  <IconButton
                                    size="small"
                                    color="primary"
                                    disabled={isBusy}
                                    onClick={() => {
                                      setAssignDriverMode('parking');
                                      setAssignDriverSession(session);
                                    }}
                                  >
                                    {isBusy ? <CircularProgress size={16} /> : <PlayArrowOutlinedIcon fontSize="small" />}
                                  </IconButton>
                                </Tooltip>
                              ) : (
                                stageAction && (
                                  <Tooltip title={stageAction.label}>
                                    <IconButton
                                      size="small"
                                      color="success"
                                      disabled={isBusy}
                                      onClick={() => {
                                        if (stageAction.endpoint === 'mark-parked' && !session.slotNumber) {
                                          setReassignSession(session);
                                          setPostReassignAction('mark-parked');
                                        } else if (stageAction.endpoint === 'assign-for-delivery') {
                                          setAssignDriverMode('delivery');
                                          setAssignDriverSession(session);
                                        } else {
                                          void runStageAction(session, stageAction.endpoint);
                                        }
                                      }}
                                    >
                                      {isBusy ? <CircularProgress size={16} /> : <PlayArrowOutlinedIcon fontSize="small" />}
                                    </IconButton>
                                  </Tooltip>
                                )
                              )}
                              <Tooltip title="Manual override">
                                <IconButton
                                  size="small"
                                  color="warning"
                                  disabled={isBusy}
                                  onClick={() => setConfirmOverride(session)}
                                >
                                  <WarningAmberOutlinedIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Change slot">
                                <IconButton
                                  size="small"
                                  color="primary"
                                  disabled={isBusy}
                                  onClick={() => {
                                    setReassignSession(session);
                                    setPostReassignAction(undefined);
                                  }}
                                >
                                  <SwapHorizOutlinedIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                              <Tooltip title="Process vehicle exit">
                                <IconButton
                                  size="small"
                                  color="error"
                                  disabled={isBusy}
                                  onClick={() => void handleExit(session.vehicleNumber)}
                                >
                                  <LogoutOutlinedIcon fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            </>
                          )}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  );
                })}
                {sessions.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={12} align="center">
                      No sessions found.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
              </Table>
            </TableContainer>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, lg: 4 }}>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="h6" gutterBottom>
              Quick Stats
            </Typography>
            <Stack spacing={1.5}>
              <StatRow label="Total shown" value={sessions.length} />
              <StatRow
                label="Active"
                value={sessions.filter((s) => s.status === 'ACTIVE').length}
              />
              <StatRow
                label="Exited"
                value={sessions.filter((s) => s.status === 'EXITED').length}
              />
            </Stack>
          </Paper>
        </Grid>
      </Grid>

      <EntryDialog
        open={dialogOpen}
        onClose={() => setDialogOpen(false)}
        onCreated={() => {
          setDialogOpen(false);
          void load();
        }}
      />

      {reassignSession && (
        <ReassignSlotDialog
          session={reassignSession}
          onClose={() => {
            setReassignSession(null);
            setPostReassignAction(undefined);
          }}
          onReassigned={() => {
            if (postReassignAction && reassignSession) {
              void runStageAction(reassignSession, postReassignAction);
            }
            setReassignSession(null);
            setPostReassignAction(undefined);
          }}
        />
      )}

      {timelineSession && (
        <VehicleTimelineDialog session={timelineSession} onClose={() => setTimelineSession(null)} />
      )}

      {editSession && (
        <EditSessionDialog
          session={editSession}
          onClose={() => setEditSession(null)}
          onSaved={() => {
            setEditSession(null);
            void load();
          }}
        />
      )}

      {assignDriverSession && (
        <AssignDriverDialog
          session={assignDriverSession}
          mode={assignDriverMode}
          onClose={() => setAssignDriverSession(null)}
          onAssigned={(driver) => {
            const endpoint = assignDriverMode === 'parking' ? 'assign-for-parking' : 'assign-for-delivery';
            void runStageAction(assignDriverSession, endpoint, {
              valetId: driver.id,
              valetName: driver.name,
            });
            setAssignDriverSession(null);
          }}
        />
      )}

      <Dialog open={confirmOverride !== null} onClose={() => setConfirmOverride(null)}>
        <DialogTitle>Confirm Manual Override</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to flag <strong>{confirmOverride?.vehicleNumber}</strong> for manual override?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmOverride(null)} color="inherit">
            Cancel
          </Button>
          <Button
            variant="contained"
            color="warning"
            onClick={() => {
              if (confirmOverride) {
                void runStageAction(confirmOverride, 'manual-override');
              }
              setConfirmOverride(null);
            }}
          >
            Confirm Override
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}

function StatRow({ label, value }: { label: string; value: number }) {
  return (
    <Stack direction="row" justifyContent="space-between">
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={700}>
        {value}
      </Typography>
    </Stack>
  );
}

function AssignDriverDialog({
  session,
  mode,
  onClose,
  onAssigned,
}: {
  session: ParkingSession;
  mode: DriverAssignMode;
  onClose: () => void;
  onAssigned: (driver: ValetIdentity) => void;
}) {
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>
        {mode === 'parking' ? 'Assign Driver to Park' : 'Assign Driver for Delivery'} — {session.vehicleNumber}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1} sx={{ pt: 1 }}>
          {VALET_DRIVERS.map((driver) => (
            <Button key={driver.id} variant="outlined" onClick={() => onAssigned(driver)}>
              {driver.name}
            </Button>
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
      </DialogActions>
    </Dialog>
  );
}

function EntryDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [vehicleNumber, setVehicleNumber] = useState('');
  const [wheelCategory, setWheelCategory] = useState('4');
  const [vehicleType, setVehicleType] = useState('car');
  const [hospitalSide, setHospitalSide] = useState('');
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);
  const [areas, setAreas] = useState<ParkingArea[]>([]);
  const [selectedAreaId, setSelectedAreaId] = useState('');
  const [slots, setSlots] = useState<ParkingSlot[]>([]);
  const [selectedSlotId, setSelectedSlotId] = useState('');
  const [useCorridor, setUseCorridor] = useState(false);
  const [selectedDriverId, setSelectedDriverId] = useState('');

  useEffect(() => {
    if (open) {
      void get<ParkingAreaList>('/parking/areas').then((data) => setAreas(data.areas)).catch(() => {});
    }
  }, [open]);

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
    setSaving(true);
    setError(undefined);
    try {
      await post('/parking/vehicles', {
        vehicleNumber,
        wheelCategory: parseInt(wheelCategory, 10),
        vehicleType,
        hospitalSide: hospitalSide || undefined,
        areaId: selectedAreaId || undefined,
        slotId: useCorridor ? undefined : selectedSlotId || undefined,
        useCorridor: useCorridor || undefined,
        valetId: selectedDriverId || undefined,
        valetName: VALET_DRIVERS.find((d) => d.id === selectedDriverId)?.name || undefined,
      });
      setVehicleNumber('');
      setWheelCategory('4');
      setVehicleType('car');
      setHospitalSide('');
      setSelectedAreaId('');
      setSelectedSlotId('');
      setUseCorridor(false);
      setSelectedDriverId('');
      onCreated();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to add vehicle.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Add Vehicle Entry</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            autoFocus
            required
            label="Vehicle Number"
            value={vehicleNumber}
            onChange={(e) => setVehicleNumber(e.target.value)}
            helperText="Plate number (e.g. KA01AB1234)"
          />
          <TextField
            required
            label="Vehicle Type"
            value={vehicleType}
            onChange={(e) => setVehicleType(e.target.value)}
            helperText="car, suv, van, truck, bus, motorcycle"
          />
          <TextField
            required
            label="Wheel Category"
            type="number"
            value={wheelCategory}
            onChange={(e) => setWheelCategory(e.target.value)}
            helperText="Number of wheels (2, 4, 6, etc.)"
          />
          <TextField
            select
            label="Hospital Side / Gate"
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
          <Divider />
          <Typography variant="subtitle2" color="text.secondary">
            Dispatch (optional)
          </Typography>
          <TextField
            select
            label="Assign Driver"
            value={selectedDriverId}
            onChange={(e) => setSelectedDriverId(e.target.value)}
            helperText="Dispatch a valet driver now to park this vehicle, or assign later"
          >
            <MenuItem value="">— Assign later —</MenuItem>
            {VALET_DRIVERS.map((driver) => (
              <MenuItem key={driver.id} value={driver.id}>
                {driver.name}
              </MenuItem>
            ))}
          </TextField>
          <Typography variant="subtitle2" color="text.secondary">
            Parking Assignment (optional)
          </Typography>
          <TextField
            select
            label="Parking Area"
            value={selectedAreaId}
            onChange={(e) => setSelectedAreaId(e.target.value)}
            helperText="Select a parking area (basement, side, outside, etc.)"
          >
            <MenuItem value="">— Auto-assign —</MenuItem>
            {areas.map((area) => (
              <MenuItem key={area.areaId} value={area.areaId}>
                {area.name} ({area.areaType}) — {area.availableSlots}/{area.totalSlots} free
              </MenuItem>
            ))}
          </TextField>
          {selectedAreaId && !!selectedArea?.corridorCapacity && (
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
          {selectedAreaId && !useCorridor && (
            <TextField
              select
              label="Slot"
              value={selectedSlotId}
              onChange={(e) => setSelectedSlotId(e.target.value)}
              helperText="Select a specific available slot"
            >
              <MenuItem value="">— Any available —</MenuItem>
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
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={!vehicleNumber || !vehicleType || saving}
        >
          {saving ? 'Adding…' : 'Add Vehicle'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function EditSessionDialog({
  session,
  onClose,
  onSaved,
}: {
  session: ParkingSession;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [vehicleType, setVehicleType] = useState(session.vehicleType);
  const [wheelCategory, setWheelCategory] = useState(String(session.wheelCategory));
  const [hospitalSide, setHospitalSide] = useState(session.hospitalSide ?? '');
  const [error, setError] = useState<string>();
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    setError(undefined);
    try {
      const body: UpdateSessionRequest = {};
      if (vehicleType !== session.vehicleType) body.vehicleType = vehicleType;
      const newWheels = parseInt(wheelCategory, 10);
      if (newWheels !== session.wheelCategory) body.wheelCategory = newWheels;
      const newSide = hospitalSide || null;
      if (newSide !== (session.hospitalSide ?? null)) body.hospitalSide = newSide;
      await patch(`/parking/sessions/${encodeURIComponent(session.sessionId)}`, body);
      onSaved();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update session.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Edit Entry — {session.vehicleNumber}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField
            label="Vehicle Type"
            value={vehicleType}
            onChange={(e) => setVehicleType(e.target.value)}
            helperText="car, suv, van, truck, bus, motorcycle"
          />
          <TextField
            label="Wheel Category"
            type="number"
            value={wheelCategory}
            onChange={(e) => setWheelCategory(e.target.value)}
            helperText="Number of wheels (2, 3, 4, 6)"
          />
          <TextField
            select
            label="Hospital Side / Gate"
            value={hospitalSide}
            onChange={(e) => setHospitalSide(e.target.value)}
            helperText="Where the vehicle was received"
          >
            <MenuItem value="">— Not specified —</MenuItem>
            {HOSPITAL_SIDES.map((side) => (
              <MenuItem key={side} value={side}>
                {side}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          onClick={() => void submit()}
          disabled={!vehicleType || saving}
        >
          {saving ? 'Saving…' : 'Save Changes'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function ReassignSlotDialog({
  session,
  onClose,
  onReassigned,
}: {
  session: ParkingSession;
  onClose: () => void;
  onReassigned: () => void;
}) {
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
      onReassigned();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to reassign slot.');
    } finally {
      setSaving(false);
    }
  };

  const dialogTitle = session.slotNumber
    ? `Change Slot — ${session.vehicleNumber}`
    : `Select Slot — ${session.vehicleNumber}`;
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

function VehicleTimelineDialog({
  session,
  onClose,
}: {
  session: ParkingSession;
  onClose: () => void;
}) {
  const [events, setEvents] = useState<ParkingTimelineEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(undefined);
    void get<ParkingTimelineList>(`/parking/sessions/${encodeURIComponent(session.sessionId)}/timeline`)
      .then((data) => {
        if (active) setEvents(data.events);
      })
      .catch((cause) => {
        if (active) setError(cause instanceof ApiError ? cause.message : 'Unable to load timeline.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [session.sessionId]);

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>Vehicle Timeline</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          <Paper variant="outlined" sx={{ p: 2 }}>
            <Grid container spacing={1}>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Vehicle Number
                </Typography>
                <Typography fontWeight={700}>{session.vehicleNumber}</Typography>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Vehicle Type
                </Typography>
                <Typography>{session.vehicleType}</Typography>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Session ID
                </Typography>
                <Typography>{session.sessionId}</Typography>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Current Stage
                </Typography>
                <Box>
                  {session.currentStage ? (
                    <Chip size="small" color="info" label={TIMELINE_STAGE_DISPLAY_NAMES[session.currentStage]} />
                  ) : (
                    <Typography>—</Typography>
                  )}
                </Box>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Hospital Side
                </Typography>
                <Typography>{session.hospitalSide || '—'}</Typography>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Parking Area
                </Typography>
                <Typography>{session.areaName || '—'}</Typography>
              </Grid>
              <Grid size={6}>
                <Typography variant="caption" color="text.secondary">
                  Parking Slot
                </Typography>
                <Typography>{session.slotNumber || '—'}</Typography>
              </Grid>
            </Grid>
          </Paper>

          {loading && <LinearProgress />}
          {error && <Alert severity="error">{error}</Alert>}

          {!loading && !error && (
            <Stack spacing={0}>
              {events.map((event, idx) => {
                const isLast = idx === events.length - 1;
                const isCurrent = isLast;
                return (
                  <Stack key={event.eventId} direction="row" spacing={1.5}>
                    <Stack alignItems="center" sx={{ width: 20 }}>
                      <Box
                        sx={{
                          width: 12,
                          height: 12,
                          borderRadius: '50%',
                          bgcolor: isCurrent ? 'success.main' : 'primary.main',
                          mt: '4px',
                          flexShrink: 0,
                        }}
                      />
                      {!isLast && (
                        <Box sx={{ width: 2, flexGrow: 1, bgcolor: 'divider', minHeight: 32 }} />
                      )}
                    </Stack>
                    <Box sx={{ pb: 2.5, minWidth: 0 }}>
                      <Typography variant="caption" color="text.secondary">
                        {formatTime(event.timestamp)}
                      </Typography>
                      <Typography fontWeight={isCurrent ? 700 : 500}>{event.displayName}</Typography>
                      {event.slotNumber && (
                        <Typography variant="body2" color="text.secondary">
                          Parking slot: {event.areaName ? `${event.areaName} - ` : ''}
                          {event.slotNumber}
                        </Typography>
                      )}
                      {event.valetName && (
                        <Typography variant="body2" color="text.secondary">
                          Valet: {event.valetName}
                        </Typography>
                      )}
                      {event.notes && (
                        <Typography variant="body2" color="text.secondary">
                          Notes: {event.notes}
                        </Typography>
                      )}
                    </Box>
                  </Stack>
                );
              })}
              {events.length === 0 && (
                <Typography color="text.secondary" sx={{ textAlign: 'center', py: 2 }}>
                  No timeline events yet.
                </Typography>
              )}
            </Stack>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
