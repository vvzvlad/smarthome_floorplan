import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { nextTick } from 'vue'

// --- Module mocks (must be declared before importing the store) ---

// Mock the api module so saveConfig/sendCommand/publishRaw are spies.
vi.mock('../utils/api', () => ({
    saveConfig: vi.fn().mockResolvedValue(undefined),
    sendCommand: vi.fn().mockResolvedValue(undefined),
    publishRaw: vi.fn().mockResolvedValue(undefined),
}))

// Mock uuid for determinism. A counter keeps generated ids unique where needed.
let uuidCounter = 0
vi.mock('uuid', () => ({
    v4: () => `fixed-uuid-${uuidCounter++}`,
}))

import { useFloorplanStore } from './floorplan'
import * as api from '../utils/api'
import type { FloorplanConfig, EntityConfig } from '../types/floorplan'

const saveConfigMock = vi.mocked(api.saveConfig)
const sendCommandMock = vi.mocked(api.sendCommand)
const publishRawMock = vi.mocked(api.publishRaw)

beforeEach(() => {
    setActivePinia(createPinia())
    vi.useFakeTimers()
    uuidCounter = 0
    saveConfigMock.mockClear()
    sendCommandMock.mockClear()
    publishRawMock.mockClear()
    saveConfigMock.mockResolvedValue(undefined)
    sendCommandMock.mockResolvedValue(undefined)
    publishRawMock.mockResolvedValue(undefined)
})

afterEach(() => {
    vi.useRealTimers()
})

// Build a number entity wired to a read topic.
function numberEntity(overrides: Partial<EntityConfig> = {}): EntityConfig {
    return {
        id: 'n1',
        entityId: 'number.thermostat',
        label: 'Thermostat',
        type: 'number',
        x: 10,
        y: 10,
        shape: 'circle',
        style: {
            width: 5,
            height: 5,
            colors: { onColor: '#facc15', offColor: '#94a3b8' },
            onOpacity: 0.8,
            offOpacity: 0.3,
            gradientRadius: 30,
            rotation: 0,
        },
        labelConfig: { show: true, offsetX: 0, offsetY: 10, color: '#fff' },
        numberConfig: { readTopic: 'z/temp', writeTopic: 'z/temp/set', min: 0, max: 100, step: 1, unit: '', size: 2.5 },
        ...overrides,
    }
}

// Build a toggle entity wired to a read/write topic.
function toggleEntity(overrides: Partial<EntityConfig> = {}): EntityConfig {
    return {
        id: 't1',
        entityId: 'toggle.lamp',
        label: 'Lamp',
        type: 'toggle',
        x: 10,
        y: 10,
        shape: 'circle',
        style: {
            width: 5,
            height: 5,
            colors: { onColor: '#facc15', offColor: '#94a3b8' },
            onOpacity: 0.8,
            offOpacity: 0.3,
            gradientRadius: 30,
            rotation: 0,
        },
        labelConfig: { show: true, offsetX: 0, offsetY: 10, color: '#fff' },
        toggleConfig: { readTopic: 'z/lamp/state', writeTopic: 'z/lamp/set', onValue: 'ON', offValue: 'OFF', size: 2.5 },
        ...overrides,
    }
}

function makeConfig(entities: EntityConfig[]): FloorplanConfig {
    return { id: 'cfg', name: 'Test', imageBase64: '', entities }
}

