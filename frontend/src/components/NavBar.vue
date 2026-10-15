<template>
    <nav class="navbar" :class="{ 'navbar--open': open }" aria-label="Main">
        <div class="brand">
            <span class="brand-name">CodeMas</span>
            <span class="brand-role">{{ roleLabel }}</span>
        </div>

        <div class="nav-section">
            <template v-if="authStore.isStudent">
                <router-link to="/home" class="nav-item" :class="{ 'is-active': activePath === '/home' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
                    Home
                </router-link>
                <router-link to="/exams" class="nav-item" :class="{ 'is-active': activePath === '/exams' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    Exams
                </router-link>
                <router-link to="/results" class="nav-item" :class="{ 'is-active': activePath === '/results' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    My results
                    <template v-if="counts.newDecisions"><span class="nav-badge" aria-hidden="true">{{ counts.newDecisions }}</span><span class="sr-only">({{ plural(counts.newDecisions, 'new decision') }})</span></template>
                </router-link>
                <router-link to="/disputes" class="nav-item" :class="{ 'is-active': activePath === '/disputes' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    Disputes
                    <template v-if="counts.newRulings"><span class="nav-badge" aria-hidden="true">{{ counts.newRulings }}</span><span class="sr-only">({{ plural(counts.newRulings, 'new ruling') }})</span></template>
                </router-link>
                <router-link to="/leaderboard" class="nav-item" :class="{ 'is-active': activePath === '/leaderboard' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6l4-4 4 4"/><path d="M12 2v10.3"/><path d="M4.93 10.93A10 10 0 1 0 19.07 10.93"/></svg>
                    Leaderboard
                </router-link>
            </template>

            <template v-if="authStore.isTrainer">
                <div class="nav-label">Teaching</div>
                <router-link to="/dashboard" class="nav-item" :class="{ 'is-active': activePath === '/dashboard' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                    Overview
                </router-link>
                <router-link to="/dashboard/history" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/history' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                    Exams
                </router-link>
                <router-link to="/dashboard/submissions" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/submissions' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
                    Submissions
                </router-link>
                <router-link to="/dashboard/students" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/students' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>
                    Students
                </router-link>
                <router-link to="/dashboard/create" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/create' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="16"/><line x1="8" y1="12" x2="16" y2="12"/></svg>
                    Create exam
                </router-link>
                <router-link to="/leaderboard" class="nav-item" :class="{ 'is-active': activePath === '/leaderboard' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 6l4-4 4 4"/><path d="M12 2v10.3"/><path d="M4.93 10.93A10 10 0 1 0 19.07 10.93"/></svg>
                    Leaderboard
                </router-link>

                <div class="nav-label" style="margin-top:12px">Integrity</div>
                <router-link to="/dashboard/plagiarism/cohorts" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/plagiarism/cohorts' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="9" cy="7" r="4"/><path d="M3 21v-2a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v2"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/><path d="M21 21v-2a4 4 0 0 0-3-3.87"/></svg>
                    Investigation
                    <template v-if="counts.casesToDecide"><span class="nav-badge" aria-hidden="true">{{ counts.casesToDecide }}</span><span class="sr-only">({{ plural(counts.casesToDecide, 'case') }} to decide)</span></template>
                </router-link>
                <router-link to="/dashboard/plagiarism/policy" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/plagiarism/policy' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M19.07 4.93A10 10 0 0 0 4.93 19.07"/><path d="M4.93 4.93A10 10 0 0 0 19.07 19.07"/></svg>
                    Policy
                </router-link>
                <router-link to="/dashboard/monitoring" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/monitoring' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                    Monitoring
                </router-link>
                <router-link to="/dashboard/code-search" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/code-search' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    Code search
                </router-link>

                <div class="nav-label" style="margin-top:12px">Support</div>
                <router-link to="/dashboard/support/disputes" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/support/disputes' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    Disputes
                    <template v-if="counts.openAppeals"><span class="nav-badge" aria-hidden="true">{{ counts.openAppeals }}</span><span class="sr-only">({{ plural(counts.openAppeals, 'open appeal') }})</span></template>
                </router-link>

                <div class="nav-label" style="margin-top:12px">Admin</div>
                <router-link to="/dashboard/accounts" class="nav-item" :class="{ 'is-active': activePath === '/dashboard/accounts' }" active-class="" exact-active-class="">
                    <svg class="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/><line x1="12" y1="11" x2="12" y2="17"/><line x1="9" y1="14" x2="15" y2="14"/></svg>
                    Accounts
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
import { computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { attention, loadAttention } from '../utils/attention'
import { plural } from '../utils/format'

// `open` is only used on narrow screens, where the sidebar slides in over the page
defineProps<{ open?: boolean }>()

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

// Highlight the nav item whose path is the longest prefix of the current URL, so detail
// pages (e.g. /dashboard/submissions/42) keep their section highlighted. Some detail pages
// live elsewhere in the URL tree, so they are mapped explicitly.
const NAV_PATHS = ['/home', '/exams', '/results', '/disputes', '/leaderboard', '/dashboard', '/dashboard/students', '/dashboard/submissions', '/dashboard/history', '/dashboard/create', '/leaderboard', '/dashboard/plagiarism/cohorts', '/dashboard/plagiarism/policy', '/dashboard/monitoring', '/dashboard/code-search', '/dashboard/support/disputes', '/dashboard/accounts']
const ALIASES: Record<string, string> = {
    '/exams': '/exams',
}
const activePath = computed<string>(() => {
    const path = route.path
    for (const [prefix, target] of Object.entries(ALIASES)) {
        if (path === prefix || path.startsWith(prefix + '/')) return target
    }
    let best = ''
    for (const p of NAV_PATHS) {
        if ((path === p || path.startsWith(p + '/')) && p.length > best.length) best = p
    }
    return best
})

// Badge counts: fetched once per page visited (no polling), shared with the page that shows them
watch(() => route.path, () => { if (authStore.user) loadAttention() }, { immediate: true })
const counts = computed(() => ({
    newDecisions: attention.data?.new_decisions ?? 0,   // student: My results
    newRulings: attention.data?.new_rulings ?? 0,       // student: Disputes
    casesToDecide: attention.data?.cases_to_decide ?? 0, // trainer: Investigation
    openAppeals: attention.data?.open_appeals ?? 0,     // trainer: Disputes
}))

const initials = computed<string>(() =>
    (authStore.user?.username || '').slice(0, 2).toUpperCase()
)

const roleLabel = computed<string>(() =>
    authStore.isTrainer ? 'Trainer' : 'Student'
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
    flex-direction: column;
    gap: 2px;
    padding: 24px 20px;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    background: var(--surface);
    z-index: 1;
}
.brand-name {
    font-family: var(--font-display);
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text);
}
.brand-role {
    font-size: 13px;
    color: var(--text-dim);
}

