import { useState } from 'react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { AppShell, type Page } from './components/AppShell';
import { createAppTheme } from './theme';
import { DashboardPage } from './pages/DashboardPage';
import { RecognitionPage } from './pages/RecognitionPage';
import { ParkingPage } from './pages/ParkingPage';
import { ParkingLayoutPage } from './pages/ParkingLayoutPage';
import { LookupPage } from './pages/LookupPage';
import { AlertsPage } from './pages/AlertsPage';

export function App() {
  const [page, setPage] = useState<Page>('dashboard');
  const [mode, setMode] = useState<'light' | 'dark'>('light');

  const toggleMode = () => setMode((prev) => (prev === 'light' ? 'dark' : 'light'));
  const theme = createAppTheme(mode);

  const content =
    page === 'dashboard' ? <DashboardPage /> :
    page === 'recognition' ? <RecognitionPage /> :
    page === 'parking' ? <ParkingPage /> :
    page === 'layout' ? <ParkingLayoutPage /> :
    page === 'alerts' ? <AlertsPage /> :
    <LookupPage />;

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppShell page={page} onPageChange={setPage} mode={mode} toggleMode={toggleMode}>
        {content}
      </AppShell>
    </ThemeProvider>
  );
}
