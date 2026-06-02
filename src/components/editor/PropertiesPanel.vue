<script setup lang="ts">
import { useFloorplanStore } from '../../stores/floorplan';
import { computed, ref, onMounted } from 'vue';
import { fetchDevices, getIconStatus, uploadIcon, deleteIcon } from '../../utils/api';
import { resizeImageToPng, imageDownloadFilename } from '../../utils/image';
import { filterDevices, parseNumberField, defaultTextConfig, defaultNumberConfig, defaultButtonConfig, defaultToggleConfig } from '../../utils/entityForm';
const store = useFloorplanStore();


const hasSelection = computed(() => !!store.selectedEntityId);
const selectedEntity = computed(() => store.selectedEntity);

function addEntity() {
    store.addEntity('light');
}

function addTextEntity() {
    store.addEntity('text');
}

function addNumberEntity() {
    store.addEntity('number');
}

function addButtonEntity() {
    store.addEntity('button');
}

function addToggleEntity() {
    store.addEntity('toggle');
}

function deleteEntity() {
    if (store.selectedEntityId) {
        store.removeEntity(store.selectedEntityId);
    }
}

function duplicateEntity() {
    if (store.selectedEntityId) {
        store.duplicateEntity(store.selectedEntityId);
    }
}

const replaceImageInput = ref<HTMLInputElement | null>(null);

function triggerReplaceImage() {
    replaceImageInput.value?.click();
}

function onReplaceImageFile(event: Event) {
    const target = event.target as HTMLInputElement;
    if (target.files && target.files[0]) {
        const reader = new FileReader();
        reader.onload = (e) => {
            if (e.target?.result) {
                store.setBaseImage(e.target.result as string);
            }
        };
        reader.readAsDataURL(target.files[0]);
    }
}

const hasBaseImage = computed(() => !!store.config.imageBase64);

function downloadBaseImage() {
    const dataUri = store.config.imageBase64;
    const filename = imageDownloadFilename(dataUri, store.config.name);
    if (!filename) return; // no image to download
    const a = document.createElement('a');
    a.href = dataUri;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
}

const iconInput = ref<HTMLInputElement | null>(null);
const hasCustomIcon = ref(false);
const iconVersion = ref(0);
// Cache-busting query so the <img> preview refreshes after upload/reset.
const iconPreviewSrc = computed(() => `/apple-touch-icon.png?v=${iconVersion.value}`);

onMounted(async () => {
    try {
        hasCustomIcon.value = (await getIconStatus()).custom;
    } catch { /* ignore: icon status is non-critical */ }
});

function triggerIconUpload() {
    iconInput.value?.click();
}

async function onIconFile(event: Event) {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    try {
        const png = await resizeImageToPng(file, 180);
        await uploadIcon(png);
        hasCustomIcon.value = true;
        iconVersion.value++;
    } catch (e) {
        console.error('Icon upload failed', e);
        alert('Failed to upload icon');
    } finally {
        target.value = '';
    }
}

async function resetIcon() {
    try {
        await deleteIcon();
        hasCustomIcon.value = false;
        iconVersion.value++;
    } catch (e) {
        console.error('Icon reset failed', e);
    }
}

function clearAll() {
    if (confirm('Are you sure you want to clear the entire floorplan config?')) {
        store.clearConfig();
    }
}

defineProps<{
    isDrawing: boolean
}>();

defineEmits(['toggle-draw-mode']);

function clearPoints() {
    if (store.selectedEntityId) {
        store.updateEntity(store.selectedEntityId, { points: [] });
    }
}

const version = __APP_VERSION__;

const knownDevices = ref<string[]>([]);
const showDeviceList = ref(false);

const filteredDevices = computed(() => {
    return filterDevices(knownDevices.value, selectedEntity.value?.entityId ?? '');
});

async function refreshDevices() {
    try {
        knownDevices.value = await fetchDevices();
    } catch { /* ignore */ }
}

function selectDevice(name: string) {
    if (selectedEntity.value) {
        selectedEntity.value.entityId = name;
    }
    showDeviceList.value = false;
}

function hideDeviceList() {
    setTimeout(() => { showDeviceList.value = false; }, 200);
}

