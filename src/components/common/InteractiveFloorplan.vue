<script setup lang="ts">
import type { FloorplanConfig, EntityState, BinaryColors, EntityConfig } from '../../types/floorplan';
import { computed, ref, useTemplateRef } from 'vue';
import { formatTextValue } from '../../utils/textEntity';
import {
  resolveNumberValue,
  computeNextStep,
  isAtMin,
  isAtMax,
  formatNumberDisplay,
} from '../../utils/numberWidget';
import { formatButtonLabel } from '../../utils/buttonWidget';
import { resolveToggleState } from '../../utils/toggleWidget';
import { resolveSelectValue } from '../../utils/selectWidget';
import { brightnessToGradientOpacity, brightnessToShapeOpacity } from '../../utils/entityVisual';
import { useSvgAspectRatio } from '../../utils/useSvgAspectRatio';

const props = defineProps<{
    config: FloorplanConfig,
    entityStates: Record<string, EntityState>,
    topicValues: Record<string, string>,
}>();

const emit = defineEmits<{
    (e: 'entity-click', entityId: string): void
    (e: 'entity-long-press', entityId: string): void
    (e: 'entity-set-value', entityId: string, writeTopic: string, value: number): void
    (e: 'entity-send', topic: string, value: string): void
    (e: 'entity-toggle', entityId: string, writeTopic: string, value: string, nextOn: boolean): void
    (e: 'entity-select', entityId: string, writeTopic: string, value: string): void
}>();

const hasImage = computed(() => !!props.config.imageBase64);
const svgEl = useTemplateRef<SVGSVGElement>('svgOverlay');
const aspectRatio = useSvgAspectRatio(svgEl);

// Long Press Logic
const longPressTimer = ref<number | null>(null);
const isLongPress = ref(false);
const pointerStart = ref({ x: 0, y: 0 });

function handlePointerDown(event: PointerEvent, entity: any) {
    if (event.button !== 0) return; // Only left click
    isLongPress.value = false;
    pointerStart.value = { x: event.clientX, y: event.clientY };

    longPressTimer.value = window.setTimeout(() => {
        isLongPress.value = true;
        emit('entity-long-press', entity.entityId);
    }, 500); // 500ms threshold
}

function handlePointerUp(event: PointerEvent, entity: any) {
    if (longPressTimer.value) {
        clearTimeout(longPressTimer.value);
        longPressTimer.value = null;
    }

    if (!isLongPress.value) {
        // Check if moved significantly (drag check)
        const dx = Math.abs(event.clientX - pointerStart.value.x);
        const dy = Math.abs(event.clientY - pointerStart.value.y);
        if (dx < 10 && dy < 10) {
            emit('entity-click', entity.entityId);
        }
    }
    isLongPress.value = false;
}

function handlePointerLeave() {
    if (longPressTimer.value) {
        clearTimeout(longPressTimer.value);
        longPressTimer.value = null;
    }
}

function getEntityValues(entity: any) {
    const state = props.entityStates[entity.entityId] || { state: 'off' };
    const { style } = entity;
    const colors = style.colors as BinaryColors;

    if (state.state == 'off') {
        return {
            color: colors.offColor,
            opacity: style.offOpacity
        };
    }

    const color = colors.onColor;
    // Map brightness 0-255 to 0-1, multiplied by the configured max opacity.
    const opacity = brightnessToGradientOpacity(state.brightness, style.onOpacity);

    return { color, opacity };
}

function getEntityPositionStyle(entity: any) {
    const { style, x, y } = entity;
    return {
        left: `${x}%`,
        top: `${y}%`,
        width: `${style.width}%`,
        height: `${style.height}%`,
        transform: `translate(-50%, -50%) rotate(${style.rotation}deg)`,
        position: 'absolute' as const,
        zIndex: 1
    };
}

function getEntityVisualStyle(entity: any) {
    const { color, opacity } = getEntityValues(entity);
    const { shape } = entity;
    const state = props.entityStates[entity.entityId] || { state: 'off' };

    // Ensure minimum visibility for low brightness if ON
    // If Opacity is 0.8, and brightness is 1/255, we want at least say 0.1 or 0.2
    // Map 0-255 brightness to range [0.3, style.onOpacity]; only when ON with a
    // known brightness, otherwise keep the opacity from getEntityValues.
    let effectiveOpacity = opacity;
    if (state.state == 'on' && state.brightness !== undefined) {
        effectiveOpacity = brightnessToShapeOpacity(state.brightness, entity.style.onOpacity);
    }

    return {
        width: '100%',
        height: '100%',
        backgroundColor: color,
        opacity: effectiveOpacity,
        borderRadius: shape === 'circle' ? '50%' : '4px',
        cursor: 'pointer',
        boxShadow: state.state == 'on' ? `0 0 15px ${color}` : 'none',
        transition: 'all 0.3s ease'
    };
}

function getLabelStyle(entity: any) {
    const { offsetX, offsetY, color } = entity.labelConfig || {};
    return {
        transform: `translate(-50%, -50%) translate(${offsetX || 0}%, ${offsetY || 0}%)`,
        color: color || '#ffffff',
        pointerEvents: 'auto' as const,
        cursor: 'pointer' as const
    };
}

