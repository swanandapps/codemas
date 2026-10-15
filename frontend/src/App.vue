<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'

const route = useRoute()
// Pages that render without the sidebar layout
const isAuthPage = computed<boolean>(() =>
    route.name === 'login' || route.name === 'register' || route.name === 'not-found'
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
    font-family: var(--font-sans);
    font-size: var(--fs-base);
    background: var(--bg);
    color: var(--text);
    line-height: 1.55;
    -webkit-font-smoothing: antialiased;
}

h1, h2, h3, h4 { font-family: var(--font-display); color: var(--text); }
h1 { font-size: var(--fs-xl); font-weight: 600; letter-spacing: -0.02em; }
h2 { font-size: var(--fs-md); font-weight: 600; }
h3 { font-size: var(--fs-base); font-weight: 600; }

/* Interface labels use Poppins like masaischool.com; reading text stays Inter */
button, .btn, th, label { font-family: var(--font-display); }

a { color: var(--red-ink); text-decoration: none; }
a:hover { color: var(--accent-hover); text-decoration: underline; }

code, pre, kbd { font-family: var(--font-mono); }

.tabular { font-variant-numeric: tabular-nums; }

:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: .01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: .01ms !important;
    }
}

::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-dim); }

/* Global button reset */
button { cursor: pointer; border: none; outline: none; }

/* Global input style */
input, textarea, select {
    font-family: inherit;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border2);
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 14px;
    width: 100%;
    outline: none;
    transition: border-color 0.15s;
}
input:focus, textarea:focus, select:focus {
    border-color: var(--accent);
}
input::placeholder, textarea::placeholder {
    color: var(--text-dim);
}
select option { background: var(--surface); color: var(--text); }

/* Every dropdown gets the same arrow, inset from the edge: the browser's own arrow ignores
   padding and sits against the rounded border. !important because pages restyle their
   selects with a background/padding shorthand, which would drop the arrow or let text run under it. */
select:not([multiple]) {
    appearance: none;
    -webkit-appearance: none;
    padding-right: 40px !important;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23544D4F' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") !important;
    background-repeat: no-repeat !important;
    background-position: right 14px center !important;
    background-size: 12px !important;
    cursor: pointer;
}
select:not([multiple]):disabled { cursor: not-allowed; opacity: 0.6; }
</style>
