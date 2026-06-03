import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import {
    sendCommand,
    checkSession,
    fetchConfig,
    saveConfig,
    fetchStates,
    fetchTopicValues,
    fetchDevices,
    getIconStatus,
    uploadIcon,
    deleteIcon,
    publishRaw,
    fetchBootstrap,
    login,
} from './api'

// Build a minimal Response-like stub. Only the fields api.ts reads are needed.
function makeResponse(opts: { ok?: boolean; status?: number; json?: unknown; jsonThrows?: boolean } = {}) {
    const ok = opts.ok ?? true
    const status = opts.status ?? (ok ? 200 : 500)
    return {
        ok,
        status,
        json: vi.fn(async () => {
            if (opts.jsonThrows) throw new SyntaxError('Unexpected token')
            return opts.json
        }),
    } as unknown as Response
}

let fetchMock: ReturnType<typeof vi.fn>
let reloadMock: ReturnType<typeof vi.fn>
let originalLocation: Location

beforeEach(() => {
    fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    // window.location.reload is non-configurable in jsdom; swap the whole object.
    originalLocation = window.location
    reloadMock = vi.fn()
    Object.defineProperty(window, 'location', {
        configurable: true,
        value: { ...originalLocation, reload: reloadMock },
    })
})

afterEach(() => {
    vi.unstubAllGlobals()
    Object.defineProperty(window, 'location', { configurable: true, value: originalLocation })
    vi.restoreAllMocks()
})

describe('sendCommand', () => {
    it('encodes the entity id (space, slash, unicode) and posts {state}', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true }))
        await sendCommand('living room/свет', 'ON')

        expect(fetchMock).toHaveBeenCalledTimes(1)
        const [url, init] = fetchMock.mock.calls[0]
        expect(url).toBe(`/api/entity/${encodeURIComponent('living room/свет')}/command`)
        // The id must be percent-encoded: no raw space or slash leaks into the path.
        expect(url).not.toContain(' ')
        expect((url as string).endsWith('/command')).toBe(true)
        expect(init.method).toBe('POST')
        expect(JSON.parse(init.body)).toEqual({ state: 'ON' })
    })

    it('throws on a non-ok response', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 500 }))
        await expect(sendCommand('id', 'OFF')).rejects.toThrow('Failed to send command')
    })
})

describe('checkSession', () => {
    it('200 + {auth:true} -> true', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: { auth: true } }))
        expect(await checkSession()).toBe(true)
    })

    it('200 + {auth:false} -> false', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: { auth: false } }))
        expect(await checkSession()).toBe(false)
    })

    it('non-ok -> false', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 401 }))
        expect(await checkSession()).toBe(false)
    })

    it('fetch throws -> false', async () => {
        fetchMock.mockRejectedValue(new TypeError('network down'))
        expect(await checkSession()).toBe(false)
    })

    it('malformed json -> false', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, jsonThrows: true }))
        expect(await checkSession()).toBe(false)
    })

    it('does not trigger a reload even on a non-ok session check', async () => {
        // checkSession calls bare fetch, not apiFetch, so it must never reload.
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 401 }))
        await checkSession()
        expect(reloadMock).not.toHaveBeenCalled()
    })
})

describe('fetchBootstrap', () => {
    it('returns the parsed body on ok and never reloads', async () => {
        const body = { auth: true, title: 'My House', config: { id: 'a' }, states: {}, topics: {} }
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: body }))
        const result = await fetchBootstrap()
        const [url, init] = fetchMock.mock.calls[0]
        expect(url).toBe('/api/bootstrap')
        expect((init as RequestInit).credentials).toBe('same-origin')
        expect(result).toEqual(body)
        expect(reloadMock).not.toHaveBeenCalled()
    })

    it('returns a safe unauthenticated default on a non-ok response (no reload)', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 401 }))
        expect(await fetchBootstrap()).toEqual({ auth: false, title: 'HA Floorplan' })
        expect(reloadMock).not.toHaveBeenCalled()
    })

    it('returns a safe default when fetch throws', async () => {
        fetchMock.mockRejectedValue(new TypeError('network down'))
        expect(await fetchBootstrap()).toEqual({ auth: false, title: 'HA Floorplan' })
    })
})

