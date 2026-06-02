<script setup lang="ts">
import { computed, ref } from 'vue';
import type { EntityConfig } from '../../types/floorplan';
import { useFloorplanStore } from '../../stores/floorplan';
import { formatTextValue } from '../../utils/textEntity';
import { dragDeltaPercent } from '../../utils/coords';
import { resolveNumberValue, formatNumberDisplay } from '../../utils/numberWidget';
import { formatButtonLabel } from '../../utils/buttonWidget';
import { resolveToggleState } from '../../utils/toggleWidget';
import { entityStyle, labelTransform } from '../../utils/entityVisual';

const props = defineProps<{
  entity: EntityConfig
}>();

const store = useFloorplanStore();
const isSelected = computed(() => store.selectedEntityId === props.entity.id);

// Drag logic
const isDragging = ref(false);
const dragStart = ref({ x: 0, y: 0 });

const isLabelDragging = ref(false);
const labelDragStart = ref({ x: 0, y: 0 });

// We need to calculate % movement based on parent size. 
// Since we don't have easy access to parent ref here without inject/props, 
// we'll rely on event.target.offsetParent to get dimensions.

function onMouseDown(event: MouseEvent) {
  event.stopPropagation();
  store.selectedEntityId = props.entity.id;

  isDragging.value = true;
  dragStart.value = { x: event.clientX, y: event.clientY };

  window.addEventListener('mousemove', onMouseMove);
  window.addEventListener('mouseup', onMouseUp);
}

function onMouseMove(event: MouseEvent) {
  if (!isDragging.value) return;

  // Calculate percentage change. We need the container dimensions; assume the
  // entity's parent is the .image-wrapper. dragDeltaPercent now guards against
  // zero dimensions (see coords.ts), which makes this previously-unguarded path
  // safe from divide-by-zero.
  const container = document.querySelector('.image-wrapper');
  if (!container) return;

  const rect = container.getBoundingClientRect();
  const { dxPercent, dyPercent } = dragDeltaPercent(
    { x: event.clientX, y: event.clientY },
    dragStart.value,
    rect,
  );

  store.updateEntity(props.entity.id, {
    x: props.entity.x + dxPercent,
    y: props.entity.y + dyPercent
  });

  dragStart.value = { x: event.clientX, y: event.clientY };
}

function onMouseUp() {
  isDragging.value = false;
  window.removeEventListener('mousemove', onMouseMove);
  window.removeEventListener('mouseup', onMouseUp);
}

// Touch Logic
function onTouchStart(event: TouchEvent) {
  event.stopPropagation();
  // Prevent scrolling if we are starting a drag
  // event.preventDefault(); 

  store.selectedEntityId = props.entity.id;

  const touch = event.touches[0];
  if (!touch) return;

  isDragging.value = true;
  dragStart.value = { x: touch.clientX, y: touch.clientY };

  window.addEventListener('touchmove', onTouchMove, { passive: false });
  window.addEventListener('touchend', onTouchEnd);
}

function onTouchMove(event: TouchEvent) {
  if (!isDragging.value) return;
  event.preventDefault(); // Stop scrolling

  const touch = event.touches[0];
  if (!touch) return;

  const container = document.querySelector('.image-wrapper');
  if (!container) return;

  const rect = container.getBoundingClientRect();
  const { dxPercent, dyPercent } = dragDeltaPercent(
    { x: touch.clientX, y: touch.clientY },
    dragStart.value,
    rect,
  );

  store.updateEntity(props.entity.id, {
    x: props.entity.x + dxPercent,
    y: props.entity.y + dyPercent
  });

  dragStart.value = { x: touch.clientX, y: touch.clientY };
}

function onTouchEnd() {
  isDragging.value = false;
  window.removeEventListener('touchmove', onTouchMove);
  window.removeEventListener('touchend', onTouchEnd);
}




// Label Drag Logic
const labelRef = ref<HTMLElement | null>(null);

function onLabelMouseDown(event: MouseEvent) {
  event.stopPropagation(); // Don't drag entity
  store.selectedEntityId = props.entity.id;
  isLabelDragging.value = true;
  labelDragStart.value = { x: event.clientX, y: event.clientY };
  window.addEventListener('mousemove', onLabelMouseMove);
  window.addEventListener('mouseup', onLabelMouseUp);
}

function onLabelMouseMove(event: MouseEvent) {
  if (!isLabelDragging.value || !labelRef.value) return;

  // Calculate percentage change based on LABEL dimensions. dragDeltaPercent
  // guards against zero dimensions (yields a 0 delta), so the explicit
  // zero-dimension early return is no longer needed: a zero size leaves the
  // offset unchanged just as before.
  const rect = labelRef.value.getBoundingClientRect();
  const { dxPercent, dyPercent } = dragDeltaPercent(
    { x: event.clientX, y: event.clientY },
    labelDragStart.value,
    rect,
  );

  // Update labelConfig offset
  const currentConfig = props.entity.labelConfig;
  store.updateEntity(props.entity.id, {
    labelConfig: {
      ...currentConfig,
      offsetX: (currentConfig.offsetX || 0) + dxPercent,
      offsetY: (currentConfig.offsetY || 0) + dyPercent
    }
  });

  labelDragStart.value = { x: event.clientX, y: event.clientY };
}

function onLabelMouseUp() {
  isLabelDragging.value = false;
  window.removeEventListener('mousemove', onLabelMouseMove);
  window.removeEventListener('mouseup', onLabelMouseUp);
}

