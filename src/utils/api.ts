// Auth is carried by a server-set, signed, HttpOnly session cookie (key `fp_session`).
// Same-origin requests send it automatically, so the frontend never touches the token.

const REQUEST_TIMEOUT_MS = 15000;

// iOS Safari/WebKit can leave a fetch() pending indefinitely (e.g. a wedged service
// worker after returning from background or after an auth action), which means the
// promise never settles and the UI freezes (the login button stays stuck on "...").
// Wrapping every request with an AbortController-based deadline guarantees the promise
// always settles — on a stall it rejects with an AbortError so callers' finally/catch
// run and the UI can recover. We use AbortController + setTimeout rather than
// AbortSignal.timeout because the latter is unsupported on older iOS.
async function fetchWithTimeout(
    input: RequestInfo | URL,
    init: RequestInit = {},
    timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<Response> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        return await fetch(input, { ...init, signal: controller.signal });
    } finally {
        clearTimeout(timer);
    }
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> ?? {}),
    };
    const res = await fetchWithTimeout(path, { credentials: 'same-origin', ...options, headers });
    if (res.status === 401) {
        // Session expired/absent -> reload to show the login form.
        window.location.reload();
    }
    return res;
}

export async function fetchConfig(): Promise<object> {
    const res = await apiFetch('/api/config');
    if (!res.ok) throw new Error('Failed to fetch config');
    return res.json();
}

/** Fetch the floorplan config. Plain fetch (not apiFetch) so a 401 does NOT trigger
 *  the reload path. The service worker serves this from cache (StaleWhileRevalidate)
 *  on repeat loads. Returns null when unauthenticated (401). */
export async function fetchConfigCached(): Promise<object | null> {
    const res = await fetch('/api/config', { credentials: 'same-origin' });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error('Failed to fetch config');
    return res.json();
}

export async function saveConfig(config: object): Promise<void> {
    const res = await apiFetch('/api/config', {
        method: 'POST',
        body: JSON.stringify(config),
    });
    if (!res.ok) throw new Error('Failed to save config');
}

export async function fetchStates(): Promise<Record<string, Record<string, unknown>>> {
    const res = await apiFetch('/api/states');
    if (!res.ok) throw new Error('Failed to fetch states');
    return res.json();
}

export async function sendCommand(entityId: string, state: 'ON' | 'OFF'): Promise<void> {
    const encodedId = encodeURIComponent(entityId);
    const res = await apiFetch(`/api/entity/${encodedId}/command`, {
        method: 'POST',
        body: JSON.stringify({ state }),
    });
    if (!res.ok) throw new Error('Failed to send command');
}

export async function publishRaw(topic: string, value: string): Promise<void> {
    const res = await apiFetch('/api/mqtt/publish', {
        method: 'POST',
        body: JSON.stringify({ topic, value }),
    });
    if (!res.ok) throw new Error('Failed to publish value');
}

export async function fetchTopicValues(): Promise<Record<string, string>> {
    const res = await apiFetch('/api/mqtt/topics');
    if (!res.ok) throw new Error('Failed to fetch topic values');
    return res.json();
}

export async function login(password: string): Promise<boolean> {
    const res = await fetchWithTimeout('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ password }),
    });
    return res.ok;
}

export async function logout(): Promise<void> {
    await fetchWithTimeout('/api/logout', { method: 'POST', credentials: 'same-origin' });
}

/** Returns true if the current session cookie is authenticated. Never triggers a reload. */
export async function checkSession(): Promise<boolean> {
    try {
        const res = await fetchWithTimeout('/api/session', { credentials: 'same-origin' });
        if (!res.ok) return false;
        const data = await res.json();
        return data.auth === true;
    } catch {
        return false;
    }
}

export interface BootstrapData {
    auth: boolean;
    title: string;
    // Included as a fallback (and for older cached frontend bundles). The current
    // frontend normally paints from the SW-cached /api/config and only reads this
    // when that cache misses.
    config?: object;
    states?: Record<string, Record<string, unknown>>;
    topics?: Record<string, string>;
}

/** One-shot startup payload (auth + title, plus config/states/topics when authed).
 *  Public endpoint; never triggers the 401 reload path. */
export async function fetchBootstrap(): Promise<BootstrapData> {
    try {
        const res = await fetchWithTimeout('/api/bootstrap', { credentials: 'same-origin' });
        if (!res.ok) return { auth: false, title: 'HA Floorplan' };
        return await res.json();
    } catch {
        return { auth: false, title: 'HA Floorplan' };
    }
}

/** URL of the backend camera snapshot proxy for a camera URL. `bust` is appended as a
 *  cache-buster so each refresh frame is a distinct request. */
export function cameraImageUrl(url: string, bust?: number): string {
    const base = `/api/camera?url=${encodeURIComponent(url)}`;
    return bust === undefined ? base : `${base}&t=${bust}`;
}

/** Cameras that are off: widget id -> epoch seconds when they turn back on. Plain fetch
 *  (not apiFetch): App.vue also calls it at startup before the session is confirmed, and a
 *  401 there must not trigger the reload path. */
export async function fetchCameraPower(): Promise<Record<string, number>> {
    const res = await fetchWithTimeout('/api/camera/power', { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Failed to fetch camera power');
    return res.json();
}

/** Send a camera widget's off or on request. Returns when the camera turns back on
 *  (epoch seconds), or null when it is on. */
export async function setCameraPower(widgetId: string, on: boolean): Promise<number | null> {
    const res = await apiFetch(`/api/camera/${encodeURIComponent(widgetId)}/power`, {
        method: 'POST',
        body: JSON.stringify({ on }),
    });
    if (!res.ok) throw new Error('Failed to set camera power');
    return (await res.json()).until;
}

/** Last 24 hours of a chart widget's value as [epoch seconds, value] pairs (5-minute
 *  averages). `params` is `device` + `path` or `topic`, see chartRequestParams. Plain fetch
 *  (not apiFetch): the floorplan paints from the cached config before the session is
 *  confirmed, and a 401 there must not trigger the reload path. */
export async function fetchChart(params: Record<string, string>): Promise<[number, number][]> {
    const res = await fetchWithTimeout(`/api/chart?${new URLSearchParams(params)}`, { credentials: 'same-origin' });
    if (!res.ok) throw new Error('Failed to fetch chart');
    return (await res.json()).points;
}

export async function fetchDevices(): Promise<string[]> {
    const res = await apiFetch('/api/devices');
    if (!res.ok) throw new Error('Failed to fetch devices');
    return res.json();
}

export async function fetchInfo(): Promise<{ title: string }> {
    const res = await fetchWithTimeout('/api/info');
    if (!res.ok) return { title: 'HA Floorplan' };
    return res.json();
}

export async function getIconStatus(): Promise<{ custom: boolean }> {
    const res = await apiFetch('/api/icon');
    if (!res.ok) throw new Error('Failed to fetch icon status');
    return res.json();
}

export async function uploadIcon(png: Blob): Promise<void> {
    const res = await apiFetch('/api/icon', {
        method: 'POST',
        headers: { 'Content-Type': 'image/png' },
        body: png,
    });
    if (!res.ok) throw new Error('Failed to upload icon');
}

export async function deleteIcon(): Promise<void> {
    const res = await apiFetch('/api/icon', { method: 'DELETE' });
    if (!res.ok) throw new Error('Failed to delete icon');
}