describe('setTopicValues', () => {
    it('clears optimistic numberValue when incoming raw matches within epsilon', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity()]))
        store.entityStates['number.thermostat'] = { state: 'off', brightness: 255, numberValue: 21.5 }

        store.setTopicValues({ 'z/temp': '21.5' })
        expect(store.entityStates['number.thermostat'].numberValue).toBeUndefined()
    })

    it('retains optimistic numberValue when raw differs', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity()]))
        store.entityStates['number.thermostat'] = { state: 'off', brightness: 255, numberValue: 21.5 }

        store.setTopicValues({ 'z/temp': '22.0' })
        expect(store.entityStates['number.thermostat'].numberValue).toBe(21.5)
    })

    it('retains optimistic numberValue when raw is non-numeric (NaN)', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity()]))
        store.entityStates['number.thermostat'] = { state: 'off', brightness: 255, numberValue: 21.5 }

        store.setTopicValues({ 'z/temp': 'not-a-number' })
        expect(store.entityStates['number.thermostat'].numberValue).toBe(21.5)
    })

    it('skips entities that are not number type or have no numberConfig', () => {
        const store = useFloorplanStore()
        const light = numberEntity({ id: 'l1', entityId: 'light.x', type: 'light', numberConfig: undefined })
        store.loadConfig(makeConfig([light]))
        store.entityStates['light.x'] = { state: 'off', brightness: 255, numberValue: 5 }

        store.setTopicValues({ 'z/temp': '5' })
        // Non-number entity is skipped; optimistic value untouched.
        expect(store.entityStates['light.x'].numberValue).toBe(5)
    })

    it('skips when the read topic is absent from incoming values', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity()]))
        store.entityStates['number.thermostat'] = { state: 'off', brightness: 255, numberValue: 21.5 }

        store.setTopicValues({ 'some/other/topic': '21.5' })
        expect(store.entityStates['number.thermostat'].numberValue).toBe(21.5)
    })

    it('stores the raw topic values map', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity()]))
        store.setTopicValues({ 'z/temp': '99' })
        expect(store.topicValues).toEqual({ 'z/temp': '99' })
    })

    it('clears optimistic toggleOn (on) once read topic reports onValue', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([toggleEntity()]))
        store.entityStates['toggle.lamp'] = { state: 'off', brightness: 255, toggleOn: true }

        store.setTopicValues({ 'z/lamp/state': 'ON' })
        expect(store.entityStates['toggle.lamp'].toggleOn).toBeUndefined()
    })

    it('clears optimistic toggleOn (off) once read topic reports offValue', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([toggleEntity()]))
        store.entityStates['toggle.lamp'] = { state: 'off', brightness: 255, toggleOn: false }

        store.setTopicValues({ 'z/lamp/state': 'OFF' })
        expect(store.entityStates['toggle.lamp'].toggleOn).toBeUndefined()
    })

    it('retains optimistic toggleOn when read topic reports a non-matching value', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([toggleEntity()]))
        store.entityStates['toggle.lamp'] = { state: 'off', brightness: 255, toggleOn: true }

        // Optimistic is ON (expects 'ON'), but read reports 'OFF' -> keep optimistic.
        store.setTopicValues({ 'z/lamp/state': 'OFF' })
        expect(store.entityStates['toggle.lamp'].toggleOn).toBe(true)
    })

    it('retains optimistic toggleOn when onValue === offValue (ambiguous report)', () => {
        const store = useFloorplanStore()
        // Misconfig: onValue and offValue are identical, so a reported value
        // matches BOTH states -> the report is ambiguous and must not reconcile.
        store.loadConfig(makeConfig([toggleEntity({
            toggleConfig: { readTopic: 'z/lamp/state', writeTopic: 'z/lamp/set', onValue: '1', offValue: '1', size: 2.5 },
        })]))
        store.entityStates['toggle.lamp'] = { state: 'off', brightness: 255, toggleOn: true }

        store.setTopicValues({ 'z/lamp/state': '1' })
        expect(store.entityStates['toggle.lamp'].toggleOn).toBe(true)
    })
})

