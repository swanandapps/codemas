<template>
    <div class="dashboard">
        <div class="dash-header">
            <h1>Overview</h1>
            <div class="tab-row">
                <button :class="['tab-btn', activeTab === 'overview' ? 'active' : '']" @click="activeTab = 'overview'">
                    Overview
                </button>
                <button :class="['tab-btn', activeTab === 'history' ? 'active' : '']" @click="switchHistory">
                    Exam History
                    <span class="tab-count" v-if="exams.length">{{ exams.length }}</span>
                </button>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading dashboard...</div>

        <!-- ── OVERVIEW TAB ──────────────────────────────────────────────── -->
        <template v-else-if="activeTab === 'overview'">
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Total Students</div>
                    <div class="kpi-value">{{ data.kpis.total_students }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Total Submissions</div>
                    <div class="kpi-value">{{ data.kpis.total_submissions }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Overall Pass Rate</div>
                    <div class="kpi-value" :class="rateColor(data.kpis.pass_rate)">
                        {{ data.kpis.pass_rate }}%
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Pending Flags</div>
                    <div class="kpi-value" :class="data.kpis.plagiarism_flags > 0 ? 'warn' : 'good'">
                        {{ data.kpis.plagiarism_flags }}
                    </div>
                </div>
            </div>

            <div class="chart-row">
                <div class="chart-card half">
                    <h3>Pass Rate by Question</h3>
                    <apexchart type="bar" height="340" :options="passRateOptions" :series="passRateSeries" />
                </div>
                <div class="chart-card half">
                    <h3>Avg Execution Time (ms)</h3>
                    <apexchart type="bar" height="340" :options="execTimeOptions" :series="execTimeSeries" />
                </div>
                <div class="chart-card narrow">
                    <h3>Language Distribution</h3>
                    <apexchart type="donut" height="260" :options="langOptions" :series="langSeries" />
                </div>
            </div>

            <div class="chart-card full" v-if="data.cohort_comparison.length > 0">
                <h3>Cohort Comparison</h3>
                <apexchart type="bar" height="220" :options="cohortOptions" :series="cohortSeries" />
            </div>

            <div class="table-row">
                <div class="table-card">
                    <h3>Top Performers</h3>
                    <table class="mini-table">
                        <thead><tr><th>Student</th><th>Cohort</th><th>Pass Rate</th><th>Submissions</th></tr></thead>
                        <tbody>
                            <tr v-for="s in data.top_performers" :key="s.student_id" class="clickable" @click="router.push(`/dashboard/students/${s.student_id}`)">
                                <td><strong>{{ s.username }}</strong></td>
                                <td>{{ s.cohort || '—' }}</td>
                                <td><span class="rate good">{{ s.pass_rate }}%</span></td>
                                <td>{{ s.total_submissions }}</td>
                            </tr>
                            <tr v-if="data.top_performers.length === 0"><td colspan="4" class="empty-row">No data yet</td></tr>
                        </tbody>
                    </table>
                </div>
                <div class="table-card">
                    <h3>Needs Attention <span class="sub-label">(&lt;40% pass rate)</span></h3>
                    <table class="mini-table">
                        <thead><tr><th>Student</th><th>Cohort</th><th>Pass Rate</th><th>Flags</th></tr></thead>
                        <tbody>
                            <tr v-for="s in data.struggling_students" :key="s.student_id" class="clickable" @click="router.push(`/dashboard/students/${s.student_id}`)">
                                <td><strong>{{ s.username }}</strong></td>
                                <td>{{ s.cohort || '—' }}</td>
                                <td><span class="rate low">{{ s.pass_rate }}%</span></td>
                                <td>
                                    <span v-if="s.plagiarism_flags > 0" class="flag-warn">⚠ {{ s.plagiarism_flags }}</span>
                                    <span v-else class="flag-ok">✓</span>
                                </td>
                            </tr>
                            <tr v-if="data.struggling_students.length === 0"><td colspan="4" class="empty-row">All students above 40%</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </template>

        <!-- ── HISTORY TAB ───────────────────────────────────────────────── -->
        <template v-else-if="activeTab === 'history'">
            <div v-if="loadingHistory" class="loading">Loading exam history...</div>

            <div v-else class="history-list">
                <div v-for="exam in exams" :key="exam.exam_id" class="exam-card">
                    <!-- Exam header row -->
                    <div class="exam-header">
                        <div class="exam-meta">
                            <div class="exam-title-row">
                                <span class="exam-title">{{ exam.title }}</span>
                                <span :class="['exam-status', exam.status]">{{ exam.status }}</span>
                            </div>
                            <div class="exam-details">
                                <span>{{ exam.question_count }} questions</span>
                                <span class="dot">·</span>
                                <span>{{ exam.duration_minutes }} min</span>
                                <span class="dot">·</span>
                                <span>{{ exam.enrolled }} enrolled</span>
                                <span class="dot">·</span>
                                <span v-if="exam.top_language" class="lang-chip-sm">{{ exam.top_language }}</span>
                                <span v-if="exam.start_time">Started {{ fmtDate(exam.start_time) }}</span>
                            </div>
                        </div>
                        <button class="expand-btn" @click="toggle(exam.exam_id)">
                            <svg :style="{ transform: expanded.has(exam.exam_id) ? 'rotate(180deg)' : '' }"
                                width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="6 9 12 15 18 9"/>
                            </svg>
                        </button>
                    </div>

                    <!-- KPI strip -->
                    <div class="exam-kpis">
                        <div class="ekpi">
                            <div class="ekpi-val">{{ exam.submitters }}<span class="ekpi-denom">/{{ exam.enrolled }}</span></div>
                            <div class="ekpi-label">Submitted</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar sub-bar" :style="{ width: exam.submission_pct + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.submission_pct }}%</div>
                        </div>

                        <div class="ekpi">
                            <div class="ekpi-val" :class="passClass(exam.pass_pct)">{{ exam.pass_pct }}%</div>
                            <div class="ekpi-label">Pass Rate</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar" :class="'pass-bar-' + passClass(exam.pass_pct)" :style="{ width: exam.pass_pct + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.total_submissions }} submissions</div>
                        </div>

                        <div class="ekpi">
                            <div class="ekpi-val" :class="exam.flag_pct > 15 ? 'text-red' : exam.flag_pct > 5 ? 'text-yellow' : 'text-muted'">
                                {{ exam.flag_pct }}%
                            </div>
                            <div class="ekpi-label">Behavioural Flags</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar flag-bar" :style="{ width: Math.min(exam.flag_pct * 3, 100) + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.behavioural_flags }} flags</div>
                        </div>

                        <div class="ekpi">
                            <div class="ekpi-val" :class="exam.similarity_pairs > 0 ? 'text-red' : 'text-muted'">
                                {{ exam.similarity_pairs }}
                            </div>
                            <div class="ekpi-label">Similarity Pairs</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar sim-bar" :style="{ width: Math.min(exam.similarity_pairs * 10, 100) + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.confirmed_plagiarism }} confirmed</div>
                        </div>

                        <div class="ekpi">
                            <div class="ekpi-val">{{ fmtSolveTime(exam.avg_solve_s) }}</div>
                            <div class="ekpi-label">Avg Solve Time</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar time-bar" :style="{ width: Math.min((exam.avg_solve_s || 0) / (exam.duration_minutes * 60) * 100, 100) + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.avg_exec_ms ? exam.avg_exec_ms + 'ms exec' : '—' }}</div>
                        </div>

                        <div class="ekpi hardest-ekpi" v-if="exam.hardest_question">
                            <div class="hardest-title" :title="exam.hardest_question">{{ exam.hardest_question }}</div>
                            <div class="ekpi-label">Hardest Question</div>
                            <div class="ekpi-bar-wrap">
                                <div class="ekpi-bar" :class="'pass-bar-' + passClass(exam.hardest_pass_rate)" :style="{ width: (exam.hardest_pass_rate || 0) + '%' }" />
                            </div>
                            <div class="ekpi-pct">{{ exam.hardest_pass_rate }}% pass</div>
                        </div>
                    </div>

                    <!-- Expanded: per-question breakdown -->
                    <div v-if="expanded.has(exam.exam_id)" class="question-breakdown">
                        <div class="qb-header">
                            <span>Question</span>
                            <span>Difficulty</span>
                            <span>Attempts</span>
                            <span>Pass Rate</span>
                            <span>Behavioural Flags</span>
                            <span>Test Cases</span>
                        </div>
                        <div v-for="q in exam.questions" :key="q.question_id" class="qb-row">
                            <span class="qb-title">{{ q.title }}</span>
                            <span :class="['diff-chip', q.difficulty]">{{ q.difficulty }}</span>
                            <span class="qb-val">{{ q.total_attempts }}</span>
                            <span class="qb-pass">
                                <div class="inline-bar-wrap">
                                    <div class="inline-bar" :class="'pass-bar-' + passClass(q.pass_rate)" :style="{ width: q.pass_rate + '%' }" />
                                </div>
                                <span :class="['qb-pct', passClass(q.pass_rate)]">{{ q.pass_rate }}%</span>
                            </span>
                            <span class="qb-val" :class="q.flag_count > 0 ? 'text-red' : 'text-muted'">
                                {{ q.flag_count > 0 ? '⚠ ' + q.flag_count : '—' }}
                            </span>
                            <span class="qb-val text-muted">{{ q.test_case_count }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const loading = ref(true)
const loadingHistory = ref(false)
const activeTab = ref<'overview' | 'history'>('overview')
const exams = ref<any[]>([])
const expanded = ref<Set<number>>(new Set())
let historyLoaded = false

const data = ref<any>({
    kpis: { total_students: 0, total_submissions: 0, pass_rate: 0, plagiarism_flags: 0 },
    question_stats: [],
    language_distribution: {},
    cohort_comparison: [],
    top_performers: [],
    struggling_students: [],
})

onMounted(async () => {
    try {
        const res = await api.get('/dashboard/')
        data.value = res.data
    } finally {
        loading.value = false
    }
})

async function switchHistory() {
    activeTab.value = 'history'
    if (historyLoaded) return
    loadingHistory.value = true
    try {
        const res = await api.get('/dashboard/exams/')
        exams.value = res.data
        historyLoaded = true
    } finally {
        loadingHistory.value = false
    }
}

function toggle(id: number) {
    if (expanded.value.has(id)) expanded.value.delete(id)
    else expanded.value.add(id)
    expanded.value = new Set(expanded.value)
}

function rateColor(rate: number) {
    return rate >= 70 ? 'good' : rate >= 40 ? 'mid' : 'warn'
}

function passClass(rate: number) {
    return rate >= 65 ? 'good' : rate >= 40 ? 'mid' : 'low'
}

function fmtDate(d: string) {
    return new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

function fmtSolveTime(s: number | null) {
    if (!s) return '—'
    const m = Math.floor(s / 60)
    const sec = Math.round(s % 60)
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}

// ── Chart computed ────────────────────────────────────────────────────────────

const langSeries = computed(() => Object.values(data.value.language_distribution) as number[])
const langOptions = computed(() => ({
    labels: Object.keys(data.value.language_distribution),
    colors: ['#2ecc71', '#3498db', '#e63946'],
    legend: { position: 'bottom' },
    theme: { mode: 'dark' },
    chart: { background: 'transparent' },
    dataLabels: { style: { fontSize: '12px' } },
    plotOptions: { pie: { donut: { size: '60%' } } },
}))

// Deduplicate questions by title across exams — average the pass rate
const dedupedQuestionStats = computed(() => {
    const map = new Map<string, any>()
    for (const q of data.value.question_stats) {
        if (map.has(q.question_title)) {
            const e = map.get(q.question_title)
            e._count++
            e._pass_sum += q.pass_rate
            e._exec_sum += (q.avg_execution_time || 0)
            e.pass_rate = Math.round(e._pass_sum / e._count)
            e.avg_execution_time = Math.round(e._exec_sum / e._count)
        } else {
            map.set(q.question_title, { ...q, _count: 1, _pass_sum: q.pass_rate, _exec_sum: q.avg_execution_time || 0 })
        }
    }
    return Array.from(map.values()).sort((a, b) => b.pass_rate - a.pass_rate)
})

const passRateSeries = computed(() => [{ name: 'Pass Rate %', data: dedupedQuestionStats.value.map((q: any) => q.pass_rate) }])
const passRateOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'dark' },
    colors: ['#2ecc71'],
    plotOptions: { bar: { borderRadius: 4, horizontal: true } },
    xaxis: { max: 100, categories: dedupedQuestionStats.value.map((q: any) => q.question_title), labels: { formatter: (v: number) => v + '%', style: { fontSize: '11px' } } },
    yaxis: { labels: { style: { fontSize: '11px' } } },
    dataLabels: { formatter: (v: number) => v + '%' },
    grid: { borderColor: '#2a2a2a' },
}))

