<template>
    <div class="page">
        <router-link to="/dashboard/plagiarism/cohorts" class="back-link">
            ← All Cohorts
        </router-link>

        <div v-if="loading" class="loading">Loading cohort data…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else-if="data">
            <div class="page-header">
                <div>
                    <h1 class="page-title">{{ data.exam.title }}</h1>
                    <p class="page-subtitle" v-if="data.exam.start_time">
                        {{ fmtDate(data.exam.start_time) }}
                        <span v-if="data.exam.end_time"> → {{ fmtDate(data.exam.end_time) }}</span>
                    </p>
                </div>
                <span :class="['health-badge', healthClass]">{{ healthLabel }}</span>
            </div>

            <div class="kpi-strip">
                <div class="kpi-card">
                    <div class="kpi-label">Total Students</div>
                    <div class="kpi-value">{{ data.stats.total_submissions }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Flagged Students</div>
                    <div class="kpi-value" :class="rateClass(data.stats.flag_rate)">
                        {{ data.stats.flagged_students }}
                    </div>
                    <div class="kpi-sub">{{ pct(data.stats.flag_rate) }} flag rate</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Behavioural Flags</div>
                    <div class="kpi-value">{{ data.stats.behavioural_count }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Similarity Pairs</div>
                    <div class="kpi-value">{{ data.stats.similarity_count }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cheating Rings</div>
                    <div class="kpi-value" :class="data.stats.ring_count > 0 ? 'danger' : 'safe'">
                        {{ data.stats.ring_count }}
                    </div>
                </div>
            </div>

            <!-- Cheating rings -->
            <div v-if="data.rings.length" class="section">
                <h2 class="section-title">
                    Cheating Rings
                    <span class="section-sub">Students connected by shared similarity flags</span>
                </h2>
                <div class="rings-list">
                    <div v-for="(ring, idx) in data.rings" :key="idx" class="ring-card">
                        <div class="ring-header">
                            <div class="ring-size-badge">{{ ring.size }} members</div>
                            <div class="ring-scores">
                                <span class="score-pill sim">avg sim {{ pct(ring.avg_similarity) }}</span>
                                <span class="score-pill max">max {{ pct(ring.max_similarity) }}</span>
                                <span v-if="ring.confirmed > 0" class="score-pill confirmed">
                                    {{ ring.confirmed }} confirmed
                                </span>
                            </div>
                        </div>
                        <div class="ring-members">
                            <router-link
                                v-for="m in ring.members"
                                :key="m.student_id"
                                :to="`/dashboard/support/student/${m.student_id}`"
                                class="member-chip"
                            >
                                {{ m.username }}
                            </router-link>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Student risk ranking -->
            <div class="section">
                <h2 class="section-title">
                    Student Risk Ranking
                    <span class="section-sub">Flagged students sorted by combined risk score</span>
                </h2>

                <div v-if="data.students.length === 0" class="empty-state">
                    No flagged students in this cohort.
                </div>
                <table v-else class="student-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Student</th>
                            <th>Combined Risk</th>
                            <th>Behavioural</th>
                            <th>Sim Pairs</th>
                            <th>Max Sim</th>
                            <th>Past Flags</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="(s, idx) in data.students" :key="s.student_id" :class="rowClass(s.combined_risk)">
                            <td class="rank-cell">{{ idx + 1 }}</td>
                            <td>
                                <router-link :to="`/dashboard/support/student/${s.student_id}`" class="student-link">
                                    {{ s.username }}
                                </router-link>
                            </td>
                            <td>
                                <div class="risk-bar-wrap">
                                    <div class="risk-bar-track">
                                        <div class="risk-bar-fill" :style="{ width: pct(s.combined_risk), background: riskColor(s.combined_risk) }"></div>
                                    </div>
                                    <span class="risk-val">{{ s.combined_risk.toFixed(2) }}</span>
                                </div>
                            </td>
                            <td>
                                <span v-if="s.behavioural_risk !== null" :class="['conf-badge', s.behavioural_confidence || '']">
                                    {{ s.behavioural_confidence }} ({{ Number(s.behavioural_risk).toFixed(2) }})
                                </span>
                                <span v-else class="na">—</span>
                            </td>
                            <td>{{ s.similarity_pairs > 0 ? s.similarity_pairs : '—' }}</td>
                            <td>{{ s.max_similarity > 0 ? pct(s.max_similarity) : '—' }}</td>
                            <td>
                                <span v-if="s.past_flags > 0" class="past-flag-badge">{{ s.past_flags }} prior</span>
                                <span v-else class="na">—</span>
                            </td>
                            <td>
                                <router-link :to="`/dashboard/support/student/${s.student_id}`" class="investigate-btn">
                                    Investigate →
                                </router-link>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

interface RingMember { student_id: number; username: string }
interface Ring {
    size: number
    members: RingMember[]
    avg_similarity: number
    max_similarity: number
    confirmed: number
}
interface Student {
    student_id: number
    username: string
    submission_id: number
    behavioural_risk: number | null
    behavioural_confidence: string | null
    similarity_pairs: number
    max_similarity: number
    past_flags: number
    combined_risk: number
}
interface CohortDetail {
    exam: { id: number; title: string; start_time: string | null; end_time: string | null }
    stats: { total_submissions: number; flagged_students: number; flag_rate: number; behavioural_count: number; similarity_count: number; ring_count: number }
    students: Student[]
    rings: Ring[]
}

const route = useRoute()
const data = ref<CohortDetail | null>(null)
const loading = ref(true)
const error = ref('')

const healthClass = computed(() => {
    if (!data.value) return ''
    const r = data.value.stats.flag_rate
    return r >= 0.25 ? 'red' : r >= 0.10 ? 'amber' : 'green'
})
const healthLabel = computed(() => {
    return healthClass.value === 'red' ? 'High Risk'
         : healthClass.value === 'amber' ? 'Moderate'
         : 'Healthy'
})

function pct(val: number): string { return (val * 100).toFixed(1) + '%' }
function rateClass(rate: number): string { return rate >= 0.25 ? 'danger' : rate >= 0.10 ? 'warn' : '' }
function rowClass(risk: number): string { return risk >= 0.6 ? 'row-high' : risk >= 0.3 ? 'row-med' : '' }
function riskColor(risk: number): string {
    if (risk >= 0.7) return 'var(--red)'
    if (risk >= 0.4) return '#f59e0b'
    return '#22c55e'
}
function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

async function load() {
    loading.value = true
    error.value = ''
    try {
        const res = await api.get(`/plagiarism/cohorts/${route.params.id}/`)
        data.value = res.data
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
    max-width: 1000px;
    margin: 0 auto;
    padding: 32px 24px;
}

.back-link {
    display: inline-block;
    font-size: 13px;
    color: #6366f1;
    text-decoration: none;
    margin-bottom: 20px;
}
.back-link:hover { text-decoration: underline; }

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

.page-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    margin-bottom: 24px;
}
.page-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 4px;
}
.page-subtitle { font-size: 13px; color: var(--text-dim); margin: 0; }

.health-badge {
    font-size: 11px;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 20px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
.health-badge.green { background: rgba(34,197,94,0.12);  color: #22c55e; }
.health-badge.amber { background: rgba(245,158,11,0.12); color: #f59e0b; }
.health-badge.red   { background: rgba(230,57,70,0.12);  color: var(--red); }

/* KPI strip */
.kpi-strip {
    display: flex;
    gap: 12px;
    margin-bottom: 28px;
    flex-wrap: wrap;
}
.kpi-card {
    flex: 1;
    min-width: 120px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
}
.kpi-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; }
.kpi-value { font-size: 28px; font-weight: 700; color: var(--text); line-height: 1; }
.kpi-value.warn   { color: #f59e0b; }
.kpi-value.danger { color: var(--red); }
.kpi-value.safe   { color: #22c55e; }
.kpi-sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }

/* Sections */
.section { margin-bottom: 36px; }
.section-title {
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
    margin: 0 0 14px;
    display: flex;
    align-items: baseline;
    gap: 10px;
}
.section-sub { font-size: 12px; color: var(--text-dim); font-weight: 400; }

/* Rings */
.rings-list { display: flex; flex-direction: column; gap: 10px; }
.ring-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-left: 4px solid var(--red);
    border-radius: var(--radius);
    padding: 14px 18px;
}
.ring-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 10px;
    flex-wrap: wrap;
}
.ring-size-badge {
    font-size: 13px;
    font-weight: 700;
    color: var(--red);
    background: rgba(230,57,70,0.12);
    padding: 3px 10px;
    border-radius: 20px;
}
.ring-scores { display: flex; gap: 8px; flex-wrap: wrap; }
.score-pill {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 20px;
}
.score-pill.sim       { background: rgba(245,158,11,0.15); color: #f59e0b; }
.score-pill.max       { background: rgba(230,57,70,0.12);  color: var(--red); }
.score-pill.confirmed { background: rgba(34,197,94,0.12);  color: #22c55e; }

.ring-members { display: flex; flex-wrap: wrap; gap: 8px; }
.member-chip {
    font-size: 12px;
    font-weight: 600;
    padding: 4px 12px;
    background: var(--surface2);
    border-radius: 20px;
    color: var(--text);
    text-decoration: none;
    border: 1px solid var(--border);
    transition: background 0.15s;
}
.member-chip:hover { background: rgba(99,102,241,0.15); color: #818cf8; }

/* Student table */
.student-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.student-table th {
    text-align: left;
    padding: 8px 12px;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-dim);
    text-transform: uppercase;
    border-bottom: 1px solid var(--border);
}
.student-table td {
    padding: 10px 12px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: middle;
}
.student-table tr:last-child td { border-bottom: none; }
.student-table tr.row-high { background: rgba(230,57,70,0.05); }
.student-table tr.row-med  { background: rgba(245,158,11,0.05); }

.rank-cell { color: var(--text-dim); font-size: 12px; font-weight: 600; width: 32px; }

.student-link {
    font-weight: 600;
    color: var(--text);
    text-decoration: none;
}
.student-link:hover { color: #818cf8; }

.risk-bar-wrap { display: flex; align-items: center; gap: 8px; }
.risk-bar-track {
    flex: 1;
    height: 6px;
    background: var(--surface2);
    border-radius: 3px;
    overflow: hidden;
    min-width: 60px;
}
.risk-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.risk-val { font-size: 12px; font-weight: 600; color: var(--text); white-space: nowrap; }

.conf-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 20px;
}
.conf-badge.high   { background: rgba(230,57,70,0.12);  color: var(--red); }
.conf-badge.medium { background: rgba(245,158,11,0.12); color: #f59e0b; }
.conf-badge.low    { background: var(--surface2);        color: var(--text-dim); }

.past-flag-badge {
    font-size: 11px;
    font-weight: 600;
    padding: 2px 8px;
    background: rgba(245,158,11,0.15);
    color: #f59e0b;
    border-radius: 20px;
}

.na { color: var(--text-dim); }

.investigate-btn {
    font-size: 12px;
    font-weight: 600;
    color: #818cf8;
    text-decoration: none;
    white-space: nowrap;
}
.investigate-btn:hover { text-decoration: underline; }
</style>
