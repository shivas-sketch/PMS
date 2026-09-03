import { useEffect, useState } from 'react';
import { CssBaseline, ThemeProvider } from '@mui/material';
import { AppShell, type Page } from './components/AppShell';
import { MinimalShell } from './components/MinimalShell';
import { createAppTheme } from './theme';
import { DashboardPage } from './pages/DashboardPage';
import { RecognitionPage } from './pages/RecognitionPage';
import { ParkingPage } from './pages/ParkingPage';
import { ParkingLayoutPage } from './pages/ParkingLayoutPage';
import { LookupPage } from './pages/LookupPage';
import { AlertsPage } from './pages/AlertsPage';
import { RoleSelectPage } from './pages/RoleSelectPage';
import { DriverTasksPage } from './pages/DriverTasksPage';
import { CustomerPage } from './pages/CustomerPage';
import type { Identity } from './roles';

const IDENTITY_STORAGE_KEY = 'pms.identity';

function loadIdentity(): Identity | null {
  try {
    const raw = localStorage.getItem(IDENTITY_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Identity) : null;
  } catch {
    return null;
  }
}

const ADMIN_NAV: Page[] = ['dashboard', 'recognition', 'parking', 'layout', 'lookup', 'alerts'];
const OPERATOR_NAV: Page[] = ['dashboard', 'recognition', 'parking', 'lookup', 'alerts'];

export function App() {
  const [identity, setIdentity] = useState<Identity | null>(() => loadIdentity());
  const [page, setPage] = useState<Page>('dashboard');
  const [mode, setMode] = useState<'light' | 'dark'>('light');

  const toggleMode = () => setMode((prev) => (prev === 'light' ? 'dark' : 'light'));
  const theme = createAppTheme(mode);

  useEffect(() => {
    if (identity) {
      localStorage.setItem(IDENTITY_STORAGE_KEY, JSON.stringify(identity));
    } else {
      localStorage.removeItem(IDENTITY_STORAGE_KEY);
    }
  }, [identity]);

  const switchRole = () => {
    setIdentity(null);
    setPage('dashboard');
  };

  if (!identity) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <RoleSelectPage onSelect={setIdentity} />
      </ThemeProvider>
    );
  }

  if (identity.role === 'VALET_DRIVER') {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <MinimalShell
          title="Valet Driver"
          identityLabel={identity.person.name}
          mode={mode}
          toggleMode={toggleMode}
          onSwitchRole={switchRole}
        >
          <DriverTasksPage driver={identity.person} />
        </MinimalShell>
      </ThemeProvider>
    );
  }

  if (identity.role === 'CUSTOMER') {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <MinimalShell
          title="Customer Portal"
          identityLabel="Guest"
          mode={mode}
          toggleMode={toggleMode}
          onSwitchRole={switchRole}
        >
          <CustomerPage />
        </MinimalShell>
      </ThemeProvider>
    );
  }

  const navItems = identity.role === 'ADMIN' ? ADMIN_NAV : OPERATOR_NAV;
  const activePage = navItems.includes(page) ? page : 'dashboard';

  const content =
    activePage === 'dashboard' ? <DashboardPage /> :
    activePage === 'recognition' ? <RecognitionPage /> :
    activePage === 'parking' ? <ParkingPage /> :
    activePage === 'layout' ? <ParkingLayoutPage /> :
    activePage === 'alerts' ? <AlertsPage /> :
    <LookupPage />;

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <AppShell
        page={activePage}
        onPageChange={setPage}
        mode={mode}
        toggleMode={toggleMode}
        navItems={navItems}
        identityLabel={identity.role === 'ADMIN' ? 'Admin' : `${identity.person.name} · Valet Operator`}
        onSwitchRole={switchRole}
      >
        {content}
      </AppShell>
    </ThemeProvider>
  );
}
