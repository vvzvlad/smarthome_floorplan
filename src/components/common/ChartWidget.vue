<script setup lang="ts">
// Line chart of one value over the last 24 hours, shared by the viewer
// (InteractiveFloorplan.vue) and the editor overlay (EntityOverlay.vue). The
// history comes from /api/chart (InfluxDB, 5-minute averages); it is fetched on
// mount, whenever the widget's source changes and every 5 minutes. Width comes
// from the parent (in % of the floorplan), the height follows from the 5:2 shape.
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { ChartConfig } from '../../types/floorplan';
import { fetchChart } from '../../utils/api';
import {
  chartRequestParams, chartRange, chartPolylinePoints, chartTimeTicks, formatChartValue,
  CHART_VIEW_W, CHART_VIEW_H, type ChartPoint,
} from '../../utils/chartWidget';

const REFRESH_MS = 5 * 60 * 1000;

const props = defineProps<{
  config?: ChartConfig;
  entityId: string;
}>();

const points = ref<ChartPoint[]>([]);
// The moment the points were fetched: the right edge of the time axis.
const nowS = ref(Date.now() / 1000);

// Serialized, so editing an unrelated field (format, width) does not refetch.
const requestKey = computed(() => JSON.stringify(chartRequestParams(props.config, props.entityId)));

// Number of the latest request: an older response that arrives later is dropped.
let requestSeq = 0;

async function load() {
  const seq = ++requestSeq;
  const params = chartRequestParams(props.config, props.entityId);
  if (!params) {
    points.value = [];
    return;
  }
  try {
    const result = await fetchChart(params);
    if (seq !== requestSeq) return;
    nowS.value = Date.now() / 1000;
    points.value = result;
  } catch {
    // A failed request shows "No data": the old points may belong to a source the widget no longer has.
    if (seq === requestSeq) points.value = [];
  }
}

watch(requestKey, load);

let timer: number | null = null;
onMounted(() => {
  load();
  timer = window.setInterval(load, REFRESH_MS);
});
onUnmounted(() => {
  if (timer !== null) clearInterval(timer);
});

const range = computed(() => chartRange(points.value));
const line = computed(() => chartPolylinePoints(points.value, nowS.value));
const ticks = computed(() => chartTimeTicks(nowS.value));
// Half a tick label in % of the widget width: "HH:00" at 0.8cqw monospace is about 2.4cqw
// wide and the widget is config.width cqw. A tick closer to an edge would have its label cut
// by the box, so only its grid line is drawn.
const tickLabelMargin = computed(() => (1.2 / (props.config?.width || 15)) * 100);
const format = computed(() => props.config?.format ?? '{}');
</script>

<template>
  <div class="chart-widget">
    <template v-if="range">
      <svg :viewBox="`0 0 ${CHART_VIEW_W} ${CHART_VIEW_H}`" preserveAspectRatio="none" aria-hidden="true">
        <line v-for="t in ticks" :key="t.label" class="chart-grid" :x1="t.x" :x2="t.x" y1="0" :y2="CHART_VIEW_H" />
        <polyline :points="line" />
      </svg>
      <template v-for="t in ticks" :key="t.label">
        <span v-if="t.x > tickLabelMargin && t.x < CHART_VIEW_W - tickLabelMargin"
          class="chart-tick" :style="{ left: `${t.x}%` }">{{ t.label }}</span>
      </template>
      <span class="chart-label chart-max">{{ formatChartValue(format, range.max) }}</span>
      <span class="chart-label chart-min">{{ formatChartValue(format, range.min) }}</span>
    </template>
    <span v-else class="chart-empty">No data</span>
  </div>
</template>
