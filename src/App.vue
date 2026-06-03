<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { RouterView, RouterLink } from 'vue-router';
import { useFloorplanStore } from './stores/floorplan';
import LoginForm from './components/LoginForm.vue';
import { logout, fetchStates, fetchTopicValues, fetchBootstrap, fetchConfigCached } from './utils/api';
import { needsMigration, migrateConfig } from './utils/configMigration';
import { normalizeEntityState } from './utils/entityState';
import type { FloorplanConfig } from './types/floorplan';

const store = useFloorplanStore();
const isAuthenticated = ref(false);
// Gates LoginForm until the session probe finishes, so it never flashes.
const authChecked = ref(false);
const appTitle = ref('HA Floorplan');
let pollInterval: ReturnType<typeof setInterval> | null = null;

// Apply a raw config payload to the store, replicating the prior init handling:
// strip whitespace from any image base64, migrate legacy shapes, then load.
function applyConfig(rawConfig: object) {
    try {
        let config = rawConfig as any;
        if (typeof config.imageBase64 === 'string' && config.imageBase64) {
            config.imageBase64 = config.imageBase64.replace(/\s/g, '');
        }
        if (needsMigration(config)) {
            config = migrateConfig(config);
        }
        store.loadConfig(config as FloorplanConfig);
    } catch (e) {
        console.error('Failed to load config from server', e);
    }
}

// Push a states map into the store, normalizing each payload to a display state.
function applyStates(states: Record<string, Record<string, unknown>>) {
    for (const [friendlyName, payload] of Object.entries(states)) {
        const stateStr = normalizeEntityState(payload);
        store.setEntityState(friendlyName, stateStr, payload);
    }
}

async function loadStates() {
    // The two reads are independent — fetch them in parallel so polling latency
    // is one round-trip, not two. Apply each only if it resolved.
    const [statesResult, topicsResult] = await Promise.allSettled([
        fetchStates(),
        fetchTopicValues(),
    ]);
    if (statesResult.status === 'fulfilled') {
        applyStates(statesResult.value);
    } else {
        console.error('Failed to load states', statesResult.reason);
    }
    if (topicsResult.status === 'fulfilled') {
        store.setTopicValues(topicsResult.value);
    } else {
        console.error('Failed to load topic values', topicsResult.reason);
    }
}

async function onLoginSuccess() {
    isAuthenticated.value = true;
    // The login set the session cookie; we're definitely authed. Fetch the dynamic
    // bootstrap and the (SW-cached) config in parallel to populate the app.
    const [boot, rawConfig] = await Promise.all([
        fetchBootstrap(),
        fetchConfigCached().catch(() => null),
    ]);
    appTitle.value = boot.title || 'HA Floorplan';
    if (rawConfig) applyConfig(rawConfig);
    applyStates(boot.states ?? {});
    store.setTopicValues(boot.topics ?? {});
    if (!pollInterval) pollInterval = setInterval(loadStates, 5000);
}

async function onLogout() {
    // Always return to the login screen. A failed/timed-out logout request is
    // intentionally ignored — the reload happens regardless, so the user is never
    // stranded, and we avoid an unhandled promise rejection.
    try {
        await logout();
    } catch {
        // Server-side session cleanup may have failed (e.g. a timed-out request);
        // reloading still drops the in-memory app state and shows the login form.
    } finally {
        // Drop the SW-cached config so a logged-out user can't briefly see the
        // previous floorplan via the optimistic render on the next open.
        if ('caches' in window) {
            try { await caches.delete('api-config'); } catch { /* best-effort */ }
        }
        window.location.reload();
    }
}

onMounted(async () => {
    // Fire both in parallel: the (SW-cached) config and the dynamic bootstrap.
    const bootP = fetchBootstrap();
    const configP = fetchConfigCached().catch(() => null);

    // Optimistic paint: if a config is available (instant from the SW cache on repeat
    // loads), render the floorplan now WITHOUT waiting for the auth round-trip. A
    // never-authenticated client gets 401 -> null here, so it never sees the app.
    const rawConfig = await configP;
    if (rawConfig) {
        isAuthenticated.value = true;
        applyConfig(rawConfig);
        authChecked.value = true; // paint immediately (repeat load: ~0 RTT)
    }

    // Bootstrap confirms the session and brings live device state.
    const boot = await bootP;
    appTitle.value = boot.title || 'HA Floorplan';
    if (boot.auth) {
        isAuthenticated.value = true;
        if (!rawConfig) {
            // First authed load with a cold cache: config wasn't ready before bootstrap;
            // it resolved (or will) via configP — apply it if present.
            const late = await configP;
            if (late) applyConfig(late);
        }
        applyStates(boot.states ?? {});
        store.setTopicValues(boot.topics ?? {});
        if (!pollInterval) pollInterval = setInterval(loadStates, 5000);
    } else {
        // Session invalid/expired: drop any optimistic view and show login.
        isAuthenticated.value = false;
    }
    authChecked.value = true;
});

onUnmounted(() => {
    if (pollInterval) clearInterval(pollInterval);
});
</script>

<template>
  <LoginForm v-if="authChecked && !isAuthenticated" @success="onLoginSuccess" />
  <template v-else-if="isAuthenticated">
    <header class="app-header glass-panel">
      <div class="logo">{{ appTitle }}</div>
      <nav>
        <RouterLink to="/" active-class="active">Viewer</RouterLink>
        <RouterLink to="/editor" active-class="active">Editor</RouterLink>
        <a href="#" class="logout-link" @click.prevent="onLogout">Logout</a>
      </nav>
    </header>

    <main>
      <RouterView />
    </main>
  </template>
</template>

<style scoped>
.app-header {
  height: calc(60px + env(safe-area-inset-top, 0px));
  display: flex;
  align-items: center;
  justify-content: space-between;
  /* Pad for the iOS status bar / notch (safe-area insets) so content
     doesn't render under the system status bar with viewport-fit=cover. */
  padding: env(safe-area-inset-top, 0px) calc(2rem + env(safe-area-inset-right, 0px)) 0 calc(2rem + env(safe-area-inset-left, 0px));
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
  /* Reserve the iOS bottom safe area (home indicator) so content
     does not sit under it with viewport-fit=cover. */
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

@media (max-width: 768px) {
  .app-header {
    height: auto;
    /* Add iOS safe-area insets on top of the base mobile padding. */
    padding:
      calc(0.25rem + env(safe-area-inset-top, 0px))
      calc(0.5rem + env(safe-area-inset-right, 0px))
      0.25rem
      calc(0.5rem + env(safe-area-inset-left, 0px));
  }

  .logo {
    font-size: 0.85rem;
  }

  nav {
    gap: 0.25rem;
  }

  nav a {
    padding: 0.2rem 0.5rem;
    font-size: 0.85rem;
  }
}
</style>
