import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'

import InteractiveFloorplan from './InteractiveFloorplan.vue'
import type { FloorplanConfig, EntityConfig, EntityState, NumberConfig } from '../../types/floorplan'

// A 1x1 transparent PNG data URI, so `hasImage` is truthy and the canvas renders.
const IMG =
    'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='

function numberEntity(numberConfig: Partial<NumberConfig> = {}, overrides: Partial<EntityConfig> = {}): EntityConfig {
    return {
        id: 'num-1',
        entityId: 'number.thermostat',
        label: 'Thermostat',
        type: 'number',
        x: 50,
        y: 50,
        points: [],
        shape: 'circle',
        style: {
            width: 5,
            height: 5,
            colors: { onColor: '#facc15', offColor: '#94a3b8' },
            onOpacity: 0.8,
            offOpacity: 0.3,
            gradientRadius: 30,
            rotation: 0,
        },
        labelConfig: { show: true, offsetX: 0, offsetY: 10, color: '#ffffff' },
        numberConfig: { readTopic: 'home/r/read', writeTopic: 'home/r/set', min: 0, max: 100, step: 5, unit: '%', size: 2.5, ...numberConfig },
        ...overrides,
    }
}

function lightEntity(overrides: Partial<EntityConfig> = {}): EntityConfig {
    return {
        id: 'light-1',
        entityId: 'light.living_room',
        label: 'Living Room',
        type: 'light',
        x: 30,
        y: 40,
        points: [],
        shape: 'circle',
        style: {
            width: 5,
            height: 5,
            colors: { onColor: '#facc15', offColor: '#94a3b8' },
            onOpacity: 0.8,
            offOpacity: 0.3,
            gradientRadius: 30,
            rotation: 0,
        },
        labelConfig: { show: false, offsetX: 0, offsetY: 10, color: '#ffffff' },
        ...overrides,
    }
}

function makeConfig(entities: EntityConfig[]): FloorplanConfig {
    return { id: 'cfg-1', name: 'Test', imageBase64: IMG, entities }
}

function mountWith(
    entities: EntityConfig[],
    entityStates: Record<string, EntityState> = {},
    topicValues: Record<string, string> = {},
) {
    return mount(InteractiveFloorplan, {
        props: { config: makeConfig(entities), entityStates, topicValues },
    })
}

describe('InteractiveFloorplan — number stepper', () => {
    it('emits entity-set-value with (entityId, writeTopic, nextValue) when clicking "+"', async () => {
        // optimistic value 50, step 5 -> "+" should send 55 to the write topic.
        const entity = numberEntity()
        const wrapper = mountWith([entity], { 'number.thermostat': { state: 'off', numberValue: 50 } })

        // Last button in the stepper is "+" (template order: −, value, +).
        const buttons = wrapper.findAll('.number-stepper button')
        expect(buttons).toHaveLength(2)
        const plus = buttons[1]
        expect(plus.text()).toBe('+')

        await plus.trigger('click')

        const emitted = wrapper.emitted('entity-set-value')
        expect(emitted).toHaveLength(1)
        expect(emitted![0]).toEqual(['number.thermostat', 'home/r/set', 55])
    })

    it('decrements with "−"', async () => {
        const entity = numberEntity()
        const wrapper = mountWith([entity], { 'number.thermostat': { state: 'off', numberValue: 50 } })

        const minus = wrapper.findAll('.number-stepper button')[0]
        expect(minus.text()).toBe('−')
        await minus.trigger('click')

        const emitted = wrapper.emitted('entity-set-value')
        expect(emitted![0]).toEqual(['number.thermostat', 'home/r/set', 45])
    })

    it('emits NOTHING and disables "+" when already at max', async () => {
        // At max (100): "+" is disabled and a click must not emit.
        const entity = numberEntity({ min: 0, max: 100, step: 5 })
        const wrapper = mountWith([entity], { 'number.thermostat': { state: 'off', numberValue: 100 } })

        const plus = wrapper.findAll('.number-stepper button')[1]
        expect((plus.element as HTMLButtonElement).disabled).toBe(true)

        // Even forcing the click handler must yield no emit (computeNextStep -> null).
        await plus.trigger('click')
        expect(wrapper.emitted('entity-set-value')).toBeUndefined()
    })

    it('disables "−" at min', async () => {
        const entity = numberEntity({ min: 0, max: 100, step: 5 })
        const wrapper = mountWith([entity], { 'number.thermostat': { state: 'off', numberValue: 0 } })

        const minus = wrapper.findAll('.number-stepper button')[0]
        expect((minus.element as HTMLButtonElement).disabled).toBe(true)
        await minus.trigger('click')
        expect(wrapper.emitted('entity-set-value')).toBeUndefined()
    })

    it('clamps the "+" step to max and emits the clamped value, not an overshoot', async () => {
        // value 98, step 5, max 100 -> clamp to 100 (not 103).
        const entity = numberEntity({ min: 0, max: 100, step: 5 })
        const wrapper = mountWith([entity], { 'number.thermostat': { state: 'off', numberValue: 98 } })

        await wrapper.findAll('.number-stepper button')[1].trigger('click')
        const emitted = wrapper.emitted('entity-set-value')
        expect(emitted![0]).toEqual(['number.thermostat', 'home/r/set', 100])
    })
})

