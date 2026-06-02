// Pure presentational helpers for entities. Extracted from EntityOverlay.vue
// (editor) and InteractiveFloorplan.vue (viewer) so the inline-style math and
// the brightness->opacity formulas can be unit-tested independently.

import type { EntityConfig, LabelConfig } from '../types/floorplan';

/**
 * Build the inline style object for an entity overlay in the editor. Mirrors
 * EntityOverlay.vue's styleObject exactly:
 *  - text/number/button entities render the same transparent, bordered move
 *    handle,
 *  - light entities use the offColor (with a '#94a3b8' fallback when the colors
 *    object lacks an offColor), a circle/square borderRadius, opacity, rotation,
 *  - selection toggles the border color and zIndex.
 */
export function entityStyle(
  entity: Pick<EntityConfig, 'shape' | 'style' | 'x' | 'y' | 'type'>,
  isSelected: boolean,
): Record<string, string | number> {
  const { shape, style, x, y, type } = entity;

  if (type === 'text' || type === 'number' || type === 'button') {
    return {
      left: `${x}%`,
      top: `${y}%`,
      position: 'absolute' as const,
      transform: 'translate(-50%, -50%)',
      border: isSelected ? '2px solid var(--color-primary)' : '2px solid transparent',
      borderRadius: '4px',
      cursor: 'move',
      zIndex: isSelected ? 10 : 1,
      background: 'transparent',
    };
  }

  // Safely access offColor from union type.
  let backgroundColor = '#94a3b8'; // default
  const colors = style.colors as unknown as Record<string, unknown>;
  if (colors && 'offColor' in colors) {
    backgroundColor = colors.offColor as string;
  }

  return {
    left: `${x}%`,
    top: `${y}%`,
    width: `${style.width}%`,
    height: `${style.height}%`,
    backgroundColor,
    opacity: style.offOpacity,
    transform: `translate(-50%, -50%) rotate(${style.rotation}deg)`,
    position: 'absolute' as const,
    border: isSelected ? '2px solid var(--color-primary)' : '2px solid transparent',
    borderRadius: shape === 'circle' ? '50%' : '4px',
    cursor: 'move',
    zIndex: isSelected ? 10 : 1,
  };
}

/**
 * Build the transform/color style for an entity label. Mirrors the labelStyle
 * computed in EntityOverlay.vue: missing offsets default to 0, missing color to
 * '#ffffff'.
 */
export function labelTransform(
  labelConfig: Partial<LabelConfig> | undefined,
): { transform: string; color: string } {
  const { offsetX, offsetY, color } = labelConfig || {};
  return {
    transform: `translate(-50%, -50%) translate(${offsetX || 0}%, ${offsetY || 0}%)`,
    color: color || '#ffffff',
  };
}

/**
 * Brightness->opacity for the SVG light gradient (viewer, getEntityValues).
 * Linear map: (brightness / 255) * onOpacity. When brightness is undefined the
 * full onOpacity is returned unchanged.
 *
 * NOTE: this formula intentionally DIFFERS from brightnessToShapeOpacity below
 * (which floors at 0.3). The divergence is preserved exactly as in the original
 * InteractiveFloorplan.vue code; the two are NOT unified.
 */
export function brightnessToGradientOpacity(
  brightness: number | undefined,
  onOpacity: number,
): number {
  if (brightness === undefined) return onOpacity;
  return (brightness / 255) * onOpacity;
}

/**
 * Brightness->opacity for the entity SHAPE fill (viewer, getEntityVisualStyle).
 * Maps brightness into [0.3, onOpacity] so a dim-but-on light stays visible:
 * 0.3 + (brightness/255) * (onOpacity - 0.3). When brightness is undefined the
 * onOpacity is returned unchanged.
 *
 * NOTE: this floors at 0.3, unlike brightnessToGradientOpacity. The divergence
 * is preserved exactly as in the original code; the two are NOT unified.
 */
export function brightnessToShapeOpacity(
  brightness: number | undefined,
  onOpacity: number,
): number {
  if (brightness === undefined) return onOpacity;
  const minOpacity = 0.3;
  const brightnessFactor = brightness / 255;
  return minOpacity + brightnessFactor * (onOpacity - minOpacity);
}
