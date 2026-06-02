import { describe, it, expect } from 'vitest'
import { resolveSelectValue } from './selectWidget'

describe('resolveSelectValue', () => {
  it('optimistic wins over raw value', () => {
    expect(resolveSelectValue('heat', 'cool')).toBe('heat')
  })

  it('optimistic empty-string wins (not treated as undefined)', () => {
    // An empty-string option value is legitimate and must win over the raw
    // topic value (precedence is decided with !== undefined, not truthiness).
    expect(resolveSelectValue('', 'cool')).toBe('')
  })

  it('raw used when optimistic is undefined', () => {
    expect(resolveSelectValue(undefined, 'cool')).toBe('cool')
  })

  it('both undefined -> undefined', () => {
    expect(resolveSelectValue(undefined, undefined)).toBeUndefined()
  })
})
