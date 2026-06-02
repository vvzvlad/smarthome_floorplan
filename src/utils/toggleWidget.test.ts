import { describe, it, expect } from 'vitest'
import { resolveToggleState } from './toggleWidget'

describe('resolveToggleState', () => {
  it('optimistic true wins over raw value', () => {
    expect(resolveToggleState(true, 'OFF', 'ON')).toBe(true)
  })

  it('optimistic false wins (not treated as undefined)', () => {
    expect(resolveToggleState(false, 'ON', 'ON')).toBe(false)
  })

  it('raw equal to onValue -> true', () => {
    expect(resolveToggleState(undefined, 'ON', 'ON')).toBe(true)
  })

  it('raw equal to offValue -> false', () => {
    expect(resolveToggleState(undefined, 'OFF', 'ON')).toBe(false)
  })

  it('raw undefined -> false', () => {
    expect(resolveToggleState(undefined, undefined, 'ON')).toBe(false)
  })

  it('unrelated raw value -> false', () => {
    expect(resolveToggleState(undefined, 'whatever', 'ON')).toBe(false)
  })
})