function onTypeChange() {
    if (!selectedEntity.value) return;
    if (selectedEntity.value.type === 'text' && !selectedEntity.value.textConfig) {
        store.updateEntity(selectedEntity.value.id, { textConfig: defaultTextConfig() });
    }
    if (selectedEntity.value.type === 'number' && !selectedEntity.value.numberConfig) {
        store.updateEntity(selectedEntity.value.id, { numberConfig: defaultNumberConfig() });
    }
    if (selectedEntity.value.type === 'button' && !selectedEntity.value.buttonConfig) {
        store.updateEntity(selectedEntity.value.id, { buttonConfig: defaultButtonConfig() });
    }
    if (selectedEntity.value.type === 'toggle' && !selectedEntity.value.toggleConfig) {
        store.updateEntity(selectedEntity.value.id, { toggleConfig: defaultToggleConfig() });
    }
}

function setTextJsonPath(e: Event) {
    if (selectedEntity.value?.textConfig) {
        selectedEntity.value.textConfig.jsonPath = (e.target as HTMLInputElement).value;
    }
}

function setTextFormat(e: Event) {
    if (selectedEntity.value?.textConfig) {
        selectedEntity.value.textConfig.format = (e.target as HTMLInputElement).value;
    }
}

function setNumberField(key: 'readTopic' | 'writeTopic' | 'unit', e: Event) {
    if (selectedEntity.value?.numberConfig) {
        (selectedEntity.value.numberConfig as any)[key] = (e.target as HTMLInputElement).value;
    }
}

function setNumberNum(key: 'min' | 'max' | 'step' | 'size', e: Event) {
    if (selectedEntity.value?.numberConfig) {
        const n = parseNumberField((e.target as HTMLInputElement).value);
        if (n !== null) (selectedEntity.value.numberConfig as any)[key] = n;
    }
}

function setButtonField(key: 'topic' | 'value' | 'text', e: Event) {
    if (selectedEntity.value?.buttonConfig) {
        (selectedEntity.value.buttonConfig as any)[key] = (e.target as HTMLInputElement).value;
    }
}
function setButtonNum(key: 'size', e: Event) {
    if (selectedEntity.value?.buttonConfig) {
        const n = parseNumberField((e.target as HTMLInputElement).value);
        if (n !== null) (selectedEntity.value.buttonConfig as any)[key] = n;
    }
}

function setToggleField(key: 'readTopic' | 'writeTopic' | 'onValue' | 'offValue', e: Event) {
    if (selectedEntity.value?.toggleConfig) {
        (selectedEntity.value.toggleConfig as any)[key] = (e.target as HTMLInputElement).value;
    }
}
function setToggleNum(key: 'size', e: Event) {
    if (selectedEntity.value?.toggleConfig) {
        const n = parseNumberField((e.target as HTMLInputElement).value);
        if (n !== null) (selectedEntity.value.toggleConfig as any)[key] = n;
    }
}
</script>

