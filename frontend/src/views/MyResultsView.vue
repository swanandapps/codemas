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


            <!-- Submissions list -->
            <div v-if="submissions.length === 0" class="empty">No submissions yet.</div>

            <!-- Grouped by exam -->
            <div v-for="group in groupedByExam" :key="group.exam_title" class="exam-group">
                <div class="exam-card">
                    <div class="exam-card-top">
                        <span class="exam-card-title">{{ group.exam_title }}</span>
                        <span v-if="examStatByTitle[group.exam_title]?.rank" class="exam-rank">
                            Rank #{{ examStatByTitle[group.exam_title].rank }}
                            <span class="exam-rank-of">of {{ examStatByTitle[group.exam_title].cohort_size }}</span>
                        </span>
                    </div>

                    <div class="exam-metrics" v-if="examStatByTitle[group.exam_title]">
                        <div class="exam-metric">
                            <span class="exam-metric-val">{{ examStatByTitle[group.exam_title].questions_solved }}/{{ examStatByTitle[group.exam_title].questions_total }}</span>
                            <span class="exam-metric-label">Solved</span>
                        </div>
                        <div class="exam-metric">
                            <span class="exam-metric-val accent">{{ examStatByTitle[group.exam_title].points }}</span>
                            <span class="exam-metric-label">Points</span>
                        </div>
                        <div class="exam-metric">
                            <span class="exam-metric-val">{{ examStatByTitle[group.exam_title].pass_rate }}%</span>
                            <span class="exam-metric-label">Pass Rate</span>
                        </div>
                        <div class="exam-metric">
                            <span class="exam-metric-val">{{ examStatByTitle[group.exam_title].attempts }}</span>
                            <span class="exam-metric-label">Attempts</span>
                        </div>
                    </div>
                    <div class="exam-metrics" v-else>
                        <span class="exam-group-meta">{{ group.submissions.length }} submissions · {{ group.passedCount }} passed</span>
                    </div>

                    <!-- AI summary of the whole exam -->
                    <div class="exam-ai" v-if="examStatByTitle[group.exam_title]">
                        <div class="exam-ai-head"><span class="exam-ai-icon">✦</span> AI Summary</div>
                        <p v-if="examSummaries[examStatByTitle[group.exam_title].exam_id]?.loading" class="exam-ai-muted">Generating summary…</p>
                        <p v-else-if="examSummaries[examStatByTitle[group.exam_title].exam_id]?.text" class="exam-ai-text">
                            {{ examSummaries[examStatByTitle[group.exam_title].exam_id].text }}
                        </p>
                        <p v-else class="exam-ai-muted">AI summary unavailable.</p>
                    </div>
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

                        <!-- AI feedback (rubric + hint) for this submission -->
                        <div class="section">
                            <div class="section-label">AI Feedback</div>
                            <div v-if="!aiData[sub.id]?.loaded" class="loading-inline">Loading...</div>
                            <template v-else>
                                <div v-if="aiData[sub.id].rubric" class="ai-fb">
                                    <div class="ai-fb-head">
                                        <span class="ai-fb-icon">✦</span>
                                        <span class="ai-fb-title">Rubric Score</span>
                                        <span class="ai-fb-total" :class="scoreClass(aiData[sub.id].rubric.total_score, 8)">{{ aiData[sub.id].rubric.total_score }}/8</span>
                                    </div>
                                    <div v-for="dim in rubricDims(aiData[sub.id].rubric)" :key="dim.label" class="ai-fb-dim">
                                        <div class="ai-fb-dim-top">
                                            <span>{{ dim.label }}</span>
                                            <span :class="scoreClass(dim.score, 2)">{{ dim.score }}/2</span>
                                        </div>
                                        <div class="ai-fb-bar"><div class="ai-fb-bar-fill" :class="scoreClass(dim.score, 2)" :style="{ width: (dim.score / 2 * 100) + '%' }"></div></div>
                                        <p class="ai-fb-note">{{ dim.note }}</p>
                                    </div>
                                    <p class="ai-fb-overall">{{ aiData[sub.id].rubric.overall_feedback }}</p>
                                </div>
                                <div v-if="aiData[sub.id].hint" class="ai-fb-hint">
                                    <span class="ai-fb-hint-label">Hint</span> {{ aiData[sub.id].hint }}
                                </div>
                                <div v-if="!aiData[sub.id].rubric && !aiData[sub.id].hint" class="loading-inline">No AI feedback for this submission.</div>
                            </template>
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

