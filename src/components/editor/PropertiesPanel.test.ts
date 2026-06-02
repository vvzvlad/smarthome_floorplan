import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'

// PropertiesPanel imports api + image helpers; mock both so onMounted's
// getIconStatus() and any file work resolve without touching the network/Canvas.
vi.mock('../../utils/api', () => ({
    fetchDevices: vi.fn().mockResolvedValue([]),
    getIconStatus: vi.fn().mockResolvedValue({ custom: false }),
    uploadIcon: vi.fn().mockResolvedValue(undefined),
    deleteIcon: vi.fn().mockResolvedValue(undefined),
}))
vi.mock('../../utils/image', () => ({
    resizeImageToPng: vi.fn().mockResolvedValue(new Blob()),
    imageDownloadFilename: vi.fn().mockReturnValue('Test.png'),
}))

// `__APP_VERSION__` is injected by vite's `define` at build time but is absent in
// the Vitest runtime. The component reads it at setup; provide it as a global so
// mounting doesn't throw ReferenceError. (Test-only; no config/component change.)
vi.stubGlobal('__APP_VERSION__', 'test')

import PropertiesPanel from './PropertiesPanel.vue'
import { useFloorplanStore } from '../../stores/floorplan'
import { defaultTextConfig, defaultNumberConfig } from '../../utils/entityForm'
// Import the mocked helper so individual tests can override its return value.
import { imageDownloadFilename } from '../../utils/image'
import type { EntityConfig, FloorplanConfig } from '../../types/floorplan'

function lightEntity(overrides: Partial<EntityConfig> = {}): EntityConfig {
    return {
        id: 'e1',
        entityId: 'light.kitchen',
        label: 'Kitchen',
        type: 'light',
        x: 50,
        y: 50,
        points: [],
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
        labelConfig: { show: true, offsetX: 0, offsetY: 10, color: '#ffffff' },
        ...overrides,
    }
}

function makeConfig(entity: EntityConfig): FloorplanConfig {
    return { id: 'c1', name: 'Test', imageBase64: '', entities: [entity] }
}

// Mount with a testing pinia where `entity` is the selected entity. Actions are
// stubbed (spied) by default; getters still compute from the seeded state.
function mountPanel(entity: EntityConfig) {
    const wrapper = mount(PropertiesPanel, {
        props: { isDrawing: false },
        global: {
            plugins: [
                createTestingPinia({
                    createSpy: vi.fn,
                    initialState: {
                        floorplan: {
                            config: makeConfig(entity),
                            selectedEntityId: entity.id,
                        },
                    },
                }),
            ],
        },
    })
    return { wrapper, store: useFloorplanStore() }
}

// Mount with nothing selected (selectedEntityId: null), so the global-config
// section (Floorplan Image + Download Config) renders. Actions are stubbed (spied).
function mountNoSelection(config: FloorplanConfig) {
    const wrapper = mount(PropertiesPanel, {
        props: { isDrawing: false },
        global: {
            plugins: [
                createTestingPinia({
                    createSpy: vi.fn,
                    initialState: {
                        floorplan: {
                            config,
                            selectedEntityId: null,
                        },
                    },
                }),
            ],
        },
    })
    return { wrapper, store: useFloorplanStore() }
}

