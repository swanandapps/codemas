<template>
  <div>
    <div class="detail">
        <div class="page-header">
            <button class="back-btn" @click="router.back()">← Back</button>
            <div v-if="student">
                <h1>{{ student.username }}</h1>
                <span class="cohort-tag">{{ student.cohort || 'No cohort' }}</span>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading...</div>

        <template v-else-if="student">
            <!-- KPI row -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">
                        Pass Rate
                        <span class="tip" data-tip="% of all submissions that passed all hidden test cases across every contest">?</span>
                    </div>
                    <div class="kpi-value" :class="rateColor(student.pass_rate)">{{ student.pass_rate }}%</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">
                        Submissions
                        <span class="tip" data-tip="Total attempts made across all weekly contests, including retries">?</span>
                    </div>
                    <div class="kpi-value">{{ student.total_submissions }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">
                        Integrity Confidence
                        <span class="tip" data-tip="How confident we are this student wrote their own code. LOW = 3+ signals fired (paste + speed + tab switches simultaneously) — most suspicious. HIGH = 1 signal — likely fine. Clean = no flags at all.">?</span>
                    </div>
                    <div :class="['kpi-value', 'conf-value', maxConfidence ?? 'clean']">
                        {{ maxConfidence ? maxConfidence.toUpperCase() : 'Clean' }}
                    </div>
                    <div class="kpi-sub">{{ behaviouralFlags.length }} flag{{ behaviouralFlags.length !== 1 ? 's' : '' }} total</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">
                        Cohort Rank
                        <span class="tip" data-tip="Pass rate ranking within this student's cohort. #1 = highest pass rate.">?</span>
                    </div>
                    <div class="kpi-value">
                        {{ student.cohort_rank ? `#${student.cohort_rank} / ${student.cohort_size}` : '—' }}
                    </div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="tab-row">
                <button :class="['tab-btn', activeTab === 'overview' ? 'active' : '']" @click="activeTab = 'overview'">Overview</button>
                <button :class="['tab-btn', activeTab === 'plagiarism' ? 'active' : '']" @click="activeTab = 'plagiarism'">
                    Plagiarism
                    <span class="tab-badge" v-if="behaviouralFlags.length + plagiarismFlags.length > 0">
                        {{ behaviouralFlags.length + plagiarismFlags.length }}
                    </span>
                </button>
            </div>

            <!-- ── OVERVIEW TAB ── -->
            <template v-if="activeTab === 'overview'">
            <!-- Performance trend chart -->
            <div class="chart-card" v-if="performanceTrend.length > 0">
                <h3>Weekly Contest Performance &nbsp;<span class="legend-dot passed">● passed</span><span class="legend-dot failed">● failed</span></h3>
                <apexchart type="line" height="220" :options="trendOptions" :series="trendSeries" />
            </div>

            <!-- Per question breakdown -->
            <h2 class="section-title">Attempts by Question</h2>
            <div v-for="q in questions" :key="q.question_id" class="question-block">
                <div class="question-header">
                    <span class="q-title">{{ q.question_title }}</span>
                    <span class="q-meta">{{ q.attempts.length }} / {{ q.max_attempts }} attempts</span>
                </div>
                <table class="attempt-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Status</th>
                            <th>Language</th>
                            <th>Exec Time</th>
                            <th>Solve Time</th>
                            <th>Time Used %</th>
                            <th>Paste</th>
                            <th>Plagiarism</th>
                            <th>Submitted</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="a in q.attempts" :key="a.attempt_number" class="attempt-row" @click="openDrawer(a, q.question_title)">
                            <td>#{{ a.attempt_number }}</td>
                            <td><span :class="['status', a.status]">{{ a.status }}</span></td>
                            <td>{{ a.language }}</td>
                            <td>{{ a.execution_time_ms ? a.execution_time_ms + 'ms' : '—' }}</td>
                            <td>{{ a.solve_time_seconds ? formatSolveTime(a.solve_time_seconds) : '—' }}</td>
                            <td>
                                <div class="pct-bar">
                                    <div
                                        class="pct-fill"
                                        :style="{ width: (a.percent_time_used || 0) + '%' }"
                                        :class="pctClass(a.percent_time_used)"
                                    />
                                    <span>{{ a.percent_time_used?.toFixed(0) || 0 }}%</span>
                                </div>
                            </td>
                            <td>
                                <span v-if="a.paste_detected" class="badge warn">⚠ Detected</span>
                                <span v-else class="badge ok">✓</span>
                            </td>
                            <td>
                                <span v-if="a.plagiarism" :class="['badge', a.plagiarism.review_status === 'confirmed' ? 'danger' : 'warn']">
                                    {{ (a.plagiarism.score * 100).toFixed(0) }}%
                                </span>
                                <span v-else class="badge ok">✓</span>
                            </td>
                            <td class="date">{{ formatDate(a.submitted_at) }}</td>
                            <td>
                                <button class="view-code-btn" @click.stop="openDrawer(a, q.question_title)">
                                    View Details
                                </button>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            </template><!-- end overview tab -->

            <!-- ── PLAGIARISM TAB ── -->
            <template v-if="activeTab === 'plagiarism'">

                <!-- Behavioural Flags -->
                <h2 class="section-title">Behavioural Flags <span class="section-count">{{ behaviouralFlags.length }}</span></h2>
                <div v-if="behaviouralFlags.length === 0" class="empty-state">No behavioural flags for this student.</div>
                <div v-for="f in behaviouralFlags" :key="f.id" class="flag-card">
                    <div class="flag-card-top">
                        <div class="flag-card-left">
                            <span class="flag-question">{{ f.question }}</span>
                            <span class="flag-exam">{{ f.exam }}</span>
                        </div>
                        <div class="flag-card-right">
                            <span :class="['conf-badge', f.confidence]">{{ f.confidence }}</span>
                            <span class="risk-score">Risk {{ (f.risk_score * 100).toFixed(0) }}%</span>
                            <span :class="['badge', f.review_status]">{{ f.review_status }}</span>
                        </div>
                    </div>
                    <div class="score-bars">
                        <div class="score-bar-row">
                            <span class="score-label">Paste</span>
                            <div class="score-track"><div class="score-fill paste-fill" :style="{ width: (f.paste_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (f.paste_score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="score-bar-row">
                            <span class="score-label">Speed</span>
                            <div class="score-track"><div class="score-fill time-fill" :style="{ width: (f.time_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (f.time_score * 100).toFixed(0) }}%</span>
                        </div>
                    </div>
                    <div class="signals-list" v-if="f.signals?.length">
                        <span v-for="sig in f.signals" :key="sig" class="signal-chip">⚠ {{ sig }}</span>
                    </div>
                </div>

                <!-- Similarity Flags -->
                <h2 class="section-title" style="margin-top:28px">Similarity Flags <span class="section-count">{{ plagiarismFlags.length }}</span></h2>
                <div v-if="plagiarismFlags.length === 0" class="empty-state">No similarity matches found.</div>
                <div v-for="f in plagiarismFlags" :key="f.id" class="flag-card">
                    <div class="flag-card-top">
                        <div class="flag-card-left">
                            <span class="flag-question">{{ f.question }}</span>
                            <span class="flag-exam">Matched with <strong>{{ f.matched_student }}</strong></span>
                        </div>
                        <div class="flag-card-right">
                            <span class="sim-score-badge">{{ (f.similarity_score * 100).toFixed(1) }}% similar</span>
                            <span :class="['badge', f.review_status]">{{ f.review_status }}</span>
                        </div>
                    </div>
                </div>

            </template><!-- end plagiarism tab -->
        </template>
    </div>

    <!-- Submission forensic drawer -->
    <transition name="drawer">
        <div v-if="drawer.open" class="drawer-backdrop" @click.self="drawer.open = false">
            <div class="drawer">
                <!-- Drawer header -->
                <div class="drawer-header">
                    <div>
                        <div class="drawer-title">{{ drawer.questionTitle }}</div>
                        <div class="drawer-meta">
                            Attempt #{{ drawer.attempt?.attempt_number }}
                            &nbsp;·&nbsp;
                            <span :class="['status', drawer.attempt?.status]">{{ drawer.attempt?.status }}</span>
                            &nbsp;·&nbsp;
                            {{ drawer.attempt ? formatDate(drawer.attempt.submitted_at) : '' }}
                        </div>
                    </div>
                    <button class="drawer-close" @click="drawer.open = false">✕</button>
                </div>

                <div class="drawer-body">
                    <!-- Raw metrics row -->
                    <div class="drawer-metrics">
                        <div class="metric-chip">
                            <span class="metric-label">Exec Time</span>
                            <span class="metric-val">{{ drawer.attempt?.execution_time_ms ? drawer.attempt.execution_time_ms + 'ms' : '—' }}</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Solve Time</span>
                            <span class="metric-val">{{ drawer.attempt?.solve_time_seconds ? formatSolveTime(drawer.attempt.solve_time_seconds) : '—' }}</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Time Used</span>
                            <span class="metric-val">{{ drawer.attempt?.percent_time_used?.toFixed(0) ?? '—' }}%</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Paste Chars</span>
                            <span :class="['metric-val', drawer.attempt?.paste_detected ? 'val-warn' : '']">
                                {{ drawer.attempt?.paste_char_count ?? 0 }}
                            </span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Tab Switches</span>
                            <span :class="['metric-val', (drawer.attempt?.tab_switch_count ?? 0) >= 3 ? 'val-warn' : '']">
                                {{ drawer.attempt?.tab_switch_count ?? 0 }}
                            </span>
                        </div>
                    </div>

                    <!-- Behavioural analysis -->
                    <div v-if="drawer.attempt?.behavioural" class="drawer-section">
                        <div class="drawer-section-title">
                            Behavioural Analysis
                            <span :class="['conf-pill', drawer.attempt.behavioural.confidence]">
                                {{ drawer.attempt.behavioural.confidence.toUpperCase() }} integrity confidence
                            </span>
                            <span class="risk-num">Risk {{ (drawer.attempt.behavioural.risk_score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="signal-bars">
                            <div class="signal-row">
                                <span class="signal-name">Paste</span>
                                <div class="signal-track">
                                    <div class="signal-fill paste-fill" :style="{ width: (drawer.attempt.behavioural.paste_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ (drawer.attempt.behavioural.paste_score * 100).toFixed(0) }}%</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Speed</span>
                                <div class="signal-track">
                                    <div class="signal-fill time-fill" :style="{ width: (drawer.attempt.behavioural.time_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ (drawer.attempt.behavioural.time_score * 100).toFixed(0) }}%</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Tab</span>
                                <div class="signal-track">
                                    <div class="signal-fill tab-fill" :style="{ width: (drawer.attempt.behavioural.tab_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ (drawer.attempt.behavioural.tab_score * 100).toFixed(0) }}%</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Surprise</span>
                                <div class="signal-track">
                                    <div class="signal-fill surprise-fill" :style="{ width: (drawer.attempt.behavioural.surprise_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ (drawer.attempt.behavioural.surprise_score * 100).toFixed(0) }}%</span>
                            </div>
                        </div>
                        <div v-if="drawer.attempt.behavioural.signals?.length" class="signal-chips">
                            <span v-for="sig in drawer.attempt.behavioural.signals" :key="sig" class="signal-chip">⚠ {{ sig }}</span>
                        </div>
                    </div>
                    <div v-else class="drawer-section">
                        <div class="drawer-section-title">Behavioural Analysis</div>
                        <p class="no-flags">No behavioural flags on this submission.</p>
                    </div>

                    <!-- Similarity match -->
                    <div v-if="drawer.attempt?.plagiarism" class="drawer-section">
                        <div class="drawer-section-title">Similarity Match</div>
                        <div class="sim-match-row">
                            <span class="sim-label">Matched with</span>
                            <strong class="sim-student">{{ drawer.attempt.plagiarism.matched_student }}</strong>
                            <span :class="['badge', drawer.attempt.plagiarism.review_status === 'confirmed' ? 'danger' : 'warn']">
                                {{ (drawer.attempt.plagiarism.score * 100).toFixed(1) }}% similar
                            </span>
                            <span :class="['badge', drawer.attempt.plagiarism.review_status]">
                                {{ drawer.attempt.plagiarism.review_status }}
                            </span>
                        </div>
                    </div>

                    <!-- Code -->
                    <div class="drawer-section">
                        <div class="drawer-section-title">Code</div>
                        <div v-if="drawer.codeLoading" class="no-flags">Loading...</div>
                        <pre v-else class="drawer-code">{{ drawer.code }}</pre>
                    </div>
                </div>
            </div>
        </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()
const loading = ref<boolean>(true)
const student = ref<any>(null)
const questions = ref<any[]>([])
const performanceTrend = ref<any[]>([])
const plagiarismFlags = ref<any[]>([])
const behaviouralFlags = ref<any[]>([])
const activeTab = ref<'overview' | 'plagiarism'>('overview')

const maxConfidence = computed<string | null>(() => {
    if (behaviouralFlags.value.some(f => f.confidence === 'high')) return 'high'
    if (behaviouralFlags.value.some(f => f.confidence === 'medium')) return 'medium'
    if (behaviouralFlags.value.some(f => f.confidence === 'low')) return 'low'
    return null
})

const drawer = ref<{
    open: boolean
    questionTitle: string
    attempt: any | null
    code: string
    codeLoading: boolean
}>({ open: false, questionTitle: '', attempt: null, code: '', codeLoading: false })

async function openDrawer(attempt: any, questionTitle: string): Promise<void> {
    drawer.value = { open: true, questionTitle, attempt, code: '', codeLoading: true }
    try {
        const res = await api.get(`/submissions/${attempt.submission_id}/`)
        drawer.value.code = res.data.code
    } catch {
        drawer.value.code = 'Failed to load code.'
    } finally {
        drawer.value.codeLoading = false
    }
}

onMounted(async () => {
    try {
        const res = await api.get(`/dashboard/students/${route.params.id}/`)
        student.value = res.data.student
        questions.value = res.data.questions
        performanceTrend.value = res.data.performance_trend
        plagiarismFlags.value = res.data.plagiarism_flags
        behaviouralFlags.value = res.data.behavioural_flags ?? []
    } finally {
        loading.value = false
    }
})

function rateColor(rate: number): string {
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'bad'
}
function pctClass(pct: number | null): string {
    if (!pct) return ''
    if (pct >= 80) return 'high'
    if (pct >= 50) return 'mid'
    return 'low'
}
function formatDate(iso: string): string {
    return new Date(iso).toLocaleString()
}
function formatSolveTime(seconds: number): string {
    const m = Math.floor(seconds / 60)
    const s = seconds % 60
    return m > 0 ? `${m}m ${s}s` : `${s}s`
}

// Trend chart — one point per weekly contest exam, green dot = passed majority of questions
const trendSeries = computed(() => [{
    name: '% Time Used',
    data: performanceTrend.value.map((p: any) => p.pct_time_used ?? null),
}])
const trendOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'dark' },
    colors: ['#3b82f6'],
    stroke: { curve: 'smooth', width: 2 },
    markers: {
        size: 8,
        strokeWidth: 0,
        hover: { size: 10 },
        discrete: performanceTrend.value.map((p: any, i: number) => ({
            seriesIndex: 0,
            dataPointIndex: i,
            fillColor: p.status === 'passed' ? '#10b981' : '#e63946',
            strokeColor: 'transparent',
            size: 8,
        })),
    },
    xaxis: {
        categories: performanceTrend.value.map((p: any) => p.date.slice(5)),
        labels: { style: { fontSize: '11px' } },
    },
    yaxis: { min: 0, max: 100, labels: { formatter: (v: number) => v + '%' } },
    dataLabels: { enabled: false },
    tooltip: {
        custom: ({ series, seriesIndex, dataPointIndex }: any) => {
            const p = performanceTrend.value[dataPointIndex]
            const color = p.status === 'passed' ? '#10b981' : '#e63946'
            const pct = series[seriesIndex][dataPointIndex]
            return `<div style="padding:8px 12px;font-size:12px;background:#1a1f2e;border:1px solid #2a3045;border-radius:6px">
                <div style="color:#94a3b8;margin-bottom:6px;font-size:11px">${p.exam}</div>
                <span style="color:${color};font-weight:700">${p.status.toUpperCase()}</span>
                &nbsp;·&nbsp;${p.questions_passed}/${p.questions_attempted} questions passed<br/>
                <span style="color:#64748b;font-size:11px">Avg ${pct}% of exam time used</span>
            </div>`
        }
    },
    grid: { borderColor: '#2a2a2a' },
}))

