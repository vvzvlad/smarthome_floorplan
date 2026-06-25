import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { extractJsonPath, formatTextValue, formatRawTopicValue } from './textEntity'

describe('extractJsonPath', () => {
    it('resolves a nested hit "a.b.c"', () => {
        const obj = { a: { b: { c: 42 } } }
        expect(extractJsonPath(obj, 'a.b.c')).toBe(42)
    })

    it('resolves a single key', () => {
        expect(extractJsonPath({ temperature: 21.5 }, 'temperature')).toBe(21.5)
    })

    it('empty path: split("") yields a single "" key -> undefined unless present', () => {
        // path '' splits to [''] which is not a key on the object.
        expect(extractJsonPath({ a: 1 }, '')).toBeUndefined()
        // But an actual empty-string key resolves.
        expect(extractJsonPath({ '': 7 }, '')).toBe(7)
    })

    it('intermediate null short-circuits to undefined', () => {
        expect(extractJsonPath({ a: null }, 'a.b')).toBeUndefined()
    })

    it('intermediate undefined short-circuits to undefined', () => {
        expect(extractJsonPath({ a: undefined } as Record<string, unknown>, 'a.b')).toBeUndefined()
    })

    it('intermediate primitive (number) is not an object -> undefined', () => {
        expect(extractJsonPath({ a: 5 }, 'a.b')).toBeUndefined()
    })

    it('intermediate primitive (string) is not an object -> undefined', () => {
        // typeof acc === 'object' is false for strings, so we stop.
        expect(extractJsonPath({ a: 'hello' }, 'a.length')).toBeUndefined()
    })

    it('prototype key like "toString" is reachable via `in` semantics', () => {
        // The code uses `key in acc`, which includes inherited keys; the value is
        // the inherited function, not a leaf value.
        const r = extractJsonPath({ a: 1 }, 'toString')
        expect(typeof r).toBe('function')
    })

    it('resolves an array index "items.0"', () => {
        const obj = { items: ['first', 'second'] }
        expect(extractJsonPath(obj, 'items.0')).toBe('first')
        expect(extractJsonPath(obj, 'items.1')).toBe('second')
    })
})

describe('formatTextValue', () => {
    it('substitutes the resolved value into "{}"', () => {
        expect(formatTextValue('Temp: {} C', { temperature: 21 }, 'temperature')).toBe('Temp: 21 C')
    })

    it('rawPayload undefined -> placeholder dash', () => {
        expect(formatTextValue('Temp: {} C', undefined, 'temperature')).toBe('Temp: — C')
    })

    it('resolved null -> placeholder dash', () => {
        expect(formatTextValue('{}', { v: null }, 'v')).toBe('—')
    })

    it('resolved missing (undefined) -> placeholder dash', () => {
        expect(formatTextValue('{}', { other: 1 }, 'v')).toBe('—')
    })

    it('resolved 0 must NOT become a dash (!= null check)', () => {
        expect(formatTextValue('{}', { v: 0 }, 'v')).toBe('0')
    })

    it('resolved false must NOT become a dash', () => {
        expect(formatTextValue('{}', { v: false }, 'v')).toBe('false')
    })

    it('resolved empty string must NOT become a dash', () => {
        expect(formatTextValue('[{}]', { v: '' }, 'v')).toBe('[]')
    })

    it('format without "{}" is returned unchanged (replace is a no-op)', () => {
        expect(formatTextValue('static text', { v: 1 }, 'v')).toBe('static text')
        expect(formatTextValue('static text', undefined, 'v')).toBe('static text')
    })
})

describe('formatRawTopicValue', () => {
    it('substitutes a raw string into "{}"', () => {
        expect(formatRawTopicValue('{} °C', '23.9')).toBe('23.9 °C')
    })

    it('undefined (topic not seen yet) -> placeholder dash', () => {
        expect(formatRawTopicValue('{} °C', undefined)).toBe('— °C')
    })

    it('the string "0" is kept (not a dash)', () => {
        expect(formatRawTopicValue('{}', '0')).toBe('0')
    })

    it('empty string is substituted verbatim', () => {
        expect(formatRawTopicValue('[{}]', '')).toBe('[]')
    })

    it('format without "{}" is returned unchanged', () => {
        expect(formatRawTopicValue('static text', '23.9')).toBe('static text')
        expect(formatRawTopicValue('static text', undefined)).toBe('static text')
    })
})

describe('property-based: extractJsonPath', () => {
    it('never throws on arbitrary objects and arbitrary dotted paths', () => {
        fc.assert(
            fc.property(
                fc.object(),
                fc.array(fc.string(), { maxLength: 6 }).map(parts => parts.join('.')),
                (obj, path) => {
                    expect(() => extractJsonPath(obj as Record<string, unknown>, path)).not.toThrow()
                },
            ),
        )
    })

    it('a planted nested leaf is retrievable via its dot-path', () => {
        // Generate path segments that are safe object keys (no dots, non-empty,
        // and not inherited Object.prototype members which `in` would also match).
        const segment = fc
            .string({ minLength: 1, maxLength: 8 })
            .filter(s => !s.includes('.') && !(s in Object.prototype) && s !== '__proto__')
        fc.assert(
            fc.property(
                fc.array(segment, { minLength: 1, maxLength: 5 }),
                fc.anything(),
                (segments, leaf) => {
                    fc.pre(leaf !== undefined)
                    // Build a nested object planting `leaf` at the segment path.
                    const root: Record<string, unknown> = {}
                    let cursor: Record<string, unknown> = root
                    segments.forEach((seg, i) => {
                        if (i === segments.length - 1) {
                            cursor[seg] = leaf
                        } else {
                            const next: Record<string, unknown> = {}
                            cursor[seg] = next
                            cursor = next
                        }
                    })
                    const got = extractJsonPath(root, segments.join('.'))
                    expect(got).toStrictEqual(leaf)
                },
            ),
        )
    })
})
