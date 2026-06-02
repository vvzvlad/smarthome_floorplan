// Auth is carried by a server-set, signed, HttpOnly session cookie (key `fp_session`).
// Same-origin requests send it automatically, so the frontend never touches the token.

async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(options.headers as Record<string, string> ?? {}),
    };
    const res = await fetch(path, { credentials: 'same-origin', ...options, headers });
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
    const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ password }),
    });
    return res.ok;
}

export async function logout(): Promise<void> {
    await fetch('/api/logout', { method: 'POST', credentials: 'same-origin' });
}

/** Returns true if the current session cookie is authenticated. Never triggers a reload. */
export async function checkSession(): Promise<boolean> {
    try {
        const res = await fetch('/api/session', { credentials: 'same-origin' });
        if (!res.ok) return false;
        const data = await res.json();
        return data.auth === true;
    } catch {
        return false;
    }
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