describe('apiFetch 401 behavior (via fetchConfig)', () => {
    it('a 401 response triggers window.location.reload() exactly once', async () => {
        // 401 is not ok, so fetchConfig also throws — but reload must have fired.
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 401 }))
        await expect(fetchConfig()).rejects.toThrow('Failed to fetch config')
        expect(reloadMock).toHaveBeenCalledTimes(1)
    })

    it('a non-401 response does not reload', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 500 }))
        await expect(fetchConfig()).rejects.toThrow('Failed to fetch config')
        expect(reloadMock).not.toHaveBeenCalled()
    })

    it('sends default Content-Type application/json and credentials same-origin', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: {} }))
        await fetchConfig()
        const [, init] = fetchMock.mock.calls[0]
        expect(init.headers['Content-Type']).toBe('application/json')
        expect(init.credentials).toBe('same-origin')
    })

    it('caller header overrides are merged over the defaults', async () => {
        // uploadIcon passes Content-Type: image/png, which must win over the default.
        fetchMock.mockResolvedValue(makeResponse({ ok: true }))
        await uploadIcon(new Blob(['x'], { type: 'image/png' }))
        const [, init] = fetchMock.mock.calls[0]
        expect(init.headers['Content-Type']).toBe('image/png')
        // credentials default is still present.
        expect(init.credentials).toBe('same-origin')
    })
})

describe('ok/throw consumers (parametrized table)', () => {
    type Case = {
        name: string
        run: () => Promise<unknown>
        path: string
        method?: string
        okBody?: unknown
        expected?: unknown
        errorMsg: string
        assertInit?: (init: RequestInit) => void
    }

    const cases: Case[] = [
        {
            name: 'fetchConfig',
            run: () => fetchConfig(),
            path: '/api/config',
            okBody: { id: 'a', entities: [] },
            expected: { id: 'a', entities: [] },
            errorMsg: 'Failed to fetch config',
        },
        {
            name: 'saveConfig',
            run: () => saveConfig({ id: 'a', name: 'n' }),
            path: '/api/config',
            method: 'POST',
            okBody: undefined,
            expected: undefined,
            errorMsg: 'Failed to save config',
            assertInit: (init) => {
                // Body must be the JSON-serialized config.
                expect(JSON.parse(init.body as string)).toEqual({ id: 'a', name: 'n' })
            },
        },
        {
            name: 'fetchStates',
            run: () => fetchStates(),
            path: '/api/states',
            okBody: { 'light.x': { state: 'on' } },
            expected: { 'light.x': { state: 'on' } },
            errorMsg: 'Failed to fetch states',
        },
        {
            name: 'fetchTopicValues',
            run: () => fetchTopicValues(),
            path: '/api/mqtt/topics',
            okBody: { 'z/t': '42' },
            expected: { 'z/t': '42' },
            errorMsg: 'Failed to fetch topic values',
        },
        {
            name: 'fetchDevices',
            run: () => fetchDevices(),
            path: '/api/devices',
            okBody: ['light.a', 'light.b'],
            expected: ['light.a', 'light.b'],
            errorMsg: 'Failed to fetch devices',
        },
        {
            name: 'getIconStatus',
            run: () => getIconStatus(),
            path: '/api/icon',
            okBody: { custom: true },
            expected: { custom: true },
            errorMsg: 'Failed to fetch icon status',
        },
        {
            name: 'uploadIcon',
            run: () => uploadIcon(new Blob(['png-bytes'], { type: 'image/png' })),
            path: '/api/icon',
            method: 'POST',
            okBody: undefined,
            expected: undefined,
            errorMsg: 'Failed to upload icon',
            assertInit: (init) => {
                expect((init.headers as Record<string, string>)['Content-Type']).toBe('image/png')
                expect(init.body).toBeInstanceOf(Blob)
            },
        },
        {
            name: 'deleteIcon',
            run: () => deleteIcon(),
            path: '/api/icon',
            method: 'DELETE',
            okBody: undefined,
            expected: undefined,
            errorMsg: 'Failed to delete icon',
            assertInit: (init) => {
                expect(init.method).toBe('DELETE')
            },
        },
        {
            name: 'publishRaw',
            run: () => publishRaw('z/t/set', '42'),
            path: '/api/mqtt/publish',
            method: 'POST',
            okBody: undefined,
            expected: undefined,
            errorMsg: 'Failed to publish value',
            assertInit: (init) => {
                expect(JSON.parse(init.body as string)).toEqual({ topic: 'z/t/set', value: '42' })
            },
        },
    ]

    it.each(cases)('$name returns parsed body on ok', async (c) => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: c.okBody }))
        const result = await c.run()
        const [url, init] = fetchMock.mock.calls[0]
        expect(url).toBe(c.path)
        if (c.method) expect((init as RequestInit).method).toBe(c.method)
        if (c.assertInit) c.assertInit(init as RequestInit)
        if (c.expected !== undefined) expect(result).toEqual(c.expected)
    })

    it.each(cases)('$name throws its specific error on non-ok', async (c) => {
        fetchMock.mockResolvedValue(makeResponse({ ok: false, status: 500 }))
        await expect(c.run()).rejects.toThrow(c.errorMsg)
    })
})

