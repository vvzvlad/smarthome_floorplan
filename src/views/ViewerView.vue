<script setup lang="ts">
import InteractiveFloorplan from '../components/common/InteractiveFloorplan.vue';
import { useFloorplanStore } from '../stores/floorplan';

const store = useFloorplanStore();
</script>

<template>
  <div class="viewer-view">
    <InteractiveFloorplan :config="store.config" :entity-states="store.entityStates"
      @entity-click="(id) => store.toggleEntityState(id)" />
  </div>
</template>

<style>
.viewer-view {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
}

</style>
