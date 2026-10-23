import { describe, it, expect } from 'vitest'
import { isSensorActive, isSensorKnown, sensorIconStyle, sensorCaption, SENSOR_UNKNOWN_COLOR } from './sensorWidget'

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

describe('sensorCaption', () => {
  const cfg = { jsonPath: 'contact', onValue: 'false', size: 2.1, icon: '', onText: 'open', offText: 'closed' }

  it('label and the word of the current state', () => {
    expect(sensorCaption('Window', { contact: true }, cfg)).toBe('Window: closed')
    expect(sensorCaption('Window', { contact: false }, cfg)).toBe('Window: open')
  })

  it('em dash until the field is reported; the word alone without a label', () => {
    expect(sensorCaption('Window', { battery: 100 }, cfg)).toBe('Window: —')
    expect(sensorCaption('', { contact: true }, cfg)).toBe('closed')
  })

  it('no caption when both words are empty or absent (config saved before captions)', () => {
    expect(sensorCaption('Window', { contact: true }, { ...cfg, onText: '', offText: '' })).toBe('')
    expect(sensorCaption('Window', { contact: true }, { jsonPath: 'contact', onValue: 'false', size: 2.1, icon: '' } as never)).toBe('')
  })
})