describe('toggleEntityState', () => {
    it('off -> on: sets state on, shouldLightUp true, preserves brightness, sends ON', async () => {
        const store = useFloorplanStore()
        store.entityStates['light.a'] = { state: 'off', brightness: 200 }

        await store.toggleEntityState('light.a')
        const st = store.entityStates['light.a']
        expect(st.state).toBe('on')
        expect(st.shouldLightUp).toBe(true)
        expect(st.brightness).toBe(200)
        expect(sendCommandMock).toHaveBeenCalledWith('light.a', 'ON')
    })

    it('on -> off: sets state off, shouldLightUp false, sends OFF', async () => {
        const store = useFloorplanStore()
        store.entityStates['light.a'] = { state: 'on', brightness: 255, shouldLightUp: true }

        await store.toggleEntityState('light.a')
        const st = store.entityStates['light.a']
        expect(st.state).toBe('off')
        expect(st.shouldLightUp).toBe(false)
        expect(sendCommandMock).toHaveBeenCalledWith('light.a', 'OFF')
    })

    it('unknown id defaults to off then flips to on', async () => {
        const store = useFloorplanStore()
        await store.toggleEntityState('light.unknown')
        expect(store.entityStates['light.unknown'].state).toBe('on')
        expect(sendCommandMock).toHaveBeenCalledWith('light.unknown', 'ON')
    })

    it('sendCommand rejection does NOT roll back the optimistic state', async () => {
        // Documenting current fire-and-forget behavior: errors are swallowed,
        // the optimistic state stays applied.
        sendCommandMock.mockRejectedValueOnce(new Error('command failed'))
        const store = useFloorplanStore()
        store.entityStates['light.a'] = { state: 'off', brightness: 255 }

        await store.toggleEntityState('light.a')
        // Flush the rejected promise's .catch microtask.
        await vi.runAllTimersAsync()
        await Promise.resolve()

        expect(store.entityStates['light.a'].state).toBe('on')
    })
})

describe('setNumberValue', () => {
    it('writeTopic present -> optimistic numberValue set + publishRaw(topic, String(value))', () => {
        const store = useFloorplanStore()
        store.entityStates['number.t'] = { state: 'on', brightness: 100 }

        store.setNumberValue('number.t', 'z/t/set', 42)
        expect(store.entityStates['number.t'].numberValue).toBe(42)
        expect(publishRawMock).toHaveBeenCalledWith('z/t/set', '42')
        // Existing state/brightness preserved.
        expect(store.entityStates['number.t'].state).toBe('on')
        expect(store.entityStates['number.t'].brightness).toBe(100)
    })

    it('empty writeTopic -> early return, no optimistic value, publishRaw not called', () => {
        const store = useFloorplanStore()
        store.entityStates['number.t'] = { state: 'on', brightness: 100 }

        store.setNumberValue('number.t', '', 42)
        expect(store.entityStates['number.t'].numberValue).toBeUndefined()
        expect(publishRawMock).not.toHaveBeenCalled()
    })

    it('seeds defaults for an unknown entity while still setting numberValue', () => {
        const store = useFloorplanStore()
        store.setNumberValue('number.new', 'z/t/set', 7)
        expect(store.entityStates['number.new']).toMatchObject({ state: 'off', brightness: 255, numberValue: 7 })
    })
})

describe('sendButtonValue', () => {
    it('topic present -> publishRaw(topic, value)', () => {
        const store = useFloorplanStore()
        store.sendButtonValue('home/scene', 'ON')
        expect(publishRawMock).toHaveBeenCalledWith('home/scene', 'ON')
    })

    it('empty topic -> early return, publishRaw not called', () => {
        const store = useFloorplanStore()
        store.sendButtonValue('', 'ON')
        expect(publishRawMock).not.toHaveBeenCalled()
    })
})

describe('setToggleValue', () => {
    it('writeTopic present, nextOn true -> optimistic toggleOn true + publishRaw(topic, value)', () => {
        const store = useFloorplanStore()
        store.entityStates['toggle.lamp'] = { state: 'on', brightness: 100 }

        store.setToggleValue('toggle.lamp', 'z/lamp/set', 'ON', true)
        expect(store.entityStates['toggle.lamp'].toggleOn).toBe(true)
        expect(publishRawMock).toHaveBeenCalledWith('z/lamp/set', 'ON')
        // Existing state/brightness preserved.
        expect(store.entityStates['toggle.lamp'].state).toBe('on')
        expect(store.entityStates['toggle.lamp'].brightness).toBe(100)
    })

    it('writeTopic present, nextOn false -> optimistic toggleOn false stored + publishRaw(topic, value)', () => {
        const store = useFloorplanStore()
        store.entityStates['toggle.lamp'] = { state: 'on', brightness: 100 }

        store.setToggleValue('toggle.lamp', 'z/lamp/set', 'OFF', false)
        expect(store.entityStates['toggle.lamp'].toggleOn).toBe(false)
        expect(publishRawMock).toHaveBeenCalledWith('z/lamp/set', 'OFF')
    })

    it('empty writeTopic -> early return, no optimistic state, publishRaw not called', () => {
        const store = useFloorplanStore()
        store.entityStates['toggle.lamp'] = { state: 'on', brightness: 100 }

        store.setToggleValue('toggle.lamp', '', 'ON', true)
        expect(store.entityStates['toggle.lamp'].toggleOn).toBeUndefined()
        expect(publishRawMock).not.toHaveBeenCalled()
    })

    it('seeds defaults for an unknown entity while still setting toggleOn', () => {
        const store = useFloorplanStore()
        store.setToggleValue('toggle.new', 'z/lamp/set', 'ON', true)
        expect(store.entityStates['toggle.new']).toMatchObject({ state: 'off', brightness: 255, toggleOn: true })
    })
})

