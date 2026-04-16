export type EntityType = 'light';
export type EntityShape = 'circle' | 'square' | 'rect' | 'custom';

export interface BinaryColors {
  onColor: string;
  offColor: string;
}

export interface EntityStyle {
  width: number; // css value or percentage
  height: number;
  colors: BinaryColors;
  onOpacity: number;
  offOpacity: number;
  gradientRadius: number; // percentage
  rotation: number; // degrees
}

export interface LabelConfig {
  show: boolean;
  offsetX: number;
  offsetY: number;
  color: string;
}

export interface EntityConfig {
  id: string; // Internal UUID for the UI
  entityId: string; // HA Entity ID e.g. light.living_room
  label: string; // Display name
  type: EntityType;
  x: number; // Percentage 0-100
  y: number; // Percentage 0-100
  points?: { x: number; y: number }[]; // Polygon points (percentage)
  shape: EntityShape;
  style: EntityStyle;
  labelConfig: LabelConfig;
  // Runtime state (not saved in config, but handy to have loosely coupled or in a separate store, 
  // but for experimentation mode we might want to store simulation state here or in a parallel map)
}

export interface FloorplanConfig {
  id: string;
  name: string;
  imageBase64: string; // Data URI
  entities: EntityConfig[];
}

export interface EntityState {
  state: string;
  brightness?: number; // 0-255
  shouldLightUp?: boolean;
}
