<template>
    <div class="app-layout">
        <!-- Phone and small-tablet top bar: the sidebar becomes a slide-in menu -->
        <header v-if="!hideNav" class="mobile-bar">
            <span class="mobile-brand">CodeMas</span>
            <button
                type="button"
                class="menu-btn"
                :aria-expanded="navOpen"
                aria-controls="app-nav"
                @click="navOpen = !navOpen"
            >
                {{ navOpen ? 'Close' : 'Menu' }}
            </button>
        </header>

        <NavBar v-if="!hideNav" id="app-nav" :open="navOpen" />
        <div v-if="navOpen && !hideNav" class="nav-backdrop" @click="navOpen = false"></div>

        <main class="main-content" :class="{ 'main-content--full': hideNav }">
            <slot />
        </main>
    </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import NavBar from '../components/NavBar.vue'

const route = useRoute()
const hideNav = computed<boolean>(() => Boolean(route.meta.hideNav))

// Slide-in menu state for narrow screens; closes after navigating or on Escape
const navOpen = ref(false)
watch(() => route.fullPath, () => { navOpen.value = false })

function onKeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') navOpen.value = false
}
window.addEventListener('keydown', onKeydown)
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>

<style scoped>
.app-layout {
    display: flex;
    min-height: 100vh;
    background: var(--bg);
}
.main-content {
    margin-left: 240px;
    flex: 1;
    min-width: 0;
    padding: 40px 56px;
    min-height: 100vh;
    background: var(--bg);
}
.main-content--full {
    margin-left: 0;
    padding: 0;
}

.mobile-bar,
.nav-backdrop {
    display: none;
}

@media (max-width: 899px) {
    .mobile-bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 56px;
        padding: 0 16px;
        background: var(--surface);
        border-bottom: 1px solid var(--border);
        z-index: 90;
    }
    .mobile-brand {
        font-family: var(--font-display);
        font-size: 18px;
        font-weight: 700;
    }
    .menu-btn {
        min-height: 40px;
        padding: 0 18px;
        border-radius: var(--radius-pill);
        border: 1px solid var(--border2);
        background: var(--surface);
        color: var(--text);
        font-family: var(--font-display);
        font-weight: 500;
        font-size: 14px;
    }
    .nav-backdrop {
        display: block;
        position: fixed;
        inset: 0;
        background: rgba(33, 25, 27, 0.4);
        z-index: 95;
    }
    .main-content {
        margin-left: 0;
        padding: 80px 16px 32px;
    }
    .main-content--full {
        padding: 0;
    }
}
</style>