<template>
    <div class="properties-panel glass-panel">
        <div class="panel-header">
            <h2>Properties</h2>
        </div>

        <div class="panel-content">
            <div v-if="!hasSelection" class="global-actions">
                <p class="hint">Select an entity to edit properties, or add new items.</p>

                <div class="button-group">
                    <button @click="addEntity">Add Light Entity</button>
                    <button @click="addTextEntity" class="secondary">Add Text Widget</button>
                    <button @click="addNumberEntity" class="secondary">Add Number Selector</button>
                    <button @click="addButtonEntity" class="secondary">Add Button Widget</button>
                    <button @click="addToggleEntity" class="secondary">Add Toggle Switch</button>
                </div>

                <div class="config-actions">
                    <h3>Global Config</h3>
                    <div class="input-group">
                        <label>Floorplan Name</label>
                        <input type="text" v-model="store.config.name">
                    </div>

                    <div class="input-group">
                        <label>Floorplan Image</label>
                        <button class="secondary small" @click="triggerReplaceImage">Replace Image</button>
                        <button class="secondary small" @click="downloadBaseImage" :disabled="!hasBaseImage">Download Image</button>
                        <input ref="replaceImageInput" type="file" accept="image/*" class="hidden-input"
                            @change="onReplaceImageFile">
                    </div>

                    <div class="input-group">
                        <label>App Icon (Home Screen)</label>
                        <div class="app-icon-row">
                            <img :src="iconPreviewSrc" alt="App icon preview" class="app-icon-preview" />
                            <div class="app-icon-buttons">
                                <button class="secondary small" @click="triggerIconUpload">Upload</button>
                                <button v-if="hasCustomIcon" class="secondary small" @click="resetIcon">Standard</button>
                            </div>
                        </div>
                        <input ref="iconInput" type="file" accept="image/*" class="hidden-input" @change="onIconFile">
                        <p class="hint small">Resized to 180x180. On iPhone, re-add to Home Screen to apply a changed icon.</p>
                    </div>

                    <div class="io-actions">
                        <button class="secondary" @click="clearAll" style="color: var(--color-danger)">Clear All</button>
                    </div>
                </div>
            </div>

            <div v-else-if="selectedEntity" class="entity-properties">
                <div class="header-row">
                    <h3>{{ selectedEntity.label }}</h3>
                    <button class="icon-btn close" @click="store.selectedEntityId = null">X</button>
                </div>

                <div class="scroll-area">
                    <div class="input-group">
                        <label>Label</label>
                        <input type="text" v-model="selectedEntity.label">
                    </div>
                    <div class="input-group">
                        <label>Type</label>
                        <select v-model="selectedEntity.type" @change="onTypeChange">
                            <option value="light">Light</option>
                            <option value="text">Text</option>
                            <option value="number">Number</option>
                            <option value="button">Button</option>
                            <option value="toggle">Toggle</option>
                        </select>
                    </div>

                    <div class="input-group">
                        <label>Entity ID</label>
                        <div class="device-selector">
                            <input type="text" v-model="selectedEntity.entityId"
                                   placeholder="z2m friendly_name"
                                   autocomplete="off"
                                   @focus="refreshDevices(); showDeviceList = true"
                                   @blur="hideDeviceList">
                            <div v-if="showDeviceList && filteredDevices.length > 0" class="device-dropdown">
                                <div v-for="name in filteredDevices" :key="name"
                                     class="device-option"
                                     @mousedown.prevent="selectDevice(name)">
                                    {{ name }}
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Text entity config -->
                    <template v-if="selectedEntity.type === 'text'">
                        <div class="section-title">Text Data</div>
                        <div class="input-group">
                            <label>JSON Path</label>
                            <input type="text"
                                :value="selectedEntity.textConfig?.jsonPath ?? ''"
                                @input="setTextJsonPath"
                                placeholder="e.g. temperature">
                        </div>
                        <div class="input-group">
                            <label>Format</label>
                            <input type="text"
                                :value="selectedEntity.textConfig?.format ?? ''"
                                @input="setTextFormat"
                                placeholder="e.g. Temp: {} °C">
                        </div>
                        <p class="hint small">Use <code>{}</code> as placeholder for the value.</p>
                    </template>

                    <!-- Number entity config -->
                    <template v-else-if="selectedEntity.type === 'number'">
                        <div class="section-title">Number Range</div>
                        <div class="input-group">
                            <label>Read Topic</label>
                            <input type="text" :value="selectedEntity.numberConfig?.readTopic ?? ''"
                                @input="setNumberField('readTopic', $event)" placeholder="e.g. home/room/setpoint">
                        </div>
                        <div class="input-group">
                            <label>Write Topic</label>
                            <input type="text" :value="selectedEntity.numberConfig?.writeTopic ?? ''"
                                @input="setNumberField('writeTopic', $event)" placeholder="e.g. home/room/setpoint/set">
                        </div>
                        <div class="row">
                            <div class="input-group">
                                <label>Min</label>
                                <input type="number" :value="selectedEntity.numberConfig?.min ?? 0" @input="setNumberNum('min', $event)">
                            </div>
                            <div class="input-group">
                                <label>Max</label>
                                <input type="number" :value="selectedEntity.numberConfig?.max ?? 100" @input="setNumberNum('max', $event)">
                            </div>
                        </div>
                        <div class="row">
                            <div class="input-group">
                                <label>Step</label>
                                <input type="number" :value="selectedEntity.numberConfig?.step ?? 1" step="any" @input="setNumberNum('step', $event)">
                            </div>
                            <div class="input-group">
                                <label>Unit</label>
                                <input type="text" :value="selectedEntity.numberConfig?.unit ?? ''" @input="setNumberField('unit', $event)" placeholder="°C, %">
                            </div>
                        </div>
                        <div class="input-group">
                            <label>Size</label>
                            <input type="number" :value="selectedEntity.numberConfig?.size ?? 2.5" step="0.1" min="0.5" @input="setNumberNum('size', $event)">
                        </div>
                        <p class="hint small">Publishes the raw value (no JSON) to the write topic; reads it from the read topic.</p>
                    </template>

                    <!-- Button entity config -->
                    <template v-else-if="selectedEntity.type === 'button'">
                        <div class="section-title">Button Action</div>
                        <div class="input-group">
                            <label>Topic</label>
                            <input type="text" :value="selectedEntity.buttonConfig?.topic ?? ''"
                                @input="setButtonField('topic', $event)" placeholder="e.g. home/room/scene">
                        </div>
                        <div class="input-group">
                            <label>Value</label>
                            <input type="text" :value="selectedEntity.buttonConfig?.value ?? ''"
                                @input="setButtonField('value', $event)" placeholder="e.g. ON">
                        </div>
                        <div class="input-group">
                            <label>Button Text</label>
                            <input type="text" :value="selectedEntity.buttonConfig?.text ?? ''"
                                @input="setButtonField('text', $event)" placeholder="e.g. Send">
                        </div>
                        <div class="input-group">
                            <label>Size</label>
                            <input type="number" :value="selectedEntity.buttonConfig?.size ?? 2.5" step="0.1" min="0.5" @input="setButtonNum('size', $event)">
                        </div>
                        <p class="hint small">Publishes the raw value to the topic on click.</p>
                    </template>

                    <!-- Toggle entity config -->
                    <template v-else-if="selectedEntity.type === 'toggle'">
                        <div class="section-title">Toggle Switch</div>
                        <div class="input-group">
                            <label>Read Topic</label>
                            <input type="text" :value="selectedEntity.toggleConfig?.readTopic ?? ''"
                                @input="setToggleField('readTopic', $event)" placeholder="e.g. home/lamp/state">
                        </div>
                        <div class="input-group">
                            <label>Write Topic</label>
                            <input type="text" :value="selectedEntity.toggleConfig?.writeTopic ?? ''"
                                @input="setToggleField('writeTopic', $event)" placeholder="e.g. home/lamp/set">
                        </div>
                        <div class="row">
                            <div class="input-group">
                                <label>On Value</label>
                                <input type="text" :value="selectedEntity.toggleConfig?.onValue ?? ''"
                                    @input="setToggleField('onValue', $event)" placeholder="ON">
                            </div>
                            <div class="input-group">
                                <label>Off Value</label>
                                <input type="text" :value="selectedEntity.toggleConfig?.offValue ?? ''"
                                    @input="setToggleField('offValue', $event)" placeholder="OFF">
                            </div>
                        </div>
                        <div class="input-group">
                            <label>Size</label>
                            <input type="number" :value="selectedEntity.toggleConfig?.size ?? 2.5" step="0.1" min="0.5" @input="setToggleNum('size', $event)">
                        </div>
                        <p class="hint small">Reads the raw value from the read topic; publishes On/Off value to the write topic on click.</p>
                    </template>

                    <!-- Light entity config -->
                    <template v-else>
                        <div class="section-title">Visuals</div>

                        <div class="row">
                            <div class="input-group">
                                <label>Shape</label>
                                <select v-model="selectedEntity.shape">
                                    <option value="circle">Circle</option>
                                    <option value="square">Square</option>
                                </select>
                            </div>
                        </div>

                        <div class="row">
                            <div class="input-group">
                                <label>Width (%)</label>
                                <input type="number" v-model="selectedEntity.style.width" step="0.1">
                            </div>
                            <div class="input-group">
                                <label>Height (%)</label>
                                <input type="number" v-model="selectedEntity.style.height" step="0.1">
                            </div>
                        </div>
                        <div class="row">
                            <div class="input-group">
                                <label>Spread Radius (%)</label>
                                <input type="number" v-model="selectedEntity.style.gradientRadius" step="1">
                            </div>
                        </div>

                        <div class="section-title">Default Colors</div>
                        <div class="input-group">
                            <label>On Color</label>
                            <div class="color-picker-row">
                                <input type="color" v-model="(selectedEntity.style.colors as any).onColor">
                                <input type="text" v-model="(selectedEntity.style.colors as any).onColor">
                            </div>
                        </div>

                        <div class="input-group">
                            <label>Off Color</label>
                            <div class="color-picker-row">
                                <input type="color" v-model="(selectedEntity.style.colors as any).offColor">
                                <input type="text" v-model="(selectedEntity.style.colors as any).offColor">
                            </div>
                        </div>

                        <div class="section-title">Label Display</div>
                        <div class="input-group checkbox">
                            <label>
                                <input type="checkbox" v-model="selectedEntity.labelConfig.show">
                                Show Label
                            </label>
                        </div>

                        <div>
                            <div class="section-title">Light Zone</div>
                            <p class="hint small">
                                {{ isDrawing ? 'Click on canvas to add points.' : 'Define a custom shape for light spread.'
                                }}
                            </p>
                            <div class="input-group inline">
                                <button @click="$emit('toggle-draw-mode')" :class="{ active: isDrawing }">
                                    {{ isDrawing ? 'Finish' : 'Draw' }}
                                </button>
                                <button v-if="selectedEntity.points && selectedEntity.points.length > 0"
                                    @click="clearPoints" class="secondary">
                                    Clear
                                </button>
                            </div>
                        </div>
                    </template>

                    <div class="danger-actions" style="margin-top: 1rem;">
                        <button class="secondary" @click="duplicateEntity">Duplicate Entity</button>
                        <button class="icon-btn danger" @click="deleteEntity">Remove Entity</button>
                    </div>
                </div>
            </div>
        </div>

        <div class="panel-footer">
            {{ version }}
        </div>
    </div>
