<template>
    <div class="login-page">
        <div class="login-card">
            <div class="brand">
                <span class="brand-name">CodeMas</span>
            </div>
            <h2>Welcome back</h2>
            <p class="subtitle">Sign in to your account</p>

            <form @submit.prevent="handleLogin">
                <div class="form-group">
                    <label for="login-username">Username</label>
                    <input id="login-username" v-model="username" type="text" required />
                    <label for="login-password">Password</label>
                    <input id="login-password" v-model="password" type="password" required />
                </div>
                <div v-if="error" class="error-msg">{{ error }}</div>
                <button type="submit" class="submit-btn" :disabled="loading">
                    {{ loading ? 'Signing in...' : 'Sign in' }}
                </button>
            </form>

            <p class="footer-link">Don't have an account? <router-link to="/register">Register</router-link></p>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const username = ref<string>('')
const password = ref<string>('')
const error = ref<string>('')
const loading = ref<boolean>(false)

async function handleLogin(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
        await authStore.login(username.value, password.value)
        if (authStore.isTrainer) {
            router.push('/dashboard')
        } else {
            router.push('/home')
        }
    } catch (e: any) {
        error.value = e.response?.data?.error || 'Login failed'
    } finally {
        loading.value = false
    }
}
</script>

<style scoped>
.login-page {
    min-height: 100vh;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    box-sizing: border-box;
}
.login-card {
    width: 100%;
    max-width: 400px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 40px;
    box-shadow: var(--shadow-lg);
    box-sizing: border-box;
}
.brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 32px;
}
.brand-name {
    font-family: var(--font-display);
    font-size: 18px;
    font-weight: 700;
    color: var(--text);
}
@media (max-width: 600px) {
    .login-card {
        padding: 28px 20px;
    }
}
h2 {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    margin-bottom: 6px;
}
.subtitle {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 28px;
}
.form-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 20px;
}
.form-group label {
    font-family: var(--font-display);
    font-size: var(--fs-xs);
    color: var(--text-muted);
    margin-top: 10px;
}
.form-group label:first-child {
    margin-top: 0;
}
.form-group input {
    min-height: 40px;
}
.error-msg {
    color: var(--red-ink);
    font-size: 13px;
    padding: 10px 14px;
    background: var(--red-dim);
    border: 1px solid var(--red);
    border-radius: var(--radius-sm);
}
.submit-btn {
    width: 100%;
    padding: 12px;
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    border-radius: var(--radius-pill);
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: var(--accent-hover); }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.footer-link {
    text-align: center;
    margin-top: 20px;
    font-size: 13px;
    color: var(--text-dim);
}
.footer-link a { color: var(--accent); }
</style>