describe('setEntityState', () => {
    it("'on' -> shouldLightUp true", () => {
        const store = useFloorplanStore()
        store.setEntityState('light.a', 'on')
        expect(store.entityStates['light.a'].shouldLightUp).toBe(true)
    })

    it("'off' -> shouldLightUp false", () => {
        const store = useFloorplanStore()
        store.setEntityState('light.a', 'off')
        expect(store.entityStates['light.a'].shouldLightUp).toBe(false)
    })

    it("'idle' -> shouldLightUp false", () => {
        const store = useFloorplanStore()
        store.setEntityState('light.a', 'idle')
        expect(store.entityStates['light.a'].shouldLightUp).toBe(false)
    })

    it('rawPayload provided is stored', () => {
        const store = useFloorplanStore()
        store.setEntityState('light.a', 'on', { temperature: 20 })
        expect(store.entityStates['light.a'].rawPayload).toEqual({ temperature: 20 })
    })

    it('rawPayload omitted -> key absent', () => {
        const store = useFloorplanStore()
        store.setEntityState('light.a', 'on')
        expect('rawPayload' in store.entityStates['light.a']).toBe(false)
    })

    it('unknown entity is seeded with defaults', () => {
        const store = useFloorplanStore()
        store.setEntityState('light.fresh', 'on')
        expect(store.entityStates['light.fresh']).toMatchObject({ state: 'on', brightness: 255 })
    })
})

describe('addEntity', () => {
    it("'light' -> no text/number config, selection set, entityStates seeded {off,255}", () => {
        const store = useFloorplanStore()
        store.addEntity('light')
        const e = store.config.entities[0]
        expect(e.type).toBe('light')
        expect(e.textConfig).toBeUndefined()
        expect(e.numberConfig).toBeUndefined()
        expect(store.selectedEntityId).toBe(e.id)
        expect(store.entityStates[e.entityId]).toEqual({ state: 'off', brightness: 255 })
    })

    it("'text' -> textConfig present", () => {
        const store = useFloorplanStore()
        store.addEntity('text')
        const e = store.config.entities[0]
        expect(e.textConfig).toEqual({ jsonPath: 'temperature', format: '{}' })
        expect(e.numberConfig).toBeUndefined()
    })

    it("'number' -> numberConfig present", () => {
        const store = useFloorplanStore()
        store.addEntity('number')
        const e = store.config.entities[0]
        expect(e.numberConfig).toBeDefined()
        expect(e.numberConfig).toMatchObject({ readTopic: '', writeTopic: '', min: 0, max: 100, step: 1 })
        expect(e.textConfig).toBeUndefined()
    })

    it("'button' -> buttonConfig seeded with defaults", () => {
        const store = useFloorplanStore()
        store.addEntity('button')
        const e = store.config.entities[0]
        expect(e.type).toBe('button')
        expect(e.buttonConfig).toEqual({ topic: '', value: '', text: 'Send', size: 2.5 })
        expect(e.numberConfig).toBeUndefined()
        expect(e.textConfig).toBeUndefined()
    })

    it("'toggle' -> toggleConfig seeded with defaults", () => {
        const store = useFloorplanStore()
        store.addEntity('toggle')
        const e = store.config.entities[0]
        expect(e.type).toBe('toggle')
        expect(e.toggleConfig).toEqual({ readTopic: '', writeTopic: '', onValue: 'ON', offValue: 'OFF', size: 2.5 })
        expect(e.numberConfig).toBeUndefined()
        expect(e.textConfig).toBeUndefined()
        expect(e.buttonConfig).toBeUndefined()
    })

    it('honors custom x/y', () => {
        const store = useFloorplanStore()
        store.addEntity('light', 33, 77)
        const e = store.config.entities[0]
        expect(e.x).toBe(33)
        expect(e.y).toBe(77)
    })
})