.nav-section {
    flex: 1;
    padding: 20px 12px;
    display: flex;
    flex-direction: column;
    gap: 2px;
}
.nav-label {
    font-size: 12px;
    font-weight: 500;
    color: var(--text-dim);
    padding: 0 10px;
    margin-bottom: 8px;
}
.nav-item {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 9px 14px;
    min-height: 38px;
    border-radius: var(--radius-pill);
    color: var(--text-muted);
    text-decoration: none;
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 500;
    transition: background-color 0.15s, color 0.15s;
}
.nav-item:hover {
    background: var(--surface2);
    color: var(--text);
    text-decoration: none;
}
.nav-item.is-active {
    background: var(--accent-tint);
    color: var(--red-ink);
    font-weight: 600;
}
.nav-icon {
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    opacity: 0.7;
}
.nav-item.is-active .nav-icon { opacity: 1; }
.nav-badge {
    margin-left: auto;
    min-width: 20px;
    height: 20px;
    padding: 0 6px;
    border-radius: var(--radius-pill);
    background: var(--red);
    color: #fff;
    font-size: 11px;
    font-weight: 700;
    line-height: 20px;
    text-align: center;
    font-variant-numeric: tabular-nums;
}

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
    color: var(--text);
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
    border-radius: var(--radius-pill);
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 500;
    transition: all 0.15s;
}
.logout-btn:hover {
    background: var(--surface2);
    border-color: var(--border2);
    color: var(--text);
}

@media (max-width: 899px) {
    .navbar {
        transform: translateX(-100%);
        transition: transform 0.2s ease;
        box-shadow: none;
        width: min(280px, 85vw);
    }
    .navbar--open {
        transform: none;
        box-shadow: var(--shadow-lg);
    }
}
</style>
