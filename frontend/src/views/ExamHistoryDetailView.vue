<template>
    <div class="detail-page">

        <!-- Header -->
        <div class="page-header">
            <button class="back-btn" @click="router.push(route.query.from === 'runs' ? '/dashboard/plagiarism/policy?tab=runs' : '/dashboard/history')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                {{ route.query.from === 'runs' ? 'Run History' : 'Exam History' }}
            </button>
            <div v-if="exam" class="header-main">
                <div class="header-left">
                    <div class="title-row">
                        <h1>{{ exam.title }}</h1>
                        <span :class="['status-badge', exam.status]">{{ exam.status }}</span>
                    </div>
                    <div class="meta-row">
                        <span>{{ exam.question_count }} questions</span>
                        <span class="dot">·</span>
                        <span>{{ exam.duration_minutes }} min</span>
                        <span class="dot">·</span>
                        <span>{{ exam.enrolled }} enrolled</span>
                        <span v-if="exam.top_language" class="dot">·</span>
                        <span v-if="exam.top_language" class="lang-chip">{{ exam.top_language }}</span>
                        <span class="dot">·</span>
                        <span>Started {{ fmtDate(exam.start_time) }}</span>
                        <span v-if="exam.end_time" class="dot">·</span>
                        <span v-if="exam.end_time">Ended {{ fmtDate(exam.end_time) }}</span>
                    </div>
                    <p v-if="exam.description" class="exam-desc">{{ exam.description }}</p>
                </div>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Loading exam details...</div>
        <div v-else-if="!exam" class="state-msg">Exam not found.</div>

        <template v-else>
            <!-- KPI Strip -->
            <div class="kpi-strip">
                <div class="kpi">
                    <div class="kpi-val">{{ exam.submitters }}<span class="kpi-denom">/{{ exam.enrolled }}</span></div>
                    <div class="kpi-label">Submitted</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-blue" :style="{ width: exam.submission_pct + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.submission_pct }}% participation</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="passClass(exam.pass_pct)">{{ exam.pass_pct }}%</div>
                    <div class="kpi-label">Pass Rate</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar" :class="'bar-' + passClass(exam.pass_pct)" :style="{ width: exam.pass_pct + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.total_submissions }} total submissions</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="exam.flag_pct > 15 ? 'text-red' : exam.flag_pct > 5 ? 'text-yellow' : 'text-muted'">{{ exam.flag_pct }}%</div>
                    <div class="kpi-label">Behavioural Flags</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-red" :style="{ width: Math.min(exam.flag_pct * 3, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.behavioural_flags }} flagged submissions</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="exam.similarity_pairs > 0 ? 'text-red' : 'text-muted'">{{ exam.similarity_pairs }}</div>
                    <div class="kpi-label">Similarity Pairs</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-yellow" :style="{ width: Math.min(exam.similarity_pairs * 10, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.confirmed_plagiarism }} confirmed</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val">{{ fmtTime(exam.avg_solve_s) }}</div>
                    <div class="kpi-label">Avg Solve Time</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-blue" :style="{ width: Math.min((exam.avg_solve_s || 0) / (exam.duration_minutes * 60) * 100, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.avg_exec_ms ? exam.avg_exec_ms + 'ms exec' : '—' }}</div>
                </div>
                <div class="kpi" v-if="exam.hardest_question">
                    <div class="kpi-val kpi-val-sm">{{ exam.hardest_question }}</div>
                    <div class="kpi-label">Hardest Question</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar" :class="'bar-' + passClass(exam.hardest_pass_rate)" :style="{ width: (exam.hardest_pass_rate || 0) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.hardest_pass_rate }}% pass rate</div>
                </div>
            </div>

            <!-- Questions + Top Performers side by side -->
            <div class="two-col">

                <!-- Questions -->
                <div class="panel">
                    <div class="panel-header">Questions</div>
                    <div class="q-header q-grid">
                        <span>Question</span>
                        <span>Difficulty</span>
                        <span>Attempts</span>
                        <span>Pass Rate</span>
                        <span>Avg Solve</span>
                        <span>Flags</span>
                    </div>
                    <div v-for="q in exam.questions" :key="q.question_id" class="q-row q-grid">
                        <span class="q-title">{{ q.title }}</span>
                        <span :class="['diff-chip', q.difficulty]">{{ q.difficulty }}</span>
                        <span class="cell-muted">{{ q.total_attempts }}</span>
                        <span>
                            <div class="inline-bar-wrap">
                                <div class="inline-bar" :class="'bar-' + passClass(q.pass_rate)" :style="{ width: q.pass_rate + '%' }"/>
                            </div>
                            <span :class="['pct', passClass(q.pass_rate)]">{{ q.pass_rate }}%</span>
                        </span>
                        <span class="cell-muted">{{ fmtTime(q.avg_solve_s) }}</span>
                        <span :class="q.flag_count > 0 ? 'text-red' : 'cell-muted'">
                            {{ q.flag_count > 0 ? '⚠ ' + q.flag_count : '—' }}
                        </span>
                    </div>
                </div>

                <!-- Top Performers -->
                <div class="panel">
                    <div class="panel-header">Top Performers</div>
                    <div v-if="exam.top_performers.length === 0" class="empty-state">No submissions yet</div>
                    <div v-else>
                        <div class="tp-header tp-grid">
                            <span>#</span>
                            <span>Student</span>
                            <span>Solved</span>
                            <span>Avg Time</span>
                            <span>Flags</span>
                        </div>
                        <div v-for="s in exam.top_performers" :key="s.student_id"
                             class="tp-row tp-grid"
                             @click="router.push('/dashboard/students/' + s.student_id)">
                            <span class="rank" :class="{ 'rank-gold': s.rank === 1, 'rank-silver': s.rank === 2, 'rank-bronze': s.rank === 3 }">
                                {{ s.rank === 1 ? '🥇' : s.rank === 2 ? '🥈' : s.rank === 3 ? '🥉' : s.rank }}
                            </span>
                            <span class="tp-name">{{ s.full_name }}</span>
                            <span>
                                <span :class="passClass(s.pass_rate)">{{ s.questions_passed }}/{{ s.total_questions }}</span>
                            </span>
                            <span class="cell-muted">{{ fmtTime(s.avg_solve_s) }}</span>
                            <span :class="(s.behavioural_flags + s.similarity_flags) > 0 ? 'text-red' : 'cell-muted'">
                                {{ (s.behavioural_flags + s.similarity_flags) > 0 ? '⚠ ' + (s.behavioural_flags + s.similarity_flags) : '—' }}
                            </span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- All Students -->
            <div class="panel" style="margin-top: 16px;">
                <div class="panel-header">
                    All Students
                    <span class="panel-count">{{ exam.students.length }} enrolled</span>
                </div>
                <div class="st-header st-grid">
                    <span>Rank</span>
                    <span>Student</span>
                    <span>Submitted</span>
                    <span>Solved</span>
                    <span>Pass Rate</span>
                    <span>Avg Solve</span>
                    <span>Behav. Flags</span>
                    <span>Sim. Flags</span>
                </div>
                <div v-for="s in exam.students" :key="s.student_id"
                     class="st-row st-grid"
                     @click="router.push('/dashboard/students/' + s.student_id)">
                    <span class="cell-muted">#{{ s.rank }}</span>
                    <span class="st-name">{{ s.full_name }}</span>
                    <span>
                        <span v-if="s.submitted" class="badge-yes">Yes</span>
                        <span v-else class="badge-no">No</span>
                    </span>
                    <span :class="passClass(s.pass_rate)">{{ s.questions_passed }}/{{ s.total_questions }}</span>
                    <span>
                        <div class="inline-bar-wrap">
                            <div class="inline-bar" :class="'bar-' + passClass(s.pass_rate)" :style="{ width: s.pass_rate + '%' }"/>
                        </div>
                        <span :class="['pct', passClass(s.pass_rate)]">{{ s.pass_rate }}%</span>
                    </span>
                    <span class="cell-muted">{{ fmtTime(s.avg_solve_s) }}</span>
                    <span :class="s.behavioural_flags > 0 ? 'text-red' : 'cell-muted'">
                        {{ s.behavioural_flags > 0 ? '⚠ ' + s.behavioural_flags : '—' }}
                    </span>
                    <span :class="s.similarity_flags > 0 ? 'text-red' : 'cell-muted'">
                        {{ s.similarity_flags > 0 ? '⚠ ' + s.similarity_flags : '—' }}
                    </span>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'