describe('fetchWithTimeout (request timeout guard)', () => {
    it('rejects (never hangs) when the request stalls until the timeout aborts it', async () => {
        vi.useFakeTimers()
        try {
            fetchMock.mockImplementation((_url: unknown, init: RequestInit) =>
                new Promise((_resolve, reject) => {
                    init.signal!.addEventListener('abort', () =>
                        reject(new DOMException('The operation was aborted.', 'AbortError')))
                }))
            const pending = login('pw')
            // Attach the rejection expectation BEFORE advancing so there is no
            // unhandled rejection while timers run. Assert the rejection is the
            // timeout's AbortError specifically, so the test can't pass on some
            // unrelated failure occurring before the abort fires.
            const assertion = expect(pending).rejects.toThrow(/aborted/i)
            await vi.advanceTimersByTimeAsync(15000)
            await assertion
        } finally {
            vi.useRealTimers()
        }
    })

    it('passes an AbortSignal to the underlying fetch', async () => {
        fetchMock.mockResolvedValue(makeResponse({ ok: true, json: { auth: true } }))
        await checkSession()
        const [, init] = fetchMock.mock.calls[0]
        expect((init as RequestInit).signal).toBeInstanceOf(AbortSignal)
    })

    it('clears the timeout on success so a slow follow-up never aborts the resolved request', async () => {
        vi.useFakeTimers()
        try {
            let captured: AbortSignal | undefined
            fetchMock.mockImplementation((_url: unknown, init: RequestInit) => {
                captured = init.signal!
                return Promise.resolve(makeResponse({ ok: true, json: { auth: true } }))
            })
            await checkSession()
            expect(captured!.aborted).toBe(false)
            await vi.advanceTimersByTimeAsync(60000)
            expect(captured!.aborted).toBe(false)
        } finally {
            vi.useRealTimers()
        }
    })

    it('fetchBootstrap returns the safe default when the request times out', async () => {
        vi.useFakeTimers()
        try {
            fetchMock.mockImplementation((_url: unknown, init: RequestInit) =>
                new Promise((_resolve, reject) => {
                    init.signal!.addEventListener('abort', () =>
                        reject(new DOMException('The operation was aborted.', 'AbortError')))
                }))
            const pending = fetchBootstrap()
            await vi.advanceTimersByTimeAsync(15000)
            await expect(pending).resolves.toEqual({ auth: false, title: 'HA Floorplan' })
        } finally {
            vi.useRealTimers()
        }
    })
})
