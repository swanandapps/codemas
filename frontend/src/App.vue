<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'

const route = useRoute()
const isAuthPage = computed<boolean>(() =>
    route.name === 'login' || route.name === 'register'
)
</script>

<template>
    <AppLayout v-if="!isAuthPage">
        <RouterView />
    </AppLayout>
    <RouterView v-else />
</template>

<style>
@import './assets/theme.css';

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
}

h1 { font-size: 24px; font-weight: 700; color: var(--text); }
h2 { font-size: 18px; font-weight: 600; color: var(--text); }
h3 { font-size: 14px; font-weight: 600; color: var(--text-muted); }

a { color: var(--red); text-decoration: none; }
a:hover { color: var(--red-hover); }

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--surface); }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

/* Global button reset */
button { font-family: inherit; cursor: pointer; border: none; outline: none; }

/* Global input style */
input, textarea, select {
    font-family: inherit;
    background: var(--surface2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 14px;
    font-size: 14px;
    width: 100%;
    outline: none;
    transition: border-color 0.15s;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--red);
}
input::placeholder, textarea::placeholder {
    color: var(--text-dim);
}
select option { background: var(--surface2); }
</style>
