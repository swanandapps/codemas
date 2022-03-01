<template>
    <div class="login-page">
        <div class="login-card">
            <div class="brand">
                <div class="logo">CM</div>
                <span class="brand-name">Code<span class="brand-red">Mas</span></span>
            </div>
            <h2>Welcome back</h2>
            <p class="subtitle">Sign in to your account</p>

            <form @submit.prevent="handleLogin">
                <div class="form-group">
                    <input v-model="username" type="text" placeholder="Username" required />
                    <input v-model="password" type="password" placeholder="Password" required />
                </div>
                <div v-if="error" class="error-msg">{{ error }}</div>
                <button type="submit" class="submit-btn" :disabled="loading">
                    {{ loading ? 'Signing in...' : 'Sign In' }}
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
            router.push('/exams')
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
}
.login-card {
    width: 400px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 40px;
    box-shadow: var(--shadow-lg);
}
.brand {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 32px;
}
.logo {
    width: 36px;
    height: 36px;
    background: var(--red);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 13px;
    color: white;
}
.brand-name {
    font-size: 18px;
    font-weight: 700;
    color: var(--text);
}
.brand-red { color: var(--red); }
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
    gap: 12px;
    margin-bottom: 20px;
}
.error-msg {
    color: var(--red);
    font-size: 13px;
    padding: 10px 14px;
    background: var(--red-dim);
    border: 1px solid rgba(230,57,70,0.3);
    border-radius: var(--radius-sm);
}
.submit-btn {
    width: 100%;
    padding: 12px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: var(--red-hover); }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.footer-link {
    text-align: center;
    margin-top: 20px;
    font-size: 13px;
    color: var(--text-dim);
}
.footer-link a { color: var(--red); }
</style>
