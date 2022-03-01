<template>
    <div class="register-page">
        <div class="register-card">
            <div class="brand">
                <div class="logo">CM</div>
                <span class="brand-name">Code<span class="brand-red">Mas</span></span>
            </div>
            <h2>Create account</h2>
            <p class="subtitle">Join the platform</p>

            <form @submit.prevent="handleRegister">
                <div class="form-group">
                    <input v-model="username" type="text" placeholder="Username" required />
                    <input v-model="email" type="email" placeholder="Email" required />
                    <input v-model="password" type="password" placeholder="Password" required />
                    <select v-model="role">
                        <option value="student">Student</option>
                        <option value="trainer">Trainer</option>
                    </select>
                    <input v-model="cohort" type="text" placeholder="Cohort (e.g. May 2026)" />
                </div>
                <div v-if="error" class="error-msg">{{ error }}</div>
                <button type="submit" class="submit-btn" :disabled="loading">
                    {{ loading ? 'Creating account...' : 'Create Account' }}
                </button>
            </form>

            <p class="footer-link">Already have an account? <router-link to="/login">Sign in</router-link></p>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const username = ref<string>('')
const email = ref<string>('')
const password = ref<string>('')
const role = ref<string>('student')
const cohort = ref<string>('')
const error = ref<string>('')
const loading = ref<boolean>(false)

async function handleRegister(): Promise<void> {
    loading.value = true
    error.value = ''
    console.log('hii')
    try {
        await api.post('/auth/register/', {
            username: username.value,
            email: email.value,
            password: password.value,
            role: role.value,
            cohort: cohort.value,
        })
        router.push('/login')
    } catch (e: any) {
        error.value = e.response?.data?.error || 'Registration failed'
    } finally {
        loading.value = false
    }
}
</script>

<style scoped>
.register-page {
    min-height: 100vh;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
}
.register-card {
    width: 420px;
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
    margin-bottom: 12px;
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
