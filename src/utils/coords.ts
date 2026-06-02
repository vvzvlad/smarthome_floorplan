// Pure coordinate / geometry helpers shared by the editor canvas and entity
// overlay. Extracted from CanvasArea.vue and EntityOverlay.vue so the math can
// be unit-tested in isolation and is no longer duplicated across components.

export interface Point {
  x: number;
  y: number;
}

export interface RectLike {
  left: number;
  top: number;
  width: number;
  height: number;
}

/**
 * Convert a screen-space pointer position into image-space percentages (0-100)
 * relative to the given bounding rect. Previously duplicated ~4x across
 * CanvasArea.vue and EntityOverlay.vue.
 *
 * Guards against zero width/height so callers never get NaN/Infinity: a zero
 * dimension yields 0 on that axis instead of dividing by zero.
 */
export function toImagePercent(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): Point {
  const x = rect.width === 0 ? 0 : ((clientX - rect.left) / rect.width) * 100;
  const y = rect.height === 0 ? 0 : ((clientY - rect.top) / rect.height) * 100;
  return { x, y };
}

// Zoom bounds and step, matching the original CanvasArea.vue behavior.
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 5;
const ZOOM_STEP = 0.25;

/**
 * Apply a zoom delta (in ZOOM_STEP multiples, typically +1 / -1) to the current
 * zoom and clamp into [0.5, 5]. Mirrors zoomIn/zoomOut in CanvasArea.vue.
 */
export function clampZoom(current: number, delta: number): number {
  const next = current + delta * ZOOM_STEP;
  return Math.min(Math.max(next, ZOOM_MIN), ZOOM_MAX);
}

/**
 * Compute the drag delta as image-space percentages from a previous to a
 * current pointer position, given the dragged surface's dimensions.
 *
 * NOTE: This is the SINGLE shared drag-delta function. The entity-drag path in
 * EntityOverlay.vue previously divided by width/height with NO zero guard
 * (latent divide-by-zero producing NaN), while the label-drag path DID guard
 * against zero dimensions by bailing out. Unifying both paths here deliberately
 * makes the entity-drag path safe too: a zero dimension yields a 0 delta on
 * that axis instead of NaN/Infinity.
 */
export function dragDeltaPercent(
  curr: Point,
  prev: Point,
  rect: { width: number; height: number },
): { dxPercent: number; dyPercent: number } {
  const dx = curr.x - prev.x;
  const dy = curr.y - prev.y;
  const dxPercent = rect.width === 0 ? 0 : (dx / rect.width) * 100;
  const dyPercent = rect.height === 0 ? 0 : (dy / rect.height) * 100;
  return { dxPercent, dyPercent };
}

/**
 * Serialize polygon points into the "x y,x y,..." string used by SVG <polygon>.
 * Undefined or empty input yields an empty string. From CanvasArea.vue.
 */
export function pointsToSvgString(points?: Point[]): string {
  if (!points) return '';
  return points.map((p) => `${p.x} ${p.y}`).join(',');
}

/**
 * Return a new points array with `p` appended. Immutable: does not mutate the
 * input. Undefined input is treated as an empty list. Mirrors the
 * "[...(points || []), p]" pattern in CanvasArea.vue.
 */
export function appendPoint(points: Point[] | undefined, p: Point): Point[] {
  return [...(points || []), p];
}

/**
 * Return a new points array with the element at `index` removed. Immutable:
 * does not mutate the input. Out-of-range indices are a no-op (returns a copy).
 * Mirrors the splice-on-a-copy pattern in CanvasArea.vue.
 */
export function removePointAt(points: Point[] | undefined, index: number): Point[] {
  const copy = [...(points || [])];
  if (index < 0 || index >= copy.length) return copy;
  copy.splice(index, 1);
  return copy;
}