const execTimeSeries = computed(() => [{ name: 'Avg Exec Time (ms)', data: dedupedQuestionStats.value.map((q: any) => q.avg_execution_time) }])
const execTimeOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'dark' },
    colors: ['#3498db'],
    plotOptions: { bar: { borderRadius: 4 } },
    xaxis: { categories: dedupedQuestionStats.value.map((q: any) => q.question_title), labels: { style: { fontSize: '11px' }, rotate: -25 } },
    dataLabels: { formatter: (v: number) => v + 'ms' },
    grid: { borderColor: '#2a2a2a' },
}))

const cohortSeries = computed(() => [
    { name: 'Pass Rate %', data: data.value.cohort_comparison.map((c: any) => c.pass_rate) },
    { name: 'Students', data: data.value.cohort_comparison.map((c: any) => c.student_count) },
])
const cohortOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'dark' },
    colors: ['#2ecc71', '#3498db'],
    xaxis: { categories: data.value.cohort_comparison.map((c: any) => c.cohort) },
    plotOptions: { bar: { borderRadius: 4, columnWidth: '50%' } },
    dataLabels: { enabled: false },
    legend: { position: 'top' },
    grid: { borderColor: '#2a2a2a' },
}))
</script>

<style scoped>
.dashboard { max-width: 1100px; }
.dash-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h1 { margin: 0; }
h3 { margin: 0 0 16px; font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

.tab-row { display: flex; gap: 4px; }
.tab-btn {
    padding: 8px 18px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
}
.tab-btn:hover { color: var(--text); border-color: var(--border2); }
.tab-btn.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.tab-count { background: var(--surface2); padding: 1px 6px; border-radius: 8px; font-size: 11px; }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px 24px; }
.kpi-label { font-size: 11px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; margin-bottom: 8px; }
.kpi-value { font-size: 36px; font-weight: 700; color: var(--text); }
.kpi-value.good { color: var(--green); }
.kpi-value.mid { color: var(--yellow); }
.kpi-value.warn { color: var(--red); }

