import { describe, it, expect } from 'vitest'
import fc from 'fast-check'
import { migrateConfig, needsMigration, normalizeImportedConfig } from './configMigration'

// Helpers to build minimal entity-shaped objects for the migration logic.
// We only populate the fields the migration code inspects (style.*).
function entityWith(style: any) {
    return { id: 'e1', entityId: 'x', label: 'l', type: 'light', x: 0, y: 0, shape: 'circle', style }
}

describe('needsMigration — branch matrix', () => {
    it('entities missing -> false', () => {
        expect(needsMigration({})).toBe(false)
    })

    it('entities not an array -> false', () => {
        expect(needsMigration({ entities: 'nope' })).toBe(false)
        expect(needsMigration({ entities: { 0: 'x' } })).toBe(false)
    })

    it('empty array -> false', () => {
        expect(needsMigration({ entities: [] })).toBe(false)
    })

    it('entity with no style -> false', () => {
        expect(needsMigration({ entities: [{ id: 'e' }] })).toBe(false)
    })

    it('old onColor only, no colors -> true', () => {
        expect(needsMigration({ entities: [entityWith({ onColor: '#fff' })] })).toBe(true)
    })

    it('old offColor only, no colors -> true', () => {
        expect(needsMigration({ entities: [entityWith({ offColor: '#000' })] })).toBe(true)
    })

    it('both old AND new colors present -> false', () => {
        expect(
            needsMigration({ entities: [entityWith({ onColor: '#fff', colors: { onColor: '#fff', offColor: '#000' } })] }),
        ).toBe(false)
    })

    it('only new colors -> false', () => {
        expect(needsMigration({ entities: [entityWith({ colors: { onColor: '#fff', offColor: '#000' } })] })).toBe(false)
    })

    it('mixed array (one stale, one clean) -> true', () => {
        const config = {
            entities: [
                entityWith({ colors: { onColor: '#fff', offColor: '#000' } }),
                entityWith({ onColor: '#abc' }),
            ],
        }
        expect(needsMigration(config)).toBe(true)
    })
})

describe('migrateConfig / migrateEntityColors', () => {
    it('entities missing -> returned unchanged', () => {
        const cfg = { name: 'x' }
        expect(migrateConfig(cfg as any)).toBe(cfg as any)
    })

    it('entities not an array -> returned unchanged', () => {
        const cfg = { entities: 'nope' }
        expect(migrateConfig(cfg as any)).toBe(cfg as any)
    })

    it('entity already has style.colors -> untouched', () => {
        const colors = { onColor: '#111', offColor: '#222' }
        const cfg = { entities: [entityWith({ colors, onColor: '#999' })] }
        migrateConfig(cfg as any)
        // The existing colors object is preserved verbatim and old keys are NOT
        // removed because the function returns early on the colors guard.
        expect(cfg.entities[0].style.colors).toBe(colors)
        expect(cfg.entities[0].style.onColor).toBe('#999')
    })

    it('entity with no style -> untouched', () => {
        const cfg = { entities: [{ id: 'e' }] as any[] }
        migrateConfig(cfg as any)
        expect(cfg.entities[0]).toEqual({ id: 'e' })
    })

    it('onColor only -> colors.onColor set, offColor defaults to #94a3b8, old keys deleted', () => {
        const cfg = { entities: [entityWith({ onColor: '#abcdef' })] }
        migrateConfig(cfg as any)
        const style = cfg.entities[0].style
        expect(style.colors).toEqual({ onColor: '#abcdef', offColor: '#94a3b8' })
        expect('onColor' in style).toBe(false)
        expect('offColor' in style).toBe(false)
    })

    it('offColor only -> onColor defaults to #facc15', () => {
        const cfg = { entities: [entityWith({ offColor: '#123456' })] }
        migrateConfig(cfg as any)
        const style = cfg.entities[0].style
        expect(style.colors).toEqual({ onColor: '#facc15', offColor: '#123456' })
        expect('onColor' in style).toBe(false)
        expect('offColor' in style).toBe(false)
    })

    it('both old colors -> both preserved, old keys gone', () => {
        const cfg = { entities: [entityWith({ onColor: '#aaa', offColor: '#bbb' })] }
        migrateConfig(cfg as any)
        const style = cfg.entities[0].style
        expect(style.colors).toEqual({ onColor: '#aaa', offColor: '#bbb' })
        expect('onColor' in style).toBe(false)
        expect('offColor' in style).toBe(false)
    })

    it('style with neither old color -> no colors added', () => {
        const cfg = { entities: [entityWith({ width: 5 })] }
        migrateConfig(cfg as any)
        expect(cfg.entities[0].style.colors).toBeUndefined()
    })

    it('mixed config -> only the stale entity is migrated', () => {
        const cleanColors = { onColor: '#fff', offColor: '#000' }
        const cfg = {
            entities: [
                entityWith({ colors: cleanColors }),
                entityWith({ onColor: '#abc' }),
            ],
        }
        migrateConfig(cfg as any)
        expect(cfg.entities[0].style.colors).toBe(cleanColors)
        expect(cfg.entities[1].style.colors).toEqual({ onColor: '#abc', offColor: '#94a3b8' })
        expect('onColor' in cfg.entities[1].style).toBe(false)
    })

    it('mutates input in place (returns the same reference)', () => {
        const cfg = { entities: [entityWith({ onColor: '#abc' })] }
        const result = migrateConfig(cfg as any)
        // Documented behavior: same object, mutated in place.
        expect(result).toBe(cfg as any)
        expect((result.entities as any)[0].style.colors).toBeDefined()
    })
})

