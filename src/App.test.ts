import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createTestingPinia } from '@pinia/testing'
import { createRouter, createMemoryHistory, type Router } from 'vue-router'

// Mock the api module App.vue talks to. checkSession gates the whole app.
vi.mock('./utils/api', () => ({
    checkSession: vi.fn(),
    logout: vi.fn().mockResolvedValue(undefined),
    fetchConfig: vi.fn(),
    fetchStates: vi.fn().mockResolvedValue({}),
    fetchInfo: vi.fn(),
    fetchTopicValues: vi.fn().mockResolvedValue({}),
}))

import App from './App.vue'
import * as api from './utils/api'
import { useFloorplanStore } from './stores/floorplan'
import type { FloorplanConfig } from './types/floorplan'

const checkSessionMock = vi.mocked(api.checkSession)
const fetchConfigMock = vi.mocked(api.fetchConfig)
const fetchInfoMock = vi.mocked(api.fetchInfo)

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
    fetchInfoMock.mockResolvedValue({ title: 'HA Floorplan' })
    fetchConfigMock.mockResolvedValue(emptyConfig())
})

describe('App.vue — auth gate', () => {
    it('renders LoginForm and no header when the session is not authenticated', async () => {
        checkSessionMock.mockResolvedValue(false)
        const { wrapper } = await mountApp()
        await flushPromises()

        expect(wrapper.find('.login-overlay').exists()).toBe(true)
        expect(wrapper.find('header.app-header').exists()).toBe(false)
        // Init must NOT have run on the unauthenticated branch.
        expect(fetchConfigMock).not.toHaveBeenCalled()
    })

    it('renders the header + RouterView (no LoginForm) when authenticated, and loads config', async () => {
        checkSessionMock.mockResolvedValue(true)
        fetchInfoMock.mockResolvedValue({ title: 'My House' })
        const { wrapper, store } = await mountApp()
        await flushPromises()

        // Header present, login gone.
        const header = wrapper.find('header.app-header')
        expect(header.exists()).toBe(true)
        expect(wrapper.find('.login-overlay').exists()).toBe(false)
        // appTitle reflects fetchInfo.
        expect(header.find('.logo').text()).toBe('My House')
        // Viewer route rendered through RouterView.
        expect(wrapper.find('.stub-viewer').exists()).toBe(true)
        // Init ran: config fetched and loaded into the store.
        expect(fetchConfigMock).toHaveBeenCalledTimes(1)
        expect(store.config.name).toBe('Test')
    })

    it('falls back to the default title and does not crash when fetchInfo rejects', async () => {
        checkSessionMock.mockResolvedValue(true)
        fetchInfoMock.mockRejectedValue(new Error('info down'))
        const { wrapper } = await mountApp()
        await flushPromises()

        const header = wrapper.find('header.app-header')
        expect(header.exists()).toBe(true)
        // Title stays at the component default.
        expect(header.find('.logo').text()).toBe('HA Floorplan')
    })
})

describe('App.vue — config migration on init', () => {
    it('migrates an old-format config (style.onColor) before loading it into the store', async () => {
        checkSessionMock.mockResolvedValue(true)
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
        fetchConfigMock.mockResolvedValue(oldConfig)

        const { store } = await mountApp()
        await flushPromises()

        // The store received the migrated structure: colors object present, old keys gone.
        const ent = store.config.entities[0] as { style: Record<string, unknown> }
        expect(ent.style.colors).toEqual({ onColor: '#ff0000', offColor: '#00ff00' })
        expect(ent.style.onColor).toBeUndefined()
        expect(ent.style.offColor).toBeUndefined()
    })
})