function getPointsString(points: { x: number, y: number }[]) {
    return points.map(p => `${p.x} ${p.y}`).join(',');
}

function getTextValue(entity: EntityConfig): string {
    if (!entity.textConfig) return '';
    const { jsonPath, format } = entity.textConfig;
    return formatTextValue(format, props.entityStates[entity.entityId]?.rawPayload, jsonPath);
}

function getTextPositionStyle(entity: EntityConfig) {
    const size = entity.textConfig?.size ?? 1.8;
    return {
        left: `${entity.x}%`,
        top: `${entity.y}%`,
        position: 'absolute' as const,
        transform: 'translate(-50%, -50%)',
        zIndex: 1,
        fontSize: `${size}cqw`,
    };
}

function getNumberValue(entity: EntityConfig): number {
  const cfg = entity.numberConfig;
  if (!cfg) return 0;
  const st = props.entityStates[entity.entityId];
  return resolveNumberValue(st?.numberValue, props.topicValues[cfg.readTopic], cfg.min);
}

function stepNumber(entity: EntityConfig, dir: 1 | -1) {
  // Thin wrapper: read the current value, delegate the clamped arithmetic to
  // computeNextStep, and emit only when it returns a non-null new value.
  const cfg = entity.numberConfig;
  if (!cfg) return;
  const next = computeNextStep(getNumberValue(entity), dir, cfg);
  if (next === null) return;
  emit('entity-set-value', entity.entityId, cfg.writeTopic, next);
}

function getNumberDisplay(entity: EntityConfig): string {
    const cfg = entity.numberConfig;
    if (!cfg) return '';
    return formatNumberDisplay(getNumberValue(entity), cfg.unit);
}

function getNumberPositionStyle(entity: EntityConfig) {
  const size = entity.numberConfig?.size ?? 2.5;
  return {
    left: `${entity.x}%`,
    top: `${entity.y}%`,
    position: 'absolute' as const,
    transform: 'translate(-50%, -50%)',
    zIndex: 2,
    fontSize: `${size}cqw`,
  };
}

function getButtonLabel(entity: EntityConfig): string {
  if (!entity.buttonConfig) return '';
  return formatButtonLabel(entity.buttonConfig.text, entity.label);
}

function getButtonPositionStyle(entity: EntityConfig) {
  const size = entity.buttonConfig?.size ?? 2.5;
  return {
    left: `${entity.x}%`,
    top: `${entity.y}%`,
    position: 'absolute' as const,
    transform: 'translate(-50%, -50%)',
    zIndex: 2,
    fontSize: `${size}cqw`,
  };
}

function sendButton(entity: EntityConfig) {
  const cfg = entity.buttonConfig;
  if (!cfg) return;
  emit('entity-send', cfg.topic, cfg.value);
}

function getToggleState(entity: EntityConfig): boolean {
  const cfg = entity.toggleConfig;
  if (!cfg) return false;
  const st = props.entityStates[entity.entityId];
  return resolveToggleState(st?.toggleOn, props.topicValues[cfg.readTopic], cfg.onValue);
}

function getTogglePositionStyle(entity: EntityConfig) {
  const size = entity.toggleConfig?.size ?? 2.5;
  return {
    left: `${entity.x}%`,
    top: `${entity.y}%`,
    position: 'absolute' as const,
    transform: 'translate(-50%, -50%)',
    zIndex: 2,
    fontSize: `${size}cqw`,
  };
}

function toggleEntity(entity: EntityConfig) {
  const cfg = entity.toggleConfig;
  if (!cfg) return;
  const nextOn = !getToggleState(entity);
  emit('entity-toggle', entity.entityId, cfg.writeTopic, nextOn ? cfg.onValue : cfg.offValue, nextOn);
}

function getSelectValue(entity: EntityConfig): string | undefined {
  const cfg = entity.selectConfig;
  if (!cfg) return undefined;
  const st = props.entityStates[entity.entityId];
  return resolveSelectValue(st?.selectValue, props.topicValues[cfg.readTopic]);
}

function getSelectPositionStyle(entity: EntityConfig) {
  const size = entity.selectConfig?.size ?? 2.5;
  return {
    left: `${entity.x}%`,
    top: `${entity.y}%`,
    position: 'absolute' as const,
    transform: 'translate(-50%, -50%)',
    zIndex: 2,
    fontSize: `${size}cqw`,
  };
}

function selectOption(entity: EntityConfig, value: string) {
  const cfg = entity.selectConfig;
  if (!cfg) return;
  emit('entity-select', entity.entityId, cfg.writeTopic, value);
}

function atMin(entity: EntityConfig): boolean {
  const c = entity.numberConfig;
  if (!c) return false;
  return isAtMin(getNumberValue(entity), c.min, c.max);
}
function atMax(entity: EntityConfig): boolean {
  const c = entity.numberConfig;
  if (!c) return false;
  return isAtMax(getNumberValue(entity), c.min, c.max);
}

