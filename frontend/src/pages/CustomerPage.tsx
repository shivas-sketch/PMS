import { useCallback, useState } from 'react';
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
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import RoomServiceOutlinedIcon from '@mui/icons-material/RoomServiceOutlined';
import { get, post, ApiError } from '../api/client';
import type { ParkingSession, ParkingTimelineStage } from '../types';
import { TIMELINE_STAGE_DISPLAY_NAMES } from '../types';

const IN_DELIVERY_FLOW_STAGES: ParkingTimelineStage[] = [
  'REQUESTED_FOR_DELIVERY',
  'ASSIGNED_FOR_DELIVERY',
  'DELIVERY_REQUEST_ACCEPTED',
  'PICKED_UP',
  'ARRIVED',
  'REQUESTED_FOR_MANUAL_OVERRIDE',
];

export function CustomerPage() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<ParkingSession | null>(null);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const [requesting, setRequesting] = useState(false);
  const [requestMessage, setRequestMessage] = useState<{ type: 'success' | 'error'; text: string }>();

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(undefined);
    setResult(null);
    setRequestMessage(undefined);
    setSearched(true);
    try {
      setResult(await get<ParkingSession>(`/parking/vehicles/${encodeURIComponent(query.trim())}`));
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 404) {
        setError('No vehicle found with that number.');
      } else {
        setError(cause instanceof ApiError ? cause.message : 'Lookup failed.');
      }
    } finally {
      setLoading(false);
    }
  }, [query]);

  const requestDelivery = async () => {
    if (!result) return;
    setRequesting(true);
    setRequestMessage(undefined);
    try {
      await post(`/parking/sessions/${encodeURIComponent(result.sessionId)}/request-delivery`);
      const refreshed = await get<ParkingSession>(`/parking/vehicles/${encodeURIComponent(result.vehicleNumber)}`);
      setResult(refreshed);
      setRequestMessage({ type: 'success', text: 'Your vehicle has been requested. A valet is on the way to retrieve it.' });
    } catch (cause) {
      setRequestMessage({
        type: 'error',
        text: cause instanceof ApiError ? cause.message : 'Unable to request delivery.',
      });
    } finally {
      setRequesting(false);
    }
  };

  const canRequestDelivery = result?.status === 'ACTIVE' && result.currentStage === 'PARKED';
  const isInDeliveryFlow =
    result?.status === 'ACTIVE' && !!result.currentStage && IN_DELIVERY_FLOW_STAGES.includes(result.currentStage);

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">My Vehicle</Typography>
        <Typography color="text.secondary">
          Look up your vehicle and request it back whenever you&apos;re ready.
        </Typography>
      </Box>

      <Stack direction="row" spacing={2}>
        <TextField
          fullWidth
          placeholder="Enter vehicle number (e.g. KA01AB1234)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void search();
          }}
        />
        <Button
          variant="contained"
          startIcon={<SearchOutlinedIcon />}
          disabled={!query.trim() || loading}
          onClick={() => void search()}
        >
          Search
        </Button>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      {searched && !error && !result && !loading && (
        <Typography color="text.secondary">No results. Try a different vehicle number.</Typography>
      )}

      {loading && (
        <Box sx={{ display: 'grid', placeItems: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      )}

      {result && !loading && (
        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={700}>
                {result.vehicleNumber}
              </Typography>
              <Chip label={result.status} color={result.status === 'ACTIVE' ? 'success' : 'default'} />
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Vehicle Type" value={result.vehicleType} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField
                  label="Current Status"
                  value={result.currentStage ? TIMELINE_STAGE_DISPLAY_NAMES[result.currentStage] : '—'}
                />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Entry Time" value={formatTime(result.entryTime)} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Exit Time" value={result.exitTime ? formatTime(result.exitTime) : '—'} />
              </Grid>
            </Grid>

            {canRequestDelivery && (
              <>
                <Divider sx={{ my: 2 }} />
                <Button
                  variant="contained"
                  color="success"
                  fullWidth
                  startIcon={requesting ? <CircularProgress size={18} color="inherit" /> : <RoomServiceOutlinedIcon />}
                  disabled={requesting}
                  onClick={() => void requestDelivery()}
                >
                  Request My Vehicle
                </Button>
              </>
            )}

            {isInDeliveryFlow && (
              <Alert severity="info" sx={{ mt: 2 }}>
                Your vehicle is on its way — current status:{' '}
                {result.currentStage ? TIMELINE_STAGE_DISPLAY_NAMES[result.currentStage] : ''}.
              </Alert>
            )}

            {requestMessage && (
              <Alert severity={requestMessage.type} sx={{ mt: 2 }}>
                {requestMessage.text}
              </Alert>
            )}
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}

function DetailField({ label, value }: { label: string; value: string }) {
  return (
    <Stack spacing={0.5}>
      <Typography variant="overline" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="body1" fontWeight={600}>
        {value}
      </Typography>
    </Stack>
  );
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}
