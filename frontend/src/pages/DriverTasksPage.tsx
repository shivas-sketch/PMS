import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  IconButton,
  Stack,
  Typography,
} from '@mui/material';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
import PlayArrowOutlinedIcon from '@mui/icons-material/PlayArrowOutlined';
import { get, post, ApiError } from '../api/client';
import { AssignSlotDialog } from '../components/AssignSlotDialog';
import type { ParkingSession, ParkingTimelineStage, VehicleList } from '../types';
import { TIMELINE_STAGE_DISPLAY_NAMES } from '../types';
import type { ValetIdentity } from '../roles';

const DRIVER_ACTIONS: Record<string, { label: string; endpoint: string }> = {
  ASSIGNED_FOR_PARKING: { label: 'Accept Parking Request', endpoint: 'accept-parking-request' },
  PARKING_REQUEST_ACCEPTED: { label: 'Mark as Parked', endpoint: 'mark-parked' },
  ASSIGNED_FOR_DELIVERY: { label: 'Accept Delivery', endpoint: 'accept-delivery' },
  DELIVERY_REQUEST_ACCEPTED: { label: 'Mark Picked Up', endpoint: 'picked-up' },
  PICKED_UP: { label: 'Mark Arrived', endpoint: 'arrived' },
  ARRIVED: { label: 'Deliver Vehicle', endpoint: 'delivered' },
};

const DRIVER_STAGES = Object.keys(DRIVER_ACTIONS) as ParkingTimelineStage[];

type Props = {
  driver: ValetIdentity;
};

export function DriverTasksPage({ driver }: Props) {
  const [sessions, setSessions] = useState<ParkingSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState<string>();
  const [slotSession, setSlotSession] = useState<ParkingSession | null>(null);
  const [pendingEndpoint, setPendingEndpoint] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const data = await get<VehicleList>('/parking/vehicles?status=ACTIVE');
      setSessions(
        data.vehicles.filter(
          (s) =>
            !!s.currentStage &&
            DRIVER_STAGES.includes(s.currentStage) &&
            (s.currentValetId === driver.id || s.currentValetName === driver.name)
        )
      );
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load tasks.');
    } finally {
      setLoading(false);
    }
  }, [driver.id]);

  useEffect(() => {
    void load();
    const interval = setInterval(() => void load(), 10000);
    return () => clearInterval(interval);
  }, [load]);

  const runAction = async (session: ParkingSession, endpoint: string) => {
    if (endpoint === 'mark-parked' && !session.slotNumber) {
      setSlotSession(session);
      setPendingEndpoint(endpoint);
      return;
    }
    setBusy(session.sessionId);
    setError(undefined);
    try {
      await post(`/parking/sessions/${encodeURIComponent(session.sessionId)}/${endpoint}`, {
        valetId: driver.id,
        valetName: driver.name,
      });
      await load();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to update this task.');
    } finally {
      setBusy(undefined);
    }
  };

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Box>
          <Typography variant="h4">My Tasks</Typography>
          <Typography color="text.secondary">Vehicles waiting on a valet action.</Typography>
        </Box>
        <IconButton onClick={() => void load()} aria-label="Refresh tasks">
          <RefreshOutlinedIcon />
        </IconButton>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {loading && sessions.length === 0 ? (
        <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : sessions.length === 0 ? (
        <Card>
          <CardContent>
            <Typography color="text.secondary" textAlign="center">
              No pending tasks right now. Check back soon.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={2}>
          {sessions.map((session) => {
            const action = session.currentStage ? DRIVER_ACTIONS[session.currentStage] : undefined;
            const isBusy = busy === session.sessionId;
            return (
              <Card key={session.sessionId} variant="outlined">
                <CardContent>
                  <Stack
                    direction={{ xs: 'column', sm: 'row' }}
                    justifyContent="space-between"
                    alignItems={{ sm: 'center' }}
                    spacing={2}
                  >
                    <Box>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Typography variant="h6" fontWeight={700}>
                          {session.vehicleNumber}
                        </Typography>
                        {session.currentStage && (
                          <Chip size="small" variant="outlined" label={TIMELINE_STAGE_DISPLAY_NAMES[session.currentStage]} />
                        )}
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {session.vehicleType} · {session.wheelCategory} wheels
                        {session.areaName ? ` · ${session.areaName}` : ''}
                        {session.slotNumber ? ` · Slot ${session.slotNumber}` : ''}
                        {session.hospitalSide ? ` · ${session.hospitalSide}` : ''}
                      </Typography>
                    </Box>
                    {action && (
                      <Button
                        variant="contained"
                        startIcon={isBusy ? <CircularProgress size={16} color="inherit" /> : <PlayArrowOutlinedIcon />}
                        disabled={isBusy}
                        onClick={() => void runAction(session, action.endpoint)}
                      >
                        {action.label}
                      </Button>
                    )}
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Stack>
      )}

      {slotSession && pendingEndpoint && (
        <AssignSlotDialog
          session={slotSession}
          onClose={() => {
            setSlotSession(null);
            setPendingEndpoint(null);
          }}
          onAssigned={async () => {
            const session = slotSession;
            const endpoint = pendingEndpoint;
            setSlotSession(null);
            setPendingEndpoint(null);
            if (!session || !endpoint) return;
            // Slot assigned; run the originally-intended action.
            setBusy(session.sessionId);
            setError(undefined);
            try {
              await post(`/parking/sessions/${encodeURIComponent(session.sessionId)}/${endpoint}`, {
                valetId: driver.id,
                valetName: driver.name,
              });
              await load();
            } catch (cause) {
              setError(cause instanceof ApiError ? cause.message : 'Unable to update this task.');
            } finally {
              setBusy(undefined);
            }
          }}
        />
      )}
    </Stack>
  );
}
