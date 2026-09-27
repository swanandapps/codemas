<template>
    <nav class="navbar">
        <div class="brand">
            <div class="logo">CM</div>
            <span class="brand-name">Code<span class="brand-red">Mas</span></span>
        </div>

        <div class="nav-section">
            <div class="nav-label">Menu</div>
            <template v-if="authStore.isStudent">
                <router-link to="/home" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                    Home
                </router-link>
                <router-link to="/exams" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    Exams
                </router-link>
                <router-link to="/results" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    My Results
                </router-link>
                <router-link to="/leaderboard" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6l4-4 4 4"/><path d="M12 2v10.3"/><path d="M4.93 10.93A10 10 0 1 0 19.07 10.93"/></svg>
                    Leaderboard
                </router-link>
            </template>

            <template v-if="authStore.isTrainer">
                <router-link to="/dashboard" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    Overview
                </router-link>
                <router-link to="/dashboard/students" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    Students
                </router-link>
                <router-link to="/dashboard/accounts" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
                    Accounts
                </router-link>
                <router-link to="/dashboard/submissions" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    Submissions
                </router-link>
                <router-link to="/dashboard/history" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    Exam History
                </router-link>

                <div class="nav-label" style="margin-top:12px">Support</div>
                <router-link to="/dashboard/support/disputes" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    Disputes
                </router-link>

                <div class="nav-label" style="margin-top:12px">Integrity</div>
                <router-link to="/dashboard/plagiarism" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    Flags
                </router-link>
                <router-link to="/dashboard/plagiarism/queue" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    Queue
                </router-link>
                <router-link to="/dashboard/plagiarism/cohorts" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0-3-3.87"/></svg>
                    Investigation
                </router-link>
                <router-link to="/dashboard/plagiarism/policy" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93A10 10 0 0 0 4.93 19.07"/><path d="M4.93 4.93A10 10 0 0 0 19.07 19.07"/></svg>
                    Policy
                </router-link>

                <router-link to="/dashboard/monitoring" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                    Monitoring
                </router-link>
                <router-link to="/dashboard/costs" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                    Cost Analysis
                </router-link>
                <router-link to="/dashboard/code-search" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    Code Search
                </router-link>

                <div class="nav-label" style="margin-top:12px">Exams</div>
                <router-link to="/dashboard/create" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                    Create Exam
                </router-link>
                <router-link to="/leaderboard" class="nav-item">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6l4-4 4 4"/><path d="M12 2v10.3"/><path d="M4.93 10.93A10 10 0 1 0 19.07 10.93"/></svg>
                    Leaderboard
                </router-link>
            </template>
        </div>

        <div class="nav-bottom">
            <div class="user-card">
                <div class="user-avatar">{{ initials }}</div>
                <div class="user-info">
                    <div class="user-name">{{ authStore.user?.username }}</div>
                    <div class="user-role">{{ authStore.user?.role }}</div>
                </div>
            </div>
            <button class="logout-btn" @click="logout">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
                Logout
            </button>
        </div>
    </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const initials = computed<string>(() =>
    (authStore.user?.username || '').slice(0, 2).toUpperCase()
)

function logout(): void {
    authStore.logout()
    router.push('/login')
}
</script>

<style scoped>
.navbar {
    width: 240px;
    height: 100vh;
    background: var(--surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    position: fixed;
    left: 0; top: 0; bottom: 0;
    z-index: 100;
    overflow-y: auto;       /* scroll when the menu is taller than the viewport */
    overscroll-behavior: contain;
}

.brand {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 24px 20px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--surface);
    z-index: 1;
}
.logo {
    width: 34px;
    height: 34px;
    background: var(--red);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 800;
    font-size: 13px;
    color: white;
    letter-spacing: 0.5px;
    flex-shrink: 0;
}
.brand-name {
    font-size: 17px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.3px;
}
.brand-red { color: var(--red); }

.nav-section {
    flex: 1;
    padding: 20px 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.nav-label {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    padding: 0 8px;
    margin-bottom: 8px;
}
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    text-decoration: none;
    font-size: 14px;
    font-weight: 500;
    transition: all 0.15s;
}
.nav-item:hover {
    background: var(--surface2);
    color: var(--text);
}
.nav-item.router-link-active {
    background: var(--red-dim);
    color: var(--red);
    border: 1px solid rgba(230,57,70,0.2);
}
.nav-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    opacity: 0.7;
}
.nav-item.router-link-active .nav-icon { opacity: 1; }

.nav-bottom {
    padding: 16px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.user-card {
    display: flex;
    align-items: center;
    gap: 10px;
}
.user-avatar {
    width: 34px;
    height: 34px;
    border-radius: 50%;
    background: var(--surface3);
    border: 1px solid var(--border2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    color: var(--red);
    flex-shrink: 0;
}
.user-name {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.user-role {
    font-size: 11px;
    color: var(--text-dim);
    text-transform: capitalize;
}
.logout-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    padding: 8px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 500;
    transition: all 0.15s;
}
.logout-btn:hover {
    background: var(--red-dim);
    border-color: var(--red);
    color: var(--red);
}
</style>