const router = useRouter()
const route  = useRoute()

const exam    = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
    try {
        const res = await api.get(`/dashboard/exams/${route.params.id}/`)
        exam.value = res.data
    } finally {
        loading.value = false
    }
})

function passClass(rate: number | null) {
    if (!rate) return 'text-muted'
    return rate >= 65 ? 'good' : rate >= 40 ? 'mid' : 'low'
}

function fmtDate(d: string) {
    return new Date(d).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function fmtTime(s: number | null) {
    if (!s) return '—'
    const m = Math.floor(s / 60)
    const sec = Math.round(s % 60)
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}
</script>

<style scoped>
.detail-page { padding-bottom: 60px; }

/* Header */
.back-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm);
    color: var(--text-dim); font-size: 12px; font-weight: 600; cursor: pointer;
    padding: 6px 12px; margin-bottom: 20px; transition: all 0.15s;
}
.back-btn:hover { border-color: var(--border2); color: var(--text); }

.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.title-row h1 { font-size: 24px; font-weight: 800; color: var(--text); }
.status-badge { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; padding: 3px 9px; border-radius: 10px; }
.status-badge.ended { background: var(--surface3); color: var(--text-dim); }
.status-badge.live  { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.draft { background: rgba(241,196,15,0.1); color: var(--yellow); }

.meta-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-dim); flex-wrap: wrap; }
.dot { color: var(--border2); }
.lang-chip { font-size: 11px; font-family: monospace; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 7px; color: var(--text-muted); }
.exam-desc { margin-top: 10px; font-size: 13px; color: var(--text-dim); line-height: 1.5; max-width: 680px; }

