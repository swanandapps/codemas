<template>
    <div class="results-page">
        <h1>My Results</h1>

        <div v-if="loading" class="loading">Loading...</div>

        <template v-else>
            <!-- Personal KPIs -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Score</div>
                    <div class="kpi-value accent">{{ myStats?.score ?? 0 }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cohort Rank</div>
                    <div class="kpi-value">
                        {{ myStats?.rank ? `#${myStats.rank}` : '—' }}
                        <span class="kpi-sub">of {{ myStats?.cohort_size }}</span>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Pass Rate</div>
                    <div class="kpi-value" :class="rateColor(myStats?.pass_rate ?? 0)">{{ myStats?.pass_rate ?? 0 }}%</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Streak</div>
                    <div class="kpi-value">
                        {{ myStats?.streak ? `🔥 ${myStats.streak}` : '—' }}
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Beats Cohort</div>
                    <div class="kpi-value" :class="rateColor(myStats?.beats_pct ?? 0)">
                        {{ myStats?.beats_pct != null ? myStats.beats_pct + '%' : '—' }}
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Avg Speed</div>
                    <div class="kpi-value">{{ myStats?.avg_execution_time ? myStats.avg_execution_time + 'ms' : '—' }}</div>
                </div>
            </div>

            <!-- Difficulty breakdown -->
            <div class="diff-row" v-if="myStats">
                <div class="diff-card easy">
                    <span class="diff-label">Easy</span>
                    <span class="diff-count">{{ myStats.difficulty_breakdown.easy }}</span>
                    <span class="diff-pts">×10 pts</span>
                </div>
                <div class="diff-card medium">
                    <span class="diff-label">Medium</span>
                    <span class="diff-count">{{ myStats.difficulty_breakdown.medium }}</span>
                    <span class="diff-pts">×20 pts</span>
                </div>
                <div class="diff-card hard">
                    <span class="diff-label">Hard</span>
                    <span class="diff-count">{{ myStats.difficulty_breakdown.hard }}</span>
                    <span class="diff-pts">×30 pts</span>
                </div>
            </div>

            <!-- Activity Calendar -->
            <div class="chart-card" v-if="myStats && Object.keys(myStats.activity_calendar).length > 0">
                <h3>Activity — Last 52 Weeks</h3>
                <div class="calendar-grid">
                    <div
                        v-for="(day, i) in calendarDays"
                        :key="i"
                        :class="['cal-cell', intensityClass(day.count)]"
                        :title="`${day.date}: ${day.count} submission${day.count !== 1 ? 's' : ''}`"
                    />
                </div>
                <div class="cal-legend">
                    <span>Less</span>
                    <div class="cal-cell l0" />
                    <div class="cal-cell l1" />
                    <div class="cal-cell l2" />
                    <div class="cal-cell l3" />
                    <div class="cal-cell l4" />
                    <span>More</span>
                </div>
            </div>

            <!-- Performance trend chart -->
            <div class="chart-card" v-if="submissions.length > 1">
                <h3>Submission History</h3>
                <apexchart
                    type="bar"
                    height="200"
                    :options="trendOptions"
                    :series="trendSeries"
                />
            </div>

            <!-- Submissions list -->
            <div v-if="submissions.length === 0" class="empty">No submissions yet.</div>

            <!-- Grouped by exam -->
            <div v-for="group in groupedByExam" :key="group.exam_title" class="exam-group">
                <div class="exam-group-header">
                    <span class="exam-group-title">{{ group.exam_title }}</span>
                    <span class="exam-group-meta">
                        {{ group.submissions.length }} submission{{ group.submissions.length !== 1 ? 's' : '' }}
                        &nbsp;·&nbsp;
                        {{ group.passedCount }} passed
                    </span>
                </div>

                <div v-for="sub in group.submissions" :key="sub.id" class="submission-card">
                    <div class="card-header" @click="toggleExpand(sub.id)">
                        <div class="card-title">
                            <span class="expand-icon">{{ expanded[sub.id] ? '▾' : '▸' }}</span>
                            <div>
                                <h3>{{ sub.question_title }}</h3>
                            </div>
                        </div>
                        <div class="card-right">
                            <div class="card-meta">
                                <span>Attempt #{{ sub.attempt_number }}</span>
                                <span class="lang-badge">{{ sub.language }}</span>
                                <span v-if="sub.execution_time_ms">⚡ {{ sub.execution_time_ms }}ms</span>
                                <span v-if="solveTime(sub)">🕐 {{ solveTime(sub) }}</span>
                                <span class="date">{{ formatDate(sub.submitted_at) }}</span>
                            </div>
                            <span :class="['status-badge', sub.status]">{{ sub.status }}</span>
                        </div>
                    </div>

                    <div v-if="expanded[sub.id]" class="card-body">
                        <div class="section">
                            <div class="section-label">Question</div>
                            <p class="question-desc">{{ sub.question_description || 'No description.' }}</p>
                        </div>
                        <div class="section">
                            <div class="section-label">Your Code</div>
                            <pre class="code-block">{{ sub.code }}</pre>
                        </div>
                        <div class="section">
                            <div class="section-label">Test Results</div>
                            <div v-if="!results[sub.id]" class="loading-inline">Loading...</div>
                            <div v-else class="results-list">
                                <div
                                    v-for="r in results[sub.id]"
                                    :key="r.id"
                                    :class="['result-row', r.passed ? 'pass' : 'fail']"
                                >
                                    <span class="result-icon">{{ r.passed ? '✓' : '✗' }}</span>
                                    <span>Input: <code>{{ r.test_case_input }}</code></span>
                                    <span>Expected: <code>{{ r.test_case_expected }}</code></span>
                                    <span>Got: <code>{{ r.actual_output || '—' }}</code></span>
                                    <span v-if="r.error_message" class="err">{{ r.error_message }}</span>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

interface Submission {
    id: number
    exam_title: string
    question_title: string
    question_description: string
    attempt_number: number
    status: string
    language: string
    code: string
    execution_time_ms: number | null
    time_remaining_seconds: number | null
    submitted_at: string
}

interface TestResult {
    id: number
    test_case_input: string
    test_case_expected: string
    passed: boolean
    actual_output: string
    error_message: string
}

interface MyStats {
    score: number
    streak: number
    rank: number | null
    cohort_size: number
    total_submissions: number
    passed: number
    pass_rate: number
    beats_pct: number | null
    avg_execution_time: number | null
    activity_calendar: Record<string, number>
    difficulty_breakdown: { easy: number; medium: number; hard: number }
}

const submissions = ref<Submission[]>([])
const results = ref<Record<number, TestResult[]>>({})
const expanded = ref<Record<number, boolean>>({})
const loading = ref<boolean>(true)
const myStats = ref<MyStats | null>(null)

onMounted(async () => {
    try {
        const [subsRes, statsRes] = await Promise.all([
            api.get('/submissions/'),
            api.get('/leaderboard/me/'),
        ])
        submissions.value = subsRes.data.results ?? subsRes.data
        myStats.value = statsRes.data
        await Promise.all(subsRes.data.map((s: Submission) => loadResults(s.id)))
    } finally {
        loading.value = false
    }
})

const groupedByExam = computed(() => {
    const map: Record<string, { exam_title: string; submissions: Submission[]; passedCount: number }> = {}
    for (const sub of submissions.value) {
        if (!map[sub.exam_title]) {
            map[sub.exam_title] = { exam_title: sub.exam_title, submissions: [], passedCount: 0 }
        }
        map[sub.exam_title].submissions.push(sub)
        if (sub.status === 'passed') map[sub.exam_title].passedCount++
    }
    return Object.values(map)
})

const calendarDays = computed(() => {
    const days = []
    const today = new Date()
    for (let i = 363; i >= 0; i--) {
        const d = new Date(today)
        d.setDate(d.getDate() - i)
        const key = d.toISOString().slice(0, 10)
        days.push({ date: key, count: myStats.value?.activity_calendar[key] ?? 0 })
    }
    return days
})

function intensityClass(count: number): string {
    if (count === 0) return 'l0'
    if (count === 1) return 'l1'
    if (count <= 3) return 'l2'
    if (count <= 5) return 'l3'
    return 'l4'
}

async function loadResults(submissionId: number): Promise<void> {
    try {
        const res = await api.get(`/results/${submissionId}/`)
        results.value[submissionId] = res.data
    } catch {
        results.value[submissionId] = []
    }
}

async function toggleExpand(submissionId: number): Promise<void> {
    expanded.value[submissionId] = !expanded.value[submissionId]
}

// Stats computed from submissions
const stats = computed(() => {
    const total = submissions.value.length
    const passed = submissions.value.filter(s => s.status === 'passed').length
    const passRate = total ? Math.round(passed / total * 100) : 0

    return { total, passed, passRate, avgSolveTime: total ? `${passed}/${total}` : '—' }
})

function rateColor(rate: number): string {
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'bad'
}

function solveTime(sub: Submission): string | null {
    if (sub.time_remaining_seconds === null) return null
    const m = Math.floor(sub.time_remaining_seconds / 60)
    const sec = sub.time_remaining_seconds % 60
    return `${m}m ${sec}s left`
}

function formatDate(iso: string): string {
    return new Date(iso).toLocaleString()
}

// Chart — pass/fail per submission
const trendSeries = computed(() => [{
    name: 'Execution Time (ms)',
    data: submissions.value
        .filter(s => s.execution_time_ms)
        .map(s => s.execution_time_ms as number),
}])
const trendOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'dark' },
    colors: submissions.value.map(s => s.status === 'passed' ? '#2ecc71' : '#e63946'),
    plotOptions: { bar: { borderRadius: 4 } },
    xaxis: {
        categories: submissions.value
            .filter(s => s.execution_time_ms)
            .map((s, i) => `#${i + 1}`),
        labels: { style: { fontSize: '11px' } },
    },
    yaxis: { labels: { formatter: (v: number) => v + 'ms' } },
    dataLabels: { enabled: false },
    grid: { borderColor: '#2a2a2a' },
    tooltip: {
        y: { formatter: (v: number) => v + 'ms' },
    },
}))
</script>

