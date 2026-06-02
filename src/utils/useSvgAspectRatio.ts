import { ref, watch, onUnmounted, type Ref } from 'vue';

/**
 * Reactively tracks an element's on-screen width/height ratio.
 *
 * The light "glow" is rendered inside an SVG using `preserveAspectRatio="none"`,
 * which stretches the square viewBox to the underlying image's pixel size. As a
 * result a circle in viewBox units becomes an ellipse on screen. By compensating
 * the vertical radius with this aspect ratio, radial glows stay perfectly round
 * regardless of the underlying image aspect ratio. Tracking it reactively (via a
 * ResizeObserver) keeps the value current on first render, on window/container
 * resize, and after the image loads.
 */
export function useSvgAspectRatio(elRef: Ref<Element | null>): Ref<number> {
    const aspectRatio = ref<number>(1);
    let observer: ResizeObserver | null = null;

    function measure(el: Element): void {
        const { width, height } = el.getBoundingClientRect();
        // Guard against divide-by-zero / not-yet-laid-out state.
        if (height > 0) {
            aspectRatio.value = width / height;
        }
    }

    watch(elRef, (el) => {
        observer?.disconnect();
        observer = null;
        if (!el) return;
        measure(el);
        // jsdom (vitest) has no ResizeObserver; only observe when available.
        if (typeof ResizeObserver !== 'undefined') {
            observer = new ResizeObserver(() => measure(el));
            observer.observe(el);
        }
    }, { immediate: true });

    onUnmounted(() => observer?.disconnect());

    return aspectRatio;
}
