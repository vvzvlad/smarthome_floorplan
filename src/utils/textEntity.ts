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

/**
 * Format the raw (non-JSON) value of an MQTT topic for a text widget in 'topic'
 * source mode. Substitutes the raw string into the format's "{}" placeholder; a
 * missing value (topic not seen yet) becomes the em-dash placeholder. An empty
 * string is substituted verbatim, mirroring formatTextValue's `!= null` policy.
 */
export function formatRawTopicValue(format: string, rawValue: string | undefined): string {
    return format.replace('{}', rawValue != null ? rawValue : '—');
}