<style scoped>
.results-page { max-width: 900px; }
h1 { margin-bottom: 24px; }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.kpi-label { font-size: 11px; text-transform: uppercase; color: var(--text-dim); font-weight: 600; letter-spacing: 0.5px; margin-bottom: 8px; }
.kpi-value { font-size: 28px; font-weight: 700; color: var(--text); }
.kpi-value.good { color: var(--green); }
.kpi-value.mid { color: var(--yellow); }
.kpi-value.bad { color: var(--red); }
.kpi-value.accent { color: var(--blue); }
.kpi-sub { font-size: 13px; color: var(--text-dim); font-weight: 400; margin-left: 4px; }

.diff-row { display: flex; gap: 12px; margin-bottom: 16px; }
.diff-card {
    flex: 1;
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 14px 20px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    font-size: 14px;
}
.diff-card.easy { background: rgba(46,204,113,0.07); border-color: rgba(46,204,113,0.2); }
.diff-card.medium { background: var(--yellow-dim); border-color: rgba(241,196,15,0.2); }
.diff-card.hard { background: var(--red-dim); border-color: rgba(230,57,70,0.2); }
.diff-label { font-weight: 700; flex: 1; color: var(--text-muted); }
.diff-count { font-size: 24px; font-weight: 700; color: var(--text); }
.diff-pts { font-size: 11px; color: var(--text-dim); }

