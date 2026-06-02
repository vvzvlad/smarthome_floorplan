import { describe, it, expect, vi, afterEach } from 'vitest'
import { sanitizeFilenameBase, triggerDownload } from './download'

describe('sanitizeFilenameBase', () => {
    it('falls back to "floorplan" for an empty string', () => {
        expect(sanitizeFilenameBase('')).toBe('floorplan')
    })

    it('falls back to "floorplan" for a whitespace-only string', () => {
        expect(sanitizeFilenameBase('   ')).toBe('floorplan')
    })

    it('replaces spaces with underscores', () => {
        expect(sanitizeFilenameBase('New Floorplan')).toBe('New_Floorplan')
    })

    it('falls back to "floorplan" for a symbols-only string', () => {
        expect(sanitizeFilenameBase('!!!')).toBe('floorplan')
    })

    it('preserves hyphens and underscores', () => {
        expect(sanitizeFilenameBase('a-b_c')).toBe('a-b_c')
    })

    it('preserves Unicode (Cyrillic) letters', () => {
        expect(sanitizeFilenameBase('Мой план')).toBe('Мой_план')
    })

    it('collapses path-unsafe characters into underscores', () => {
        expect(sanitizeFilenameBase('a/b\\c.png')).toBe('a_b_c_png')
    })

    it('trims leading/trailing separators', () => {
        expect(sanitizeFilenameBase('..name..')).toBe('name')
    })
})

describe('triggerDownload', () => {
    afterEach(() => vi.restoreAllMocks())

    it('clicks a transient anchor once and removes it afterwards', () => {
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

        triggerDownload('blob:x', 'f.json')

        expect(clickSpy).toHaveBeenCalledTimes(1)
        // The function calls a.remove(), so no leftover anchor should linger.
        const leftover = Array.from(document.body.querySelectorAll('a')).find(
            (a) => a.getAttribute('download') === 'f.json',
        )
        expect(leftover).toBeUndefined()
    })
})
