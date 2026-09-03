import type { ReactNode } from 'react';
import { AppBar, Avatar, Box, Button, IconButton, Toolbar, Tooltip, Typography } from '@mui/material';
import LocalHospitalOutlinedIcon from '@mui/icons-material/LocalHospitalOutlined';
import LightModeOutlinedIcon from '@mui/icons-material/LightModeOutlined';
import DarkModeOutlinedIcon from '@mui/icons-material/DarkModeOutlined';
import LogoutOutlinedIcon from '@mui/icons-material/LogoutOutlined';

type Props = {
  title: string;
  identityLabel: string;
  mode: 'light' | 'dark';
  toggleMode: () => void;
  onSwitchRole: () => void;
  children: ReactNode;
};

/** Lightweight, sidebar-free shell used for the Valet Driver and Customer roles. */
export function MinimalShell({ title, identityLabel, mode, toggleMode, onSwitchRole, children }: Props) {
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar
        position="static"
        elevation={0}
        color="inherit"
        sx={{ borderBottom: (theme) => `1px solid ${theme.palette.divider}` }}
      >
        <Toolbar sx={{ gap: 1.5 }}>
          <Avatar variant="rounded" sx={{ bgcolor: 'primary.main' }}>
            <LocalHospitalOutlinedIcon />
          </Avatar>
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="subtitle1" fontWeight={750} noWrap>
              {title}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {identityLabel}
            </Typography>
          </Box>
          <Box sx={{ flexGrow: 1 }} />
          <Tooltip title="Toggle color mode">
            <IconButton onClick={toggleMode} aria-label="Toggle color mode">
              {mode === 'dark' ? <LightModeOutlinedIcon /> : <DarkModeOutlinedIcon />}
            </IconButton>
          </Tooltip>
          <Button startIcon={<LogoutOutlinedIcon />} onClick={onSwitchRole} color="inherit">
            Switch Role
          </Button>
        </Toolbar>
      </AppBar>
      <Box sx={{ p: { xs: 2, md: 3 }, maxWidth: 1000, mx: 'auto' }}>{children}</Box>
    </Box>
  );
}
