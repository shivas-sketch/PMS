export type ValetIdentity = {
  id: string;
  name: string;
};

export type Identity =
  | { role: 'ADMIN' }
  | { role: 'CUSTOMER' }
  | { role: 'VALET_OPERATOR'; person: ValetIdentity }
  | { role: 'VALET_DRIVER'; person: ValetIdentity };

// Seeded valet staff. In a system with real accounts these would come from
// the backend; for now they let the Valet Operator / Valet Driver roles be
// tried out without building a full login flow.
export const VALET_OPERATORS: ValetIdentity[] = [
  { id: 'op-1', name: 'Anita Rao' },
  { id: 'op-2', name: 'Vikram Shah' },
];

export const VALET_DRIVERS: ValetIdentity[] = [
  { id: 'drv-1', name: 'Ravi Kumar' },
  { id: 'drv-2', name: 'Suresh Patil' },
  { id: 'drv-3', name: 'Arjun Nair' },
  { id: 'drv-4', name: 'Meena Iyer' },
];
