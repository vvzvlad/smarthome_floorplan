<script setup lang="ts">
import { ref } from 'vue';
import { checkCredentials, setCredentials } from '../utils/api';
import type { UserRole } from '../utils/api';

const emit = defineEmits<{ (e: 'success', role: UserRole): void }>();

const role = ref<UserRole>('viewer');
const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
    error.value = '';
    loading.value = true;
    try {
        const ok = await checkCredentials(role.value, password.value);
        if (ok) {
            setCredentials(role.value, password.value);
            emit('success', role.value);
        } else {
            error.value = 'Wrong password';
        }
    } catch {
        error.value = 'Cannot connect to server';
    } finally {
        loading.value = false;
    }
}
</script>

<template>
    <div class="login-overlay">
        <div class="login-box">
            <h2>Smart Home Floorplan</h2>
            <form @submit.prevent="submit">
                <div class="role-selector">
                    <label :class="{ active: role === 'viewer' }">
                        <input type="radio" v-model="role" value="viewer" />
                        Viewer
                    </label>
                    <label :class="{ active: role === 'editor' }">
                        <input type="radio" v-model="role" value="editor" />
                        Editor
                    </label>
                </div>
                <input
                    type="password"
                    v-model="password"
                    placeholder="Password"
                    autocomplete="current-password"
                    :disabled="loading"
                    autofocus
                />
                <button type="submit" :disabled="loading || !password">
                    {{ loading ? '...' : 'Login' }}
                </button>
                <p v-if="error" class="error">{{ error }}</p>
            </form>
        </div>
    </div>
</template>

<style scoped>
.login-overlay {
    position: fixed;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--color-bg-primary, #1a1a2e);
    z-index: 9999;
}

.login-box {
    background: var(--color-bg-secondary, #16213e);
    padding: 2rem;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    min-width: 280px;
    border: 1px solid rgba(255, 255, 255, 0.1);
}

.login-box h2 {
    margin: 0;
    text-align: center;
    font-size: 1.1rem;
    color: var(--color-text-primary, #fff);
}

.login-box form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
}

.role-selector {
    display: flex;
    gap: 0.5rem;
}

.role-selector label {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.4rem;
    padding: 0.4rem 0.75rem;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    cursor: pointer;
    color: var(--color-text-secondary, #aaa);
    font-size: 0.9rem;
    transition: background 0.15s, color 0.15s;
}

.role-selector label.active {
    background: var(--color-bg-tertiary, #0f3460);
    color: var(--color-text-primary, #fff);
    border-color: var(--color-text-accent, #e94560);
}

.role-selector input[type="radio"] {
    display: none;
}

.error {
    color: #ef4444;
    font-size: 0.85rem;
    margin: 0;
    text-align: center;
}
</style>