// AI feedback (rubric + hint) per submission — lazy-loaded when a card expands
interface AiFeedback { rubric: any | null; hint: string | null; loaded: boolean }
const aiData = ref<Record<number, AiFeedback>>({})

function scoreClass(score: number, max: number): string {
    const pct = score / max
    if (pct >= 0.75) return 'good'
    if (pct >= 0.4) return 'mid'
    return 'low'
}
function rubricDims(r: any) {
    return [
        { label: 'Correctness', score: r.correctness_score, note: r.correctness_note },
        { label: 'Code Quality', score: r.code_quality_score, note: r.code_quality_note },
        { label: 'Approach', score: r.approach_score, note: r.approach_note },
        { label: 'Edge Cases', score: r.edge_case_score, note: r.edge_case_note },
    ]
}
async function loadAi(submissionId: number): Promise<void> {
    if (aiData.value[submissionId]?.loaded) return
    const [r, h] = await Promise.all([
        api.get(`/ai/rubric/${submissionId}/`).catch(() => null),
        api.get(`/ai/hint/${submissionId}/`).catch(() => null),
    ])
    aiData.value[submissionId] = {
        rubric: r && typeof r.data?.total_score === 'number' ? r.data : null,
        hint: h && typeof h.data?.hint === 'string' ? h.data.hint : null,
        loaded: true,
    }
}

// Per-exam metrics + cohort rank
interface ExamStat {
    exam_id: number
    exam_title: string
    questions_total: number
    questions_solved: number
    points: number
    attempts: number
    passed: number
    pass_rate: number
    rank: number | null
    cohort_size: number
}
const examStats = ref<ExamStat[]>([])
const examStatByTitle = computed(() => {
    const m: Record<string, ExamStat> = {}
    for (const s of examStats.value) m[s.exam_title] = s
    return m
})

// AI exam summaries, keyed by exam_id (generated on demand server-side)
const examSummaries = ref<Record<number, { text: string | null; loading: boolean }>>({})
async function loadExamSummary(examId: number): Promise<void> {
    if (examSummaries.value[examId]) return
    examSummaries.value[examId] = { text: null, loading: true }
    try {
        const res = await api.get(`/ai/exam-summary/${examId}/`)
        examSummaries.value[examId] = { text: res.data?.summary ?? null, loading: false }
    } catch {
        examSummaries.value[examId] = { text: null, loading: false }
    }
}