</script>

<style scoped>
.detail { max-width: 1000px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.back-btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); font-size: 13px;
    cursor: pointer; transition: all 0.15s;
}
.back-btn:hover { border-color: var(--border2); color: var(--text); }
h1 { margin: 0 0 4px; }
.cohort-tag { font-size: 12px; background: var(--blue-dim); color: var(--blue); padding: 2px 10px; border-radius: 10px; }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.kpi-label {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; text-transform: uppercase; color: var(--text-dim);
    letter-spacing: 0.5px; font-weight: 600; margin-bottom: 8px;
}
.kpi-value { font-size: 28px; font-weight: 700; color: var(--text); }

/* Tooltip */
.tip {
    display: inline-flex; align-items: center; justify-content: center;
    width: 14px; height: 14px; border-radius: 50%;
    background: var(--border); color: var(--text-dim);
    font-size: 9px; font-weight: 700; cursor: default;
    position: relative; flex-shrink: 0;
}
.tip::after {
    content: attr(data-tip);
    position: absolute; bottom: calc(100% + 6px); left: 50%;
    transform: translateX(-50%);
    background: #1e2535; border: 1px solid var(--border);
    color: var(--text-muted); font-size: 11px; font-weight: 400;
    text-transform: none; letter-spacing: 0;
    padding: 6px 10px; border-radius: 6px;
    width: 220px; white-space: normal; line-height: 1.5;
    pointer-events: none; opacity: 0; transition: opacity 0.15s;
    z-index: 10;
}
.tip:hover::after { opacity: 1; }

