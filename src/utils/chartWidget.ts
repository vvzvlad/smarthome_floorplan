// Pure logic for the chart widget (a line of one value over the last 24 hours,
// read from InfluxDB through /api/chart), used by ChartWidget.vue.

import type { ChartConfig } from '../types/floorplan';

/** One history point as /api/chart returns it: [epoch seconds, value]. */
export type ChartPoint = [number, number];

/** Time span the chart covers, in seconds. */
export const CHART_WINDOW_S = 24 * 60 * 60;

/** SVG viewBox of the line: x 0..100 (time), y 0..CHART_VIEW_H (value), stretched onto the plot box above the time labels. */
export const CHART_VIEW_W = 100;
export const CHART_VIEW_H = 40;
/** Empty band above the highest and below the lowest value, so the stroke is not clipped by the box edge. */
export const CHART_PAD = 4;

/**
 * Query parameters of /api/chart for a widget: `device` + `path` for a field of
 * the z2m device state, `topic` for a raw MQTT topic. null while the config
 * lacks what its source needs (no request is made).
 */
export function chartRequestParams(config: ChartConfig | undefined, entityId: string): Record<string, string> | null {
  if (!config) return null;
  if (config.source === 'topic') return config.readTopic ? { topic: config.readTopic } : null;
  return entityId && config.jsonPath ? { device: entityId, path: config.jsonPath } : null;
}

/** Lowest and highest value of the points; null when there are none. */
export function chartRange(points: ChartPoint[]): { min: number; max: number } | null {
  if (points.length === 0) return null;
  let min = Infinity;
  let max = -Infinity;
  for (const [, value] of points) {
    if (value < min) min = value;
    if (value > max) max = value;
  }
  return { min, max };
}

const round2 = (n: number) => Math.round(n * 100) / 100;

/**
 * The `points` attribute of the SVG polyline: x maps time from nowS - 24 h to
 * nowS onto 0..CHART_VIEW_W, y maps the value range onto CHART_VIEW_H - CHART_PAD
 * .. CHART_PAD (the highest value at the top). A flat series is padded by 1 on both sides, so its
 * line runs across the middle. No points -> ''.
 */
export function chartPolylinePoints(points: ChartPoint[], nowS: number): string {
  const range = chartRange(points);
  if (!range) return '';
  const lo = range.min === range.max ? range.min - 1 : range.min;
  const hi = range.min === range.max ? range.max + 1 : range.max;
  const start = nowS - CHART_WINDOW_S;
  return points
    .map(([t, value]) => {
      const x = ((t - start) / CHART_WINDOW_S) * CHART_VIEW_W;
      const y = CHART_VIEW_H - CHART_PAD - ((value - lo) / (hi - lo)) * (CHART_VIEW_H - 2 * CHART_PAD);
      return `${round2(x)},${round2(y)}`;
    })
    .join(' ');
}

/**
 * Ticks of the time axis: every whole local hour divisible by `stepH` within
 * the last 24 hours before nowS, oldest first, with x on 0..CHART_VIEW_W and
 * the "HH:00" label in the viewer's local time.
 */
export function chartTimeTicks(nowS: number, stepH = 6): { x: number; label: string }[] {
  const start = nowS - CHART_WINDOW_S;
  const d = new Date(nowS * 1000);
  d.setHours(d.getHours() - (d.getHours() % stepH), 0, 0, 0);
  const ticks: { x: number; label: string }[] = [];
  while (d.getTime() / 1000 > start) {
    const x = ((d.getTime() / 1000 - start) / CHART_WINDOW_S) * CHART_VIEW_W;
    ticks.unshift({ x: round2(x), label: `${String(d.getHours()).padStart(2, '0')}:00` });
    d.setHours(d.getHours() - stepH);
  }
  return ticks;
}

/** A min/max label: the value rounded to one decimal put into the format's "{}". */
export function formatChartValue(format: string, value: number): string {
  return format.replace('{}', String(Math.round(value * 10) / 10));
}
