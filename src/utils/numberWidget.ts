// Pure logic for the number stepper widget, shared by the read-only preview in
// EntityOverlay.vue (editor) and the interactive stepper in
// InteractiveFloorplan.vue (viewer). Extracted so the value resolution, the
// step arithmetic and the float-drift rounding can be unit-tested once and stay
// consistent between both components (the R-shared consolidation).

/**
 * Resolve the value a number widget should display, in precedence order:
 *   1. the optimistic / last user value (if defined),
 *   2. the parsed read-topic value (if present and finite),
 *   3. `min` as the fallback.
 *
 * The optimistic value of `0` must win, so we check `!== undefined` rather than
 * a falsy check.
 */
export function resolveNumberValue(
  optimistic: number | undefined,
  rawTopicValue: string | undefined,
  min: number,
): number {
  if (optimistic !== undefined) return optimistic;
  const n = rawTopicValue !== undefined ? parseFloat(rawTopicValue) : NaN;
  return Number.isFinite(n) ? n : min;
}

/**
 * Round `value` to the number of decimal places implied by `step`, to avoid
 * floating-point drift (e.g. 0.1 + 0.2 = 0.30000000000000004). Handles both
 * decimal ("0.25") and exponential ("1e-7") string forms of the step.
 * Matches InteractiveFloorplan.vue's original roundToStep exactly.
 */
export function roundToStep(value: number, step: number | string): number {
  const str = Math.abs(step as number).toString();
  let decimals = 0;
  if (str.includes('e-')) {
    decimals = parseInt(str.split('e-')[1] ?? '', 10) || 0;
  } else if (str.includes('.')) {
    decimals = (str.split('.')[1] ?? '').length;
  }
  return Number(value.toFixed(Math.min(decimals, 100)));
}

/**
 * Compute the next clamped value when stepping a number widget in direction
 * `dir` (+1 or -1). Mirrors InteractiveFloorplan.vue's stepNumber arithmetic:
 *  - the step is `Math.abs(step) || 1` (guards 0 / negative step),
 *  - min/max are normalized so an inverted config still works,
 *  - the candidate is rounded to the step's precision then clamped,
 *  - returns null when the result equals the current value (no-op, no emit).
 */
export function computeNextStep(
  current: number,
  dir: 1 | -1,
  cfg: { min: number; max: number; step: number },
): number | null {
  const step = Math.abs(cfg.step) || 1; // guard against 0 / negative step
  const lo = Math.min(cfg.min, cfg.max);
  const hi = Math.max(cfg.min, cfg.max);
  let next = roundToStep(current + dir * step, step);
  if (next < lo) next = lo;
  if (next > hi) next = hi;
  if (next === current) return null;
  return next;
}

/**
 * True when `value` is at or below the lower of the (possibly inverted) bounds.
 */
export function isAtMin(value: number, min: number, max: number): boolean {
  return value <= Math.min(min, max);
}

/**
 * True when `value` is at or above the higher of the (possibly inverted) bounds.
 */
export function isAtMax(value: number, min: number, max: number): boolean {
  return value >= Math.max(min, max);
}

/**
 * Format a number for display, appending the unit with a single leading space
 * only when the unit is non-empty.
 */
export function formatNumberDisplay(value: number, unit?: string): string {
  return `${value}${unit ? ' ' + unit : ''}`;
}