/* Confidence pill under the flag count */
.conf-pill {
    display: inline-block; margin-top: 6px;
    padding: 2px 8px; border-radius: 10px;
    font-size: 10px; font-weight: 700; letter-spacing: 0.3px;
}
.conf-pill.low { background: rgba(230,57,70,0.15); color: #e63946; }
.conf-pill.medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.conf-pill.high { background: rgba(59,130,246,0.15); color: #3b82f6; }
.conf-value.low    { color: #e63946; }
.conf-value.medium { color: #f59e0b; }
.conf-value.high   { color: #3b82f6; }
.conf-value.clean  { color: var(--green); }
.kpi-sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.kpi-value.good { color: var(--green); }
.kpi-value.mid { color: var(--yellow); }
.kpi-value.bad { color: var(--red); }
.kpi-value.warn { color: var(--red); }

/* ── Tabs ── */
.tab-row { display: flex; gap: 4px; margin-bottom: 20px; }
.tab-btn {
    padding: 7px 18px; background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); font-size: 13px;
    font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px;
    transition: all 0.15s;
}
.tab-btn:hover { color: var(--text); border-color: var(--border2); }
.tab-btn.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.tab-badge {
    background: var(--red); color: #fff; font-size: 10px; font-weight: 700;
    padding: 1px 6px; border-radius: 10px;
}

/* ── Legend dots in chart heading ── */
.legend-dot { font-size: 12px; font-weight: 600; margin-left: 8px; }
.legend-dot.passed { color: #2ecc71; }
.legend-dot.failed { color: #e74c3c; }

/* ── Plagiarism tab ── */
.section-count { font-size: 13px; font-weight: 400; color: var(--text-dim); margin-left: 8px; }
.empty-state { color: var(--text-dim); font-size: 13px; padding: 16px 0; }

.flag-card {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 16px 20px; margin-bottom: 12px;
}
.flag-card-top { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }
.flag-card-left { display: flex; flex-direction: column; gap: 4px; }
.flag-card-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.flag-question { font-weight: 700; font-size: 14px; color: var(--text); }
.flag-exam { font-size: 12px; color: var(--text-dim); }
.risk-score { font-size: 13px; font-weight: 700; color: var(--text-muted); }
.sim-score-badge { font-size: 13px; font-weight: 700; color: var(--yellow); }

.conf-badge { font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 10px; border-radius: 10px; }
.conf-badge.high   { background: var(--red-dim); color: var(--red); }
.conf-badge.medium { background: var(--yellow-dim); color: var(--yellow); }
.conf-badge.low    { background: var(--surface2); color: var(--text-dim); }

.score-bars { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.score-bar-row { display: flex; align-items: center; gap: 10px; }
.score-label { font-size: 11px; color: var(--text-dim); width: 36px; flex-shrink: 0; }
.score-track { flex: 1; height: 5px; background: var(--surface3, #0f1117); border-radius: 3px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; }
.paste-fill { background: var(--yellow); }
.time-fill  { background: var(--red); }
.score-val { font-size: 11px; color: var(--text-dim); width: 30px; text-align: right; flex-shrink: 0; }

.signals-list { display: flex; flex-wrap: wrap; gap: 6px; }
.signal-chip {
    font-size: 11px; padding: 3px 10px; border-radius: 10px;
    background: var(--yellow-dim); color: var(--yellow); font-weight: 500;
}

.chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
h3 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.section-title { font-size: 16px; font-weight: 700; margin: 24px 0 12px; color: var(--text); }

.question-block { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.question-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.q-title { font-weight: 700; font-size: 15px; color: var(--text); }
.q-meta { font-size: 12px; color: var(--text-dim); }

.attempt-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.attempt-table th { padding: 8px 10px; font-size: 11px; text-transform: uppercase; color: var(--text-dim); border-bottom: 1px solid var(--border); text-align: left; }
.attempt-table td { padding: 10px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--text-muted); }
.attempt-table tr:last-child td { border-bottom: none; }
.attempt-row { cursor: pointer; }
.attempt-row:hover td { background: var(--surface2); }

.status { padding: 3px 10px; border-radius: 10px; font-size: 11px; font-weight: 700; text-transform: uppercase; }
.status.passed { background: rgba(46,204,113,0.12); color: var(--green); }
.status.failed { background: var(--red-dim); color: var(--red); }
.status.running { background: var(--yellow-dim); color: var(--yellow); }

.pct-bar { display: flex; align-items: center; gap: 6px; }
.pct-fill { height: 6px; border-radius: 3px; min-width: 2px; }
.pct-fill.high { background: var(--red); }
.pct-fill.mid { background: var(--yellow); }
.pct-fill.low { background: var(--green); }

.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.badge.ok { background: rgba(46,204,113,0.12); color: var(--green); }
.badge.warn { background: var(--yellow-dim); color: var(--yellow); }
.badge.danger { background: var(--red-dim); color: var(--red); }
.badge.confirmed { background: var(--red-dim); color: var(--red); }
.badge.pending { background: var(--yellow-dim); color: var(--yellow); }
.badge.dismissed { background: rgba(46,204,113,0.12); color: var(--green); }

.date { color: var(--text-dim); font-size: 12px; white-space: nowrap; }

.flag-row { display: flex; gap: 16px; align-items: center; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 8px; font-size: 14px; color: var(--text-muted); }
.sim-score { color: var(--yellow); font-weight: 600; }
.loading { color: var(--text-muted); }

.view-code-btn {
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-dim);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s;
}
.view-code-btn:hover { border-color: var(--red); color: var(--red); }

/* ── Drawer ── */
.drawer-backdrop {
    position: fixed; inset: 0; background: rgba(0,0,0,0.5); z-index: 1000;
    display: flex; justify-content: flex-end;
}
.drawer {
    background: var(--surface); border-left: 1px solid var(--border);
    width: 540px; max-width: 95vw; height: 100%;
    display: flex; flex-direction: column; overflow: hidden;
}
.drawer-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    padding: 18px 20px; border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.drawer-title { font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 4px; }
.drawer-meta { font-size: 12px; color: var(--text-dim); display: flex; align-items: center; gap: 6px; }
.drawer-close {
    background: transparent; border: none; color: var(--text-dim);
    font-size: 16px; cursor: pointer; padding: 4px; border-radius: 4px; transition: color 0.15s;
}
.drawer-close:hover { color: var(--text); }

.drawer-body { flex: 1; overflow-y: auto; padding: 0; }

.drawer-metrics {
    display: flex; flex-wrap: wrap; gap: 8px;
    padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.metric-chip {
    display: flex; flex-direction: column; gap: 2px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 8px 14px; min-width: 80px;
}
.metric-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); font-weight: 600; }
.metric-val { font-size: 15px; font-weight: 700; color: var(--text); }
.metric-val.val-warn { color: var(--yellow); }

.drawer-section { padding: 16px 20px; border-bottom: 1px solid var(--border); }
.drawer-section:last-child { border-bottom: none; }
.drawer-section-title {
    font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;
    font-weight: 700; color: var(--text-dim); margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
}
.risk-num { font-size: 12px; font-weight: 700; color: var(--text-muted); margin-left: auto; }

.signal-bars { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.signal-row { display: flex; align-items: center; gap: 10px; }
.signal-name { font-size: 11px; color: var(--text-dim); width: 52px; flex-shrink: 0; }
.signal-track { flex: 1; height: 6px; background: var(--surface3, #0f1117); border-radius: 3px; overflow: hidden; }
.signal-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.paste-fill    { background: var(--yellow); }
.time-fill     { background: var(--red); }
.tab-fill      { background: #8b5cf6; }
.surprise-fill { background: #3b82f6; }
.signal-pct { font-size: 11px; color: var(--text-dim); width: 32px; text-align: right; flex-shrink: 0; }

.signal-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.signal-chip { font-size: 11px; padding: 3px 10px; border-radius: 10px; background: var(--yellow-dim); color: var(--yellow); font-weight: 500; }

.no-flags { font-size: 13px; color: var(--text-dim); }

.sim-match-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sim-label { font-size: 12px; color: var(--text-dim); }
.sim-student { font-size: 14px; color: var(--text); }

.drawer-code {
    margin: 0; padding: 16px; overflow-x: auto;
    font-family: 'JetBrains Mono', monospace; font-size: 12px;
    line-height: 1.6; color: #a8c7a0;
    background: var(--surface2); border-radius: var(--radius-sm);
    white-space: pre; max-height: 400px; overflow-y: auto;
}

/* Drawer slide-in transition */
.drawer-enter-active, .drawer-leave-active { transition: opacity 0.2s; }
.drawer-enter-active .drawer, .drawer-leave-active .drawer { transition: transform 0.25s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer, .drawer-leave-to .drawer { transform: translateX(100%); }
</style>
