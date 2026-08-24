import { type ReactNode, useEffect, useState, useCallback } from 'react';
import {
  AppBar,
  Avatar,
  Badge,
  Box,
  Chip,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Popover,
  Stack,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import NotificationsOutlinedIcon from '@mui/icons-material/NotificationsOutlined';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import LocalParkingOutlinedIcon from '@mui/icons-material/LocalParkingOutlined';
import PhotoCameraOutlinedIcon from '@mui/icons-material/PhotoCameraOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LocalHospitalOutlinedIcon from '@mui/icons-material/LocalHospitalOutlined';
import ViewQuiltOutlinedIcon from '@mui/icons-material/ViewQuiltOutlined';
import { get, post } from '../api/client';
import type { AlertList, ParkingAlert, AlertSeverity } from '../types';

export type Page = 'dashboard' | 'recognition' | 'parking' | 'layout' | 'lookup';

type Props = {
  page: Page;
  onPageChange: (page: Page) => void;
  mode: 'light' | 'dark';
  toggleMode: () => void;
  children: ReactNode;
};

const drawerWidth = 260;

const nav: { page: Page; label: string; icon: ReactNode }[] = [
  { page: 'dashboard', label: 'Dashboard', icon: <DashboardOutlinedIcon /> },
  { page: 'recognition', label: 'Recognition', icon: <PhotoCameraOutlinedIcon /> },
  { page: 'parking', label: 'Parking', icon: <LocalParkingOutlinedIcon /> },
  { page: 'layout', label: 'Layout', icon: <ViewQuiltOutlinedIcon /> },
  { page: 'lookup', label: 'Lookup', icon: <SearchOutlinedIcon /> },
];

export function AppShell({ page, onPageChange, mode, toggleMode, children }: Props) {
  const [alerts, setAlerts] = useState<ParkingAlert[]>([]);
  const [notifAnchor, setNotifAnchor] = useState<HTMLElement | null>(null);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await get<AlertList>('/parking/alerts?limit=20');
      setAlerts(data.alerts);
    } catch {
      // silently ignore — alerts are non-critical
    }
  }, []);

  useEffect(() => {
    fetchAlerts();
    const interval = setInterval(fetchAlerts, 15000);
    return () => clearInterval(interval);
  }, [fetchAlerts]);

  const unreadCount = alerts.filter((a) => !a.read).length;

  const handleNotifClick = (e: React.MouseEvent<HTMLElement>) => {
    setNotifAnchor(e.currentTarget);
  };

  const handleNotifClose = () => {
    setNotifAnchor(null);
  };

  const handleMarkRead = async (alertId: string) => {
    try {
      await post(`/parking/alerts/${alertId}/read`);
      setAlerts((prev) =>
        prev.map((a) => (a.alertId === alertId ? { ...a, read: true } : a)),
      );
    } catch {
      // ignore
    }
  };

  const severityColor: Record<AlertSeverity, string> = {
    LOW: '#6b7280',
    MEDIUM: '#f59e0b',
    HIGH: '#f97316',
    CRITICAL: '#ef4444',
  };

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh' }}>
      <AppBar
        position="fixed"
        elevation={0}
        color="inherit"
        sx={{
          borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
          zIndex: (theme) => theme.zIndex.drawer + 1,
        }}
      >
        <Toolbar sx={{ gap: 1 }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ minWidth: drawerWidth - 24 }}>
            <Avatar variant="rounded" sx={{ bgcolor: 'primary.main' }}>
              <LocalHospitalOutlinedIcon />
            </Avatar>
            <Box sx={{ minWidth: 0 }}>
              <Typography variant="subtitle1" noWrap fontWeight={750}>
                Hospital Valet Parking
              </Typography>
              <Typography variant="caption" color="text.secondary">
                Operations Console
              </Typography>
            </Box>
          </Stack>
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title="Notifications">
            <IconButton onClick={handleNotifClick} aria-label="Notifications">
              <Badge badgeContent={unreadCount} color="error">
                <NotificationsOutlinedIcon />
              </Badge>
            </IconButton>
          </Tooltip>
          <Popover
            open={!!notifAnchor}
            anchorEl={notifAnchor}
            onClose={handleNotifClose}
            anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            PaperProps={{ sx: { width: 380, maxHeight: 480 } }}
          >
            <Box sx={{ p: 2, borderBottom: (theme) => `1px solid ${theme.palette.divider}` }}>
              <Typography variant="subtitle2" fontWeight={700}>
                Notifications
              </Typography>
              {unreadCount > 0 && (
                <Typography variant="caption" color="text.secondary">
                  {unreadCount} unread
                </Typography>
              )}
            </Box>
            {alerts.length === 0 ? (
              <Box sx={{ p: 3, textAlign: 'center' }}>
                <Typography variant="body2" color="text.secondary">
                  No alerts yet
                </Typography>
              </Box>
            ) : (
              <Box sx={{ maxHeight: 380, overflowY: 'auto' }}>
                {alerts.map((alert) => (
                  <Box
                    key={alert.alertId}
                    sx={{
                      px: 2,
                      py: 1.5,
                      borderBottom: (theme) => `1px solid ${theme.palette.divider}`,
                      cursor: alert.read ? 'default' : 'pointer',
                      bgcolor: alert.read ? 'transparent' : 'action.hover',
                      '&:hover': alert.read ? {} : { bgcolor: 'action.selected' },
                    }}
                    onClick={() => !alert.read && handleMarkRead(alert.alertId)}
                  >
                    <Stack direction="row" spacing={1} alignItems="flex-start">
                      <Box
                        sx={{
                          width: 8,
                          height: 8,
                          borderRadius: '50%',
                          mt: 0.75,
                          flexShrink: 0,
                          bgcolor: severityColor[alert.severity],
                        }}
                      />
                      <Box sx={{ minWidth: 0, flexGrow: 1 }}>
                        <Typography variant="body2" fontWeight={600} sx={{ wordBreak: 'break-word' }}>
                          {alert.message}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {new Date(alert.createdAt).toLocaleString()}
                        </Typography>
                      </Box>
                      {!alert.read && (
                        <Chip
                          label="New"
                          size="small"
                          color="error"
                          sx={{ height: 20, fontSize: '0.7rem' }}
                        />
                      )}
                    </Stack>
                  </Box>
                ))}
              </Box>
            )}
          </Popover>
          <Tooltip title="Toggle color mode">
            <IconButton onClick={toggleMode} aria-label="Toggle color mode">
              {mode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="permanent"
        sx={{
          width: drawerWidth,
          flexShrink: 0,
          '& .MuiDrawer-paper': {
            width: drawerWidth,
            boxSizing: 'border-box',
            borderRight: (theme) => `1px solid ${theme.palette.divider}`,
          },
        }}
      >
        <Toolbar />
        <Box sx={{ p: 1.5 }}>
          <Typography variant="overline" color="text.secondary">
            Operations
          </Typography>
        </Box>
        <List dense>
          {nav.map((item) => (
            <ListItemButton
              key={item.page}
              selected={page === item.page}
              onClick={() => onPageChange(item.page)}
              sx={{ mx: 1, borderRadius: 2 }}
            >
              <ListItemIcon>{item.icon}</ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
        <Box sx={{ flexGrow: 1 }} />
        <Divider />
        <Box sx={{ p: 2 }}>
          <Typography variant="caption" color="text.secondary">
            {`© ${new Date().getFullYear()} Hospital Valet Parking`}
          </Typography>
        </Box>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, bgcolor: 'background.default', minWidth: 0 }}>
        <Toolbar />
        <Box sx={{ p: { xs: 2, md: 3 } }}>{children}</Box>
      </Box>
    </Box>
  );
}
