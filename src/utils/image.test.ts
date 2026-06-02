import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { computeCoverFit, imageDownloadFilename } from './image'

// Only computeCoverFit is exercised here. The canvas-based resizeImageToPng is
// intentionally out of scope (Canvas is non-deterministic / unavailable in jsdom).
describe('computeCoverFit', () => {
    it('landscape image (w > h): scales to fill, crops horizontally', () => {
        const { scale, w, h, dx, dy } = computeCoverFit(200, 100, 180)
        // Shorter side (height) must fill -> scale = size/imgH = 1.8
        expect(scale).toBe(180 / 100)
        expect(h).toBe(180)
        expect(w).toBe(200 * 1.8)
        // Cover invariant
        expect(w).toBeGreaterThanOrEqual(180)
        expect(h).toBeGreaterThanOrEqual(180)
        // Overflow centered -> non-positive offsets
        expect(dx).toBeLessThanOrEqual(0)
        expect(dy).toBeLessThanOrEqual(0)
        expect(dy).toBe(0)
    })

    it('portrait image (h > w): scales to fill, crops vertically', () => {
        const { scale, w, h, dx, dy } = computeCoverFit(100, 200, 180)
        expect(scale).toBe(180 / 100)
        expect(w).toBe(180)
        expect(h).toBe(200 * 1.8)
        expect(w).toBeGreaterThanOrEqual(180)
        expect(h).toBeGreaterThanOrEqual(180)
        expect(dx).toBeLessThanOrEqual(0)
        expect(dy).toBeLessThanOrEqual(0)
        expect(dx).toBe(0)
    })

    it('square image: exact fit, no crop, no offset', () => {
        const { scale, w, h, dx, dy } = computeCoverFit(100, 100, 180)
        expect(scale).toBe(1.8)
        expect(w).toBe(180)
        expect(h).toBe(180)
        expect(dx).toBe(0)
        expect(dy).toBe(0)
    })

    it('upscales when the image is smaller than the target', () => {
        const { scale, w, h } = computeCoverFit(50, 50, 180)
        expect(scale).toBe(180 / 50)
        expect(w).toBeGreaterThanOrEqual(180)
        expect(h).toBeGreaterThanOrEqual(180)
    })

    it('degenerate img.width === 0 produces no NaN/Infinity', () => {
        const r = computeCoverFit(0, 100, 180)
        for (const v of Object.values(r)) {
            expect(Number.isFinite(v)).toBe(true)
        }
        expect(r.w).toBe(0)
        expect(r.h).toBe(0)
    })

    it('degenerate img.height === 0 produces no NaN/Infinity', () => {
        const r = computeCoverFit(100, 0, 180)
        for (const v of Object.values(r)) {
            expect(Number.isFinite(v)).toBe(true)
        }
    })

    // Property: for any positive dimensions, cover fit fully covers the square
    // and the centering offsets are never positive.
    it('property: w >= size && h >= size and offsets <= 0 for positive dims', () => {
        fc.assert(
            fc.property(
                fc.integer({ min: 1, max: 10000 }),
                fc.integer({ min: 1, max: 10000 }),
                fc.integer({ min: 1, max: 4096 }),
                (imgW, imgH, size) => {
                    const { w, h, dx, dy } = computeCoverFit(imgW, imgH, size)
                    expect(w).toBeGreaterThanOrEqual(size - 1e-6)
                    expect(h).toBeGreaterThanOrEqual(size - 1e-6)
                    expect(dx).toBeLessThanOrEqual(1e-6)
                    expect(dy).toBeLessThanOrEqual(1e-6)
                },
            ),
        )
    })
})

describe('imageDownloadFilename', () => {
    it('returns null for an empty string (nothing to download)', () => {
        expect(imageDownloadFilename('', 'Test')).toBeNull()
    })

    it('returns null for a non-Data-URI string', () => {
        expect(imageDownloadFilename('not-a-data-uri', 'Test')).toBeNull()
    })

    it('infers .jpg from an image/jpeg Data URI', () => {
        expect(imageDownloadFilename('data:image/jpeg;base64,xxx', 'Test')).toBe('Test.jpg')
    })

    it('infers .png from an image/png Data URI', () => {
        expect(imageDownloadFilename('data:image/png;base64,xxx', 'Test')).toBe('Test.png')
    })

    it('falls back to .png for an unknown MIME type', () => {
        expect(imageDownloadFilename('data:image/tiff;base64,xxx', 'Test')).toBe('Test.png')
    })

    it('falls back to .png when the Data URI carries no MIME type', () => {
        expect(imageDownloadFilename('data:;base64,xxx', 'Test')).toBe('Test.png')
    })

    it('sanitizes spaces and special chars in the base name', () => {
        expect(imageDownloadFilename('data:image/png;base64,xxx', 'New Floorplan')).toBe('New_Floorplan.png')
    })

    it('preserves Unicode (Cyrillic) letters in the base name', () => {
        expect(imageDownloadFilename('data:image/png;base64,AAA', 'Мой план')).toBe('Мой_план.png')
    })

    it('falls back to "floorplan" when the base name sanitizes to empty', () => {
        expect(imageDownloadFilename('data:image/png;base64,xxx', '!!!')).toBe('floorplan.png')
    })

    it('falls back to "floorplan" when the base name is empty', () => {
        expect(imageDownloadFilename('data:image/png;base64,xxx', '')).toBe('floorplan.png')
    })
})