describe('PropertiesPanel — onTypeChange', () => {
    beforeEach(() => vi.clearAllMocks())

    it('seeds a default textConfig when switching to "text" and none exists', async () => {
        const { wrapper, store } = mountPanel(lightEntity())
        await flushPromises()

        // Selected entity is light; flip its type to text, then fire @change.
        store.selectedEntity!.type = 'text'
        await wrapper.find('select').setValue('text')

        expect(store.updateEntity).toHaveBeenCalledWith('e1', { textConfig: defaultTextConfig() })
    })

    it('seeds a default numberConfig when switching to "number" and none exists', async () => {
        const { wrapper, store } = mountPanel(lightEntity())
        await flushPromises()

        store.selectedEntity!.type = 'number'
        await wrapper.find('select').setValue('number')

        expect(store.updateEntity).toHaveBeenCalledWith('e1', { numberConfig: defaultNumberConfig() })
    })

    it('does NOT overwrite an existing textConfig when switching to "text"', async () => {
        // Entity already carries a custom textConfig — onTypeChange must leave it intact.
        const entity = lightEntity({ textConfig: { jsonPath: 'humidity', format: 'H: {}' } })
        const { wrapper, store } = mountPanel(entity)
        await flushPromises()

        store.selectedEntity!.type = 'text'
        await wrapper.find('select').setValue('text')

        // No updateEntity call carrying a textConfig (the guard short-circuits).
        const calls = (store.updateEntity as unknown as { mock: { calls: unknown[][] } }).mock.calls
        const seededText = calls.some((c) => c[1] && 'textConfig' in (c[1] as object))
        expect(seededText).toBe(false)
    })

    it('does NOT overwrite an existing numberConfig when switching to "number"', async () => {
        const entity = lightEntity({
            numberConfig: { readTopic: 'r', writeTopic: 'w', min: 5, max: 9, step: 0.5, unit: 'x', size: 3 },
        })
        const { wrapper, store } = mountPanel(entity)
        await flushPromises()

        store.selectedEntity!.type = 'number'
        await wrapper.find('select').setValue('number')

        const calls = (store.updateEntity as unknown as { mock: { calls: unknown[][] } }).mock.calls
        const seededNumber = calls.some((c) => c[1] && 'numberConfig' in (c[1] as object))
        expect(seededNumber).toBe(false)
    })
})

describe('PropertiesPanel — draw mode', () => {
    beforeEach(() => vi.clearAllMocks())

    it('emits toggle-draw-mode when the Draw button is clicked', async () => {
        const { wrapper } = mountPanel(lightEntity())
        await flushPromises()

        // The Draw button lives in the light-entity "Light Zone" section.
        const drawButton = wrapper.findAll('button').find((b) => b.text() === 'Draw')
        expect(drawButton).toBeTruthy()
        await drawButton!.trigger('click')

        expect(wrapper.emitted('toggle-draw-mode')).toHaveLength(1)
    })
})

describe('PropertiesPanel — download background image', () => {
    beforeEach(() => vi.clearAllMocks())

    // Unconditionally restore any vi.spyOn-created spies (e.g. the anchor click
    // spy) so a thrown assertion can't leak a spy onto HTMLAnchorElement.prototype.
    // Scoped to this describe; vi.mock('../../utils/image', ...) is not affected.
    afterEach(() => vi.restoreAllMocks())

    it('disables the Download Image button when there is no base image', async () => {
        const { wrapper } = mountNoSelection(makeConfig(lightEntity()))
        await flushPromises()

        const btn = wrapper.findAll('button').find((b) => b.text() === 'Download Image')
        expect(btn).toBeTruthy()
        expect(btn!.attributes('disabled')).toBeDefined()
    })

    it('enables the button and triggers a download click when an image exists', async () => {
        // Spy on the anchor click so jsdom doesn't attempt navigation.
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
        const cfg = { ...makeConfig(lightEntity()), imageBase64: 'data:image/png;base64,AAA' }
        const { wrapper } = mountNoSelection(cfg)
        await flushPromises()

        const btn = wrapper.findAll('button').find((b) => b.text() === 'Download Image')
        expect(btn).toBeTruthy()
        expect(btn!.attributes('disabled')).toBeUndefined()
        await btn!.trigger('click')

        expect(clickSpy).toHaveBeenCalledTimes(1)
    })

    it('does not trigger a download when there is no filename', async () => {
        // imageDownloadFilename returns null for this call, so downloadBaseImage()
        // hits its early-return guard before creating/clicking the anchor.
        vi.mocked(imageDownloadFilename).mockReturnValueOnce(null)
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
        // Non-empty image keeps the button enabled so the click reaches the guard.
        const cfg = { ...makeConfig(lightEntity()), imageBase64: 'data:image/png;base64,AAA' }
        const { wrapper } = mountNoSelection(cfg)
        await flushPromises()

        const btn = wrapper.findAll('button').find((b) => b.text() === 'Download Image')
        expect(btn).toBeTruthy()
        await btn!.trigger('click')

        expect(clickSpy).not.toHaveBeenCalled()
    })
})

