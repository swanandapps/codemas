<template>
    <div class="register-page">
        <div class="register-card">
            <div class="brand">
                <span class="brand-name">CodeMas</span>
            </div>
            <h2>Create account</h2>
            <p class="subtitle">Create a student account to take your exams.</p>

            <form @submit.prevent="handleRegister">
                <div class="form-group">
                    <label for="register-username">Username</label>
                    <input id="register-username" v-model="username" type="text" required />
                    <label for="register-email">Email</label>
                    <input id="register-email" v-model="email" type="email" required />
                    <label for="register-password">Password</label>
                    <input id="register-password" v-model="password" type="password" required />
                    <label for="register-role">Role</label>
                    <select id="register-role" v-model="role">
                        <option value="student">Student</option>
                        <option value="trainer">Trainer</option>
                    </select>
                    <label for="register-cohort">Section</label>
                    <input id="register-cohort" v-model="cohort" type="text" placeholder="e.g. Section A" />
                </div>
                <div v-if="error" class="error-msg">{{ error }}</div>
                <button type="submit" class="submit-btn" :disabled="loading">
                    {{ loading ? 'Creating account...' : 'Create account' }}
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
        const data = e.response?.data
        // First field error (e.g. {username: ["already taken"]}) if there's no top-level message
        let fieldMsg: string | undefined
        if (data && typeof data === 'object') {
            for (const v of Object.values(data)) {
                const m = Array.isArray(v) ? v[0] : v
                if (typeof m === 'string' && m) { fieldMsg = m; break }
            }
        }
        error.value = data?.error || data?.detail || fieldMsg || 'Registration failed'
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
    padding: 16px;
    box-sizing: border-box;
}
.register-card {
    width: 100%;
    max-width: 420px;
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
    .register-card {
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
.form-group input,
.form-group select {
    min-height: 40px;
}
.error-msg {
    color: var(--red-ink);
    font-size: 13px;
    padding: 10px 14px;
    background: var(--red-dim);
    border: 1px solid var(--red);
    border-radius: var(--radius-sm);
    margin-bottom: 12px;
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
