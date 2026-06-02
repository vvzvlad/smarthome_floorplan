// Pure entity-state normalization. Extracted from App.vue's loadStates so the
// 'ON' -> 'on' mapping can be unit-tested and reused.

/**
 * Normalize a raw state payload's `state` field into the canonical 'on'/'off'.
 * Mirrors App.vue's logic: a string equal to 'ON' (case-insensitive) maps to
 * 'on'; anything else (other strings, numbers, undefined, non-strings) maps to
 * 'off'.
 */
export function normalizeEntityState(payload: { state?: unknown }): 'on' | 'off' {
  return typeof payload.state === 'string' && payload.state.toUpperCase() === 'ON' ? 'on' : 'off';
}
