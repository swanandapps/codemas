<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1 class="page-title">Exam Operations</h1>
                <p v-if="data" class="page-subtitle">{{ data.exam.title }}</p>
            </div>
            <div class="header-right">
                <div v-if="data?.exam.is_live" class="live-pill">
                    <span class="live-dot"></span> LIVE — {{ fmtTime(data.exam.seconds_remaining) }} remaining
                </div>
                <div v-else-if="data" class="ended-pill">Exam ended</div>
                <button class="refresh-btn" @click="load" :disabled="loading">↻ Refresh</button>
                <button
                    v-if="data?.exam.is_live"
                    class="end-btn"
                    @click="endExam"
                    :disabled="ending"
                >
                    {{ ending ? 'Ending…' : 'End Exam' }}
                </button>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else-if="data">
            <!-- KPI strip -->
            <div class="kpi-strip">
                <div class="kpi-card">
                    <div class="kpi-label">Students Attempted</div>
                    <div class="kpi-value">{{ data.total_students }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Passed</div>
                    <div class="kpi-value green">{{ data.passed_count }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Flagged</div>
                    <div class="kpi-value" :class="data.flagged_count > 0 ? 'red' : 'green'">{{ data.flagged_count }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Pass Rate</div>
                    <div class="kpi-value" :class="passRateClass">
                        {{ data.total_students ? Math.round(data.passed_count / data.total_students * 100) : 0 }}%
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Flag Rate</div>
                    <div class="kpi-value" :class="data.flagged_count > 0 ? 'red' : 'green'">
                        {{ data.total_students ? Math.round(data.flagged_count / data.total_students * 100) : 0 }}%
                    </div>
                </div>
            </div>

            <div class="two-col">
                <!-- Student ops table -->
                <div class="card">
                    <h2 class="card-title">Student Status</h2>
                    <table class="data-table">
                        <thead>
                            <tr><th>Student</th><th>Attempts</th><th>Last Status</th><th>Flag</th><th>Submitted</th><th></th></tr>
                        </thead>
                        <tbody>
                            <tr v-for="s in data.student_ops" :key="s.student_id" :class="{ 'row-flagged': s.has_flag }">
                                <td>
                                    <router-link :to="`/dashboard/support/student/${s.student_id}`" class="student-link">
                                        {{ s.username }}
                                    </router-link>
                                </td>
                                <td>{{ s.attempts }}</td>
                                <td>
                                    <span class="badge" :class="statusClass(s.last_status)">{{ s.last_status }}</span>
                                </td>
                                <td>
                                    <span v-if="s.has_flag" class="flag-icon" title="Behavioural flag">⚠</span>
                                    <span v-else class="ok-icon">✓</span>
                                </td>
                                <td class="muted small">{{ s.submitted_at ? fmtDate(s.submitted_at) : '—' }}</td>
                                <td>
                                    <router-link :to="`/dashboard/support/student/${s.student_id}`" class="link-btn">Case →</router-link>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Recent anomaly feed -->
                <div class="card">
                    <h2 class="card-title">Anomaly Feed</h2>
                    <p class="card-sub">Behavioural flags raised during this exam</p>

                    <div v-if="!data.recent_flags.length" class="empty-feed">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="28" height="28"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                        <p>No anomalies detected</p>
                    </div>

                    <div v-for="f in data.recent_flags" :key="f.flag_id" class="feed-item">
                        <div class="feed-header">
                            <router-link :to="`/dashboard/support/student/${f.student_id}`" class="student-link">{{ f.student }}</router-link>
                            <span class="badge" :class="confClass(f.confidence)">{{ f.confidence }}</span>
                        </div>
                        <div class="feed-question">{{ f.question }}</div>
                        <div class="feed-signals">
                            <span v-for="sig in f.signals" :key="sig" class="signal-chip">{{ sig }}</span>
                        </div>
                        <div class="feed-footer">
                            <span class="risk-num" :class="riskNumClass(f.risk_score)">{{ (f.risk_score * 100).toFixed(0) }}% risk</span>
                            <span class="badge" :class="reviewClass(f.review_status)">{{ f.review_status }}</span>
                            <router-link :to="`/dashboard/submissions/${f.submission_id}`" class="link-btn" style="margin-left:auto">View →</router-link>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route   = useRoute()
const loading = ref(true)
const error   = ref('')
const data    = ref<any>(null)
const ending  = ref(false)

async function endExam() {
    if (!confirm('End this exam? This will close submissions and trigger the plagiarism batch. This cannot be undone.')) return
    ending.value = true
    try {
        await api.patch(`/exams/${route.params.id}/`, { is_active: false })
        await load()
    } catch {
        alert('Failed to end exam. Please try again.')
    } finally {
        ending.value = false
    }
}

async function load() {
    loading.value = true
    error.value   = ''
    try {
        const res = await api.get(`/support/exam/${route.params.id}/ops/`)
        data.value = res.data
    } catch {
        error.value = 'Failed to load exam ops.'
    } finally {
        loading.value = false
    }
}

onMounted(load)

const passRateClass = computed(() => {
    if (!data.value) return ''
    const r = data.value.total_students ? data.value.passed_count / data.value.total_students * 100 : 0
    return r >= 70 ? 'green' : r >= 40 ? 'warn' : 'red'
})

function fmtTime(secs: number): string {
    const m = Math.floor(secs / 60)
    const s = secs % 60
    return `${m}m ${s}s`
}
function fmtDate(iso: string): string {
    return new Date(iso).toLocaleString()
}
function statusClass(s: string) {
    return s === 'passed' ? 'badge-green' : s === 'failed' ? 'badge-red' : s === 'running' ? 'badge-yellow' : 'badge-dim'
}
function confClass(c: string) {
    return c === 'high' ? 'badge-red' : c === 'medium' ? 'badge-yellow' : 'badge-dim'
}
function reviewClass(s: string) {
    return s === 'confirmed' ? 'badge-red' : s === 'dismissed' ? 'badge-green' : 'badge-yellow'
}
function riskNumClass(r: number) {
    return r >= 0.7 ? 'text-red' : r >= 0.4 ? 'text-warn' : 'text-green'
}
</script>

<style scoped>
.page { padding: 32px 40px; max-width: 1200px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; }
.page-title  { font-size: 22px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--text-dim); margin: 0; }
.loading   { color: var(--text-dim); padding: 40px 0; }
.error-msg { color: var(--red); padding: 20px 0; }

.header-right { display: flex; align-items: center; gap: 10px; }

.live-pill {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 14px; background: rgba(34,197,94,0.1);
    border: 1px solid rgba(34,197,94,0.3);
    border-radius: 20px; font-size: 12px; font-weight: 700; color: #22c55e;
}
.live-dot {
    width: 8px; height: 8px; border-radius: 50%; background: #22c55e;
    animation: pulse 1.5s infinite;
}
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.3; }
}
.ended-pill {
    padding: 6px 14px; background: var(--surface2);
    border: 1px solid var(--border); border-radius: 20px;
    font-size: 12px; font-weight: 600; color: var(--text-dim);
}
.refresh-btn {
    padding: 6px 14px; font-size: 12px; font-weight: 600;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer;
}
.refresh-btn:hover { color: var(--text); }
.end-btn {
    padding: 6px 16px; font-size: 12px; font-weight: 700;
    background: var(--red); border: none;
    border-radius: var(--radius-sm); color: #fff; cursor: pointer;
    transition: opacity 0.15s;
}
.end-btn:hover { opacity: 0.85; }
.end-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* KPI strip */
.kpi-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 20px; }
.kpi-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; color: var(--text); }
.kpi-value.green { color: #22c55e; }
.kpi-value.red   { color: var(--red); }
.kpi-value.warn  { color: #f59e0b; }

.two-col { display: grid; grid-template-columns: 1.2fr 1fr; gap: 16px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 24px; }
.card-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0 0 4px; }
.card-sub   { font-size: 12px; color: var(--text-dim); margin: 0 0 16px; }

.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th { text-align: left; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); padding: 0 8px 8px; border-bottom: 1px solid var(--border); }
.data-table td { padding: 9px 8px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: middle; }
.data-table tr:last-child td { border-bottom: none; }
.row-flagged td { background: rgba(230,57,70,0.04); }
.muted { color: var(--text-dim); }
.small { font-size: 12px; }

