// Pure logic for the sensor widget (a non-clickable icon coloured by a field of
// the device's z2m state), shared by the preview in EntityOverlay.vue (editor)
// and the icon in InteractiveFloorplan.vue (viewer).

import { extractJsonPath } from './textEntity';
import type { BinaryColors } from '../types/floorplan';

// Look of a sensor whose field has not been reported yet. zigbee2mqtt does not
// retain device states and a contact sensor reports only on change, so after a
// backend restart the state is unknown for a long time. Such an icon is grey,
// dimmed and drawn as a dashed outline without fill (class "unknown" in
// style.css), so it cannot be mistaken for the on or off state whatever colours
// are configured — the default offColor is the same grey.
export const SENSOR_UNKNOWN_COLOR = '#94a3b8';
export const SENSOR_UNKNOWN_OPACITY = 0.4;

/**
 * True when the field at `jsonPath` of the device's z2m payload, converted with
 * String(), equals `onValue` — e.g. `contact: false` with onValue "false" for an
 * open window. No payload yet -> false.
 */
export function isSensorActive(
  rawPayload: Record<string, unknown> | undefined,
  jsonPath: string,
  onValue: string,
): boolean {
  if (!rawPayload) return false;
  return String(extractJsonPath(rawPayload, jsonPath)) === onValue;
}

/** True once the device state carries the field at `jsonPath`. */
export function isSensorKnown(rawPayload: Record<string, unknown> | undefined, jsonPath: string): boolean {
  return !!rawPayload && extractJsonPath(rawPayload, jsonPath) !== undefined;
}

/**
 * Icon colour and opacity: onColor/offColor once the field at `jsonPath` has been
 * reported, the neutral unknown colour at reduced opacity before that.
 */
export function sensorIconStyle(
  rawPayload: Record<string, unknown> | undefined,
  jsonPath: string,
  onValue: string,
  colors: BinaryColors,
): { color: string; opacity: number } {
  if (!isSensorKnown(rawPayload, jsonPath)) {
    return { color: SENSOR_UNKNOWN_COLOR, opacity: SENSOR_UNKNOWN_OPACITY };
  }
  return { color: isSensorActive(rawPayload, jsonPath, onValue) ? colors.onColor : colors.offColor, opacity: 1 };
}
