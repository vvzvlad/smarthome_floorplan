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
            const scale = Math.max(size / img.width, size / img.height);
            const w = img.width * scale;
            const h = img.height * scale;
            ctx.drawImage(img, (size - w) / 2, (size - h) / 2, w, h);
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
