<template>
    <div class="exams-page">
        <div class="page-header">
            <div>
                <h1>Exams</h1>
                <p class="page-sub">Select an exam to view details and start</p>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Loading exams...</div>
        <div v-else-if="error" class="state-msg error">{{ error }}</div>
        <div v-else-if="exams.length === 0" class="state-msg">No exams available yet.</div>

        <div v-else class="exam-grid">
            <router-link
                v-for="exam in exams"
                :key="exam.id"
                :to="exam.finished_at ? '/results' : `/exams/${exam.id}`"
                class="exam-card"
            >
                <div class="card-top">
                    <h3>{{ exam.title }}</h3>
                    <span v-if="exam.finished_at" class="status-badge inactive">Submitted · see results</span>
                    <span v-else :class="['status-badge', exam.is_active ? 'active' : 'inactive']">
                        {{ exam.is_active ? 'Active' : 'Closed' }}
                    </span>
                </div>
                <p class="exam-desc">{{ exam.description }}</p>
                <div class="exam-meta">
                    <span class="meta-item">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                        {{ plural(exam.duration_minutes, 'minute') }}
                    </span>
                    <span class="meta-item">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                        {{ plural(exam.questions?.length || 0, 'question') }}
                    </span>
                </div>
            </router-link>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { plural } from '../utils/format'

interface Exam {
    id: number
    title: string
    description: string
    duration_minutes: number
    is_active: boolean
    finished_at?: string | null   // the student ended this exam early
}

const exams = ref<Exam[]>([])
const loading = ref<boolean>(true)
const error = ref<string>('')

onMounted(async () => {
    try {
        const res = await api.get('/exams/')
        exams.value = res.data
    } catch (e: any) {
        error.value = e.response?.data?.error || 'Failed to load exams'
    } finally {
        loading.value = false
    }
})

</script>

<style scoped>
.exams-page { max-width: 900px; margin: 0 auto; }
.page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 32px;
}
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
.state-msg { color: var(--text-muted); padding: 40px 0; }
.state-msg.error { color: var(--red-ink); }
.exam-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(380px, 1fr));
    gap: 16px;
}
.exam-card {
    display: block;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 22px;
    color: inherit;
    text-decoration: none;
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
    position: relative;
}
.exam-card:hover {
    border-color: var(--border2);
    box-shadow: var(--shadow);
}
.card-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 8px;
}
.card-top h3 { font-size: 16px; font-weight: 600; color: var(--text); }
.status-badge {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
}
.status-badge.active { background: var(--green-dim); color: var(--green-ink); }
.status-badge.inactive { background: var(--surface2); color: var(--text-muted); } /* closed is a state, not a failure */
.exam-desc {
    font-size: 13px;
    color: var(--text-muted);
    margin-bottom: 16px;
    line-height: 1.6;
}
.exam-meta {
    display: flex;
    gap: 16px;
}
.meta-item {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 13px;
    color: var(--text-dim);
}

@media (max-width: 600px) {
    .exam-grid { grid-template-columns: 1fr; }
    .page-header { flex-wrap: wrap; gap: 8px; }
}
</style>
