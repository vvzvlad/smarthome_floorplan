import type { Page, Route } from '@playwright/test'

// Deterministic backend mock shared by the E2E specs. It maintains a small
// in-memory state object (session flag, config, states, topics) so that:
//  - POST /api/config persists into `state.config` and GET returns it (reload survives),
//  - flipping `state.auth` simulates a successful login,
//  - command/publish endpoints just acknowledge with 200.
// All `/api/**` and the PWA icon route are intercepted, so no real backend runs.

export interface BackendState {
    auth: boolean
    title: string
    config: Record<string, unknown>
    states: Record<string, Record<string, unknown>>
    topics: Record<string, string>
    devices: string[]
    // Recorded request bodies for assertions (kept in the test process).
    commands: Array<{ id: string; body: unknown }>
    publishes: Array<{ topic: string; value: string }>
    logins: Array<unknown>
}

export function makeState(overrides: Partial<BackendState> = {}): BackendState {
    return {
        auth: false,
        title: 'HA Floorplan',
        config: { id: 'cfg-e2e', name: 'E2E Plan', imageBase64: '', entities: [] },
        states: {},
        topics: {},
        devices: [],
        commands: [],
        publishes: [],
        logins: [],
        ...overrides,
    }
}

function json(route: Route, body: unknown, status = 200) {
    return route.fulfill({
        status,
        contentType: 'application/json',
        body: JSON.stringify(body),
    })
}

// A 1x1 transparent PNG so the icon route resolves with a real image body.
const PNG_1x1 = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
    'base64',
)

export async function installBackend(page: Page, state: BackendState): Promise<void> {
    // PWA / apple-touch icon — keep it from hitting a real backend.
    await page.route('**/apple-touch-icon.png*', (route) =>
        route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1x1 }),
    )

    await page.route('**/api/**', async (route) => {
        const req = route.request()
        const url = new URL(req.url())
        const path = url.pathname
        const method = req.method()

        // --- session / info ---
        if (path === '/api/session' && method === 'GET') {
            return json(route, { auth: state.auth })
        }
        if (path === '/api/info' && method === 'GET') {
            return json(route, { title: state.title })
        }

        // --- login: ok flips the in-memory session to authed ---
        if (path === '/api/login' && method === 'POST') {
            state.logins.push(req.postDataJSON?.() ?? null)
            state.auth = true
            return json(route, { ok: true })
        }
        if (path === '/api/logout' && method === 'POST') {
            state.auth = false
            return json(route, { ok: true })
        }

        // --- config persistence (POST writes, GET returns the latest) ---
        if (path === '/api/config' && method === 'GET') {
            return json(route, state.config)
        }
        if (path === '/api/config' && method === 'POST') {
            state.config = req.postDataJSON()
            return json(route, { ok: true })
        }

        // --- runtime state / topics ---
        if (path === '/api/states' && method === 'GET') {
            return json(route, state.states)
        }
        if (path === '/api/mqtt/topics' && method === 'GET') {
            return json(route, state.topics)
        }
        if (path === '/api/devices' && method === 'GET') {
            return json(route, state.devices)
        }

        // --- commands / raw publish ---
        const cmdMatch = path.match(/^\/api\/entity\/(.+)\/command$/)
        if (cmdMatch && method === 'POST') {
            state.commands.push({ id: decodeURIComponent(cmdMatch[1]), body: req.postDataJSON() })
            return json(route, { ok: true })
        }
        if (path === '/api/mqtt/publish' && method === 'POST') {
            const b = req.postDataJSON() as { topic: string; value: string }
            state.publishes.push({ topic: b.topic, value: b.value })
            return json(route, { ok: true })
        }

        // --- icon status (editor onMounted) ---
        if (path === '/api/icon' && method === 'GET') {
            return json(route, { custom: false })
        }

        // Fallback: acknowledge anything else so the app never hangs on the network.
        return json(route, { ok: true })
    })
}

// A 1x1 transparent PNG data URI, used as a floorplan base image so the viewer
// renders the canvas (InteractiveFloorplan's `hasImage` becomes truthy).
export const IMG_DATA_URI =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

// Minimal light entity for viewer journeys.
export function lightEntity(overrides: Record<string, unknown> = {}) {
    return {
        id: 'light-e2e',
        entityId: 'light.living_room',
        label: 'Living Room',
        type: 'light',
        x: 50,
        y: 50,
        points: [],
        shape: 'circle',
        style: {
            width: 8,
            height: 8,
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

// Minimal number entity (write topic set) for the stepper journey.
export function numberEntity(overrides: Record<string, unknown> = {}) {
    return {
        id: 'num-e2e',
        entityId: 'number.thermostat',
        label: 'Thermostat',
        type: 'number',
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
        labelConfig: { show: false, offsetX: 0, offsetY: 10, color: '#ffffff' },
        numberConfig: { readTopic: 'home/room/setpoint', writeTopic: 'home/room/setpoint/set', min: 0, max: 100, step: 5, unit: '%', size: 4 },
        ...overrides,
    }
}
