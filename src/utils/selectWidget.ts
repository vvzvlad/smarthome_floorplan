// Pure logic for the select (multi-switch / segmented mode selector) widget,
// shared by the read-only preview in EntityOverlay.vue (editor) and the
// interactive control in InteractiveFloorplan.vue (viewer). Extracted so the
// state resolution can be unit-tested once and stay consistent between both
// components.

/**
 * Resolve the currently-selected raw value of a select (multi-switch) widget,
 * in precedence order:
 *   1. the optimistic local value (if defined),
 *   2. otherwise the raw read-topic value (which may itself be undefined when
 *      nothing has been reported yet).
 * Returns undefined when neither is known (no segment is highlighted).
 */
export function resolveSelectValue(
  optimistic: string | undefined,
  rawTopicValue: string | undefined,
): string | undefined {
  if (optimistic !== undefined) return optimistic;
  return rawTopicValue;
}
