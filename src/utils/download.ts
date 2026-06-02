/**
 * Sanitize an arbitrary name into a safe filename base (without extension).
 * Keeps Unicode letters/digits, collapses any other run of characters to a
 * single underscore, trims edge underscores, and falls back to 'floorplan'
 * when nothing usable remains.
 */
export function sanitizeFilenameBase(name: string): string {
    const safe = (name || 'floorplan')
        .trim()
        .replace(/[^\p{L}\p{N}\-_]+/gu, '_')
        .replace(/^_+|_+$/g, '');
    return safe || 'floorplan';
}

/**
 * Trigger a browser download of `href` (a Data URI or object URL) under the
 * given filename, via a transient anchor element. Callers passing an object
 * URL are responsible for revoking it afterwards.
 */
export function triggerDownload(href: string, filename: string): void {
    const a = document.createElement('a');
    a.href = href;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
}