.student-link { font-weight: 600; color: var(--red); text-decoration: none; }
.student-link:hover { text-decoration: underline; }

.flag-icon { color: #f59e0b; font-size: 14px; }
.ok-icon   { color: #22c55e; font-size: 14px; }

.link-btn { font-size: 12px; color: var(--red); text-decoration: none; font-weight: 600; }
.link-btn:hover { text-decoration: underline; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-yellow { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-red    { background: rgba(230,57,70,0.12);  color: var(--red); }
.badge-dim    { background: var(--surface2);        color: var(--text-dim); }

.empty-feed { text-align: center; padding: 32px 0; color: var(--text-dim); }
.empty-feed svg { margin: 0 auto 8px; display: block; opacity: 0.4; }
.empty-feed p { font-size: 13px; margin: 0; }

.feed-item {
    border-bottom: 1px solid var(--border); padding: 12px 0;
}
.feed-item:last-child { border-bottom: none; }
.feed-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px; }
.feed-question { font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.feed-signals { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.signal-chip { font-size: 10px; padding: 2px 6px; background: var(--surface2); border-radius: 4px; color: var(--text-dim); }
.feed-footer { display: flex; align-items: center; gap: 8px; }
.risk-num { font-size: 12px; font-weight: 700; }
.text-red   { color: var(--red); }
.text-warn  { color: #f59e0b; }
.text-green { color: #22c55e; }
</style>
