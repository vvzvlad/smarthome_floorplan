<script setup lang="ts">
import { ref } from 'vue';
import { checkCredentials, setCredentials } from '../utils/api';

const emit = defineEmits<{ (e: 'success'): void }>();

const password = ref('');
const error = ref('');
const loading = ref(false);

async function submit() {
    error.value = '';
    loading.value = true;
    try {
        const ok = await checkCredentials('admin', password.value);
        if (ok) {
            setCredentials('admin', password.value);
            emit('success');
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

input[type="password"] {
    background: var(--color-bg-tertiary, #334155);
    border: 1px solid rgba(255, 255, 255, 0.1);
    color: var(--color-text-primary, #f8fafc);
    padding: 0.6rem 0.75rem;
    border-radius: var(--radius-sm, 6px);
    font-size: 1rem;
    font-family: inherit;
    width: 100%;
    box-sizing: border-box;
    transition: border-color 0.2s;
}

input[type="password"]:focus {
    outline: none;
    border-color: var(--color-primary, #0ea5e9);
}

input[type="password"]:disabled {
    opacity: 0.5;
}

.error {
    color: #ef4444;
    font-size: 0.85rem;
    margin: 0;
    text-align: center;
}
</style>
