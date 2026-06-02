import { defineStore } from 'pinia';
import { ref, computed, watch } from 'vue';
import type { FloorplanConfig, EntityConfig, EntityState } from '../types/floorplan';
import { v4 as uuidv4 } from 'uuid';
import { saveConfig, sendCommand, publishRaw } from '../utils/api';

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

    // Raw last-known values of configured MQTT read topics (topic -> raw string)
    const topicValues = ref<Record<string, string>>({});

    const entities = computed(() => config.value.entities);
    const selectedEntity = computed(() =>
        config.value.entities.find(e => e.id === selectedEntityId.value)
    );

    // Auto-save config to server with 2-second debounce.
    // Guard against clobbering the server copy: never auto-save until a config has
    // been successfully loaded from the server, and never persist the mutation that
    // loadConfig() itself triggers. Without this, an empty/failed load (the server
    // returns the empty default) gets written straight back, wiping the real config.
    const isLoaded = ref(false);
    let skipNextSave = false;
    let saveTimer: ReturnType<typeof setTimeout> | null = null;
    watch(config, () => {
        if (!isLoaded.value) return;                          // no save before the first successful load
        if (skipNextSave) { skipNextSave = false; return; }   // ignore loadConfig's own mutation
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
                colors: {
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
            },
            ...(type === 'text' ? {
                textConfig: {
                    jsonPath: 'temperature',
                    format: '{}'
                }
            } : {}),
            ...(type === 'number' ? {
                numberConfig: { readTopic: '', writeTopic: '', min: 0, max: 100, step: 1, unit: '', size: 2.5 }
            } : {})
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

    async function toggleEntityState(entityId: string) {
        const current = entityStates.value[entityId] || { state: 'off', brightness: 255 };
        const newStateStr = current.state === 'off' ? 'on' : 'off';

        // Optimistic local update
        entityStates.value[entityId] = {
            state: newStateStr,
            brightness: current.brightness,
            shouldLightUp: newStateStr !== 'off',
        };

        const mqttState = newStateStr === 'on' ? 'ON' : 'OFF';
        sendCommand(entityId, mqttState).catch(e =>
            console.error('Failed to send command:', e)
        );
    }

    async function setNumberValue(entityId: string, writeTopic: string, value: number) {
        // Without a write topic there is nothing to send — don't show a fake optimistic value.
        if (!writeTopic) return;
        const current = entityStates.value[entityId] || { state: 'off', brightness: 255 };
        // Optimistic local update so the stepper reflects the new value immediately
        entityStates.value[entityId] = { ...current, numberValue: value };
        publishRaw(writeTopic, String(value)).catch(e =>
            console.error('Failed to publish value:', e)
        );
    }

    function setEntityState(entityId: string, state: string, rawPayload?: Record<string, unknown>) {
        const current = entityStates.value[entityId] || { state: 'off', brightness: 255 };
        const next: EntityState = {
            ...current,
            state,
            shouldLightUp: state !== 'off' && state !== 'idle',
            ...(rawPayload !== undefined ? { rawPayload } : {}),
        };
        entityStates.value[entityId] = next;
    }

    function setTopicValues(values: Record<string, string>) {
        topicValues.value = values;
        // Reconcile: drop a widget's optimistic value once its read topic reports
        // the SAME value (within epsilon), so it returns to real device state.
        for (const e of config.value.entities) {
            if (e.type !== 'number' || !e.numberConfig) continue;
            const st = entityStates.value[e.entityId];
            if (!st || st.numberValue === undefined) continue;
            const raw = values[e.numberConfig.readTopic];
            if (raw === undefined) continue;
            const n = parseFloat(raw);
            if (Number.isFinite(n) && Math.abs(n - st.numberValue) < 1e-9) {
                entityStates.value[e.entityId] = { ...st, numberValue: undefined };
            }
        }
    }

    function loadConfig(newConfig: FloorplanConfig) {
        // Suppress the auto-save that replacing config.value would otherwise trigger,
        // then mark the store loaded so genuine user edits from here on are persisted.
        skipNextSave = true;
        config.value = newConfig;
        isLoaded.value = true;
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
        topicValues,
        setBaseImage,
        addEntity,
        duplicateEntity,
        removeEntity,
        updateEntity,
        toggleEntityState,
        setNumberValue,
        setEntityState,
        setTopicValues,
        loadConfig,
        clearConfig
    };
});
