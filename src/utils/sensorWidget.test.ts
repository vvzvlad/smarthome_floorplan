import { describe, it, expect } from 'vitest'
import { isSensorActive, isSensorKnown, sensorIconStyle, SENSOR_UNKNOWN_COLOR } from './sensorWidget'

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

describe('sensorIconStyle', () => {
  const colors = { onColor: '#ef4444', offColor: '#22c55e' }

  it('reported field -> on/off colour at full opacity', () => {
    expect(sensorIconStyle({ contact: false }, 'contact', 'false', colors)).toEqual({ color: '#ef4444', opacity: 1 })
    expect(sensorIconStyle({ contact: true }, 'contact', 'false', colors)).toEqual({ color: '#22c55e', opacity: 1 })
  })

  it('no payload or field not reported yet -> unknown colour', () => {
    expect(sensorIconStyle(undefined, 'contact', 'false', colors).color).toBe(SENSOR_UNKNOWN_COLOR)
    expect(sensorIconStyle({ battery: 100 }, 'contact', 'false', colors).color).toBe(SENSOR_UNKNOWN_COLOR)
  })
})

describe('isSensorKnown', () => {
  it('false until the field is reported, true once it is (false is a value too)', () => {
    expect(isSensorKnown(undefined, 'contact')).toBe(false)
    expect(isSensorKnown({ battery: 100 }, 'contact')).toBe(false)
    expect(isSensorKnown({ contact: false }, 'contact')).toBe(true)
  })
})
