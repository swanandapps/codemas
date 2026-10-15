<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1>Cohort investigation</h1>
                <p class="page-subtitle">Flagged students per exam. Open a cohort to review students and similarity clusters.</p>
            </div>
        </div>


        <div>
            <div v-if="loading" class="loading">Loading cohorts…</div>
            <div v-else-if="error" class="error-msg">{{ error }}</div>

            <template v-else>
                <div class="legend-row">
                    <span class="legend-item" :title="METRIC_HELP.flagged"><span class="dot green"></span> Under {{ FLAGGED_WATCH_PCT }}% flagged students</span>
                    <span class="legend-item"><span class="dot amber"></span> {{ FLAGGED_WATCH_PCT }} to {{ FLAGGED_AT_RISK_PCT }}%</span>
                    <span class="legend-item"><span class="dot red"></span> {{ FLAGGED_AT_RISK_PCT }}% or more, investigate</span>
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
                                    <span class="stat-item" :title="METRIC_HELP.took">{{ plural(c.took, 'student') }} took the exam</span>
                                    <span class="stat-item">{{ plural(c.flagged_students, 'flagged student') }}</span>
                                    <span class="stat-item" :title="METRIC_HELP.flagged">{{ formatPct(c.flagged_students_rate) }} flagged students</span>
                                </div>
                            </div>
                        </div>
                        <div class="cohort-right">
                            <span class="chip b-chip">{{ plural(c.behavioural_count, 'behavioural flag') }}</span>
                            <span class="chip s-chip">{{ plural(c.similarity_count, 'similarity flag') }}</span>
                            <span v-if="c.ring_count > 0" class="chip r-chip">{{ plural(c.ring_count, 'similarity cluster') }}</span>
                            <svg class="arrow-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16">
                                <path d="M9 18l6-6-6-6"/>
                            </svg>
                        </div>
                    </router-link>
                </div>
            </template>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { formatPct, plural } from '../utils/format'
import { METRIC_HELP, FLAGGED_WATCH_PCT, FLAGGED_AT_RISK_PCT } from '../utils/metrics'

interface Cohort {
    exam_id: number
    exam_title: string
    total_submissions: number
    took: number
    flagged_students: number
    flagged_students_rate: number | null
    behavioural_count: number
    similarity_count: number
    ring_count: number
    health: 'green' | 'amber' | 'red'
}

const cohorts = ref<Cohort[]>([])
const loading = ref(true)
const error = ref('')

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
.page-header { margin-bottom: 24px; }
.page-subtitle {
    font-size: 15px;
    color: var(--text-muted);
    margin: 4px 0 0;
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
    color: var(--red-ink);
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
.dot.green  { background: var(--green); }
.dot.amber  { background: var(--yellow); }
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
    flex-wrap: wrap;
    gap: 12px;
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
    border-color: var(--accent);
}

.cohort-left { display: flex; align-items: center; gap: 14px; }

.health-dot {
    width: 12px; height: 12px;
    border-radius: 50%;
    flex-shrink: 0;
}
.health-dot.green  { background: var(--green); box-shadow: 0 0 0 3px var(--green-dim); }
.health-dot.amber  { background: var(--yellow); box-shadow: 0 0 0 3px var(--yellow-dim); }
.health-dot.red    { background: var(--red); box-shadow: 0 0 0 3px var(--red-dim); }

.cohort-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 3px;
}
.cohort-stats {
    display: flex;
    flex-wrap: wrap;
    gap: 4px 10px;
    font-size: 12px;
    color: var(--text-dim);
}
.stat-item { white-space: nowrap; }

.cohort-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.chip {
    font-size: 11px;
    font-weight: 600;
    padding: 3px 8px;
    border-radius: var(--radius-pill);
    white-space: nowrap;
}
/* Behavioural signal is a risk indicator, shown in amber like other medium-risk signals. */
.b-chip { background: var(--yellow-dim); color: var(--amber-ink); }
.s-chip { background: var(--surface2); color: var(--text-muted); }
.r-chip { background: var(--red-dim); color: var(--red-ink); }

.arrow-icon { color: var(--text-dim); flex-shrink: 0; margin-left: 4px; }
</style>
