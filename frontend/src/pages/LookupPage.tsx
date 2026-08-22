import { useCallback, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Grid2 as Grid,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import { get, ApiError } from '../api/client';
import type { ParkingSession } from '../types';

export function LookupPage() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState<ParkingSession | null>(null);
  const [searched, setSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();

  const search = useCallback(async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError(undefined);
    setResult(null);
    setSearched(true);
    try {
      setResult(
        await get<ParkingSession>(`/parking/vehicles/${encodeURIComponent(query.trim())}`),
      );
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

  return (
    <Stack spacing={3}>
      <Box>
        <Typography variant="h4">Vehicle Lookup</Typography>
        <Typography color="text.secondary">
          Search for a vehicle by plate number to view its parking session details.
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

      {result && (
        <Card>
          <CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h5" fontWeight={700}>
                {result.vehicleNumber}
              </Typography>
              <Chip
                label={result.status}
                color={result.status === 'ACTIVE' ? 'success' : 'default'}
              />
            </Stack>
            <Divider sx={{ my: 2 }} />
            <Grid container spacing={2}>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Session ID" value={result.sessionId} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Vehicle Type" value={result.vehicleType} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Wheel Category" value={String(result.wheelCategory)} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Status" value={result.status} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField label="Entry Time" value={formatTime(result.entryTime)} />
              </Grid>
              <Grid size={{ xs: 12, sm: 6 }}>
                <DetailField
                  label="Exit Time"
                  value={result.exitTime ? formatTime(result.exitTime) : '—'}
                />
              </Grid>
            </Grid>
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
