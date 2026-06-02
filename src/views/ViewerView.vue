<script setup lang="ts">
import InteractiveFloorplan from '../components/common/InteractiveFloorplan.vue';
import { useFloorplanStore } from '../stores/floorplan';

const store = useFloorplanStore();
</script>

<template>
  <div class="viewer-view">
    <InteractiveFloorplan :config="store.config" :entity-states="store.entityStates"
      :topic-values="store.topicValues"
      @entity-click="(id) => store.toggleEntityState(id)"
      @entity-set-value="(id, topic, value) => store.setNumberValue(id, topic, value)"
      @entity-send="(topic, value) => store.sendButtonValue(topic, value)"
      @entity-toggle="(id, topic, value, nextOn) => store.setToggleValue(id, topic, value, nextOn)"
      @entity-select="(id, topic, value) => store.setSelectValue(id, topic, value)" />
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
