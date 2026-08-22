import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  Grid2 as Grid,
  IconButton,
  InputLabel,
  LinearProgress,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  Typography,
} from '@mui/material';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
import LocalParkingOutlinedIcon from '@mui/icons-material/LocalParkingOutlined';
import CheckCircleOutlinedIcon from '@mui/icons-material/CheckCircleOutlined';
import DirectionsCarOutlinedIcon from '@mui/icons-material/DirectionsCarOutlined';
import DirectionsRunOutlinedIcon from '@mui/icons-material/DirectionsRunOutlined';
import RoomServiceOutlinedIcon from '@mui/icons-material/RoomServiceOutlined';
import AssignmentTurnedInOutlinedIcon from '@mui/icons-material/AssignmentTurnedInOutlined';
import CloseOutlinedIcon from '@mui/icons-material/CloseOutlined';
import { MetricCard } from '../components/MetricCard';
import { get, ApiError } from '../api/client';
import type { Capacity, ParkingArea, ParkingAreaList, ParkingSession, ParkingSlot, ParkingSlotList, ParkingTimelineStage, SlotStatus } from '../types';
import { TIMELINE_STAGE_DISPLAY_NAMES } from '../types';

const BEING_PARKED_STAGES: ParkingTimelineStage[] = ['ASSIGNED_FOR_PARKING', 'PARKING_REQUEST_ACCEPTED'];
const DELIVERY_REQUESTED_STAGES: ParkingTimelineStage[] = [
  'REQUESTED_FOR_DELIVERY',
  'ASSIGNED_FOR_DELIVERY',
  'DELIVERY_REQUEST_ACCEPTED',
];
const RETRIEVING_STAGES: ParkingTimelineStage[] = ['PICKED_UP', 'ARRIVED', 'REQUESTED_FOR_MANUAL_OVERRIDE'];

function isToday(iso: string | null | undefined): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const now = new Date();
  return (
    d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth() && d.getDate() === now.getDate()
  );
}

type TileKey =
  | 'totalCapacity'
  | 'available'
  | 'occupied'
  | 'activeSessions'
  | 'beingParked'
  | 'currentlyParked'
  | 'deliveryRequested'
  | 'valetsRetrieving'
  | 'deliveredToday';

