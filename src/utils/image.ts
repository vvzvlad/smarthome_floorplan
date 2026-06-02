const IMAGE_MIME_EXTENSIONS: Record<string, string> = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'image/svg+xml': 'svg',
    'image/bmp': 'bmp',
    'image/avif': 'avif',
};

/**
 * Derive a download filename for a base64 / Data-URI image. Infers the file
 * extension from the URI's MIME type (falling back to 'png') and sanitizes the
 * given base name. Returns null when the input is not a Data URI (nothing to
 * download).
 */
export function imageDownloadFilename(dataUri: string, baseName: string): string | null {
    if (!dataUri || !dataUri.startsWith('data:')) return null;
    const match = /^data:([^;,]*)[;,]/.exec(dataUri);
    const mime = (match?.[1] ?? '').trim().toLowerCase();
    const ext = IMAGE_MIME_EXTENSIONS[mime] ?? 'png';
    const safe = (baseName || 'floorplan')
        .trim()
        .replace(/[^\p{L}\p{N}\-_]+/gu, '_')
        .replace(/^_+|_+$/g, '');
    return `${safe || 'floorplan'}.${ext}`;
}

/**
 * Compute the center-crop "cover" fit of an image into a square target of side
 * `size`. Scales so the shorter side fills the square and the overflow is
 * centered. Returns the scale plus the drawn dimensions (w/h) and the top-left
 * offsets (dx/dy) to pass to ctx.drawImage.
 *
 * Guards against zero-sized images so callers never get NaN/Infinity.
 */
export function computeCoverFit(
    imgW: number,
    imgH: number,
    size: number,
): { scale: number; w: number; h: number; dx: number; dy: number } {
    if (imgW === 0 || imgH === 0) {
        return { scale: 0, w: 0, h: 0, dx: size / 2, dy: size / 2 };
    }
    const scale = Math.max(size / imgW, size / imgH);
    const w = imgW * scale;
    const h = imgH * scale;
    const dx = (size - w) / 2;
    const dy = (size - h) / 2;
    return { scale, w, h, dx, dy };
}

/**
 * Load an image file and render it into a square PNG of the given size using a
 * center-crop "cover" fit. Returns the PNG as a Blob. Used to normalize a
 * user-picked image into an apple-touch-icon (180x180).
 */
export function resizeImageToPng(file: File, size: number): Promise<Blob> {
    return new Promise((resolve, reject) => {
        const url = URL.createObjectURL(file);
        const img = new Image();
        img.onload = () => {
            URL.revokeObjectURL(url);
            const canvas = document.createElement('canvas');
            canvas.width = size;
            canvas.height = size;
            const ctx = canvas.getContext('2d');
            if (!ctx) {
                reject(new Error('Canvas 2D context unavailable'));
                return;
            }
            // Cover fit: scale so the shorter side fills, center-crop the overflow.
            const { w, h, dx, dy } = computeCoverFit(img.width, img.height, size);
            ctx.drawImage(img, dx, dy, w, h);
            canvas.toBlob((blob) => {
                if (blob) resolve(blob);
                else reject(new Error('Failed to encode PNG'));
            }, 'image/png');
        };
        img.onerror = () => {
            URL.revokeObjectURL(url);
            reject(new Error('Failed to load image'));
        };
        img.src = url;
    });
}
