import { Box, Card, CardActionArea, CardContent, Stack, Typography } from '@mui/material';
import type { ReactNode } from 'react';

export function MetricCard({
  label,
  value,
  icon,
  caption,
  color = 'primary',
  onClick,
}: {
  label: string;
  value: string | number;
  icon: ReactNode;
  caption?: string;
  color?: 'primary' | 'secondary' | 'success' | 'warning' | 'error' | 'info';
  onClick?: () => void;
}) {
  return (
    <Card
      onClick={onClick}
      sx={{
        cursor: onClick ? 'pointer' : 'default',
        transition: 'box-shadow 0.2s, transform 0.2s',
        '&:hover': onClick
          ? { boxShadow: 6, transform: 'translateY(-2px)' }
          : {},
      }}
    >
      <CardActionArea disabled={!onClick}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="flex-start">
            <Box>
              <Typography variant="body2" color="text.secondary">
                {label}
              </Typography>
              <Typography variant="h4" sx={{ mt: 1 }}>
                {value}
              </Typography>
              {caption && (
                <Typography variant="caption" color="text.secondary">
                  {caption}
                </Typography>
              )}
            </Box>
            <Box sx={{ color: `${color}.main` }}>{icon}</Box>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
