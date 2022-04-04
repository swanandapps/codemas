<template>
    <div class="app-layout">
        <NavBar />
        <main class="main-content">
            <slot />
        </main>
    </div>
</template>

<script setup lang="ts">
import NavBar from '../components/NavBar.vue'
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
    padding: 40px;
    min-height: 100vh;
    background: var(--bg);
}
</style>
