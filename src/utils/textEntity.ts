import type { TextConfig } from '../types/floorplan';

export type TextWords = Pick<TextConfig, 'onValue' | 'onText' | 'offText'>;

export function extractJsonPath(obj: Record<string, unknown>, path: string): unknown {
    return path.split('.').reduce((acc: unknown, key: string) => {
        if (acc !== null && acc !== undefined && typeof acc === 'object' && key in (acc as Record<string, unknown>)) {
            return (acc as Record<string, unknown>)[key];
        }
        return undefined;
    }, obj as unknown);
}

/**
 * The value as the widget shows it: onText/offText by whether it equals onValue
 * when the widget maps values to words (either word set), the value itself otherwise.
 */
function toWord(value: string, words: TextWords | undefined): string {
    if (!words?.onText && !words?.offText) return value;
    return value === (words.onValue ?? '') ? (words.onText ?? '') : (words.offText ?? '');
}

export function formatTextValue(format: string, rawPayload: Record<string, unknown> | undefined, jsonPath: string, words?: TextWords): string {
    if (!rawPayload) return format.replace('{}', '—');
    const value = extractJsonPath(rawPayload, jsonPath);
    return format.replace('{}', value != null ? toWord(String(value), words) : '—');
}

/**
 * Format the raw (non-JSON) value of an MQTT topic for a text widget in 'topic'
 * source mode. Substitutes the raw string into the format's "{}" placeholder; a
 * missing value (topic not seen yet) becomes the em-dash placeholder. An empty
 * string is substituted verbatim, mirroring formatTextValue's `!= null` policy.
 * With words set (onText or offText) the value is replaced by its word, see toWord.
 */
export function formatRawTopicValue(format: string, rawValue: string | undefined, words?: TextWords): string {
    return format.replace('{}', rawValue != null ? toWord(rawValue, words) : '—');
}
