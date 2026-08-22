import { type ReactNode } from 'react';
import {
  AppBar,
  Avatar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Stack,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import DashboardOutlinedIcon from '@mui/icons-material/DashboardOutlined';
import LocalParkingOutlinedIcon from '@mui/icons-material/LocalParkingOutlined';
import PhotoCameraOutlinedIcon from '@mui/icons-material/PhotoCameraOutlined';
import SearchOutlinedIcon from '@mui/icons-material/SearchOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LocalHospitalOutlinedIcon from '@mui/icons-material/LocalHospitalOutlined';
import ViewQuiltOutlinedIcon from '@mui/icons-material/ViewQuiltOutlined';

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