.calendar-grid {
    display: grid;
    grid-template-columns: repeat(52, 1fr);
    gap: 2px;
    margin-bottom: 8px;
}
.cal-cell {
    width: 100%;
    aspect-ratio: 1;
    border-radius: 2px;
}
.cal-cell.l0 { background: var(--surface3); }
.cal-cell.l1 { background: rgba(46,204,113,0.25); }
.cal-cell.l2 { background: rgba(46,204,113,0.5); }
.cal-cell.l3 { background: rgba(46,204,113,0.75); }
.cal-cell.l4 { background: var(--green); }
.cal-legend { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-dim); justify-content: flex-end; }
.cal-legend .cal-cell { width: 12px; height: 12px; aspect-ratio: unset; }

.chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
h3 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

.exam-group { margin-bottom: 28px; }
.exam-group-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 0 10px;
    margin-bottom: 10px;
    border-bottom: 1px solid var(--border);
}
.exam-group-title { font-size: 15px; font-weight: 700; color: var(--text); }
.exam-group-meta { font-size: 12px; color: var(--text-dim); }

.submission-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); margin-bottom: 8px; overflow: hidden; }
.card-header { display: flex; justify-content: space-between; align-items: center; padding: 14px 20px; cursor: pointer; user-select: none; transition: background 0.15s; }
.card-header:hover { background: var(--surface2); }
.card-title { display: flex; align-items: center; gap: 10px; }
.expand-icon { color: var(--text-dim); font-size: 13px; width: 13px; }
.card-title h3 { margin: 0 0 2px; font-size: 14px; font-weight: 600; color: var(--text); text-transform: none; letter-spacing: 0; }
.exam-name { font-size: 11px; color: var(--text-dim); }
.card-right { display: flex; align-items: center; gap: 12px; }
.card-meta { display: flex; gap: 12px; font-size: 12px; color: var(--text-dim); align-items: center; }
.lang-badge { padding: 2px 7px; background: var(--blue-dim); color: var(--blue); border-radius: 8px; font-size: 11px; }
.date { white-space: nowrap; }
.status-badge { padding: 3px 10px; border-radius: 20px; font-size: 11px; font-weight: 700; text-transform: uppercase; white-space: nowrap; }
.status-badge.passed { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.failed { background: var(--red-dim); color: var(--red); }
.status-badge.running { background: var(--yellow-dim); color: var(--yellow); }

.card-body { border-top: 1px solid var(--border); padding: 20px; display: flex; flex-direction: column; gap: 18px; }
.section-label { font-size: 10px; font-weight: 700; text-transform: uppercase; color: var(--text-dim); margin-bottom: 6px; letter-spacing: 0.6px; }
.question-desc { font-size: 14px; color: var(--text-muted); margin: 0; line-height: 1.6; }
.code-block { background: var(--surface2); color: #a8c7a0; padding: 16px; border: 1px solid var(--border); border-radius: var(--radius-sm); font-family: monospace; font-size: 13px; line-height: 1.6; overflow-x: auto; margin: 0; white-space: pre-wrap; }
.results-list { display: flex; flex-direction: column; gap: 6px; }
.result-row { display: flex; gap: 14px; align-items: center; padding: 8px 12px; border-radius: var(--radius-sm); font-size: 13px; flex-wrap: wrap; }
.result-row.pass { background: rgba(46,204,113,0.08); border: 1px solid rgba(46,204,113,0.2); color: var(--text-muted); }
.result-row.fail { background: var(--red-dim); border: 1px solid rgba(230,57,70,0.2); color: var(--text-muted); }
.result-icon { font-weight: bold; width: 14px; }
code { background: var(--surface3); padding: 2px 5px; border-radius: 3px; font-family: monospace; font-size: 12px; color: var(--text-muted); }
.err { color: var(--red); font-size: 11px; font-style: italic; }
.loading-inline { color: var(--text-dim); font-size: 13px; }
.loading, .empty { color: var(--text-muted); }
</style>
