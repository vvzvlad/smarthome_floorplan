import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import './style.css';
import { registerSW } from 'virtual:pwa-register';

const app = createApp(App);

app.use(createPinia());
app.use(router);

app.mount('#app');

// PWA auto-update. vite-plugin-pwa runs in `autoUpdate` mode, so `immediate: true`
// makes it reload open tabs as soon as a newly activated service worker takes
// control. The extra checks below cover the case that actually bites us: an iOS
// standalone PWA resumes from the home screen WITHOUT a navigation, so the browser
// never runs its own SW update check — we force one on resume / reconnect / hourly.
const swUpdateIntervalMs = 60 * 60 * 1000;

registerSW({
  immediate: true,
  onRegisteredSW(swUrl, registration) {
    if (!registration) return;

    const checkForUpdate = async () => {
      // Skip while an install is already in flight or we're offline.
      if (registration.installing || !navigator.onLine) return;
      try {
        // Bypass the HTTP cache so we genuinely re-fetch the SW script.
        const resp = await fetch(swUrl, {
          cache: 'no-store',
          headers: { 'cache-control': 'no-cache' },
        });
        if (resp.status === 200) await registration.update();
      } catch {
        // Transient network error — ignore and retry on the next trigger.
      }
    };

    setInterval(checkForUpdate, swUpdateIntervalMs);
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible') void checkForUpdate();
    });
    window.addEventListener('online', () => void checkForUpdate());
  },
});
