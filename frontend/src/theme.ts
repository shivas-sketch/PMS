import { createTheme, type PaletteMode } from '@mui/material/styles';

const primary = '#1B5E7A';
const secondary = '#0E3A4C';

export function createAppTheme(mode: PaletteMode) {
  return createTheme({
    palette: {
      mode,
      primary: { main: primary },
      secondary: { main: secondary },
      background: {
        default: mode === 'dark' ? '#0b1220' : '#f5f7fb',
        paper: mode === 'dark' ? '#111827' : '#ffffff',
      },
    },
    typography: {
      fontFamily: 'Inter, Arial, sans-serif',
      h4: { fontWeight: 700 },
      h5: { fontWeight: 700 },
      button: { textTransform: 'none', fontWeight: 600 },
    },
    shape: { borderRadius: 12 },
    components: {
      MuiCard: {
        styleOverrides: {
          root: {
            boxShadow:
              mode === 'dark' ? 'none' : '0 2px 12px rgba(15, 23, 42, .07)',
            border:
              mode === 'dark' ? '1px solid rgba(148,163,184,.22)' : 'none',
          },
        },
      },
    },
  });
}
