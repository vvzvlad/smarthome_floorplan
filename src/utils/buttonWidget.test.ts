import { describe, it, expect } from 'vitest'
import { formatButtonLabel } from './buttonWidget'

describe('formatButtonLabel', () => {
  it('returns the text when non-empty', () => {
    expect(formatButtonLabel('Go', 'Fallback')).toBe('Go')
  })

  it('trims surrounding whitespace from the text', () => {
    expect(formatButtonLabel('  Go  ', 'Fallback')).toBe('Go')
  })

  it('falls back when the text is empty', () => {
    expect(formatButtonLabel('', 'Fallback')).toBe('Fallback')
  })

  it('falls back when the text is whitespace only', () => {
    expect(formatButtonLabel('   ', 'Fallback')).toBe('Fallback')
  })

  it('falls back when the text is undefined', () => {
    expect(formatButtonLabel(undefined, 'Fallback')).toBe('Fallback')
  })
})
