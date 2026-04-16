<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { RouterView, RouterLink } from 'vue-router';
import { useFloorplanStore } from './stores/floorplan';
import LoginForm from './components/LoginForm.vue';
import { getAuthHeader, fetchConfig, fetchStates, fetchInfo } from './utils/api';
import { needsMigration, migrateConfig } from './utils/configMigration';
import type { FloorplanConfig } from './types/floorplan';

const store = useFloorplanStore();
const isAuthenticated = ref(false);
const appTitle = ref('HA Floorplan');
let pollInterval: ReturnType<typeof setInterval> | null = null;

async function loadStates() {
    try {
        const states = await fetchStates();
        for (const [friendlyName, s] of Object.entries(states)) {
            store.setEntityState(friendlyName, s.state === 'ON' ? 'on' : 'off');
        }
    } catch (e) {
        console.error('Failed to load states', e);
    }
}

async function initApp() {
    try {
        let config = await fetchConfig() as any;
        if (config.imageBase64) {
            config.imageBase64 = config.imageBase64.replace(/\s/g, '');
        }
        if (needsMigration(config)) {
            config = migrateConfig(config);
        }
        store.loadConfig(config as FloorplanConfig);
    } catch (e) {
        console.error('Failed to load config from server', e);
    }

    await loadStates();

    // Poll device states every 5 seconds
    pollInterval = setInterval(loadStates, 5000);
}

async function onLoginSuccess() {
    isAuthenticated.value = true;
    await initApp();
}

onMounted(async () => {
    fetchInfo().then(info => { appTitle.value = info.title; }).catch(() => {});
    // If credentials are already stored, try to use them immediately
    if (getAuthHeader()) {
        try {
            await fetchConfig();
            isAuthenticated.value = true;
            await initApp();
        } catch {
            isAuthenticated.value = false;
        }
    }
});

onUnmounted(() => {
    if (pollInterval) clearInterval(pollInterval);
});
</script>

<template>
  <LoginForm v-if="!isAuthenticated" @success="onLoginSuccess" />
  <template v-else>
    <header class="app-header glass-panel">
      <div class="logo">{{ appTitle }}</div>
      <nav>
        <RouterLink to="/" active-class="active">Viewer</RouterLink>
        <RouterLink to="/editor" active-class="active">Editor</RouterLink>
      </nav>
    </header>

    <main>
      <RouterView />
    </main>
  </template>
</template>

<style scoped>
.app-header {
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2rem;
  z-index: 100;
  position: relative;
}

.logo {
  font-weight: 700;
  font-size: 1.25rem;
  background: linear-gradient(to right, #ffffff, var(--color-text-accent));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

nav {
  display: flex;
  gap: 1rem;
}

nav a {
  color: var(--color-text-secondary);
  text-decoration: none;
  font-weight: 500;
  transition: color 0.2s;
  padding: 0.5rem 1rem;
  border-radius: var(--radius-md);
}

nav a:hover,
nav a.active {
  color: var(--color-text-primary);
  background-color: var(--color-bg-tertiary);
}

main {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative;
}
</style>