export function DashboardPage() {
  const [capacity, setCapacity] = useState<Capacity | null>(null);
  const [activeCount, setActiveCount] = useState(0);
  const [activeSessions, setActiveSessions] = useState<ParkingSession[]>([]);
  const [exitedSessions, setExitedSessions] = useState<ParkingSession[]>([]);
  const [deliveredToday, setDeliveredToday] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [detailTile, setDetailTile] = useState<TileKey | null>(null);
  const [areas, setAreas] = useState<ParkingArea[]>([]);
  const [areaSlots, setAreaSlots] = useState<Record<string, ParkingSlot[]>>({});

  const loadAreas = useCallback(async () => {
    try {
      const data = await get<ParkingAreaList>('/parking/areas');
      setAreas(data.areas);
      const slotMap: Record<string, ParkingSlot[]> = {};
      await Promise.all(
        data.areas.map(async (a) => {
          const slots = await get<ParkingSlotList>(`/parking/areas/${a.areaId}/slots`);
          slotMap[a.areaId] = slots.slots;
        }),
      );
      setAreaSlots(slotMap);
    } catch {
      // ignore – areas just won't be available
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const [cap, activeResp, exitedResp] = await Promise.all([
        get<Capacity>('/parking/capacity'),
        get<{ vehicles: ParkingSession[]; count: number }>('/parking/vehicles?status=ACTIVE'),
        get<{ vehicles: ParkingSession[]; count: number }>('/parking/vehicles?status=EXITED'),
      ]);
      setCapacity(cap);
      setActiveCount(activeResp.count);
      setActiveSessions(activeResp.vehicles);
      setExitedSessions(exitedResp.vehicles);
      setDeliveredToday(
        exitedResp.vehicles.filter((s) => s.currentStage === 'DELIVERED' && isToday(s.exitTime)).length,
      );
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load dashboard data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !capacity) {
    return (
      <Box sx={{ display: 'grid', placeItems: 'center', minHeight: 400 }}>
        <CircularProgress />
      </Box>
    );
  }

  const pct = capacity ? Math.round((capacity.occupiedSlots / capacity.totalCapacity) * 100) : 0;

  const tileSessions: Record<TileKey, ParkingSession[]> = {
    totalCapacity: activeSessions,
    available: activeSessions.filter((s) => !s.slotId),
    occupied: [],
    activeSessions: activeSessions,
    beingParked: activeSessions.filter((s) => !!s.currentStage && BEING_PARKED_STAGES.includes(s.currentStage)),
    currentlyParked: activeSessions.filter((s) => s.currentStage === 'PARKED'),
    deliveryRequested: activeSessions.filter((s) => !!s.currentStage && DELIVERY_REQUESTED_STAGES.includes(s.currentStage)),
    valetsRetrieving: activeSessions.filter((s) => !!s.currentStage && RETRIEVING_STAGES.includes(s.currentStage)),
    deliveredToday: exitedSessions.filter((s) => s.currentStage === 'DELIVERED' && isToday(s.exitTime)),
  };

  const tileTitles: Record<TileKey, string> = {
    totalCapacity: 'All Parking Areas & Slots',
    available: 'Available Slots',
    occupied: 'Occupied Slots',
    activeSessions: 'All Active Sessions',
    beingParked: 'Being Parked',
    currentlyParked: 'Currently Parked',
    deliveryRequested: 'Delivery Requested',
    valetsRetrieving: 'Valets Retrieving',
    deliveredToday: 'Delivered Today',
  };

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.5}>
        <Box>
          <Typography variant="h4">Dashboard</Typography>
          <Typography color="text.secondary">Real-time parking capacity and occupancy overview.</Typography>
        </Box>
        <IconButton onClick={() => void load()} aria-label="Refresh dashboard">
          <RefreshOutlinedIcon />
        </IconButton>
      </Stack>

      {loading && <LinearProgress />}
      {error && <Alert severity="error">{error}</Alert>}

      {capacity && (
        <>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                label="Total Capacity"
                value={capacity.totalCapacity}
                icon={<LocalParkingOutlinedIcon fontSize="large" />}
                caption="Configured slots"
                onClick={() => {
                  setDetailTile('totalCapacity');
                  void loadAreas();
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                label="Available"
                value={capacity.availableSlots}
                icon={<CheckCircleOutlinedIcon fontSize="large" />}
                color="success"
                caption="Free for entry"
                onClick={() => {
                  setDetailTile('available');
                  void loadAreas();
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                label="Occupied"
                value={capacity.occupiedSlots}
                icon={<DirectionsCarOutlinedIcon fontSize="large" />}
                color="warning"
                caption={`${pct}% utilization`}
                onClick={() => {
                  setDetailTile('occupied');
                  void loadAreas();
                }}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 3 }}>
              <MetricCard
                label="Active Sessions"
                value={activeCount}
                icon={<DirectionsCarOutlinedIcon fontSize="large" />}
                color="info"
                caption="Currently parked"
                onClick={() => setDetailTile('activeSessions')}
              />
            </Grid>
          </Grid>

          <Box sx={{ mt: 2 }}>
            <Typography variant="h6" gutterBottom>
              Occupancy
            </Typography>
            <LinearProgress
              variant="determinate"
              value={pct}
              sx={{ height: 12, borderRadius: 6, '& .MuiLinearProgress-bar': { borderRadius: 6 } }}
            />
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: 'block' }}>
              {capacity.occupiedSlots} of {capacity.totalCapacity} slots occupied ({pct}%)
            </Typography>
          </Box>

          <Box sx={{ mt: 3 }}>
            <Typography variant="h6" gutterBottom>
              Valet Journey
            </Typography>
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <MetricCard
                  label="Being Parked"
                  value={activeSessions.filter((s) => !!s.currentStage && BEING_PARKED_STAGES.includes(s.currentStage)).length}
                  icon={<DirectionsCarOutlinedIcon fontSize="large" />}
                  color="info"
                  caption="Assigned / accepted"
                  onClick={() => setDetailTile('beingParked')}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <MetricCard
                  label="Currently Parked"
                  value={activeSessions.filter((s) => s.currentStage === 'PARKED').length}
                  icon={<LocalParkingOutlinedIcon fontSize="large" />}
                  color="success"
                  caption="In a slot"
                  onClick={() => setDetailTile('currentlyParked')}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <MetricCard
                  label="Delivery Requested"
                  value={activeSessions.filter((s) => !!s.currentStage && DELIVERY_REQUESTED_STAGES.includes(s.currentStage)).length}
                  icon={<RoomServiceOutlinedIcon fontSize="large" />}
                  color="warning"
                  caption="Awaiting valet"
                  onClick={() => setDetailTile('deliveryRequested')}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <MetricCard
                  label="Valets Retrieving"
                  value={activeSessions.filter((s) => !!s.currentStage && RETRIEVING_STAGES.includes(s.currentStage)).length}
                  icon={<DirectionsRunOutlinedIcon fontSize="large" />}
                  color="warning"
                  caption="Picked up / arrived"
                  onClick={() => setDetailTile('valetsRetrieving')}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6, md: 3 }}>
                <MetricCard
                  label="Delivered Today"
                  value={deliveredToday}
                  icon={<AssignmentTurnedInOutlinedIcon fontSize="large" />}
                  color="success"
                  caption="Handed over to customer"
                  onClick={() => setDetailTile('deliveredToday')}
                />
              </Grid>
            </Grid>
          </Box>
        </>
      )}

      {detailTile && detailTile !== 'totalCapacity' && detailTile !== 'available' && detailTile !== 'occupied' && (
        <TileDetailTable
          title={tileTitles[detailTile]}
          sessions={tileSessions[detailTile]}
          onClose={() => setDetailTile(null)}
        />
      )}

      {detailTile === 'totalCapacity' && (
        <CapacityDetailTable
          areas={areas}
          areaSlots={areaSlots}
          onClose={() => setDetailTile(null)}
        />
      )}

      {detailTile === 'available' && (
        <AvailableSlotsTable
          areas={areas}
          areaSlots={areaSlots}
          activeSessions={activeSessions}
          onClose={() => setDetailTile(null)}
        />
      )}

      {detailTile === 'occupied' && (
        <OccupiedSlotsTable
          areas={areas}
          areaSlots={areaSlots}
          activeSessions={activeSessions}
          onClose={() => setDetailTile(null)}
        />
      )}
    </Stack>
  );
}