describe('duplicateEntity', () => {
    it('clones with a new id, appends "(copy)", offsets x/y by +3', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'orig', label: 'Orig', x: 10, y: 20 })]))

        store.duplicateEntity('orig')
        expect(store.config.entities).toHaveLength(2)
        const clone = store.config.entities[1]
        expect(clone.id).not.toBe('orig')
        expect(clone.label).toBe('Orig (copy)')
        expect(clone.x).toBe(13)
        expect(clone.y).toBe(23)
        expect(store.selectedEntityId).toBe(clone.id)
    })

    it('clamps x/y at 97', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'orig', x: 96, y: 99 })]))
        store.duplicateEntity('orig')
        const clone = store.config.entities[1]
        expect(clone.x).toBe(97)
        expect(clone.y).toBe(97)
    })

    it('missing id -> no-op', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'orig' })]))
        store.duplicateEntity('does-not-exist')
        expect(store.config.entities).toHaveLength(1)
    })

    it('deep clone is independent of the original', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'orig' })]))
        store.duplicateEntity('orig')
        const clone = store.config.entities[1]
        clone.style.width = 999
        clone.numberConfig!.min = -1
        // Mutating the clone must not affect the original.
        expect(store.config.entities[0].style.width).toBe(5)
        expect(store.config.entities[0].numberConfig!.min).toBe(0)
    })
})

describe('removeEntity', () => {
    it('removes the entity and clears selection if it was selected', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a' }), numberEntity({ id: 'b', entityId: 'number.b' })]))
        store.selectedEntityId = 'a'

        store.removeEntity('a')
        expect(store.config.entities.map(e => e.id)).toEqual(['b'])
        expect(store.selectedEntityId).toBeNull()
    })

    it('keeps selection when a different entity is removed', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a' }), numberEntity({ id: 'b', entityId: 'number.b' })]))
        store.selectedEntityId = 'a'

        store.removeEntity('b')
        expect(store.selectedEntityId).toBe('a')
    })

    it('unknown id -> no-op', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a' })]))
        store.removeEntity('zzz')
        expect(store.config.entities).toHaveLength(1)
    })
})

describe('updateEntity', () => {
    it('merges updates into the matching entity', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a', label: 'Old' })]))
        store.updateEntity('a', { label: 'New', x: 42 })
        expect(store.config.entities[0].label).toBe('New')
        expect(store.config.entities[0].x).toBe(42)
    })

    it('unknown id -> no-op', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a', label: 'Old' })]))
        store.updateEntity('zzz', { label: 'New' })
        expect(store.config.entities[0].label).toBe('Old')
    })
})

describe('loadConfig', () => {
    it('replaces config and reseeds entityStates for each entity', () => {
        const store = useFloorplanStore()
        store.entityStates['stale.entity'] = { state: 'on', brightness: 1 }

        store.loadConfig(makeConfig([numberEntity({ entityId: 'number.x' })]))
        expect(store.config.entities).toHaveLength(1)
        // Stale runtime state is wiped.
        expect(store.entityStates['stale.entity']).toBeUndefined()
        expect(store.entityStates['number.x']).toEqual({ state: 'off', brightness: 255 })
    })
})

