import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'

// Mock the api module App.vue talks to. fetchBootstrap gates the whole app.
vi.mock('./utils/api', () => ({
    logout: vi.fn().mockResolvedValue(undefined),
    fetchStates: vi.fn().mockResolvedValue({}),
    fetchTopicValues: vi.fn().mockResolvedValue({}),
    fetchBootstrap: vi.fn(),
}))

import App from './App.vue'
import * as api from './utils/api'
import { useFloorplanStore } from './stores/floorplan'
import type { FloorplanConfig } from './types/floorplan'

const fetchBootstrapMock = vi.mocked(api.fetchBootstrap)

// Minimal config the store can load.
function emptyConfig(): FloorplanConfig {
    return { id: 'c1', name: 'Test', imageBase64: '', entities: [] }
}

// Real routes, memory history (no jsdom URL fiddling). Stub the view components
// so we don't pull CanvasArea/InteractiveFloorplan + the whole store wiring in.
function makeRouter(): Router {
    return createRouter({
        history: createMemoryHistory(),
        routes: [
            { path: '/', name: 'viewer', component: { template: '<div class="stub-viewer" />' } },
            { path: '/editor', name: 'editor', component: { template: '<div class="stub-editor" />' } },
        ],
    })
}

async function mountApp() {
    const router = makeRouter()
    router.push('/')
    await router.isReady()
    const wrapper = mount(App, {
        global: {
            plugins: [
                router,
                createTestingPinia({ createSpy: vi.fn, stubActions: false }),
            ],
        },
    })
    return { wrapper, store: useFloorplanStore() }
}

beforeEach(() => {
    vi.clearAllMocks()
    fetchBootstrapMock.mockResolvedValue({ auth: true, title: 'HA Floorplan', config: emptyConfig(), states: {}, topics: {} })
})

describe('App.vue — auth gate', () => {
    it('renders LoginForm and no header when the session is not authenticated', async () => {
        fetchBootstrapMock.mockResolvedValue({ auth: false, title: 'HA Floorplan' })
        const { wrapper, store } = await mountApp()
        await flushPromises()

        expect(wrapper.find('.login-overlay').exists()).toBe(true)
        expect(wrapper.find('header.app-header').exists()).toBe(false)
        // Init must NOT have run on the unauthenticated branch: config untouched.
        expect(store.config.name).not.toBe('Test')
    })

    it('renders the header + RouterView (no LoginForm) when authenticated, and loads config', async () => {
        fetchBootstrapMock.mockResolvedValue({ auth: true, title: 'My House', config: emptyConfig(), states: {}, topics: {} })
        const { wrapper, store } = await mountApp()
        await flushPromises()

        // Header present, login gone.
        const header = wrapper.find('header.app-header')
        expect(header.exists()).toBe(true)
        expect(wrapper.find('.login-overlay').exists()).toBe(false)
        // appTitle reflects the bootstrap title.
        expect(header.find('.logo').text()).toBe('My House')
        // Viewer route rendered through RouterView.
        expect(wrapper.find('.stub-viewer').exists()).toBe(true)
        // Init ran: config from bootstrap loaded into the store.
        expect(store.config.name).toBe('Test')
    })

    it('falls back to the default title when the bootstrap title is missing', async () => {
        fetchBootstrapMock.mockResolvedValue({ auth: true, title: '', config: emptyConfig(), states: {}, topics: {} })
        const { wrapper } = await mountApp()
        await flushPromises()

        const header = wrapper.find('header.app-header')
        expect(header.exists()).toBe(true)
        // Title falls back to the component default.
        expect(header.find('.logo').text()).toBe('HA Floorplan')
    })
})

describe('App.vue — config migration on init', () => {
    it('migrates an old-format config (style.onColor) before loading it into the store', async () => {
        // Old shape: top-level onColor/offColor, no `colors` object -> needs migration.
        const oldConfig = {
            id: 'c1',
            name: 'Old',
            imageBase64: '',
            entities: [
                {
                    id: 'e1',
                    entityId: 'light.a',
                    label: 'A',
                    type: 'light',
                    x: 10,
                    y: 10,
                    shape: 'circle',
                    style: {
                        width: 5,
                        height: 5,
                        onColor: '#ff0000',
                        offColor: '#00ff00',
                        onOpacity: 0.8,
                        offOpacity: 0.3,
                        gradientRadius: 30,
                        rotation: 0,
                    },
                    labelConfig: { show: true, offsetX: 0, offsetY: 10, color: '#fff' },
                },
            ],
        }
        fetchBootstrapMock.mockResolvedValue({ auth: true, title: 'Old', config: oldConfig, states: {}, topics: {} })

        const { store } = await mountApp()
        await flushPromises()

        // The store received the migrated structure: colors object present, old keys gone.
        const ent = store.config.entities[0] as { style: Record<string, unknown> }
        expect(ent.style.colors).toEqual({ onColor: '#ff0000', offColor: '#00ff00' })
        expect(ent.style.onColor).toBeUndefined()
        expect(ent.style.offColor).toBeUndefined()
    })
})

describe('App.vue — logout', () => {
    let reloadMock: ReturnType<typeof vi.fn>
    let originalLocation: Location
    beforeEach(() => {
        originalLocation = window.location
        reloadMock = vi.fn()
        Object.defineProperty(window, 'location', {
            configurable: true,
            value: { ...originalLocation, reload: reloadMock },
        })
    })
    afterEach(() => {
        Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
    })

    it('reloads to the login screen after a successful logout', async () => {
        fetchBootstrapMock.mockResolvedValue({ auth: true, title: 'X', config: emptyConfig(), states: {}, topics: {} })
        vi.mocked(api.logout).mockResolvedValueOnce(undefined)
        const { wrapper } = await mountApp()
        await flushPromises()
        await wrapper.find('.logout-link').trigger('click')
        await flushPromises()
        expect(reloadMock).toHaveBeenCalledTimes(1)
    })

    // This asserts the user-facing guarantee (reload always happens). The second
    // guarantee of onLogout — that the swallowed rejection does NOT surface as an
    // unhandled promise rejection — is enforced by Vitest's global unhandled-rejection
    // tripwire: drop the `catch` in onLogout and `vitest run` fails the whole run.
    it('still reloads when logout() rejects (e.g. a timed-out request)', async () => {
        fetchBootstrapMock.mockResolvedValue({ auth: true, title: 'X', config: emptyConfig(), states: {}, topics: {} })
        vi.mocked(api.logout).mockRejectedValueOnce(new DOMException('The operation was aborted.', 'AbortError'))
        const { wrapper } = await mountApp()
        await flushPromises()
        await wrapper.find('.logout-link').trigger('click')
        await flushPromises()
        expect(reloadMock).toHaveBeenCalledTimes(1)
    })
})