</template>

<style scoped>
.properties-panel {
    width: 300px;
    background-color: var(--color-bg-primary);
    border-left: 1px solid rgba(255, 255, 255, 0.1);
    display: flex;
    flex-direction: column;
    height: 100%;
    z-index: 10;
    /* Ensure above canvas if needed */
}

@media (max-width: 768px) {
    .properties-panel {
        width: 100%;
        height: 40%;
        /* Take bottom 40% */
        border-left: none;
        border-top: 1px solid rgba(255, 255, 255, 0.1);
    }
}

.panel-header {
    padding: 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.panel-header h2 {
    margin: 0;
    font-size: 1.25rem;
}

.panel-content {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
}

.hint {
    color: var(--color-text-secondary);
    font-size: 0.9rem;
    margin-bottom: 1.5rem;
}

.button-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 2rem;
}

.input-group {
    margin-bottom: 1rem;
}

.input-group.inline {
    display: flex;
    gap: 0.5rem;
}

.input-group label {
    display: block;
    font-size: 0.85rem;
    color: var(--color-text-secondary);
    margin-bottom: 0.25rem;
}

.config-actions,
.danger-actions {
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    padding-top: 1rem;
}

.header-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
}

.icon-btn.close {
    background: transparent;
    color: var(--color-text-primary);
    padding: 0.5rem;
    font-size: 1.5rem;
}

