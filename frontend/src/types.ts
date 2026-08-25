export type Capacity = {
  totalCapacity: number;
  availableSlots: number;
  occupiedSlots: number;
};

export type ParkingTimelineStage =
  | 'ASSIGNED_FOR_PARKING'
  | 'PARKING_REQUEST_ACCEPTED'
  | 'PARKED'
  | 'REQUESTED_FOR_DELIVERY'
  | 'ASSIGNED_FOR_DELIVERY'
  | 'DELIVERY_REQUEST_ACCEPTED'
  | 'PICKED_UP'
  | 'ARRIVED'
  | 'REQUESTED_FOR_MANUAL_OVERRIDE'
  | 'DELIVERED';

export const TIMELINE_STAGE_DISPLAY_NAMES: Record<ParkingTimelineStage, string> = {
  ASSIGNED_FOR_PARKING: 'Assigned for parking',
  PARKING_REQUEST_ACCEPTED: 'Parking request accepted',
  PARKED: 'Parked',
  REQUESTED_FOR_DELIVERY: 'Requested for delivery',
  ASSIGNED_FOR_DELIVERY: 'Assigned for delivery',
  DELIVERY_REQUEST_ACCEPTED: 'Delivery request accepted',
  PICKED_UP: 'Picked up',
  ARRIVED: 'Arrived',
  REQUESTED_FOR_MANUAL_OVERRIDE: 'Requested For Manual Override',
  DELIVERED: 'Delivered',
};

export type ParkingTimelineEvent = {
  eventId: string;
  sessionId: string;
  vehicleNumber: string;
  stage: ParkingTimelineStage;
  displayName: string;
  timestamp: string;
  areaId?: string | null;
  areaName?: string | null;
  slotId?: string | null;
  slotNumber?: string | null;
  valetId?: string | null;
  valetName?: string | null;
  notes?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ParkingTimelineList = {
  events: ParkingTimelineEvent[];
  count: number;
};

export type CreateTimelineEventRequest = {
  stage: ParkingTimelineStage;
  valetId?: string | null;
  valetName?: string | null;
  notes?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type TimelineActionRequest = {
  valetId?: string | null;
  valetName?: string | null;
  notes?: string | null;
  metadata?: Record<string, unknown> | null;
};

export type ParkingSession = {
  sessionId: string;
  vehicleNumber: string;
  wheelCategory: number;
  vehicleType: string;
  hospitalSide?: string | null;
  status: 'ACTIVE' | 'EXITED';
  entryTime: string;
  exitTime: string | null;
  areaId?: string | null;
  areaName?: string | null;
  slotId?: string | null;
  slotNumber?: string | null;
  isCorridorParking?: boolean;
  currentStage?: ParkingTimelineStage | null;
};

export type VehicleList = {
  vehicles: ParkingSession[];
  count: number;
};

export type RecognitionDetails = {
  vehicleDetectionConfidence: number | null;
  plateDetectionConfidence: number | null;
  ocrConfidence: number | null;
};

export type RecognitionResult = {
  vehicleNumber: string | null;
  wheelCategory: number;
  vehicleType: string;
  confidence: number;
  details: RecognitionDetails;
  warnings: string[];
};

export type AddVehicleRequest = {
  vehicleNumber: string;
  wheelCategory: number;
  vehicleType: string;
  hospitalSide?: string | null;
  areaId?: string | null;
  slotId?: string | null;
  useCorridor?: boolean;
};

export type UpdateSessionRequest = {
  vehicleType?: string;
  wheelCategory?: number;
  hospitalSide?: string | null;
};

export const HOSPITAL_SIDES = ['North Side', 'South Side', 'East Side', 'West Side', 'Main Entrance', 'Exit Gate'] as const;

export type AreaType = 'BASEMENT' | 'GROUND' | 'SIDE' | 'OUTSIDE' | 'ROOFTOP' | 'OTHER';

export type ParkingArea = {
  areaId: string;
  name: string;
  areaType: AreaType;
  description?: string | null;
  totalSlots: number;
  availableSlots: number;
  occupiedSlots: number;
  corridorCapacity: number;
  corridorAvailable: number;
  corridorOccupied: number;
  createdAt: string;
  updatedAt: string;
};

export type ParkingAreaList = {
  areas: ParkingArea[];
  count: number;
};

export type SlotStatus = 'AVAILABLE' | 'OCCUPIED' | 'RESERVED' | 'MAINTENANCE';

export type ParkingSlot = {
  slotId: string;
  areaId: string;
  slotNumber: string;
  status: SlotStatus;
  vehicleNumber?: string | null;
  sessionId?: string | null;
  createdAt: string;
  updatedAt: string;
};

export type ParkingSlotList = {
  slots: ParkingSlot[];
  count: number;
};

export type BulkCreateSlotsRequest = {
  count: number;
  prefix?: string | null;
  startIndex?: number;
};

export type BulkCreateSlotsResponse = {
  created: number;
  slots: ParkingSlot[];
};

export type UpdateSlotRequest = {
  slotNumber?: string | null;
  status?: SlotStatus | null;
};

export type AlertSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type ParkingAlert = {
  alertId: string;
  threshold: number;
  occupiedSlots: number;
  totalCapacity: number;
  occupancyPercent: number;
  severity: AlertSeverity;
  message: string;
  read: boolean;
  createdAt: string;
  readAt?: string | null;
};

export type AlertList = {
  alerts: ParkingAlert[];
  count: number;
};
