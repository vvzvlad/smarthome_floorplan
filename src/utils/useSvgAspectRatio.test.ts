import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, ref, h, nextTick } from 'vue'

import { useSvgAspectRatio } from './useSvgAspectRatio'

// Captured ResizeObserver instances so each test can trigger the observer
// callback and assert observe()/disconnect() interactions.
let roInstances: Array<{ observe: ReturnType<typeof vi.fn>; disconnect: ReturnType<typeof vi.fn>; trigger: () => void }>

// jsdom has no real ResizeObserver; this mock records every constructed
// instance and lets tests fire the callback manually.
class MockResizeObserver {
    observe = vi.fn()
    disconnect = vi.fn()
    private cb: ResizeObserverCallback
    constructor(cb: ResizeObserverCallback) {
        this.cb = cb
        roInstances.push({
            observe: this.observe,
            disconnect: this.disconnect,
            trigger: () => this.cb([], this as unknown as ResizeObserver),
        })
    }
    unobserve = vi.fn()
}

beforeEach(() => {
    roInstances = []
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
})

afterEach(() => {
    // Only global stubs need resetting here; the spies live on freshly built
    // MockResizeObserver instances recreated per test, so there is nothing for
    // restoreAllMocks() to undo.
    vi.unstubAllGlobals()
})

// Build a detached element whose layout box is stubbed; jsdom's real
// getBoundingClientRect() returns all zeros, which would defeat the measure.
function makeEl(width: number, height: number): HTMLElement {
    const el = document.createElement('div')
    el.getBoundingClientRect = () =>
        ({ width, height, x: 0, y: 0, top: 0, left: 0, right: width, bottom: height, toJSON: () => ({}) } as DOMRect)
    return el
}

// Mount a tiny harness that owns its element ref (initialised synchronously
// from the prop) and runs the composable in setup(). Exposing `ar` and
// `elRef` lets tests read the aspect ratio and swap the observed element.
function mountWith(target: Element | null) {
    const Harness = defineComponent({
        props: { target: { type: Object as () => Element | null, default: null } },
        setup(props, { expose }) {
            const elRef = ref<Element | null>(props.target)
            const ar = useSvgAspectRatio(elRef)
            expose({ ar, elRef })
            return () => h('div')
        },
    })
    return mount(Harness, { props: { target } })
}

describe('useSvgAspectRatio', () => {
    it('measures the element synchronously on mount and observes it', () => {
        // 200x100 -> aspect ratio 2; immediate watch runs during setup.
        const wrapper = mountWith(makeEl(200, 100))

        expect(wrapper.vm.ar).toBe(2)
        // Exactly one observer was created and it observes the element.
        expect(roInstances).toHaveLength(1)
        expect(roInstances[0].observe).toHaveBeenCalledTimes(1)
        expect(roInstances[0].observe).toHaveBeenCalledWith(wrapper.vm.elRef)
    })

    it('keeps the default 1 when height is 0 (divide-by-zero guard)', () => {
        // height === 0 must not push the value to Infinity; it stays at default 1.
        const wrapper = mountWith(makeEl(200, 0))

        expect(wrapper.vm.ar).toBe(1)
    })

    it('returns the default 1 and creates no observer when there is no element', () => {
        // null element: watch returns early, so no measure and no observer.
        const wrapper = mountWith(null)

        expect(wrapper.vm.ar).toBe(1)
        expect(roInstances).toHaveLength(0)
    })

    it('updates reactively when the ResizeObserver callback fires', async () => {
        // Start at 200x100 (ar=2), then report 100x100 (ar=1) on the next resize.
        const el = makeEl(200, 100)
        const wrapper = mountWith(el)
        expect(wrapper.vm.ar).toBe(2)

        el.getBoundingClientRect = () =>
            ({ width: 100, height: 100, x: 0, y: 0, top: 0, left: 0, right: 100, bottom: 100, toJSON: () => ({}) } as DOMRect)
        roInstances[0].trigger()

        expect(wrapper.vm.ar).toBe(1)

        // End-to-end reactivity check: render the value and assert the DOM updates.
        const ReactiveHarness = defineComponent({
            props: { target: { type: Object as () => Element | null, default: null } },
            setup(props) {
                const elRef = ref<Element | null>(props.target)
                const ar = useSvgAspectRatio(elRef)
                return () => h('span', String(ar.value))
            },
        })
        const square = makeEl(100, 100)
        const w2 = mount(ReactiveHarness, { props: { target: square } })
        expect(w2.text()).toBe('1')
        square.getBoundingClientRect = () =>
            ({ width: 300, height: 100, x: 0, y: 0, top: 0, left: 0, right: 300, bottom: 100, toJSON: () => ({}) } as DOMRect)
        roInstances[1].trigger()
        await nextTick()
        expect(w2.text()).toBe('3')
    })

    it('disconnects the observer on unmount', () => {
        const wrapper = mountWith(makeEl(200, 100))
        expect(roInstances).toHaveLength(1)

        wrapper.unmount()

        expect(roInstances[0].disconnect).toHaveBeenCalled()
    })

    it('still measures once and does not throw when ResizeObserver is unavailable', () => {
        // Simulate the jsdom/SSR path where ResizeObserver is undefined.
        vi.stubGlobal('ResizeObserver', undefined)

        let wrapper: ReturnType<typeof mountWith> | undefined
        expect(() => {
            wrapper = mountWith(makeEl(200, 100))
        }).not.toThrow()

        // A single synchronous measure still ran (200x100 -> 2), but no observer.
        expect(wrapper!.vm.ar).toBe(2)
        expect(roInstances).toHaveLength(0)
    })

    it('re-observes and re-measures when the element ref changes', async () => {
        // Initial element 200x100 (ar=2), observed by instance #0.
        const wrapper = mountWith(makeEl(200, 100))
        expect(wrapper.vm.ar).toBe(2)
        expect(roInstances).toHaveLength(1)

        // Swap in a new 300x100 element (ar=3).
        const next = makeEl(300, 100)
        wrapper.vm.elRef = next
        await nextTick()

        // Old observer is disconnected; a fresh one observes the new element.
        expect(roInstances[0].disconnect).toHaveBeenCalled()
        expect(roInstances).toHaveLength(2)
        expect(roInstances[1].observe).toHaveBeenCalledWith(next)
        expect(wrapper.vm.ar).toBe(3)
    })
})
