import { describe, it, expect } from 'vitest'
import { chartRequestParams, chartRange, chartPolylinePoints, formatChartValue, CHART_WINDOW_S } from './chartWidget'
import type { ChartConfig } from '../types/floorplan'

function cfg(overrides: Partial<ChartConfig> = {}): ChartConfig {
  return { source: 'state', jsonPath: 'temperature', readTopic: '', format: '{}', width: 15, ...overrides }
}

describe('chartRequestParams', () => {
  it('device state -> device + path', () => {
    expect(chartRequestParams(cfg(), 'out-in-temp')).toEqual({ device: 'out-in-temp', path: 'temperature' })
  })

  it('raw topic -> topic only', () => {
    expect(chartRequestParams(cfg({ source: 'topic', readTopic: 'home/kiln/temp' }), 'out-in-temp'))
      .toEqual({ topic: 'home/kiln/temp' })
  })

  it('incomplete config -> null', () => {
    expect(chartRequestParams(undefined, 'dev')).toBeNull()
    expect(chartRequestParams(cfg(), '')).toBeNull()
    expect(chartRequestParams(cfg({ jsonPath: '' }), 'dev')).toBeNull()
    expect(chartRequestParams(cfg({ source: 'topic' }), 'dev')).toBeNull()
  })
})

describe('chartRange', () => {
  it('no points -> null', () => {
    expect(chartRange([])).toBeNull()
  })

  it('lowest and highest value', () => {
    expect(chartRange([[1, 5], [2, -3], [3, 12]])).toEqual({ min: -3, max: 12 })
  })
})

describe('chartPolylinePoints', () => {
  const now = 2 * CHART_WINDOW_S

  it('maps now-24h..now onto x 0..100 and the value range onto y 36..4 (padded from the edges)', () => {
    const points: [number, number][] = [[now - CHART_WINDOW_S, 10], [now - CHART_WINDOW_S / 2, 15], [now, 20]]
    expect(chartPolylinePoints(points, now)).toBe('0,36 50,20 100,4')
  })

  it('flat series runs across the middle', () => {
    expect(chartPolylinePoints([[now - CHART_WINDOW_S, 7], [now, 7]], now)).toBe('0,20 100,20')
  })

  it('no points -> empty string', () => {
    expect(chartPolylinePoints([], now)).toBe('')
  })
})

describe('formatChartValue', () => {
  it('rounds to one decimal and fills the placeholder', () => {
    expect(formatChartValue('{}°C', 21.46)).toBe('21.5°C')
    expect(formatChartValue('{}', 20)).toBe('20')
  })
})
