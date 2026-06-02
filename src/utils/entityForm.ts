// Pure helpers for the editor's PropertiesPanel form. Extracted so the device
// filtering, numeric-field parsing and default-config seeds can be unit-tested
// without mounting the component.

import type { TextConfig, NumberConfig, ButtonConfig, ToggleConfig } from '../types/floorplan';

/**
 * Filter a device list by a case-insensitive substring query. An empty query
 * returns the full list unchanged. Mirrors PropertiesPanel.vue's
 * filteredDevices computed (the query is already lowercased there before the
 * empty check; we lowercase here so callers can pass the raw query).
 */
export function filterDevices(list: string[], query: string): string[] {
  const q = query.toLowerCase();
  if (!q) return list;
  return list.filter((d) => d.toLowerCase().includes(q));
}

/**
 * Parse a numeric form-field value. Returns the parsed number, or null when the
 * input does not parse to a number (so callers can skip the assignment, exactly
 * like PropertiesPanel.vue's setNumberNum which only assigns when not NaN).
 */
export function parseNumberField(raw: string): number | null {
  const n = parseFloat(raw);
  return Number.isNaN(n) ? null : n;
}

/**
 * Default seed for a text-entity config, matching PropertiesPanel.vue's
 * onTypeChange literal.
 */
export function defaultTextConfig(): TextConfig {
  return { jsonPath: 'temperature', format: '{}' };
}

/**
 * Default seed for a number-entity config, matching PropertiesPanel.vue's
 * onTypeChange literal.
 */
export function defaultNumberConfig(): NumberConfig {
  return { readTopic: '', writeTopic: '', min: 0, max: 100, step: 1, unit: '', size: 2.5 };
}

/**
 * Default seed for a button-entity config, matching PropertiesPanel.vue's
 * onTypeChange literal.
 */
export function defaultButtonConfig(): ButtonConfig {
  return { topic: '', value: '', text: 'Send', size: 2.5 };
}

/**
 * Default seed for a toggle-entity config, matching PropertiesPanel.vue's
 * onTypeChange literal.
 */
export function defaultToggleConfig(): ToggleConfig {
  return { readTopic: '', writeTopic: '', onValue: 'ON', offValue: 'OFF', size: 2.5 };
}
