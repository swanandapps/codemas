<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1 class="page-title">Cohort Investigation</h1>
                <p class="page-subtitle">Exam-level flag rates — click any cohort to investigate students and cheating rings</p>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading cohorts…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else>
            <div class="legend-row">
                <span class="legend-item"><span class="dot green"></span> &lt;10% flag rate</span>
                <span class="legend-item"><span class="dot amber"></span> 10–25%</span>
                <span class="legend-item"><span class="dot red"></span> &gt;25% — investigate</span>
            </div>

            <div v-if="cohorts.length === 0" class="empty-state">No exams with submissions yet.</div>

            <div v-else class="cohort-list">
                <router-link
                    v-for="c in cohorts"
                    :key="c.exam_id"
                    :to="`/dashboard/plagiarism/cohorts/${c.exam_id}`"
                    class="cohort-card"
                >
                    <div class="cohort-left">
                        <span :class="['health-dot', c.health]"></span>
                        <div class="cohort-info">
                            <div class="cohort-title">{{ c.exam_title }}</div>
                            <div class="cohort-stats">
                                {{ c.total_submissions }} students &bull;
                                {{ c.flagged_students }} flagged &bull;
                                {{ pct(c.flag_rate) }} flag rate
                            </div>
                        </div>
                    </div>
                    <div class="cohort-right">
                        <span class="chip b-chip">{{ c.behavioural_count }} behavioural</span>
                        <span class="chip s-chip">{{ c.similarity_count }} similarity</span>
                        <span v-if="c.ring_count > 0" class="chip r-chip">{{ c.ring_count }} {{ c.ring_count === 1 ? 'ring' : 'rings' }}</span>
                        <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                            <path d="M9 18l6-6-6-6"/>
                        </svg>
                    </div>
                </router-link>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

interface Cohort {
    exam_id: number
    exam_title: string
    total_submissions: number
    flagged_students: number
    flag_rate: number
    behavioural_count: number
    similarity_count: number
    ring_count: number
    health: 'green' | 'amber' | 'red'
}

const cohorts = ref<Cohort[]>([])
const loading = ref(true)
const error = ref('')

function pct(rate: number): string {
    return (rate * 100).toFixed(1) + '%'
}

async function load() {
    loading.value = true
    error.value = ''
    try {
        const res = await api.get('/plagiarism/cohorts/')
        cohorts.value = res.data
    } catch (e: any) {
        error.value = e.response?.data?.error || e.message
    } finally {
        loading.value = false
    }
}

onMounted(load)
</script>

<style scoped>
.page {
    max-width: 900px;
    margin: 0 auto;
    padding: 32px 24px;
}
.page-header { margin-bottom: 24px; }
.page-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 4px;
}
.page-subtitle {
    font-size: 13px;
    color: var(--text-dim);
    margin: 0;
}

.loading, .empty-state {
    text-align: center;
    padding: 48px;
    color: var(--text-dim);
    font-size: 14px;
}
.error-msg {
    text-align: center;
    padding: 48px;
    color: var(--red);
    font-size: 14px;
}

.legend-row {
    display: flex;
    gap: 20px;
    margin-bottom: 20px;
    font-size: 12px;
    color: var(--text-dim);
}
.legend-item { display: flex; align-items: center; gap: 6px; }
.dot {
    width: 10px; height: 10px;
    border-radius: 50%;
    flex-shrink: 0;
}
.dot.green  { background: #22c55e; }
.dot.amber  { background: #f59e0b; }
.dot.red    { background: var(--red); }

.cohort-list {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.cohort-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 16px 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    text-decoration: none;
    color: var(--text);
    transition: border-color 0.15s, box-shadow 0.15s;
    cursor: pointer;
}
.cohort-card:hover {
    border-color: #6366f1;
    box-shadow: 0 2px 12px rgba(99, 102, 241, 0.1);
}

.cohort-left { display: flex; align-items: center; gap: 14px; }

.health-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}
.health-dot.green  { background: #22c55e; box-shadow: 0 0 0 3px rgba(34,197,94,0.15); }
.health-dot.amber  { background: #f59e0b; box-shadow: 0 0 0 3px rgba(245,158,11,0.15); }
.health-dot.red    { background: var(--red); box-shadow: 0 0 0 3px rgba(230,57,70,0.15); }

.cohort-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 3px;
}
.cohort-stats {
    font-size: 12px;
    color: var(--text-dim);
}

.cohort-right { display: flex; align-items: center; gap: 8px; }

.chip {
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: 20px;
}
.b-chip { background: rgba(124,58,237,0.15); color: #a78bfa; }
.s-chip { background: rgba(245,158,11,0.15); color: #f59e0b; }
.r-chip { background: rgba(230,57,70,0.15); color: var(--red); }

.arrow-icon { color: var(--text-dim); flex-shrink: 0; margin-left: 4px; }
</style>
