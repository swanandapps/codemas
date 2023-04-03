<template>
    <div class="history-page">
        <div class="page-header">
            <div>
                <h1>Exam History</h1>
                <p class="page-sub">All exams with submission, pass rate, and integrity metrics</p>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Loading...</div>

        <div v-else class="history-list">
            <div v-for="exam in exams" :key="exam.exam_id" class="exam-card">
                <!-- Header -->
                <div class="exam-header">
                    <div class="exam-meta">
                        <div class="exam-title-row">
                            <span class="exam-title" @click="router.push('/dashboard/history/' + exam.exam_id)">{{ exam.title }}</span>
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
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar sub-bar" :style="{ width: exam.submission_pct + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.submission_pct }}%</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="passClass(exam.pass_pct)">{{ exam.pass_pct }}%</div>
                        <div class="ekpi-label">Pass Rate</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar" :class="'pass-bar-' + passClass(exam.pass_pct)" :style="{ width: exam.pass_pct + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.total_submissions }} submissions</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="exam.flag_pct > 15 ? 'text-red' : exam.flag_pct > 5 ? 'text-yellow' : 'text-muted'">{{ exam.flag_pct }}%</div>
                        <div class="ekpi-label">Behavioural Flags</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar flag-bar" :style="{ width: Math.min(exam.flag_pct * 3, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.behavioural_flags }} flags</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val" :class="exam.similarity_pairs > 0 ? 'text-red' : 'text-muted'">{{ exam.similarity_pairs }}</div>
                        <div class="ekpi-label">Similarity Pairs</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar sim-bar" :style="{ width: Math.min(exam.similarity_pairs * 10, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.confirmed_plagiarism }} confirmed</div>
                    </div>

                    <div class="ekpi">
                        <div class="ekpi-val">{{ fmtSolveTime(exam.avg_solve_s) }}</div>
                        <div class="ekpi-label">Avg Solve Time</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar time-bar" :style="{ width: Math.min((exam.avg_solve_s || 0) / (exam.duration_minutes * 60) * 100, 100) + '%' }" /></div>
                        <div class="ekpi-pct">{{ exam.avg_exec_ms ? exam.avg_exec_ms + 'ms exec' : '—' }}</div>
                    </div>

                    <div class="ekpi hardest-ekpi" v-if="exam.hardest_question">
                        <div class="hardest-title" :title="exam.hardest_question">{{ exam.hardest_question }}</div>
                        <div class="ekpi-label">Hardest Question</div>
                        <div class="ekpi-bar-wrap"><div class="ekpi-bar" :class="'pass-bar-' + passClass(exam.hardest_pass_rate)" :style="{ width: (exam.hardest_pass_rate || 0) + '%' }" /></div>
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
                        <span class="qb-val" :class="q.flag_count > 0 ? 'text-red' : 'text-muted'">{{ q.flag_count > 0 ? '⚠ ' + q.flag_count : '—' }}</span>
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
.exam-title { font-size: 16px; font-weight: 700; color: var(--text); cursor: pointer; }
.exam-title:hover { color: var(--green); }
.exam-status { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 3px 8px; border-radius: 10px; }
.exam-status.ended  { background: var(--surface3); color: var(--text-dim); }
.exam-status.live   { background: rgba(46,204,113,0.12); color: var(--green); }
.exam-status.draft  { background: rgba(241,196,15,0.1); color: var(--yellow); }
.exam-details { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-dim); flex-wrap: wrap; }
.dot { color: var(--border2); }
.lang-chip-sm { font-size: 11px; font-family: monospace; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 7px; color: var(--text-muted); }
.expand-btn { background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer; padding: 6px 8px; transition: all 0.15s; flex-shrink: 0; }
.expand-btn:hover { border-color: var(--border2); color: var(--text); }
.expand-btn svg { display: block; transition: transform 0.2s; }

.exam-kpis { display: grid; grid-template-columns: repeat(6, 1fr); }
.ekpi { padding: 16px 20px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.ekpi:last-child { border-right: none; }
.ekpi-val { font-size: 22px; font-weight: 700; color: var(--text); line-height: 1; }
.ekpi-denom { font-size: 13px; color: var(--text-dim); font-weight: 400; }
.ekpi-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }
.ekpi-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin: 4px 0; }
.ekpi-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.ekpi-pct { font-size: 11px; color: var(--text-dim); }

.sub-bar  { background: #3498db; }
.flag-bar { background: var(--red); }
.sim-bar  { background: var(--yellow); }
.time-bar { background: #3498db; }
.pass-bar-good { background: var(--green); }
.pass-bar-mid  { background: var(--yellow); }
.pass-bar-low  { background: var(--red); }

.hardest-ekpi .hardest-title { font-size: 13px; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 140px; }

.text-red    { color: var(--red) !important; }
.text-yellow { color: var(--yellow) !important; }
.text-muted  { color: var(--text-muted) !important; }
.good { color: var(--green); }
.mid  { color: var(--yellow); }
.low  { color: var(--red); }

.question-breakdown { border-top: 1px solid var(--border); background: var(--surface2); }
.qb-header, .qb-row { display: grid; grid-template-columns: 2fr 90px 80px 160px 130px 80px; gap: 12px; padding: 10px 20px; align-items: center; }
.qb-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); border-bottom: 1px solid var(--border); background: var(--surface3); }
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
.diff-chip { font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 8px; border-radius: 10px; }
.diff-chip.easy   { background: rgba(46,204,113,0.12); color: var(--green); }
.diff-chip.medium { background: rgba(241,196,15,0.1); color: var(--yellow); }
.diff-chip.hard   { background: var(--red-dim); color: var(--red); }
</style>