</script>

<template>
    <div class="viewer-area">
        <div v-if="!hasImage" class="empty-state">
            <p>No floorplan loaded. Go to Editor to set up.</p>
        </div>

        <div v-else class="canvas-container">
            <div class="image-wrapper">
                <img :src="props.config.imageBase64" alt="Floorplan Base" draggable="false" />

                <svg ref="svgOverlay" class="overlay-layer" viewBox="0 0 100 100" preserveAspectRatio="none">
                    <defs>
                        <radialGradient v-for="entity in props.config.entities.filter(e => e.type === 'light')" :key="'grad-' + entity.id"
                            :id="'grad-' + entity.id" gradientUnits="userSpaceOnUse" :cx="entity.x" :cy="entity.y"
                            :r="entity.style.gradientRadius"
                            :gradientTransform="`translate(${entity.x}, ${entity.y}) scale(1, ${aspectRatio}) translate(${-entity.x}, ${-entity.y})`">
                            <stop offset="0%" :stop-color="getEntityValues(entity).color"
                                :stop-opacity="Math.max(0.3, getEntityValues(entity).opacity)" />
                            <stop offset="100%" :stop-color="getEntityValues(entity).color" stop-opacity="0" />
                        </radialGradient>
                        <clipPath v-for="entity in props.config.entities.filter(e => e.type === 'light')" :key="'clip-' + entity.id"
                            :id="'clip-' + entity.id">
                            <polygon :points="getPointsString(entity.points || [])" />
                        </clipPath>
                    </defs>
                    <ellipse v-for="entity in props.config.entities.filter(e => e.type === 'light')" :key="'poly-' + entity.id"
                        :cx="entity.x" :cy="entity.y"
                        :rx="entity.style.gradientRadius" :ry="entity.style.gradientRadius * aspectRatio"
                        :fill="props.entityStates[entity.entityId]?.shouldLightUp ? `url(#grad-${entity.id})` : 'transparent'"
                        :clip-path="entity.points && entity.points.length > 0 ? `url(#clip-${entity.id})` : undefined"
                        stroke="none" style="pointer-events: none; transition: fill-opacity 0.3s ease;" />
                </svg>

                <!-- Light entities -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'light')" :key="entity.id" class="interactive-entity"
                    :style="getEntityPositionStyle(entity)" @pointerdown="handlePointerDown($event, entity)"
                    @pointerup="handlePointerUp($event, entity)" @pointerleave="handlePointerLeave()"
                    :title="entity.label">
                    <div class="entity-shape"
                        :style="getEntityVisualStyle(entity)"></div>
                    <div v-if="entity.labelConfig.show && entity.label" class="entity-label" :style="getLabelStyle(entity)"
                        @pointerdown.stop="handlePointerDown($event, entity)"
                        @pointerup.stop="handlePointerUp($event, entity)" @pointerleave.stop="handlePointerLeave()">
                        {{ entity.label }}
                    </div>
                </div>

                <!-- Text entities -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'text')" :key="entity.id"
                    :style="getTextPositionStyle(entity)" class="text-entity">
                    {{ getTextValue(entity) }}
                </div>

                <!-- Number stepper widgets -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'number')" :key="entity.id"
                    class="number-stepper" :style="getNumberPositionStyle(entity)" :title="entity.label">
                    <button class="number-btn" :disabled="atMin(entity)" @click.stop="stepNumber(entity, -1)">−</button>
                    <span class="number-value">{{ getNumberDisplay(entity) }}</span>
                    <button class="number-btn" :disabled="atMax(entity)" @click.stop="stepNumber(entity, 1)">+</button>
                </div>

                <!-- Button widgets -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'button')" :key="entity.id"
                    class="button-widget" :style="getButtonPositionStyle(entity)" :title="entity.label">
                    <button class="button-widget-btn" @click.stop="sendButton(entity)">{{ getButtonLabel(entity) }}</button>
                </div>

                <!-- Toggle switches -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'toggle')" :key="entity.id"
                    class="toggle-switch" :class="{ on: getToggleState(entity) }"
                    :style="getTogglePositionStyle(entity)" :title="entity.label"
                    role="switch" :aria-checked="getToggleState(entity)"
                    @click.stop="toggleEntity(entity)">
                    <span class="toggle-knob"></span>
                </div>

                <!-- Multi switches (segmented mode selector) -->
                <div v-for="entity in props.config.entities.filter(e => e.type === 'select')" :key="entity.id"
                    class="multi-switch" :style="getSelectPositionStyle(entity)" :title="entity.label">
                    <button v-for="(opt, i) in entity.selectConfig?.options ?? []" :key="i"
                        class="multi-switch-btn" :class="{ active: getSelectValue(entity) === opt.value }"
                        @click.stop="selectOption(entity, opt.value)">{{ opt.label }}</button>
                </div>
            </div>
        </div>
    </div>
</template>

<style scoped>
/* Styles moved to parent component to ensure Shadow DOM injection in CE mode */
</style>