.chart-row { display: flex; gap: 16px; margin-bottom: 16px; }
.chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.chart-card.wide { flex: 2; }
.chart-card.narrow { flex: 1; }
.chart-card.half { flex: 1; }
.chart-card.full { margin-bottom: 16px; }

.table-row { display: flex; gap: 16px; margin-bottom: 16px; }
.table-card { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.mini-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.mini-table th { padding: 8px 10px; text-align: left; font-size: 11px; text-transform: uppercase; color: var(--text-dim); border-bottom: 1px solid var(--border); }
.mini-table td { padding: 10px 10px; border-bottom: 1px solid var(--border); color: var(--text-muted); }
.mini-table td strong { color: var(--text); }
.mini-table tr:last-child td { border-bottom: none; }
.clickable { cursor: pointer; }
.clickable:hover td { background: var(--surface2); }
.rate { font-weight: 700; padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.rate.good { background: rgba(46,204,113,0.12); color: var(--green); }
.rate.low { background: var(--red-dim); color: var(--red); }
.flag-warn { color: var(--yellow); font-weight: 600; }
.flag-ok { color: var(--green); }
.empty-row { color: var(--text-dim); text-align: center; padding: 16px !important; }
.sub-label { font-size: 11px; color: var(--text-dim); font-weight: normal; }
.loading { color: var(--text-muted); padding: 40px 0; }

/* ── History tab ──────────────────────────────────────────────────────────── */
.history-list { display: flex; flex-direction: column; gap: 16px; }

.exam-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    transition: border-color 0.15s;
}
.exam-card:hover { border-color: var(--border2); }

.exam-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 18px 20px 14px;
    border-bottom: 1px solid var(--border);
}
.exam-title-row { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.exam-title { font-size: 16px; font-weight: 700; color: var(--text); }
.exam-status {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 3px 8px;
    border-radius: 10px;
}
.exam-status.ended  { background: var(--surface3); color: var(--text-dim); }
.exam-status.live   { background: rgba(46,204,113,0.12); color: var(--green); }
.exam-status.draft  { background: rgba(241,196,15,0.1); color: var(--yellow); }
.exam-details { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-dim); }
.dot { color: var(--border2); }
.lang-chip-sm {
    font-size: 11px;
    font-family: monospace;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1px 7px;
    color: var(--text-muted);
}
.expand-btn {
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    padding: 6px 8px;
    transition: all 0.15s;
    flex-shrink: 0;
}
.expand-btn:hover { border-color: var(--border2); color: var(--text); }
.expand-btn svg { display: block; transition: transform 0.2s; }