/* KPI strip */
.kpi-strip {
    display: grid; grid-template-columns: repeat(6, 1fr);
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    margin-bottom: 16px; overflow: hidden;
}
.kpi { padding: 18px 20px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.kpi:last-child { border-right: none; }
.kpi-val { font-size: 24px; font-weight: 700; color: var(--text); line-height: 1; }
.kpi-val-sm { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.3; }
.kpi-denom { font-size: 14px; color: var(--text-dim); font-weight: 400; }
.kpi-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }
.kpi-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin: 4px 0; }
.kpi-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.kpi-sub { font-size: 11px; color: var(--text-dim); }

/* Two-column layout */
.two-col { display: grid; grid-template-columns: 1fr 380px; gap: 16px; }

/* Panel */
.panel {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden;
}
.panel-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px; font-size: 13px; font-weight: 700; color: var(--text);
    border-bottom: 1px solid var(--border); background: var(--surface2);
}
.panel-count { font-size: 11px; font-weight: 400; color: var(--text-dim); }
.empty-state { padding: 32px 20px; text-align: center; color: var(--text-muted); font-size: 13px; }

/* Questions table */
.q-grid { display: grid; grid-template-columns: 2fr 90px 70px 150px 80px 60px; gap: 10px; padding: 10px 20px; align-items: center; }
.q-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); background: var(--surface3); border-bottom: 1px solid var(--border); }
.q-row { font-size: 13px; border-bottom: 1px solid var(--border); }
.q-row:last-child { border-bottom: none; }
.q-title { font-weight: 500; color: var(--text); }

/* Top Performers */
.tp-grid { display: grid; grid-template-columns: 32px 1fr 60px 70px 50px; gap: 10px; padding: 10px 16px; align-items: center; }
.tp-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); background: var(--surface3); border-bottom: 1px solid var(--border); }
.tp-row { font-size: 13px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.12s; }
.tp-row:last-child { border-bottom: none; }
.tp-row:hover { background: var(--surface2); }
.tp-name { font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rank { font-size: 13px; font-weight: 700; color: var(--text-dim); }

/* All Students table */
.st-grid { display: grid; grid-template-columns: 50px 1fr 80px 70px 160px 80px 100px 90px; gap: 10px; padding: 10px 20px; align-items: center; }
.st-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); background: var(--surface3); border-bottom: 1px solid var(--border); }
.st-row { font-size: 13px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.12s; }
.st-row:last-child { border-bottom: none; }
.st-row:hover { background: var(--surface2); }
.st-name { font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* Shared */
.inline-bar-wrap { height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin-bottom: 3px; }
.inline-bar { height: 100%; border-radius: 2px; }
.pct { font-size: 12px; font-weight: 700; }

.diff-chip { font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 8px; border-radius: 10px; width: fit-content; }
.diff-chip.easy   { background: rgba(46,204,113,0.12); color: var(--green); }
.diff-chip.medium { background: rgba(241,196,15,0.1);  color: var(--yellow); }
.diff-chip.hard   { background: var(--red-dim);         color: var(--red); }

.badge-yes { font-size: 11px; font-weight: 700; background: rgba(46,204,113,0.12); color: var(--green); padding: 2px 8px; border-radius: 10px; }
.badge-no  { font-size: 11px; font-weight: 700; background: var(--surface3); color: var(--text-muted); padding: 2px 8px; border-radius: 10px; }

.bar-blue   { background: #3498db; }
.bar-red    { background: var(--red); }
.bar-yellow { background: var(--yellow); }
.bar-good   { background: var(--green); }
.bar-mid    { background: var(--yellow); }
.bar-low    { background: var(--red); }

.good { color: var(--green); }
.mid  { color: var(--yellow); }
.low  { color: var(--red); }
.text-red    { color: var(--red) !important; }
.text-yellow { color: var(--yellow) !important; }
.text-muted  { color: var(--text-muted) !important; }
.cell-muted  { color: var(--text-muted); }
.state-msg   { color: var(--text-muted); padding: 40px 0; }
</style>
