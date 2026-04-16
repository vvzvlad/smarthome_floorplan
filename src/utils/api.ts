const SESSION_KEY = 'smarthome_auth';

export function getAuthHeader(): string {
    return sessionStorage.getItem(SESSION_KEY) ?? '';
}

export function setCredentials(username: string, password: string): void {
    const encoded = btoa(`${username}:${password}`);
    sessionStorage.setItem(SESSION_KEY, `Basic ${encoded}`);
}

export function clearCredentials(): void {
    sessionStorage.removeItem(SESSION_KEY);
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

export async function fetchStates(): Promise<Record<string, { state: string }>> {
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
