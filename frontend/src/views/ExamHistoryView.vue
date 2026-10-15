<template>
    <div class="history-page">
        <div class="page-header">
            <div>
                <h1>Exams</h1>
                <p class="page-sub">All exams with participation, success rate and integrity metrics</p>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Loading...</div>

        <div v-else class="history-list">
            <div v-for="exam in exams" :key="exam.exam_id" class="exam-card">
                <!-- Header -->
                <div class="exam-header">
                    <div class="exam-meta">
                        <div class="exam-title-row">
                            <button type="button" class="exam-title" @click="router.push('/dashboard/history/' + exam.exam_id)">{{ exam.title }}</button>
                            <span :class="['exam-status', exam.status]">{{ exam.status }}</span>
                        </div>
                        <div class="exam-details">
                            <span>{{ plural(exam.question_count, 'question') }}</span>
                            <span>{{ exam.duration_minutes }} min</span>
                            <span>{{ exam.enrolled }} enrolled</span>
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
                        <div class="ekpi-val">{{ exam.took }}<span class="ekpi-denom">/{{ exam.enrolled }}</span></div>
                        <div class="ekpi-label" :title="METRIC_HELP.took">Took the exam</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar sub-bar" :style="{ width: Math.min(exam.took_rate || 0, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ formatPct(exam.took_rate) }}</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="exam.accepted_rate !== null ? passClass(exam.accepted_rate) : 'text-muted'">{{ formatPct(exam.accepted_rate) }}</div>
                        <div class="ekpi-label" :title="METRIC_HELP.accepted">Success rate</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar" :class="exam.accepted_rate !== null ? 'pass-bar-' + passClass(exam.accepted_rate) : ''" :style="{ width: (exam.accepted_rate || 0) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.passed_students }} of {{ plural(exam.took, 'student') }} passed</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="integrityClass(exam.integrity_health)">{{ formatPct(exam.flagged_students_rate) }}</div>
                        <div class="ekpi-label" :title="METRIC_HELP.flagged">Flagged students</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar flag-bar" :style="{ width: (exam.flagged_students_rate || 0) + '%' }" /></div>
                        <div class="ekpi-pct">{{ plural(exam.flagged_students, 'student') }}, {{ plural(exam.behavioural_flags, 'flag') }}</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="exam.similarity_pairs > 0 ? 'text-red' : 'text-muted'">{{ exam.similarity_pairs }}</div>
                        <div class="ekpi-label">Similarity pairs</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar sim-bar" :style="{ width: Math.min(exam.similarity_pairs * 10, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.confirmed_plagiarism }} confirmed</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val">{{ fmtSolveTime(exam.avg_solve_s) }}</div>
                        <div class="ekpi-label">Avg solve time</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar time-bar" :style="{ width: Math.min((exam.avg_solve_s || 0) / (exam.duration_minutes * 60) * 100, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.avg_exec_ms ? formatMs(exam.avg_exec_ms) + ' exec' : '—' }}</div>
                    </div>

                    <div class="ekpi hardest-ekpi" v-if="exam.hardest_question">
                        <div class="hardest-title" :title="exam.hardest_question">{{ exam.hardest_question }}</div>
                        <div class="ekpi-label">Hardest question</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar" :class="'pass-bar-' + passClass(exam.hardest_accepted_rate)" :style="{ width: (exam.hardest_accepted_rate || 0) + '%' }" /></div>
                        <div class="ekpi-pct">{{ formatPct(exam.hardest_accepted_rate) }} success rate</div>
                    </div>
                </div>

                <!-- Expanded: per-question breakdown -->
                <div v-if="expanded.has(exam.exam_id)" class="question-breakdown">
                    <div class="qb-header">
                        <span>Question</span>
                        <span>Difficulty</span>
                        <span>Attempts</span>
                        <span :title="METRIC_HELP.acceptedQuestion">Success rate</span>
                        <span>Behavioural flags</span>
                        <span>Test cases</span>
                    </div>
                    <div v-for="q in exam.questions" :key="q.question_id" class="qb-row">
                        <span class="qb-title">{{ q.title }}</span>
                        <span :class="['diff-chip', q.difficulty]">{{ q.difficulty }}</span>
                        <span class="qb-val">{{ q.total_attempts }}</span>
                        <span class="qb-pass">
                            <div class="inline-bar-wrap">
                                <div class="inline-bar" :class="'pass-bar-' + passClass(q.accepted_rate)" :style="{ width: (q.accepted_rate || 0) + '%' }" />
                            </div>
                            <span :class="['qb-pct', q.accepted_rate !== null ? passClass(q.accepted_rate) : 'text-muted']" :title="solvedCaption(q)">{{ formatPct(q.accepted_rate) }}</span>
                        </span>
                        <span class="qb-val" :class="q.flag_count > 0 ? 'text-red' : 'text-muted'">{{ q.flag_count > 0 ? plural(q.flag_count, 'flag') : '—' }}</span>
                        <span class="qb-val text-muted">{{ q.test_case_count }}</span>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { formatDate, formatMs, formatSeconds, formatPct, plural } from '../utils/format'
import { METRIC_HELP, integrityClass, solvedCaption } from '../utils/metrics'

