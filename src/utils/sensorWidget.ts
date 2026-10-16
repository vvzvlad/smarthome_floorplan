// Pure logic for the sensor widget (a non-clickable icon coloured by a field of
// the device's z2m state), shared by the preview in EntityOverlay.vue (editor)
// and the icon in InteractiveFloorplan.vue (viewer).

import { extractJsonPath } from './textEntity';

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
