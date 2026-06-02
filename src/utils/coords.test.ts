import { describe, it, expect } from 'vitest'
import {
  toImagePercent,
  clampZoom,
  dragDeltaPercent,
  pointsToSvgString,
  appendPoint,
  removePointAt,
} from './coords'

describe('toImagePercent', () => {
  const rect = { left: 100, top: 50, width: 200, height: 400 }

  it('center of the rect -> 50/50', () => {
    expect(toImagePercent(100 + 100, 50 + 200, rect)).toEqual({ x: 50, y: 50 })
  })

  it('top-left origin -> 0/0', () => {
    expect(toImagePercent(100, 50, rect)).toEqual({ x: 0, y: 0 })
  })

  it('bottom-right corner -> 100/100', () => {
    expect(toImagePercent(300, 450, rect)).toEqual({ x: 100, y: 100 })
  })

  it('zero width yields 0 on x (no NaN/Infinity)', () => {
    const r = toImagePercent(10, 50 + 200, { left: 0, top: 50, width: 0, height: 400 })
    expect(r.x).toBe(0)
    expect(Number.isFinite(r.x)).toBe(true)
    expect(r.y).toBe(50)
  })

  it('zero height yields 0 on y (no NaN/Infinity)', () => {
    const r = toImagePercent(100 + 100, 10, { left: 100, top: 0, width: 200, height: 0 })
    expect(r.y).toBe(0)
    expect(Number.isFinite(r.y)).toBe(true)
    expect(r.x).toBe(50)
  })
})

describe('clampZoom', () => {
  it('normal step up (+1 => +0.25)', () => {
    expect(clampZoom(1, 1)).toBe(1.25)
  })

  it('normal step down (-1 => -0.25)', () => {
    expect(clampZoom(1, -1)).toBe(0.75)
  })

  it('caps at the upper bound 5', () => {
    expect(clampZoom(5, 1)).toBe(5)
    expect(clampZoom(4.9, 1)).toBe(5)
  })

  it('floors at the lower bound 0.5', () => {
    expect(clampZoom(0.5, -1)).toBe(0.5)
    expect(clampZoom(0.6, -1)).toBe(0.5)
  })
})

describe('dragDeltaPercent', () => {
  it('positive delta on both axes', () => {
    const r = dragDeltaPercent({ x: 60, y: 40 }, { x: 10, y: 20 }, { width: 200, height: 100 })
    expect(r.dxPercent).toBe(25)
    expect(r.dyPercent).toBe(20)
  })

  it('negative delta', () => {
    const r = dragDeltaPercent({ x: 0, y: 0 }, { x: 50, y: 25 }, { width: 100, height: 50 })
    expect(r.dxPercent).toBe(-50)
    expect(r.dyPercent).toBe(-50)
  })

  it('zero-dimension guard yields 0 delta, never NaN/Infinity', () => {
    const r = dragDeltaPercent({ x: 50, y: 50 }, { x: 0, y: 0 }, { width: 0, height: 0 })
    expect(r.dxPercent).toBe(0)
    expect(r.dyPercent).toBe(0)
    expect(Number.isFinite(r.dxPercent)).toBe(true)
    expect(Number.isFinite(r.dyPercent)).toBe(true)
  })

  it('accumulates correctly across successive moves', () => {
    const rect = { width: 100, height: 100 }
    let x = 0
    const s1 = dragDeltaPercent({ x: 10, y: 0 }, { x: 0, y: 0 }, rect)
    x += s1.dxPercent
    const s2 = dragDeltaPercent({ x: 30, y: 0 }, { x: 10, y: 0 }, rect)
    x += s2.dxPercent
    // total moved 30px over a 100px-wide surface -> 30%
    expect(x).toBe(30)
  })
})

describe('pointsToSvgString', () => {
  it('undefined -> empty string', () => {
    expect(pointsToSvgString(undefined)).toBe('')
  })

  it('empty array -> empty string', () => {
    expect(pointsToSvgString([])).toBe('')
  })

  it('multiple points -> "x y,x y"', () => {
    expect(pointsToSvgString([{ x: 1, y: 2 }, { x: 3, y: 4 }])).toBe('1 2,3 4')
  })
})

describe('appendPoint', () => {
  it('appends to an existing list immutably', () => {
    const pts = [{ x: 1, y: 1 }]
    const out = appendPoint(pts, { x: 2, y: 2 })
    expect(out).toEqual([{ x: 1, y: 1 }, { x: 2, y: 2 }])
    expect(pts).toEqual([{ x: 1, y: 1 }]) // input not mutated
  })

  it('treats undefined input as empty', () => {
    expect(appendPoint(undefined, { x: 5, y: 6 })).toEqual([{ x: 5, y: 6 }])
  })
})

describe('removePointAt', () => {
  it('removes a middle element immutably', () => {
    const pts = [{ x: 0, y: 0 }, { x: 1, y: 1 }, { x: 2, y: 2 }]
    const out = removePointAt(pts, 1)
    expect(out).toEqual([{ x: 0, y: 0 }, { x: 2, y: 2 }])
    expect(pts).toHaveLength(3) // input not mutated
  })

  it('out-of-range index is a no-op (returns a copy)', () => {
    const pts = [{ x: 0, y: 0 }]
    expect(removePointAt(pts, 5)).toEqual([{ x: 0, y: 0 }])
    expect(removePointAt(pts, -1)).toEqual([{ x: 0, y: 0 }])
  })

  it('undefined input -> empty array', () => {
    expect(removePointAt(undefined, 0)).toEqual([])
  })
})