/* KPI strip inside each exam card */
.exam-kpis {
    display: grid;
    grid-template-columns: repeat(6, 1fr);
    gap: 0;
    padding: 0;
}
.ekpi {
    padding: 16px 20px;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.ekpi:last-child { border-right: none; }
.ekpi-val { font-size: 22px; font-weight: 700; color: var(--text); line-height: 1; }
.ekpi-denom { font-size: 13px; color: var(--text-dim); font-weight: 400; }
.ekpi-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }
.ekpi-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin: 4px 0; }
.ekpi-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.ekpi-pct { font-size: 11px; color: var(--text-dim); }

.sub-bar  { background: var(--blue, #3498db); }
.flag-bar { background: var(--red); }
.sim-bar  { background: var(--yellow); }
.time-bar { background: var(--blue, #3498db); }

.pass-bar-good { background: var(--green); }
.pass-bar-mid  { background: var(--yellow); }
.pass-bar-low  { background: var(--red); }

.hardest-ekpi .hardest-title {
    font-size: 13px;
    font-weight: 600;
    color: var(--text);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 140px;
}

.text-red    { color: var(--red) !important; }
.text-yellow { color: var(--yellow) !important; }
.text-muted  { color: var(--text-muted) !important; }
.text-green  { color: var(--green) !important; }
.good { color: var(--green); }
.mid  { color: var(--yellow); }
.low  { color: var(--red); }

/* Question breakdown table */
.question-breakdown {
    border-top: 1px solid var(--border);
    background: var(--surface2);
}
.qb-header, .qb-row {
    display: grid;
    grid-template-columns: 2fr 90px 80px 160px 130px 80px;
    gap: 12px;
    padding: 10px 20px;
    align-items: center;
}
.qb-header {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    background: var(--surface3);
}
.qb-row { border-bottom: 1px solid var(--border); font-size: 13px; }
.qb-row:last-child { border-bottom: none; }
.qb-title { font-weight: 500; color: var(--text); }
.qb-val { color: var(--text-muted); }
.qb-pass { display: flex; align-items: center; gap: 8px; }
.qb-pct { font-size: 12px; font-weight: 700; flex-shrink: 0; }
.qb-pct.good { color: var(--green); }
.qb-pct.mid  { color: var(--yellow); }
.qb-pct.low  { color: var(--red); }
.inline-bar-wrap { flex: 1; height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; }
.inline-bar { height: 100%; border-radius: 2px; }
.diff-chip {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 10px;
}
.diff-chip.easy   { background: rgba(46,204,113,0.12); color: var(--green); }
.diff-chip.medium { background: rgba(241,196,15,0.1); color: var(--yellow); }
.diff-chip.hard   { background: var(--red-dim); color: var(--red); }
</style>
