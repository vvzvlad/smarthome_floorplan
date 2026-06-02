import { describe, it, expect } from 'vitest'
import {
  entityStyle,
  labelTransform,
  brightnessToGradientOpacity,
  brightnessToShapeOpacity,
} from './entityVisual'
import type { EntityConfig } from '../types/floorplan'

function lightEntity(overrides: Partial<EntityConfig> = {}): EntityConfig {
  return {
    id: 'u1',
    entityId: 'light.x',
    label: 'X',
    type: 'light',
    x: 10,
    y: 20,
    shape: 'circle',
    style: {
      width: 5,
      height: 6,
      colors: { onColor: '#ffff00', offColor: '#112233' },
      onOpacity: 0.8,
      offOpacity: 0.4,
      gradientRadius: 15,
      rotation: 30,
    },
    labelConfig: { show: true, offsetX: 0, offsetY: 0, color: '#fff' },
    ...overrides,
  }
}

describe('entityStyle', () => {
  it('light, unselected: transparent border, zIndex 1, offColor, circle radius', () => {
    const s = entityStyle(lightEntity(), false)
    expect(s.left).toBe('10%')
    expect(s.top).toBe('20%')
    expect(s.width).toBe('5%')
    expect(s.height).toBe('6%')
    expect(s.backgroundColor).toBe('#112233')
    expect(s.opacity).toBe(0.4)
    expect(s.transform).toBe('translate(-50%, -50%) rotate(30deg)')
    expect(s.border).toBe('2px solid transparent')
    expect(s.borderRadius).toBe('50%')
    expect(s.zIndex).toBe(1)
  })

  it('light, selected: primary border, zIndex 10', () => {
    const s = entityStyle(lightEntity(), true)
    expect(s.border).toBe('2px solid var(--color-primary)')
    expect(s.zIndex).toBe(10)
  })

  it('square shape -> 4px borderRadius', () => {
    const s = entityStyle(lightEntity({ shape: 'square' }), false)
    expect(s.borderRadius).toBe('4px')
  })

  it('colors object without offColor falls back to #94a3b8', () => {
    const e = lightEntity()
    // simulate a colors object lacking offColor (runtime narrowing path)
    ;(e.style.colors as unknown as Record<string, unknown>) = { onColor: '#abc' }
    const s = entityStyle(e, false)
    expect(s.backgroundColor).toBe('#94a3b8')
  })

  it('text type: transparent background move handle, no width/height', () => {
    const s = entityStyle(lightEntity({ type: 'text' }), false)
    expect(s.background).toBe('transparent')
    expect(s.transform).toBe('translate(-50%, -50%)')
    expect(s.borderRadius).toBe('4px')
    expect(s.width).toBeUndefined()
    expect(s.height).toBeUndefined()
  })

  it('number type: same transparent move handle, selection toggles', () => {
    const s = entityStyle(lightEntity({ type: 'number' }), true)
    expect(s.background).toBe('transparent')
    expect(s.border).toBe('2px solid var(--color-primary)')
    expect(s.zIndex).toBe(10)
  })

  it('button type: same transparent move handle, no width/height', () => {
    const s = entityStyle(lightEntity({ type: 'button' }), false)
    expect(s.background).toBe('transparent')
    expect(s.transform).toBe('translate(-50%, -50%)')
    expect(s.borderRadius).toBe('4px')
    expect(s.width).toBeUndefined()
    expect(s.height).toBeUndefined()
  })
})

describe('labelTransform', () => {
  it('offset 0 vs undefined both yield 0%', () => {
    expect(labelTransform({ offsetX: 0, offsetY: 0, color: '#abc' }).transform)
      .toBe('translate(-50%, -50%) translate(0%, 0%)')
    expect(labelTransform({}).transform)
      .toBe('translate(-50%, -50%) translate(0%, 0%)')
    expect(labelTransform(undefined).transform)
      .toBe('translate(-50%, -50%) translate(0%, 0%)')
  })

  it('non-zero offsets are interpolated', () => {
    expect(labelTransform({ offsetX: 5, offsetY: -3 }).transform)
      .toBe('translate(-50%, -50%) translate(5%, -3%)')
  })

  it('color defaults to #ffffff when missing', () => {
    expect(labelTransform({}).color).toBe('#ffffff')
    expect(labelTransform({ color: '#123456' }).color).toBe('#123456')
  })
})

describe('brightness -> opacity formulas (divergent on purpose)', () => {
  it('gradient: linear (brightness/255)*onOpacity', () => {
    expect(brightnessToGradientOpacity(0, 0.8)).toBe(0)
    expect(brightnessToGradientOpacity(255, 0.8)).toBe(0.8)
    expect(brightnessToGradientOpacity(127.5, 0.8)).toBe(0.4)
  })

  it('gradient: undefined brightness returns onOpacity unchanged', () => {
    expect(brightnessToGradientOpacity(undefined, 0.8)).toBe(0.8)
  })

  it('shape: floors at 0.3, maps to [0.3, onOpacity]', () => {
    expect(brightnessToShapeOpacity(0, 0.8)).toBe(0.3)
    expect(brightnessToShapeOpacity(255, 0.8)).toBe(0.8)
    expect(brightnessToShapeOpacity(127.5, 0.8)).toBeCloseTo(0.55, 10)
  })

  it('shape: undefined brightness returns onOpacity unchanged', () => {
    expect(brightnessToShapeOpacity(undefined, 0.8)).toBe(0.8)
  })

  it('DIVERGENCE: at brightness 0 the two formulas differ (0 vs 0.3 floor)', () => {
    // This documents the deliberate divergence between the gradient and shape
    // opacity formulas in the original InteractiveFloorplan.vue code: the
    // gradient drops to 0 while the shape never goes below 0.3.
    expect(brightnessToGradientOpacity(0, 0.8)).toBe(0)
    expect(brightnessToShapeOpacity(0, 0.8)).toBe(0.3)
    expect(brightnessToGradientOpacity(0, 0.8)).not.toBe(brightnessToShapeOpacity(0, 0.8))
  })
})