describe('InteractiveFloorplan — light click vs long-press', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    function lightEl(wrapper: ReturnType<typeof mountWith>): HTMLElement {
        // The outer interactive-entity div carries the pointer handlers.
        return wrapper.find('.interactive-entity').element as HTMLElement
    }

    // @vue/test-utils' trigger() builds a MouseEvent and assigns props after the
    // fact, but `button` is a getter-only property in jsdom. Dispatch a native
    // MouseEvent whose button/clientX/clientY are set via the constructor instead;
    // the handlers only read those three fields, so a MouseEvent is sufficient.
    function dispatchPointer(
        el: HTMLElement,
        type: 'pointerdown' | 'pointerup',
        init: { button: number; clientX: number; clientY: number },
    ) {
        el.dispatchEvent(new MouseEvent(type, { ...init, bubbles: true, cancelable: true }))
    }

    it('a short pointerdown/up emits entity-click (and not long-press)', async () => {
        const wrapper = mountWith([lightEntity()], { 'light.living_room': { state: 'off' } })
        const el = lightEl(wrapper)

        dispatchPointer(el, 'pointerdown', { button: 0, clientX: 100, clientY: 100 })
        // Release well before the 500ms threshold, without moving.
        vi.advanceTimersByTime(100)
        dispatchPointer(el, 'pointerup', { button: 0, clientX: 102, clientY: 101 })
        await wrapper.vm.$nextTick()

        expect(wrapper.emitted('entity-click')).toEqual([['light.living_room']])
        expect(wrapper.emitted('entity-long-press')).toBeUndefined()
    })

    it('a >500ms hold emits entity-long-press and NOT entity-click', async () => {
        const wrapper = mountWith([lightEntity()], { 'light.living_room': { state: 'off' } })
        const el = lightEl(wrapper)

        dispatchPointer(el, 'pointerdown', { button: 0, clientX: 100, clientY: 100 })
        // Cross the 500ms threshold so the timer fires.
        vi.advanceTimersByTime(600)
        dispatchPointer(el, 'pointerup', { button: 0, clientX: 100, clientY: 100 })
        await wrapper.vm.$nextTick()

        expect(wrapper.emitted('entity-long-press')).toEqual([['light.living_room']])
        expect(wrapper.emitted('entity-click')).toBeUndefined()
    })

    it('a non-left (right) button does nothing', async () => {
        const wrapper = mountWith([lightEntity()], { 'light.living_room': { state: 'off' } })
        const el = lightEl(wrapper)

        dispatchPointer(el, 'pointerdown', { button: 2, clientX: 100, clientY: 100 })
        vi.advanceTimersByTime(600)
        dispatchPointer(el, 'pointerup', { button: 2, clientX: 100, clientY: 100 })
        await wrapper.vm.$nextTick()

        expect(wrapper.emitted('entity-click')).toBeUndefined()
        expect(wrapper.emitted('entity-long-press')).toBeUndefined()
    })

    it('a drag (moved >10px) suppresses the click', async () => {
        const wrapper = mountWith([lightEntity()], { 'light.living_room': { state: 'off' } })
        const el = lightEl(wrapper)

        dispatchPointer(el, 'pointerdown', { button: 0, clientX: 100, clientY: 100 })
        vi.advanceTimersByTime(100)
        dispatchPointer(el, 'pointerup', { button: 0, clientX: 130, clientY: 100 })
        await wrapper.vm.$nextTick()

        expect(wrapper.emitted('entity-click')).toBeUndefined()
        expect(wrapper.emitted('entity-long-press')).toBeUndefined()
    })
})