onMounted(async () => {
    try {
        // Submissions drive the history — load them first and independently so a
        // stats failure can never blank out the history list.
        const subsRes = await api.get('/submissions/')
        const subs: Submission[] = subsRes.data.results ?? subsRes.data
        submissions.value = subs

        // Stats are best-effort — a failure here must not hide the history.
        try {
            const statsRes = await api.get('/leaderboard/me/')
            myStats.value = statsRes.data
        } catch {
            myStats.value = null
        }

        // Per-exam metrics + rank, then kick off AI summaries in parallel.
        try {
            const examRes = await api.get('/leaderboard/me/exams/')
            examStats.value = examRes.data
            examStats.value.forEach(s => loadExamSummary(s.exam_id))
        } catch {
            examStats.value = []
        }

        // Test results are loaded lazily on expand (see toggleExpand) to keep the
        // page-load request count low and avoid tripping API throttles.
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

async function loadResults(submissionId: number): Promise<void> {
    if (results.value[submissionId]) return  // already loaded
    try {
        const res = await api.get(`/results/${submissionId}/`)
        results.value[submissionId] = res.data
    } catch {
        results.value[submissionId] = []
    }
}

async function toggleExpand(submissionId: number): Promise<void> {
    expanded.value[submissionId] = !expanded.value[submissionId]
    if (expanded.value[submissionId]) {
        loadResults(submissionId)  // lazy — only when the card is opened
        loadAi(submissionId)
    }
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

h3 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; }

.exam-group { margin-bottom: 28px; }
.exam-group-meta { font-size: 12px; color: var(--text-dim); }

/* Per-exam summary card */
.exam-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    margin-bottom: 12px;
}
.exam-card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.exam-card-title { font-size: 16px; font-weight: 700; color: var(--text); }
.exam-rank {
    font-size: 13px; font-weight: 700; color: var(--blue);
    background: var(--blue-dim); border: 1px solid var(--blue);
    padding: 4px 12px; border-radius: 20px;
}
.exam-rank-of { font-size: 11px; font-weight: 500; color: var(--text-dim); margin-left: 2px; }

.exam-metrics { display: flex; gap: 1px; background: var(--border); border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; margin-bottom: 14px; }
.exam-metric { flex: 1; background: var(--surface2); padding: 12px 16px; display: flex; flex-direction: column; gap: 4px; }
.exam-metric-val { font-size: 20px; font-weight: 800; color: var(--text); font-variant-numeric: tabular-nums; }
.exam-metric-val.accent { color: var(--blue); }
.exam-metric-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }

.exam-ai {
    border: 1px solid var(--blue);
    border-radius: var(--radius-sm);
    background: linear-gradient(180deg, var(--blue-dim), var(--surface2) 60px);
    padding: 12px 14px;
}
.exam-ai-head { display: flex; align-items: center; gap: 7px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--blue); margin-bottom: 8px; }
.exam-ai-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 20px; height: 20px; border-radius: 6px; background: var(--blue); color: #fff; font-size: 11px;
}
.exam-ai-text { font-size: 13px; color: var(--text); line-height: 1.65; margin: 0; }
.exam-ai-muted { font-size: 12px; color: var(--text-dim); font-style: italic; margin: 0; }

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

/* AI feedback block on each submission */
.ai-fb {
    border: 1px solid var(--blue);
    border-radius: var(--radius-sm);
    background: linear-gradient(180deg, var(--blue-dim), var(--surface2) 70px);
    padding: 14px 16px;
}
.ai-fb-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.ai-fb-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 22px; height: 22px; border-radius: 6px;
    background: var(--blue); color: #fff; font-size: 12px;
}
.ai-fb-title { font-size: 12px; font-weight: 700; color: var(--text); }
.ai-fb-total {
    margin-left: auto; font-size: 14px; font-weight: 800;
    padding: 2px 10px; border-radius: var(--radius-sm); font-variant-numeric: tabular-nums;
}
.ai-fb-total.good { background: rgba(46,204,113,0.15); color: var(--green); }
.ai-fb-total.mid  { background: var(--yellow-dim); color: var(--yellow); }
.ai-fb-total.low  { background: var(--red-dim); color: var(--red); }
.ai-fb-dim { margin-bottom: 10px; }
.ai-fb-dim-top { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.ai-fb-dim-top span:last-child { font-weight: 700; font-variant-numeric: tabular-nums; }
.ai-fb-dim-top .good { color: var(--green); }
.ai-fb-dim-top .mid  { color: var(--yellow); }
.ai-fb-dim-top .low  { color: var(--red); }
.ai-fb-bar { height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.ai-fb-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.ai-fb-bar-fill.good { background: var(--green); }
.ai-fb-bar-fill.mid  { background: var(--yellow); }
.ai-fb-bar-fill.low  { background: var(--red); }
.ai-fb-note { font-size: 11px; color: var(--text-muted); line-height: 1.5; margin: 4px 0 0; }
.ai-fb-overall {
    font-size: 12px; color: var(--text); line-height: 1.6;
    background: var(--surface); border-left: 3px solid var(--blue);
    border-radius: var(--radius-sm); padding: 9px 11px; margin: 12px 0 0;
}
.ai-fb-hint {
    margin-top: 10px; font-size: 12px; color: var(--text-muted); line-height: 1.6;
    background: var(--yellow-dim); border: 1px solid var(--yellow);
    border-radius: var(--radius-sm); padding: 10px 12px;
}
.ai-fb-hint-label { font-weight: 700; color: var(--yellow); text-transform: uppercase; font-size: 10px; letter-spacing: 0.5px; margin-right: 6px; }
</style>
