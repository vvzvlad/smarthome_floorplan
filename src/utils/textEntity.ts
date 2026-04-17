export function extractJsonPath(obj: Record<string, unknown>, path: string): unknown {
    return path.split('.').reduce((acc: unknown, key: string) => {
        if (acc !== null && acc !== undefined && typeof acc === 'object' && key in (acc as Record<string, unknown>)) {
            return (acc as Record<string, unknown>)[key];
        }
        return undefined;
    }, obj as unknown);
}

export function formatTextValue(format: string, rawPayload: Record<string, unknown> | undefined, jsonPath: string): string {
    if (!rawPayload) return format.replace('{}', '—');
    const value = extractJsonPath(rawPayload, jsonPath);
    return format.replace('{}', value != null ? String(value) : '—');
}