function TileDetailTable({
  title,
  sessions,
  onClose,
}: {
  title: string;
  sessions: ParkingSession[];
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  useEffect(() => {
    setPage(0);
  }, [title]);

  const paged = sessions.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ mt: 2 }}>
      <Box sx={{ px: 2.5, py: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h6">{title}</Typography>
          <Typography variant="body2" color="text.secondary">
            {sessions.length} session(s)
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="Close detail table">
          <CloseOutlinedIcon />
        </IconButton>
      </Box>
      <Divider />
      {sessions.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
          No sessions in this category.
        </Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Vehicle Number</TableCell>
                <TableCell>Type</TableCell>
                <TableCell>Wheels</TableCell>
                <TableCell>Hospital Side</TableCell>
                <TableCell>Area</TableCell>
                <TableCell>Slot</TableCell>
                <TableCell>Stage</TableCell>
                <TableCell>Entry Time</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((s) => (
                <TableRow key={s.sessionId} hover>
                  <TableCell>
                    <Typography fontWeight={700}>{s.vehicleNumber}</Typography>
                  </TableCell>
                  <TableCell>{s.vehicleType}</TableCell>
                  <TableCell>{s.wheelCategory}</TableCell>
                  <TableCell>{s.hospitalSide || '—'}</TableCell>
                  <TableCell>{s.areaName || '—'}</TableCell>
                  <TableCell>{s.slotNumber || '—'}</TableCell>
                  <TableCell>
                    {s.currentStage ? (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={TIMELINE_STAGE_DISPLAY_NAMES[s.currentStage]}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>{formatTime(s.entryTime)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={sessions.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[5, 10, 25, 50]}
          />
        </TableContainer>
      )}
    </Paper>
  );
}

const TRANSIT_STAGES: ParkingTimelineStage[] = [
  ...BEING_PARKED_STAGES,
  ...DELIVERY_REQUESTED_STAGES,
  ...RETRIEVING_STAGES,
];

function AvailableSlotsTable({
  areas,
  areaSlots,
  activeSessions,
  onClose,
}: {
  areas: ParkingArea[];
  areaSlots: Record<string, ParkingSlot[]>;
  activeSessions: ParkingSession[];
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [areaFilter, setAreaFilter] = useState<string>('all');

  const areaById = new Map(areas.map((a) => [a.areaId, a]));

  const allSlots = areas.flatMap((a) =>
    (areaSlots[a.areaId] || []).map((s) => ({
      ...s,
      areaName: a.name,
    })),
  );

  const slotById = new Map(allSlots.map((s) => [s.slotId, s]));
  const matchedSlotIds = new Set<string>();

  const transitRows = activeSessions
    .filter((s) => s.currentStage && TRANSIT_STAGES.includes(s.currentStage))
    .map((session) => {
      const slot = session.slotId ? slotById.get(session.slotId) : undefined;
      if (slot) {
        matchedSlotIds.add(slot.slotId);
        return {
          rowId: slot.slotId,
          slotId: slot.slotId,
          slotNumber: slot.slotNumber,
          areaName: slot.areaName,
          status: slot.status as SlotStatus,
          vehicleNumber: slot.vehicleNumber || session.vehicleNumber,
          inTransit: true,
          session,
        };
      }
      const area = session.areaId ? areaById.get(session.areaId) : undefined;
      return {
        rowId: session.sessionId,
        slotId: session.slotId || null,
        slotNumber: session.slotNumber || '—',
        areaName: session.areaName || area?.name || '—',
        status: 'AVAILABLE' as SlotStatus,
        vehicleNumber: session.vehicleNumber,
        inTransit: true,
        session,
      };
    });

  const availableRows = allSlots
    .filter((s) => !matchedSlotIds.has(s.slotId) && s.status === 'AVAILABLE')
    .map((s) => ({
      rowId: s.slotId,
      slotId: s.slotId,
      slotNumber: s.slotNumber,
      areaName: s.areaName,
      status: s.status,
      vehicleNumber: s.vehicleNumber,
      inTransit: false,
      session: undefined as ParkingSession | undefined,
    }));

  const availableSlots = [...availableRows, ...transitRows].filter(
    (s) => areaFilter === 'all' || s.areaName === areaFilter,
  );

  const paged = availableSlots.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ mt: 2 }}>
      <Box sx={{ px: 2.5, py: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h6">Available Slots</Typography>
          <Typography variant="body2" color="text.secondary">
            {availableSlots.filter((s) => !s.inTransit).length} available, {availableSlots.filter((s) => s.inTransit).length} in transit
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel id="available-area-filter-label">Zone</InputLabel>
            <Select
              labelId="available-area-filter-label"
              value={areaFilter}
              label="Zone"
              onChange={(e) => {
                setAreaFilter(e.target.value);
                setPage(0);
              }}
            >
              <MenuItem value="all">All</MenuItem>
              {areas.map((a) => (
                <MenuItem key={a.areaId} value={a.name}>
                  {a.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton onClick={onClose} aria-label="Close detail table">
            <CloseOutlinedIcon />
          </IconButton>
        </Box>
      </Box>
      <Divider />
      {availableSlots.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
          No available slots.
        </Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Area</TableCell>
                <TableCell>Slot Number</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Vehicle</TableCell>
                <TableCell>Transit Detail</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((s) => (
                <TableRow key={s.rowId} hover>
                  <TableCell>{s.areaName}</TableCell>
                  <TableCell>
                    <Typography fontWeight={700}>{s.slotNumber}</Typography>
                  </TableCell>
                  <TableCell>
                    {s.inTransit ? (
                      <Chip size="small" label="In Transit" color="info" />
                    ) : (
                      <Chip size="small" label="Available" color="success" />
                    )}
                  </TableCell>
                  <TableCell>{s.vehicleNumber || '—'}</TableCell>
                  <TableCell>
                    {s.inTransit && s.session?.currentStage
                      ? TIMELINE_STAGE_DISPLAY_NAMES[s.session.currentStage]
                      : '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={availableSlots.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[5, 10, 25, 50]}
          />
        </TableContainer>
      )}
    </Paper>
  );
}

function OccupiedSlotsTable({
  areas,
  areaSlots,
  activeSessions,
  onClose,
}: {
  areas: ParkingArea[];
  areaSlots: Record<string, ParkingSlot[]>;
  activeSessions: ParkingSession[];
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [areaFilter, setAreaFilter] = useState<string>('all');

  const sessionById = new Map(activeSessions.map((s) => [s.sessionId, s]));

  const allSlots = areas.flatMap((a) =>
    (areaSlots[a.areaId] || []).map((s) => ({
      ...s,
      areaName: a.name,
    })),
  );

  const occupiedSlots = allSlots
    .filter((s) => s.status === 'OCCUPIED' && (areaFilter === 'all' || s.areaName === areaFilter))
    .map((s) => {
      const session = s.sessionId ? sessionById.get(s.sessionId) : undefined;
      return {
        rowId: s.slotId,
        slotId: s.slotId,
        slotNumber: s.slotNumber,
        areaName: s.areaName,
        vehicleNumber: s.vehicleNumber,
        session,
      };
    });

  const paged = occupiedSlots.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ mt: 2 }}>
      <Box sx={{ px: 2.5, py: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h6">Occupied Slots</Typography>
          <Typography variant="body2" color="text.secondary">
            {occupiedSlots.length} occupied slot(s)
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel id="occupied-area-filter-label">Zone</InputLabel>
            <Select
              labelId="occupied-area-filter-label"
              value={areaFilter}
              label="Zone"
              onChange={(e) => {
                setAreaFilter(e.target.value);
                setPage(0);
              }}
            >
              <MenuItem value="all">All</MenuItem>
              {areas.map((a) => (
                <MenuItem key={a.areaId} value={a.name}>
                  {a.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton onClick={onClose} aria-label="Close detail table">
            <CloseOutlinedIcon />
          </IconButton>
        </Box>
      </Box>
      <Divider />
      {occupiedSlots.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
          No occupied slots.
        </Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Area</TableCell>
                <TableCell>Slot Number</TableCell>
                <TableCell>Vehicle</TableCell>
                <TableCell>Stage</TableCell>
                <TableCell>Entry Time</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((s) => (
                <TableRow key={s.rowId} hover>
                  <TableCell>{s.areaName}</TableCell>
                  <TableCell>
                    <Typography fontWeight={700}>{s.slotNumber}</Typography>
                  </TableCell>
                  <TableCell>{s.vehicleNumber || '—'}</TableCell>
                  <TableCell>
                    {s.session?.currentStage ? (
                      <Chip
                        size="small"
                        variant="outlined"
                        label={TIMELINE_STAGE_DISPLAY_NAMES[s.session.currentStage]}
                      />
                    ) : (
                      '—'
                    )}
                  </TableCell>
                  <TableCell>{s.session ? formatTime(s.session.entryTime) : '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={occupiedSlots.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[5, 10, 25, 50]}
          />
        </TableContainer>
      )}
    </Paper>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

function CapacityDetailTable({
  areas,
  areaSlots,
  onClose,
}: {
  areas: ParkingArea[];
  areaSlots: Record<string, ParkingSlot[]>;
  onClose: () => void;
}) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [areaFilter, setAreaFilter] = useState<string>('all');

  const allSlots = areas.flatMap((a) =>
    (areaSlots[a.areaId] || []).map((s) => ({
      ...s,
      areaName: a.name,
    })),
  );

  const filteredSlots = allSlots.filter(
    (s) => areaFilter === 'all' || s.areaName === areaFilter,
  );

  const paged = filteredSlots.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper sx={{ mt: 2 }}>
      <Box sx={{ px: 2.5, py: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h6">All Parking Areas & Slots</Typography>
          <Typography variant="body2" color="text.secondary">
            {areas.length} area(s), {filteredSlots.length} slot(s)
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControl size="small" sx={{ minWidth: 100 }}>
            <InputLabel id="capacity-area-filter-label">Zone</InputLabel>
            <Select
              labelId="capacity-area-filter-label"
              value={areaFilter}
              label="Zone"
              onChange={(e) => {
                setAreaFilter(e.target.value);
                setPage(0);
              }}
            >
              <MenuItem value="all">All</MenuItem>
              {areas.map((a) => (
                <MenuItem key={a.areaId} value={a.name}>
                  {a.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <IconButton onClick={onClose} aria-label="Close detail table">
            <CloseOutlinedIcon />
          </IconButton>
        </Box>
      </Box>
      <Divider />
      {filteredSlots.length === 0 ? (
        <Typography color="text.secondary" sx={{ py: 3, textAlign: 'center' }}>
          No parking areas or slots configured.
        </Typography>
      ) : (
        <TableContainer sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Area</TableCell>
                <TableCell>Slot Number</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Vehicle</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {paged.map((s) => (
                <TableRow key={s.slotId} hover>
                  <TableCell>{s.areaName}</TableCell>
                  <TableCell>
                    <Typography fontWeight={700}>{s.slotNumber}</Typography>
                  </TableCell>
                  <TableCell>
                    <Chip
                      size="small"
                      label={s.status}
                      color={
                        s.status === 'AVAILABLE'
                          ? 'success'
                          : s.status === 'OCCUPIED'
                            ? 'warning'
                            : 'default'
                      }
                    />
                  </TableCell>
                  <TableCell>{s.vehicleNumber || '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <TablePagination
            component="div"
            count={allSlots.length}
            page={page}
            onPageChange={(_, newPage) => setPage(newPage)}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={(e) => {
              setRowsPerPage(parseInt(e.target.value, 10));
              setPage(0);
            }}
            rowsPerPageOptions={[5, 10, 25, 50]}
          />
        </TableContainer>
      )}
    </Paper>
  );
}