describe('PropertiesPanel — download config', () => {
    beforeEach(() => vi.clearAllMocks())
    // Restore any vi.spyOn-created spies (blob-URL APIs, anchor click) so they
    // don't leak across tests. Scoped to this describe; vi.mock(...) is unaffected.
    afterEach(() => vi.restoreAllMocks())

    it('serializes store.config to a pretty-printed JSON blob and triggers a download', async () => {
        // jsdom lacks the blob-URL APIs; stub them so downloadConfig() can run.
        const createSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock')
        const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {})
        const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

        const cfg = makeConfig(lightEntity())
        const { wrapper } = mountNoSelection(cfg)
        await flushPromises()

        const btn = wrapper.findAll('button').find((b) => b.text() === 'Download Config')
        expect(btn).toBeTruthy()
        await btn!.trigger('click')

        expect(clickSpy).toHaveBeenCalledTimes(1)

        // The Blob handed to createObjectURL must contain the pretty-printed config.
        const blob = createSpy.mock.calls[0]?.[0] as Blob
        expect(blob).toBeInstanceOf(Blob)
        expect(blob.type).toBe('application/json')
        const text = await blob.text()
        expect(JSON.parse(text)).toEqual(cfg)
        expect(text).toContain('\n  ') // 2-space pretty print

        // Fix: the object URL is revoked on the next tick (setTimeout(…, 0)), not
        // synchronously, so wait one macrotask before asserting it.
        await new Promise((resolve) => setTimeout(resolve, 0))
        expect(revokeSpy).toHaveBeenCalledTimes(1)
    })
})

describe('PropertiesPanel — upload config', () => {
    beforeEach(() => vi.clearAllMocks())
    // Restore window.confirm / any spyOn-created spies after each test.
    afterEach(() => vi.restoreAllMocks())

    it('renders an Upload Config button', async () => {
        const { wrapper } = mountNoSelection(makeConfig(lightEntity()))
        await flushPromises()

        const btn = wrapper.findAll('button').find((b) => b.text() === 'Upload Config')
        expect(btn).toBeTruthy()
    })

    it('parses + validates the picked file and calls store.importConfig with it', async () => {
        vi.spyOn(window, 'confirm').mockReturnValue(true)

        const { wrapper, store } = mountNoSelection(makeConfig(lightEntity()))
        await flushPromises()

        const imported = { id: 'imp', name: 'Imported', imageBase64: '', entities: [] }
        const file = new File([JSON.stringify(imported)], 'cfg.json', { type: 'application/json' })

        // Multiple file inputs exist (image, icon, config); pick the JSON one.
        const input = wrapper.findAll('input[type=file]').find((i) => i.attributes('accept')?.includes('json'))
        expect(input).toBeTruthy()
        const inputEl = input!.element as HTMLInputElement
        Object.defineProperty(inputEl, 'files', { value: [file], configurable: true })

        await input!.trigger('change')
        await flushPromises()
        // file.text() is async; let its microtasks settle.
        await new Promise((resolve) => setTimeout(resolve, 0))

        expect(store.importConfig).toHaveBeenCalledTimes(1)
        const arg = (store.importConfig as unknown as { mock: { calls: unknown[][] } }).mock.calls[0]?.[0] as FloorplanConfig
        expect(arg.name).toBe('Imported')
        expect(arg.entities).toHaveLength(0)
    })
})
