import { describe, it, expect } from 'vitest'
import { normalizeEntityState } from './entityState'

describe('normalizeEntityState', () => {
  it("'ON' -> 'on'", () => {
    expect(normalizeEntityState({ state: 'ON' })).toBe('on')
  })

  it("'on' (lowercase) -> 'on'", () => {
    expect(normalizeEntityState({ state: 'on' })).toBe('on')
  })

  it("'OFF' -> 'off'", () => {
    expect(normalizeEntityState({ state: 'OFF' })).toBe('off')
  })

  it('undefined state -> off', () => {
    expect(normalizeEntityState({})).toBe('off')
    expect(normalizeEntityState({ state: undefined })).toBe('off')
  })

  it('numeric state -> off', () => {
    expect(normalizeEntityState({ state: 1 })).toBe('off')
  })

  it('non-string (object/null/bool) state -> off', () => {
    expect(normalizeEntityState({ state: null })).toBe('off')
    expect(normalizeEntityState({ state: true })).toBe('off')
    expect(normalizeEntityState({ state: {} })).toBe('off')
  })

  it('arbitrary string -> off', () => {
    expect(normalizeEntityState({ state: 'unavailable' })).toBe('off')
  })
})