describe('normalizeImportedConfig', () => {
    it('throws for non-object inputs', () => {
        expect(() => normalizeImportedConfig(null)).toThrow()
        expect(() => normalizeImportedConfig(42)).toThrow()
        expect(() => normalizeImportedConfig('x')).toThrow()
        expect(() => normalizeImportedConfig([])).toThrow()
    })

    it('throws when entities is missing or not an array', () => {
        expect(() => normalizeImportedConfig({ name: 'x' })).toThrow()
        expect(() => normalizeImportedConfig({ entities: 'nope' })).toThrow()
    })

    it('throws when an entity is not an object', () => {
        expect(() => normalizeImportedConfig({ entities: [null] })).toThrow()
        expect(() => normalizeImportedConfig({ entities: ['x'] })).toThrow()
    })

    it('throws when an entity is missing required string fields (id/entityId/type)', () => {
        expect(() => normalizeImportedConfig({ id: 'a', name: 'N', imageBase64: '', entities: [{ foo: 1 }] })).toThrow()
        // Has id but is missing entityId/type.
        expect(() => normalizeImportedConfig({ id: 'a', name: 'N', imageBase64: '', entities: [{ id: 'x' }] })).toThrow()
    })

    it('passes a valid minimal config through', () => {
        const cfg = { id: 'a', name: 'N', imageBase64: '', entities: [] }
        const result = normalizeImportedConfig(cfg)
        expect(result).toEqual({ id: 'a', name: 'N', imageBase64: '', entities: [] })
    })

    it('strips whitespace from imageBase64', () => {
        const result = normalizeImportedConfig({
            id: 'a', name: 'N', imageBase64: 'data:image/png;base64,AA\nAA ', entities: [],
        })
        expect(result.imageBase64).toBe('data:image/png;base64,AAAA')
    })

    it('fills default name when missing', () => {
        const result = normalizeImportedConfig({ id: 'a', imageBase64: '', entities: [] })
        expect(result.name).toBe('Imported Floorplan')
    })

    it('fills a non-empty id when missing or empty', () => {
        const missing = normalizeImportedConfig({ name: 'N', imageBase64: '', entities: [] })
        expect(typeof missing.id).toBe('string')
        expect(missing.id).toBeTruthy()

        const empty = normalizeImportedConfig({ id: '', name: 'N', imageBase64: '', entities: [] })
        expect(typeof empty.id).toBe('string')
        expect(empty.id).toBeTruthy()
    })

    it('runs color migration on imported entities', () => {
        const result = normalizeImportedConfig({
            id: 'a',
            name: 'N',
            imageBase64: '',
            entities: [
                { id: 'e1', entityId: 'x', label: 'l', type: 'light', x: 0, y: 0, shape: 'circle', style: { onColor: '#abcdef' } },
            ],
        })
        const style = (result.entities[0] as any).style
        expect(style.colors).toEqual({ onColor: '#abcdef', offColor: '#94a3b8' })
        expect('onColor' in style).toBe(false)
        expect('offColor' in style).toBe(false)
    })
})

describe('property-based: migrateConfig idempotence', () => {
    // Arbitrary that generates configs with a realistic mix of stale/clean/no-style
    // entities so the migration branches all get exercised.
    // A plausible truthy color string. The migration only cares about truthiness,
    // so a small fixed palette is enough to exercise every branch.
    const colorArb = fc.constantFrom('#facc15', '#94a3b8', '#abcdef', '#000000', '#ffffff')
    const styleArb = fc.oneof(
        // Stale: old top-level colors, no `colors`. At least one of on/off present
        // so this branch actually triggers migration.
        fc.record({ onColor: colorArb }),
        fc.record({ offColor: colorArb }),
        fc.record({ onColor: colorArb, offColor: colorArb }),
        // Already migrated.
        fc.record({ colors: fc.record({ onColor: colorArb, offColor: colorArb }) }),
        // Neither.
        fc.record({ width: fc.integer() }),
    )
    const entityArb = fc.oneof(
        fc.record({ id: fc.string(), style: styleArb }),
        // Entity without a style object at all.
        fc.record({ id: fc.string() }),
    )
    const configArb = fc.oneof(
        fc.record({ entities: fc.array(entityArb, { maxLength: 6 }) }),
        // Degenerate shapes the migration must pass through untouched.
        fc.record({ name: fc.string() }),
        fc.record({ entities: fc.string() }),
    )

    it('migrateConfig(migrateConfig(x)) deep-equals migrateConfig(x)', () => {
        fc.assert(
            fc.property(configArb, (raw) => {
                // Clone so each pass starts from an independent object (migrate mutates).
                const once = migrateConfig(structuredClone(raw) as any)
                const onceSnapshot = structuredClone(once)
                const twice = migrateConfig(once as any)
                expect(twice).toStrictEqual(onceSnapshot)
            }),
        )
    })

    it('needsMigration(migrateConfig(x)) === false', () => {
        fc.assert(
            fc.property(configArb, (raw) => {
                const migrated = migrateConfig(structuredClone(raw) as any)
                expect(needsMigration(migrated)).toBe(false)
            }),
        )
    })
})
