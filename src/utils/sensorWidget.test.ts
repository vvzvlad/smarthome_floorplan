import { describe, it, expect } from 'vitest'
import { isSensorActive } from './sensorWidget'

describe('isSensorActive', () => {
  it('boolean field equal to onValue -> true', () => {
    expect(isSensorActive({ contact: false, battery: 100 }, 'contact', 'false')).toBe(true)
  })

  it('boolean field not equal to onValue -> false', () => {
    expect(isSensorActive({ contact: true }, 'contact', 'false')).toBe(false)
  })

  it('nested path is resolved', () => {
    expect(isSensorActive({ state: { door: 'open' } }, 'state.door', 'open')).toBe(true)
  })

  it('no payload yet -> false', () => {
    expect(isSensorActive(undefined, 'contact', 'false')).toBe(false)
  })
})