describe('importConfig', () => {
    it('loads the imported config and reseeds entityStates', () => {
        const store = useFloorplanStore()
        store.entityStates['stale.entity'] = { state: 'on', brightness: 1 }

        const cfg = makeConfig([numberEntity({ entityId: 'number.imported' })])
        cfg.name = 'Imported'
        store.importConfig(cfg)

        expect(store.config.name).toBe('Imported')
        expect(store.entities).toHaveLength(1)
        // Stale runtime state is wiped; imported entity is seeded.
        expect(store.entityStates['stale.entity']).toBeUndefined()
        expect(store.entityStates['number.imported']).toEqual({ state: 'off', brightness: 255 })
    })

    it('persists the imported config exactly once, synchronously (no extra debounced save)', async () => {
        const store = useFloorplanStore()
        const cfg = makeConfig([numberEntity({ entityId: 'number.imported' })])

        store.importConfig(cfg)
        // Import persists immediately, not after the 2000ms debounce.
        expect(saveConfigMock).toHaveBeenCalledTimes(1)
        expect(saveConfigMock).toHaveBeenCalledWith(store.config)

        // loadConfig's skipNextSave must have suppressed the watcher's save, so
        // advancing past the debounce window adds no additional call.
        vi.advanceTimersByTime(2000)
        await nextTick()
        expect(saveConfigMock).toHaveBeenCalledTimes(1)
    })
})

describe('clearConfig', () => {
    it('resets config to empty, clears selection and entityStates', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a' })]))
        store.selectedEntityId = 'a'

        store.clearConfig()
        expect(store.config.entities).toEqual([])
        expect(store.config.name).toBe('New Floorplan')
        expect(store.selectedEntityId).toBeNull()
        expect(store.entityStates).toEqual({})
    })
})

describe('selectedEntity getter', () => {
    it('returns the entity matching selectedEntityId, undefined otherwise', () => {
        const store = useFloorplanStore()
        store.loadConfig(makeConfig([numberEntity({ id: 'a' })]))
        expect(store.selectedEntity).toBeUndefined()
        store.selectedEntityId = 'a'
        expect(store.selectedEntity?.id).toBe('a')
        store.selectedEntityId = 'missing'
        expect(store.selectedEntity).toBeUndefined()
    })
})

describe('debounced auto-save watcher', () => {
    it('no auto-save before the first loadConfig (guard)', async () => {
        // The watcher is guarded by isLoaded: without a prior loadConfig, mutations
        // must NOT trigger a save. This pins the data-loss-prevention behavior that
        // stops a failed/empty initial fetch from overwriting the real server config.
        const store = useFloorplanStore()
        store.addEntity('light')
        await nextTick()

        vi.advanceTimersByTime(5000)
        expect(saveConfigMock).not.toHaveBeenCalled()
    })

    it('one config mutation -> exactly one saveConfig after 2000ms', async () => {
        const store = useFloorplanStore()
        // Satisfy the isLoaded guard; the load itself consumes skipNextSave.
        store.loadConfig({ id: 'c', name: 'n', imageBase64: '', entities: [] })
        await nextTick()           // watcher fires once and consumes skipNextSave
        saveConfigMock.mockClear() // ignore anything from the load itself

        store.addEntity('light')
        // Let the deep watcher fire and schedule the timer.
        await nextTick()
        expect(saveConfigMock).not.toHaveBeenCalled()

        vi.advanceTimersByTime(2000)
        expect(saveConfigMock).toHaveBeenCalledTimes(1)
    })

    it('no save fires before 2000ms', async () => {
        const store = useFloorplanStore()
        store.loadConfig({ id: 'c', name: 'n', imageBase64: '', entities: [] })
        await nextTick()
        saveConfigMock.mockClear()

        store.addEntity('light')
        await nextTick()

        vi.advanceTimersByTime(1999)
        expect(saveConfigMock).not.toHaveBeenCalled()
        vi.advanceTimersByTime(1)
        expect(saveConfigMock).toHaveBeenCalledTimes(1)
    })

    it('rapid mutations within 2s coalesce into ONE save', async () => {
        const store = useFloorplanStore()
        store.loadConfig({ id: 'c', name: 'n', imageBase64: '', entities: [] })
        await nextTick()
        saveConfigMock.mockClear()

        store.addEntity('light')
        await nextTick()
        vi.advanceTimersByTime(500)

        store.addEntity('text')
        await nextTick()
        vi.advanceTimersByTime(500)

        store.updateEntity(store.config.entities[0].id, { label: 'changed' })
        await nextTick()
        vi.advanceTimersByTime(500)

        // Still within the debounce window after the last mutation.
        expect(saveConfigMock).not.toHaveBeenCalled()

        vi.advanceTimersByTime(2000)
        expect(saveConfigMock).toHaveBeenCalledTimes(1)
    })
})
