import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type { FloorplanConfig, EntityConfig, EntityState } from '../types/floorplan';
import { v4 as uuidv4 } from 'uuid';
import { saveConfig, sendCommand } from '../utils/api';

export const useFloorplanStore = defineStore('floorplan', () => {
    // Config starts empty; loaded from server via App.vue on startup
    const config = ref<FloorplanConfig>({
        id: uuidv4(),
        name: 'New Floorplan',
        imageBase64: '',
        entities: []
    });

    const selectedEntityId = ref<string | null>(null);

    // Runtime device states (entity_id -> state), not persisted in config
    const entityStates = ref<Record<string, EntityState>>({});

    const entities = computed(() => config.value.entities);
    const selectedEntity = computed(() =>
        config.value.entities.find(e => e.id === selectedEntityId.value)
    );

    // Auto-save config to server with 2-second debounce
    let saveTimer: ReturnType<typeof setTimeout> | null = null;
    watch(config, () => {
        if (saveTimer) clearTimeout(saveTimer);
        saveTimer = setTimeout(() => {
            saveConfig(config.value).catch(e => console.error('Auto-save failed:', e));
        }, 2000);
    }, { deep: true });

    function setBaseImage(base64: string) {
        config.value.imageBase64 = base64;
    }

    function addEntity(type: EntityConfig['type'] = 'light', x = 50, y = 50) {
        const id = uuidv4();
        const newEntity: EntityConfig = {
            id,
            entityId: `entity.${id.substring(0, 4)}`,
            label: 'New Entity',
            type,
            x,
            y,
            points: [],
            shape: 'circle',
            style: {
                width: 5,
                height: 5,
                colors: type === 'camera'
                    ? {
                        idleColor: '#6b7280',
                        recordingColor: '#ef4444',
                        streamingColor: '#3b82f6'
                    }
                    : {
                        onColor: '#facc15',
                        offColor: '#94a3b8',
                    },
                onOpacity: 0.8,
                offOpacity: 0.3,
                gradientRadius: 30,
                rotation: 0,
            },
            labelConfig: {
                show: true,
                offsetX: 0,
                offsetY: 10,
                color: '#ffffff',
            }
        };
        config.value.entities.push(newEntity);
        selectedEntityId.value = id;
        entityStates.value[newEntity.entityId] = { state: 'off', brightness: 255 };
    }

    function duplicateEntity(id: string) {
        const entity = config.value.entities.find(e => e.id === id);
        if (!entity) return;
        const newId = uuidv4();
        const clone: EntityConfig = JSON.parse(JSON.stringify(entity));
        clone.id = newId;
        clone.label = clone.label + ' (copy)';
        clone.x = Math.min(clone.x + 3, 97);
        clone.y = Math.min(clone.y + 3, 97);
        config.value.entities.push(clone);
        selectedEntityId.value = newId;
        entityStates.value[clone.entityId] = { state: 'off', brightness: 255 };
    }

    function removeEntity(id: string) {
        const index = config.value.entities.findIndex(e => e.id === id);
        if (index !== -1) {
            config.value.entities.splice(index, 1);
            if (selectedEntityId.value === id) {
                selectedEntityId.value = null;
            }
        }
    }

    function updateEntity(id: string, updates: Partial<EntityConfig>) {
        const entity = config.value.entities.find(e => e.id === id);
        if (entity) {
            Object.assign(entity, updates);
        }
    }

    async function toggleEntityState(entityId: string, entityType: string) {
        const current = entityStates.value[entityId] || { state: 'off', brightness: 255 };
        let newStateStr: string;

        if (entityType === 'camera') {
            if (current.state === 'idle') newStateStr = 'streaming';
            else if (current.state === 'streaming') newStateStr = 'recording';
            else newStateStr = 'idle';
        } else {
            newStateStr = current.state === 'off' ? 'on' : 'off';
        }

        // Optimistic local update
        entityStates.value[entityId] = {
            state: newStateStr,
            brightness: current.brightness,
            shouldLightUp: newStateStr !== 'off' && newStateStr !== 'idle',
        };

        // Send command to server (only for non-camera entities)
        if (entityType !== 'camera') {
            const mqttState = newStateStr === 'on' ? 'ON' : 'OFF';
            sendCommand(entityId, mqttState).catch(e =>
                console.error('Failed to send command:', e)
            );
        }
    }

    function setEntityState(entityId: string, state: string) {
        const current = entityStates.value[entityId] || { state: 'off', brightness: 255 };
        entityStates.value[entityId] = {
            ...current,
            state,
            shouldLightUp: state !== 'off' && state !== 'idle',
        };
    }

    function loadConfig(newConfig: FloorplanConfig) {
        config.value = newConfig;
        // Reset runtime states
        entityStates.value = {};
        newConfig.entities.forEach(e => {
            entityStates.value[e.entityId] = { state: 'off', brightness: 255 };
        });
    }

    function clearConfig() {
        config.value = {
            id: uuidv4(),
            name: 'New Floorplan',
            imageBase64: '',
            entities: []
        };
        selectedEntityId.value = null;
        entityStates.value = {};
    }

    return {
        config,
        entities,
        selectedEntityId,
        selectedEntity,
        entityStates,
        setBaseImage,
        addEntity,
        duplicateEntity,
        removeEntity,
        updateEntity,
        toggleEntityState,
        setEntityState,
        loadConfig,
        clearConfig
    };
});
