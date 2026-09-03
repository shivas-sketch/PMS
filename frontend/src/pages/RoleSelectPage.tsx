import { useState } from 'react';
import {
  Avatar,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Grid2 as Grid,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Typography,
} from '@mui/material';
import AdminPanelSettingsOutlinedIcon from '@mui/icons-material/AdminPanelSettingsOutlined';
import SupportAgentOutlinedIcon from '@mui/icons-material/SupportAgentOutlined';
import DirectionsCarFilledOutlinedIcon from '@mui/icons-material/DirectionsCarFilledOutlined';
import PersonOutlinedIcon from '@mui/icons-material/PersonOutlined';
import LocalHospitalOutlinedIcon from '@mui/icons-material/LocalHospitalOutlined';
import ArrowBackOutlinedIcon from '@mui/icons-material/ArrowBackOutlined';
import { VALET_DRIVERS, VALET_OPERATORS, type Identity } from '../roles';

type SelectableRole = 'ADMIN' | 'VALET_OPERATOR' | 'VALET_DRIVER' | 'CUSTOMER';
type PersonRole = 'VALET_OPERATOR' | 'VALET_DRIVER';

const ROLE_CARDS: { role: SelectableRole; label: string; description: string; icon: JSX.Element }[] = [
  {
    role: 'ADMIN',
    label: 'Admin',
    description: 'Full system access — parking layout, capacity, and monitoring.',
    icon: <AdminPanelSettingsOutlinedIcon fontSize="large" />,
  },
  {
    role: 'VALET_OPERATOR',
    label: 'Valet Operator',
    description: 'Dispatch drivers, register entries, and monitor active sessions.',
    icon: <SupportAgentOutlinedIcon fontSize="large" />,
  },
  {
    role: 'VALET_DRIVER',
    label: 'Valet Driver',
    description: 'Accept jobs, park vehicles, and bring them back to guests.',
    icon: <DirectionsCarFilledOutlinedIcon fontSize="large" />,
  },
  {
    role: 'CUSTOMER',
    label: 'Customer',
    description: 'Look up your vehicle and request it back when ready.',
    icon: <PersonOutlinedIcon fontSize="large" />,
  },
];

type Props = {
  onSelect: (identity: Identity) => void;
};

export function RoleSelectPage({ onSelect }: Props) {
  const [pendingRole, setPendingRole] = useState<PersonRole | null>(null);

  const people = pendingRole === 'VALET_OPERATOR' ? VALET_OPERATORS : VALET_DRIVERS;

  const handleCardClick = (role: SelectableRole) => {
    if (role === 'ADMIN') {
      onSelect({ role: 'ADMIN' });
    } else if (role === 'CUSTOMER') {
      onSelect({ role: 'CUSTOMER' });
    } else {
      setPendingRole(role);
    }
  };

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', bgcolor: 'background.default', p: 3 }}>
      <Stack spacing={4} alignItems="center" sx={{ maxWidth: 880, width: '100%' }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar variant="rounded" sx={{ bgcolor: 'primary.main', width: 48, height: 48 }}>
            <LocalHospitalOutlinedIcon />
          </Avatar>
          <Box>
            <Typography variant="h4" fontWeight={700}>
              Hospital Valet Parking
            </Typography>
            <Typography color="text.secondary">Choose how you&apos;d like to continue</Typography>
          </Box>
        </Stack>

        {!pendingRole ? (
          <Grid container spacing={3} sx={{ width: '100%' }}>
            {ROLE_CARDS.map((card) => (
              <Grid key={card.role} size={{ xs: 12, sm: 6 }}>
                <Card>
                  <CardActionArea onClick={() => handleCardClick(card.role)} sx={{ p: 3 }}>
                    <Stack spacing={1.5} alignItems="center" textAlign="center">
                      <Box sx={{ color: 'primary.main' }}>{card.icon}</Box>
                      <Typography variant="h6" fontWeight={700}>
                        {card.label}
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {card.description}
                      </Typography>
                    </Stack>
                  </CardActionArea>
                </Card>
              </Grid>
            ))}
          </Grid>
        ) : (
          <Card sx={{ width: '100%', maxWidth: 460 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                {pendingRole === 'VALET_OPERATOR' ? 'Select Operator' : 'Select Driver'}
              </Typography>
              <Typography variant="body2" color="text.secondary" gutterBottom>
                Pick your name to continue as this role.
              </Typography>
              <List sx={{ mt: 1 }}>
                {people.map((person) => (
                  <ListItemButton
                    key={person.id}
                    onClick={() => onSelect({ role: pendingRole, person })}
                    sx={{ borderRadius: 1.5, mb: 0.5, border: '1px solid', borderColor: 'divider' }}
                  >
                    <ListItemText primary={person.name} />
                  </ListItemButton>
                ))}
              </List>
              <Button startIcon={<ArrowBackOutlinedIcon />} sx={{ mt: 1 }} onClick={() => setPendingRole(null)}>
                Back
              </Button>
            </CardContent>
          </Card>
        )}
      </Stack>
    </Box>
  );
}
