<script setup lang="ts">
// Glyph of a sensor entity, shared by the viewer (InteractiveFloorplan.vue), the
// editor overlay (EntityOverlay.vue) and the icon preview in PropertiesPanel.vue.
// The uploaded icon is a CSS mask over a box filled with the state colour, so any
// monochrome icon with a transparent background (SVG or PNG) takes the on/off
// colour. Without an icon the glyph is a filled circle in the same colour, so the
// entity stays visible and draggable. Size comes from the config (cqw); a parent
// can override it with an inline font-size.
import { computed } from 'vue';
import type { BinaryColors, SensorConfig } from '../../types/floorplan';
import { sensorIconStyle, isSensorKnown } from '../../utils/sensorWidget';

const props = defineProps<{
  config?: SensorConfig;
  colors: BinaryColors;
  rawPayload?: Record<string, unknown>;
}>();

const look = computed(() =>
  sensorIconStyle(props.rawPayload, props.config?.jsonPath ?? '', props.config?.onValue ?? '', props.colors));
const known = computed(() => isSensorKnown(props.rawPayload, props.config?.jsonPath ?? ''));

const glyphStyle = computed(() => {
  const icon = props.config?.icon;
  if (!icon) return { backgroundColor: look.value.color };
  const mask = `url("${icon}")`;
  return { backgroundColor: look.value.color, maskImage: mask, WebkitMaskImage: mask };
});
</script>

<template>
  <!-- The "unknown" dashed outline is drawn on this unmasked wrapper: on the glyph the mask would clip it. -->
  <div class="sensor-icon" :class="{ unknown: !known }"
    :style="{ fontSize: `${config?.size ?? 2.1}cqw`, opacity: look.opacity, outlineColor: look.color }">
    <div class="sensor-glyph" :class="{ circle: !config?.icon }" :style="glyphStyle"></div>
  </div>
</template>
