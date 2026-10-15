<template>
    <main class="not-found">
        <div class="panel">
            <span class="wordmark">CodeMas</span>
            <h1>Page not found</h1>
            <p>There's no page at <code>{{ route.fullPath }}</code>. The link may be mistyped or out of date.</p>
            <RouterLink :to="homePath" class="home-btn">{{ homeLabel }}</RouterLink>
        </div>
    </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const route = useRoute()
const authStore = useAuthStore()

// Send people back to the home page that matches who they are
const homePath = computed(() => {
    if (!authStore.isLoggedIn) return '/login'
    return authStore.isTrainer ? '/dashboard' : '/home'
})
const homeLabel = computed(() => (authStore.isLoggedIn ? 'Go to your home page' : 'Go to sign in'))
</script>

<style scoped>
.not-found {
    min-height: 100vh;
    background: var(--bg);
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px 16px;
}
.panel {
    width: 100%;
    max-width: 440px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 40px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}
.wordmark {
    font-family: var(--font-display);
    font-size: 17px;
    font-weight: 700;
}
h1 {
    font-size: 28px;
    margin-top: 12px;
}
p {
    color: var(--text-muted);
    line-height: 1.6;
}
code {
    font-size: 13px;
    padding: 1px 6px;
    border-radius: 6px;
    background: var(--surface2);
    color: var(--text);
    word-break: break-all;
}
.home-btn {
    align-self: flex-start;
    margin-top: 8px;
    padding: 12px 24px;
    border-radius: var(--radius-pill);
    background: var(--accent);
    color: var(--accent-ink);
    font-family: var(--font-display);
    font-weight: 600;
    font-size: 14px;
    text-decoration: none;
}
.home-btn:hover {
    background: var(--accent-hover);
    color: var(--accent-ink);
    text-decoration: none;
}
</style>
