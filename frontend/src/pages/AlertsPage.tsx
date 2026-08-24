import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  FormControl,
  IconButton,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import RefreshOutlinedIcon from '@mui/icons-material/RefreshOutlined';
import CloseOutlinedIcon from '@mui/icons-material/CloseOutlined';
import { get, post, ApiError } from '../api/client';
import type { AlertList, AlertSeverity, ParkingAlert } from '../types';

const severityColor: Record<AlertSeverity, 'default' | 'success' | 'warning' | 'error'> = {
  LOW: 'default',
  MEDIUM: 'warning',
  HIGH: 'error',
  CRITICAL: 'error',
};

const severityLabel: Record<AlertSeverity, string> = {
  LOW: '50%',
  MEDIUM: '80%',
  HIGH: '90%',
  CRITICAL: '98% / Full',
};

export function AlertsPage() {
  const [alerts, setAlerts] = useState<ParkingAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [filter, setFilter] = useState<'all' | 'unread' | 'read'>('all');
  const [severityFilter, setSeverityFilter] = useState<'all' | AlertSeverity>('all');

  const load = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const data = await get<AlertList>('/parking/alerts?limit=200');
      setAlerts(data.alerts);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : 'Unable to load alerts.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const interval = setInterval(load, 15000);
    return () => clearInterval(interval);
  }, [load]);

  const handleMarkRead = async (alertId: string) => {
    try {
      await post(`/parking/alerts/${alertId}/read`);
      setAlerts((prev) => prev.map((a) => (a.alertId === alertId ? { ...a, read: true } : a)));
    } catch {
      // ignore
    }
  };

  const filteredAlerts = alerts.filter((a) => {
    const statusOk =
      filter === 'all' ? true : filter === 'unread' ? !a.read : a.read;
    const severityOk = severityFilter === 'all' ? true : a.severity === severityFilter;
    return statusOk && severityOk;
  });

  const unreadCount = alerts.filter((a) => !a.read).length;
  const readCount = alerts.filter((a) => a.read).length;

  return (
    <Stack spacing={3}>
      <Stack direction={{ xs: 'column', sm: 'row' }} justifyContent="space-between" alignItems={{ sm: 'center' }} spacing={1.5}>
        <Box>
          <Typography variant="h4">Alerts</Typography>
          <Typography color="text.secondary">
            Capacity threshold notifications and parking occupancy warnings.
          </Typography>
        </Box>
        <IconButton onClick={() => void load()} aria-label="Refresh alerts">
          <RefreshOutlinedIcon />
        </IconButton>
      </Stack>

      {error && <Alert severity="error">{error}</Alert>}

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2 }}>
        <Card sx={{ flex: '1 1 200px', minWidth: 180 }}>
          <CardContent>
            <Typography variant="h3" fontWeight={700}>
              {unreadCount}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Unread alerts
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ flex: '1 1 200px', minWidth: 180 }}>
          <CardContent>
            <Typography variant="h3" fontWeight={700}>
              {readCount}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Read alerts
            </Typography>
          </CardContent>
        </Card>
        <Card sx={{ flex: '1 1 200px', minWidth: 180 }}>
          <CardContent>
            <Typography variant="h3" fontWeight={700}>
              {alerts.length}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Total alerts
            </Typography>
          </CardContent>
        </Card>
      </Box>

      <Paper>
        <Box
          sx={{
            px: 2.5,
            py: 2,
            display: 'flex',
            flexWrap: 'wrap',
            gap: 2,
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <Typography variant="h6">Notifications</Typography>
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="alert-status-filter">Status</InputLabel>
              <Select
                labelId="alert-status-filter"
                value={filter}
                label="Status"
                onChange={(e) => setFilter(e.target.value as 'all' | 'unread' | 'read')}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="unread">Unread</MenuItem>
                <MenuItem value="read">Read</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel id="alert-severity-filter">Severity</InputLabel>
              <Select
                labelId="alert-severity-filter"
                value={severityFilter}
                label="Severity"
                onChange={(e) => setSeverityFilter(e.target.value as 'all' | AlertSeverity)}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="LOW">50% (Low)</MenuItem>
                <MenuItem value="MEDIUM">80% (Medium)</MenuItem>
                <MenuItem value="HIGH">90% (High)</MenuItem>
                <MenuItem value="CRITICAL">98% / Full</MenuItem>
              </Select>
            </FormControl>
          </Box>
        </Box>
        <Divider />
        {loading && !alerts.length ? (
          <Box sx={{ display: 'grid', placeItems: 'center', py: 6 }}>
            <CircularProgress />
          </Box>
        ) : filteredAlerts.length === 0 ? (
          <Box sx={{ py: 4, textAlign: 'center' }}>
            <Typography color="text.secondary">No alerts match the selected filters.</Typography>
          </Box>
        ) : (
          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Severity</TableCell>
                  <TableCell>Message</TableCell>
                  <TableCell>Occupancy</TableCell>
                  <TableCell>Time</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell align="right">Action</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filteredAlerts.map((alert) => (
                  <TableRow
                    key={alert.alertId}
                    hover
                    sx={{ bgcolor: alert.read ? 'transparent' : 'action.hover' }}
                  >
                    <TableCell>
                      <Chip
                        size="small"
                        color={severityColor[alert.severity]}
                        label={severityLabel[alert.severity]}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography fontWeight={alert.read ? 400 : 600}>
                        {alert.message}
                      </Typography>
                    </TableCell>
                    <TableCell>{alert.occupancyPercent}%</TableCell>
                    <TableCell>{new Date(alert.createdAt).toLocaleString()}</TableCell>
                    <TableCell>{alert.read ? 'Read' : 'Unread'}</TableCell>
                    <TableCell align="right">
                      <IconButton
                        size="small"
                        aria-label={alert.read ? 'Already read' : 'Mark as read'}
                        disabled={alert.read}
                        onClick={() => handleMarkRead(alert.alertId)}
                      >
                        <CloseOutlinedIcon fontSize="small" />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </Paper>
    </Stack>
  );
}
