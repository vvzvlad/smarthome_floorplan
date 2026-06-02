// Use localStorage (not sessionStorage) so credentials survive app relaunches.
// As an installed home-screen PWA each cold launch is a fresh session, which would
// otherwise wipe sessionStorage and force a login on every open.
const SESSION_KEY = 'smarthome_auth';

export function getAuthHeader(): string {
    return localStorage.getItem(SESSION_KEY) ?? '';
}

export function setCredentials(username: string, password: string): void {
    const encoded = btoa(`${username}:${password}`);
    localStorage.setItem(SESSION_KEY, `Basic ${encoded}`);
}

export function clearCredentials(): void {
    localStorage.removeItem(SESSION_KEY);
}

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const auth = getAuthHeader();
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(auth ? { Authorization: auth } : {}),
        ...(options.headers as Record<string, string> ?? {}),
    };
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
        clearCredentials();
        // Reload page to show login form
        window.location.reload();
    }
    return res;
}

export async function fetchConfig(): Promise<object> {
    const res = await apiFetch('/api/config');
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

export async function sendNumberCommand(entityId: string, field: string, value: number): Promise<void> {
    const encodedId = encodeURIComponent(entityId);
    const res = await apiFetch(`/api/entity/${encodedId}/command`, {
        method: 'POST',
        body: JSON.stringify({ field, value }),
    });
    if (!res.ok) throw new Error('Failed to send number command');
}

/**
 * Test credentials by making a real request to /api/config.
 * Returns true if server responds with 200, false if 401.
 */
export async function checkCredentials(username: string, password: string): Promise<boolean> {
    const encoded = btoa(`${username}:${password}`);
    const res = await fetch('/api/config', {
        headers: { Authorization: `Basic ${encoded}` },
    });
    return res.status === 200;
}

export async function fetchDevices(): Promise<string[]> {
    const res = await apiFetch('/api/devices');
    if (!res.ok) throw new Error('Failed to fetch devices');
    return res.json();
}

export async function fetchInfo(): Promise<{ title: string }> {
    const res = await fetch('/api/info');
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
