// Pure logic for the toggle (on/off switch) widget, shared by the read-only
// preview in EntityOverlay.vue (editor) and the interactive switch in
// InteractiveFloorplan.vue (viewer). Extracted so the state resolution can be
// unit-tested once and stay consistent between both components.

/**
 * Resolve the on/off state of a toggle widget, in precedence order:
 *   1. the optimistic local value (if defined — `false` must win, so check
 *      `!== undefined`),
 *   2. true when the raw read-topic value exactly equals `onValue`,
 *   3. false otherwise (off / unknown).
 */
export function resolveToggleState(
  optimistic: boolean | undefined,
  rawTopicValue: string | undefined,
  onValue: string,
): boolean {
  if (optimistic !== undefined) return optimistic;
  return rawTopicValue !== undefined && rawTopicValue === onValue;
}
