import { describe, it, expect } from 'vitest'
import {
  filterDevices,
  parseNumberField,
  defaultTextConfig,
  defaultNumberConfig,
  defaultSelectConfig,
} from './entityForm'

describe('filterDevices', () => {
  const list = ['Living Room', 'Kitchen', 'living room lamp']

  it('empty query returns the full list', () => {
    expect(filterDevices(list, '')).toBe(list)
  })

  it('case-insensitive substring match', () => {
    expect(filterDevices(list, 'LIVING')).toEqual(['Living Room', 'living room lamp'])
    expect(filterDevices(list, 'kit')).toEqual(['Kitchen'])
  })

  it('no match returns an empty array', () => {
    expect(filterDevices(list, 'garage')).toEqual([])
  })
})

describe('parseNumberField', () => {
  it('"12.5" -> 12.5', () => {
    expect(parseNumberField('12.5')).toBe(12.5)
  })

  it('"abc" -> null', () => {
    expect(parseNumberField('abc')).toBe(null)
  })

  it('"" -> null', () => {
    expect(parseNumberField('')).toBe(null)
  })

  it('parses a leading number ("12abc" -> 12, matching parseFloat)', () => {
    expect(parseNumberField('12abc')).toBe(12)
  })

  it('parses 0 (not treated as null)', () => {
    expect(parseNumberField('0')).toBe(0)
  })
})

describe('defaultTextConfig', () => {
  it('matches the contract literal', () => {
    expect(defaultTextConfig()).toEqual({ jsonPath: 'temperature', format: '{}', size: 1.8 })
  })
})

describe('defaultNumberConfig', () => {
  it('matches the contract literal', () => {
    expect(defaultNumberConfig()).toEqual({
      readTopic: '',
      writeTopic: '',
      min: 0,
      max: 100,
      step: 1,
      unit: '',
      size: 2.5,
    })
  })
})

describe('defaultSelectConfig', () => {
  it('matches the contract literal', () => {
    expect(defaultSelectConfig()).toEqual({
      readTopic: '',
      writeTopic: '',
      options: [
        { label: 'Off', value: 'OFF' },
        { label: 'Heat', value: 'heat' },
        { label: 'Cool', value: 'cool' },
      ],
      size: 2.5,
    })
  })
})