const router = useRouter()

const exams = ref<any[]>([])
const loading = ref(true)
const expanded = ref<Set<number>>(new Set())

onMounted(async () => {
    const res = await api.get('/dashboard/exams/')
    exams.value = res.data
    loading.value = false
})

function toggle(id: number) {
    if (expanded.value.has(id)) expanded.value.delete(id)
    else expanded.value.add(id)
    expanded.value = new Set(expanded.value)
}

function passClass(rate: number | null) {
    if (rate === null || rate === undefined) return 'low'
    return rate >= 65 ? 'good' : rate >= 40 ? 'mid' : 'low'
}

function fmtDate(d: string) {
    return formatDate(d)
}

function fmtSolveTime(s: number | null) {
    return formatSeconds(s)
}
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
.state-msg { color: var(--text-muted); padding: 40px 0; }

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
.exam-title {
    font-size: 16px; font-weight: 700; color: var(--text); cursor: pointer;
    background: none; border: none; padding: 0; text-align: left; font-family: var(--font-display);
    white-space: normal; min-height: 40px; display: flex; align-items: center;
}
.exam-title:hover { color: var(--accent); }
.exam-status { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 10px; }
.exam-status.ended  { background: var(--surface3); color: var(--text-dim); }
.exam-status.live   { background: var(--green-dim); color: var(--green-ink); }
.exam-status.draft  { background: var(--yellow-dim); color: var(--amber-ink); }
.exam-details { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-dim); flex-wrap: wrap; }
.lang-chip-sm { font-size: 11px; font-family: var(--font-mono); background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 7px; color: var(--text-muted); }
.expand-btn { background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer; padding: 6px 8px; transition: all 0.15s; flex-shrink: 0; }
.expand-btn:hover { border-color: var(--border2); color: var(--text); }
.expand-btn svg { display: block; transition: transform 0.2s; }

.exam-kpis { display: grid; grid-template-columns: repeat(6, 1fr); }
.ekpi { padding: 16px 20px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.ekpi:last-child { border-right: none; }
.ekpi-val { font-size: 22px; font-weight: 700; color: var(--text); line-height: 1; font-variant-numeric: tabular-nums; }
.ekpi-denom { font-size: 13px; color: var(--text-dim); font-weight: 400; }
.ekpi-label { font-size: 10px; font-weight: 700; color: var(--text-dim); }
.ekpi-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin: 4px 0; }
.ekpi-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.ekpi-pct { font-size: 11px; color: var(--text-dim); }

.sub-bar  { background: var(--text-dim); }
.flag-bar { background: var(--red); }
.sim-bar  { background: var(--yellow); }
.time-bar { background: var(--text-dim); }
.pass-bar-good { background: var(--green); }
.pass-bar-mid  { background: var(--yellow); }
.pass-bar-low  { background: var(--red); }

.hardest-ekpi .hardest-title { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.3; }

.text-red    { color: var(--red-ink) !important; }
.text-yellow, .text-amber { color: var(--amber-ink) !important; }
.text-muted  { color: var(--text-muted) !important; }
.good { color: var(--green-ink); }
.mid  { color: var(--amber-ink); }
.low  { color: var(--red-ink); }

.question-breakdown { border-top: 1px solid var(--border); background: var(--surface2); }
.qb-header, .qb-row { display: grid; grid-template-columns: 2fr 90px 80px 160px 130px 80px; gap: 12px; padding: 10px 20px; align-items: center; }
.qb-header { font-size: 10px; font-weight: 700; color: var(--text-dim); border-bottom: 1px solid var(--border); background: var(--surface3); }
.qb-row { border-bottom: 1px solid var(--border); font-size: 13px; }
.qb-row:last-child { border-bottom: none; }
.qb-title { font-weight: 500; color: var(--text); }
.qb-val { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.qb-pass { display: flex; align-items: center; gap: 8px; }
.qb-pct { font-size: 12px; font-weight: 700; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.qb-pct.good { color: var(--green-ink); }
.qb-pct.mid  { color: var(--amber-ink); }
.qb-pct.low  { color: var(--red-ink); }
.inline-bar-wrap { flex: 1; height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; }
.inline-bar { height: 100%; border-radius: 2px; }
.diff-chip { font-size: 10px; font-weight: 700; text-transform: capitalize; padding: 2px 8px; border-radius: 10px; }
.diff-chip.easy   { background: var(--green-dim); color: var(--green-ink); }
.diff-chip.medium { background: var(--yellow-dim); color: var(--amber-ink); }
.diff-chip.hard   { background: var(--red-dim); color: var(--red-ink); }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .exam-kpis { grid-template-columns: repeat(3, 1fr); }
    .exam-header { flex-wrap: wrap; gap: 10px; }
    .qb-header, .qb-row { grid-template-columns: 1.6fr 1fr 1fr; }
    .qb-header span:nth-child(5), .qb-header span:nth-child(6),
    .qb-row > :nth-child(5), .qb-row > :nth-child(6) { display: none; }
}

@media (max-width: 600px) {
    .exam-kpis { grid-template-columns: repeat(2, 1fr); }
    .exam-title-row { flex-wrap: wrap; }
    .exam-details { gap: 8px 12px; }
}
</style>
