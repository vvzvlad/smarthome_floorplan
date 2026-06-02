import { describe, it, expect } from 'vitest'
import {
  resolveNumberValue,
  roundToStep,
  computeNextStep,
  isAtMin,
  isAtMax,
  formatNumberDisplay,
} from './numberWidget'

describe('resolveNumberValue', () => {
  it('optimistic value wins over topic and min', () => {
    expect(resolveNumberValue(42, '7', 0)).toBe(42)
  })

  it('optimistic 0 wins (not treated as falsy)', () => {
    expect(resolveNumberValue(0, '7', 5)).toBe(0)
  })

  it('parses the topic value when no optimistic value', () => {
    expect(resolveNumberValue(undefined, '7.5', 0)).toBe(7.5)
  })

  it('falls back to min when topic missing', () => {
    expect(resolveNumberValue(undefined, undefined, 3)).toBe(3)
  })

  it('falls back to min when topic is NaN', () => {
    expect(resolveNumberValue(undefined, 'abc', 3)).toBe(3)
  })
})

describe('roundToStep', () => {
  it('0.1 + 0.2 drift -> 0.3 (1 decimal)', () => {
    expect(roundToStep(0.1 + 0.2, 0.1)).toBe(0.3)
  })

  it('0.25 step -> 2 decimals', () => {
    expect(roundToStep(2.50000001, 0.25)).toBe(2.5)
  })

  it('integer step -> 0 decimals', () => {
    expect(roundToStep(2.9999, 1)).toBe(3)
  })

  it('exponential "1e-7" step -> 7 decimals', () => {
    expect(roundToStep(0.12345678, 1e-7)).toBe(0.1234568)
  })

  it('accepts a string step', () => {
    expect(roundToStep(0.30000000000000004, '0.1')).toBe(0.3)
  })
})

describe('computeNextStep', () => {
  const cfg = { min: 0, max: 10, step: 1 }

  it('increments by the step', () => {
    expect(computeNextStep(5, 1, cfg)).toBe(6)
  })

  it('decrements by the step', () => {
    expect(computeNextStep(5, -1, cfg)).toBe(4)
  })

  it('clamps at the upper bound', () => {
    expect(computeNextStep(10, 1, cfg)).toBe(null) // already at max -> no-op
    expect(computeNextStep(9.5, 1, { min: 0, max: 10, step: 1 })).toBe(10)
  })

  it('clamps at the lower bound', () => {
    expect(computeNextStep(0, -1, cfg)).toBe(null) // already at min -> no-op
    expect(computeNextStep(0.5, -1, { min: 0, max: 10, step: 1 })).toBe(0)
  })

  it('normalizes an inverted min/max config', () => {
    // min=10, max=0 should behave like [0,10]
    expect(computeNextStep(5, 1, { min: 10, max: 0, step: 1 })).toBe(6)
    expect(computeNextStep(10, 1, { min: 10, max: 0, step: 1 })).toBe(null)
    expect(computeNextStep(0, -1, { min: 10, max: 0, step: 1 })).toBe(null)
  })

  it('treats zero step as 1', () => {
    expect(computeNextStep(5, 1, { min: 0, max: 10, step: 0 })).toBe(6)
  })

  it('treats negative step as its absolute value', () => {
    expect(computeNextStep(5, 1, { min: 0, max: 10, step: -2 })).toBe(7)
  })

  it('returns null on a no-op (already at bound)', () => {
    expect(computeNextStep(10, 1, cfg)).toBe(null)
  })
})

describe('isAtMin / isAtMax', () => {
  it('at the lower / upper bounds', () => {
    expect(isAtMin(0, 0, 10)).toBe(true)
    expect(isAtMax(10, 0, 10)).toBe(true)
  })

  it('inverted bounds still normalize', () => {
    expect(isAtMin(0, 10, 0)).toBe(true)
    expect(isAtMax(10, 10, 0)).toBe(true)
  })

  it('between bounds -> false', () => {
    expect(isAtMin(5, 0, 10)).toBe(false)
    expect(isAtMax(5, 0, 10)).toBe(false)
  })

  it('beyond bounds still reports at-bound (<=/>=)', () => {
    expect(isAtMin(-1, 0, 10)).toBe(true)
    expect(isAtMax(11, 0, 10)).toBe(true)
  })
})

describe('formatNumberDisplay', () => {
  it('appends the unit with a single space', () => {
    expect(formatNumberDisplay(21, '°C')).toBe('21 °C')
  })

  it('no unit -> just the value', () => {
    expect(formatNumberDisplay(21, '')).toBe('21')
    expect(formatNumberDisplay(21, undefined)).toBe('21')
  })
})