.icon-btn.danger {
    background: transparent;
    color: var(--color-danger);
    padding: 0.2rem;
}

.icon-btn.danger:hover {
    background: rgba(239, 68, 68, 0.1);
    border-color: var(--color-danger);
}

.section-title {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--color-text-accent);
    margin-top: 1.5rem;
    margin-bottom: 0.5rem;
    font-weight: 600;
}

.row {
    display: flex;
    gap: 0.5rem;
}

.color-picker-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
}

.color-picker-row input[type="color"] {
    border: none;
    width: 30px;
    height: 30px;
    padding: 0;
    background: none;
    cursor: pointer;
}

.input-group.checkbox label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    color: var(--color-text-primary);
    cursor: pointer;
}

.io-actions {
    display: flex;
    gap: 0.5rem;
    margin-top: 1rem;
}

.io-actions button {
    flex: 1;
    font-size: 0.85rem;
    padding: 0.5rem;
}

.hidden-input {
    display: none;
}

.app-icon-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
}

.app-icon-preview {
    width: 48px;
    height: 48px;
    border-radius: var(--radius-md);
    object-fit: cover;
    background: var(--color-bg-tertiary);
    flex-shrink: 0;
}

.app-icon-buttons {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
}

button.active {
    background-color: var(--color-primary);
    color: white;
}

.hint.small {
    margin-bottom: 0.5rem;
    font-size: 0.8rem;
}

.panel-footer {
    padding: 0.5rem;
    text-align: center;
    font-size: 0.7rem;
    color: var(--color-text-secondary);
    border-top: 1px solid rgba(255, 255, 255, 0.1);
    margin-top: auto;
    /* Pushes to bottom */
}
.device-selector {
    position: relative;
}

.device-dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    background: var(--color-bg-primary, #1a1a2e);
    border: 1px solid rgba(255, 255, 255, 0.2);
    border-radius: 4px;
    max-height: 180px;
    overflow-y: auto;
    z-index: 200;
    margin-top: 2px;
}

.device-option {
    padding: 0.4rem 0.6rem;
    cursor: pointer;
    font-size: 0.82rem;
    font-family: monospace;
    color: var(--color-text-primary, #fff);
}

.device-option:hover {
    background: var(--color-bg-tertiary, rgba(255, 255, 255, 0.08));
}
</style>
