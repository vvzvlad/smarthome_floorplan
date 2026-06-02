export type EntityType = 'light' | 'text' | 'number' | 'button' | 'toggle';
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

export interface TextConfig {
  jsonPath: string;   // e.g. "temperature" or "sensors.co2"
  format: string;     // e.g. "Temp: {} °C"
  size: number;         // base font size in cqw; scales the text pill
}

export interface NumberConfig {
  readTopic: string;    // MQTT topic to read the raw current value from
  writeTopic: string;   // MQTT topic to publish the raw value to
  min: number;
  max: number;
  step: number;
  unit: string;
  size: number;         // base font size in cqw; scales the whole stepper widget
}

export interface ButtonConfig {
  topic: string;   // MQTT topic to publish to on click
  value: string;   // raw value (no JSON) to publish
  text: string;    // button caption shown on the widget
  size: number;    // base font size in cqw; scales the whole widget
}

export interface ToggleConfig {
  readTopic: string;    // MQTT topic to read the current raw value from
  writeTopic: string;   // MQTT topic to publish to on toggle
  onValue: string;      // raw value representing/publishing the ON state
  offValue: string;     // raw value representing/publishing the OFF state
  size: number;         // base size in cqw; scales the whole switch
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
  textConfig?: TextConfig;
  numberConfig?: NumberConfig;
  buttonConfig?: ButtonConfig;
  toggleConfig?: ToggleConfig;
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
  rawPayload?: Record<string, unknown>;
  numberValue?: number; // optimistic local value for number widgets
  toggleOn?: boolean; // optimistic local on/off state for toggle widgets
}