function onLabelTouchStart(event: TouchEvent) {
  event.stopPropagation();
  store.selectedEntityId = props.entity.id;
  const touch = event.touches[0];
  if (!touch) return;

  isLabelDragging.value = true;
  labelDragStart.value = { x: touch.clientX, y: touch.clientY };
  window.addEventListener('touchmove', onLabelTouchMove, { passive: false });
  window.addEventListener('touchend', onLabelTouchEnd);
}

function onLabelTouchMove(event: TouchEvent) {
  if (!isLabelDragging.value || !labelRef.value) return;
  event.preventDefault();
  const touch = event.touches[0];
  if (!touch) return;

  // dragDeltaPercent guards zero dimensions (yields a 0 delta), replacing the
  // former explicit zero-dimension early return.
  const rect = labelRef.value.getBoundingClientRect();
  const { dxPercent, dyPercent } = dragDeltaPercent(
    { x: touch.clientX, y: touch.clientY },
    labelDragStart.value,
    rect,
  );

  const currentConfig = props.entity.labelConfig;
  store.updateEntity(props.entity.id, {
    labelConfig: {
      ...currentConfig,
      offsetX: (currentConfig.offsetX || 0) + dxPercent,
      offsetY: (currentConfig.offsetY || 0) + dyPercent
    }
  });

  labelDragStart.value = { x: touch.clientX, y: touch.clientY };
}

function onLabelTouchEnd() {
  isLabelDragging.value = false;
  window.removeEventListener('touchmove', onLabelTouchMove);
  window.removeEventListener('touchend', onLabelTouchEnd);
}

// Style computation
const styleObject = computed(() => entityStyle(props.entity, isSelected.value));

const labelStyle = computed(() => labelTransform(props.entity.labelConfig));

const textValue = computed(() => {
  if (props.entity.type !== 'text' || !props.entity.textConfig) return '';
  const { jsonPath, format } = props.entity.textConfig;
  return formatTextValue(format, store.entityStates[props.entity.entityId]?.rawPayload, jsonPath);
});

const numberDisplay = computed(() => {
  if (props.entity.type !== 'number' || !props.entity.numberConfig) return '';
  const cfg = props.entity.numberConfig;
  const st = store.entityStates[props.entity.entityId];
  const val = resolveNumberValue(st?.numberValue, store.topicValues[cfg.readTopic], cfg.min);
  return formatNumberDisplay(val, cfg.unit);
});

const numberSize = computed(() => `${props.entity.numberConfig?.size ?? 2.5}cqw`);

const buttonLabel = computed(() => {
  if (props.entity.type !== 'button' || !props.entity.buttonConfig) return '';
  return formatButtonLabel(props.entity.buttonConfig.text, props.entity.label);
});
const buttonSize = computed(() => `${props.entity.buttonConfig?.size ?? 2.5}cqw`);

const toggleOn = computed(() => {
  if (props.entity.type !== 'toggle' || !props.entity.toggleConfig) return false;
  const cfg = props.entity.toggleConfig;
  const st = store.entityStates[props.entity.entityId];
  return resolveToggleState(st?.toggleOn, store.topicValues[cfg.readTopic], cfg.onValue);
});
const toggleSize = computed(() => `${props.entity.toggleConfig?.size ?? 2.5}cqw`);

</script>

<template>
  <div ref="overlayRef" class="entity-overlay" :style="styleObject" @mousedown="onMouseDown" @touchstart="onTouchStart"
    @click.stop>
    <!-- Text entity: show formatted value as a pill -->
    <div v-if="entity.type === 'text'" class="text-entity" style="pointer-events: none; cursor: default;">
      {{ textValue }}
    </div>
    <!-- Number entity: non-interactive stepper preview for placement -->
    <div v-else-if="entity.type === 'number'" class="number-stepper"
      :style="{ fontSize: numberSize, pointerEvents: 'none' }">
      <span class="number-btn">−</span>
      <span class="number-value">{{ numberDisplay }}</span>
      <span class="number-btn">+</span>
    </div>
    <!-- Button entity: non-interactive button preview for placement -->
    <div v-else-if="entity.type === 'button'" class="button-widget"
      :style="{ fontSize: buttonSize, pointerEvents: 'none' }">
      <span class="button-widget-btn">{{ buttonLabel }}</span>
    </div>
    <!-- Toggle entity: non-interactive switch preview for placement -->
    <div v-else-if="entity.type === 'toggle'" class="toggle-switch" :class="{ on: toggleOn }"
      :style="{ fontSize: toggleSize, pointerEvents: 'none' }">
      <span class="toggle-knob"></span>
    </div>
    <!-- Light entity: show label if enabled -->
    <div v-else-if="entity.labelConfig.show" ref="labelRef" class="entity-label" :style="labelStyle"
      @mousedown="onLabelMouseDown" @touchstart="onLabelTouchStart" @click.stop>
      {{ entity.label }}
    </div>
  </div>
</template>

<style scoped>
.entity-overlay {
  box-sizing: border-box;
  transition: border-color 0.2s;
}

.entity-label {
  position: absolute;
  top: 50%;
  left: 50%;
  /* transform handled incorrectly inline */
  background: rgba(0, 0, 0, 0.7);
  padding: 2px 4px;
  border-radius: 4px;
  white-space: nowrap;
  pointer-events: auto;
  cursor: grab;
  line-height: 1.2;
}

.entity-label:active {
  cursor: grabbing;
}
</style>
