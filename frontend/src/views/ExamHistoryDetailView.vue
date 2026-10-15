<template>
    <div class="detail-page">

        <!-- Header -->
        <div class="page-header">
            <button class="back-btn" @click="router.push(route.query.from === 'runs' ? '/dashboard/plagiarism/policy?tab=runs' : '/dashboard/history')">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                {{ route.query.from === 'runs' ? 'Run history' : 'Exams' }}
            </button>
            <div v-if="exam" class="header-main">
                <div class="header-left">
                    <div class="title-row">
                        <h1>{{ exam.title }}</h1>
                        <span :class="['status-badge', exam.status]">{{ exam.status }}</span>
                    </div>
                    <div class="meta-row">
                        <span>{{ plural(exam.question_count, 'question') }}</span>
                        <span>{{ exam.duration_minutes }} min</span>
                        <span>{{ exam.enrolled }} enrolled</span>
                        <span v-if="exam.top_language" class="lang-chip">{{ exam.top_language }}</span>
                        <span v-if="exam.status !== 'draft'">Started {{ fmtDate(exam.start_time) }}</span>
                        <span v-else-if="exam.start_time">Opens {{ fmtDate(exam.start_time) }}</span>
                        <span v-if="exam.end_time">Ended {{ fmtDate(exam.end_time) }}</span>
                    </div>
                    <p v-if="exam.description" class="exam-desc">{{ exam.description }}</p>
                </div>
                <!-- a draft has nothing to check yet: its publish card is below -->
                <div v-if="exam.status !== 'draft'" class="check-box">
                    <EndExamButton v-if="exam.status === 'live'" :exam-id="exam.exam_id" @ended="loadExam" />
                    <!-- one filled button at a time: End exam leads while live. Ending the exam runs the
                         plagiarism check itself, so a live exam offers no "Run" — only "View" once checked -->
                    <router-link v-if="checked && !checking" :to="`/dashboard/plagiarism/cohorts/${exam.exam_id}`"
                                 :class="['check-btn', { secondary: exam.status === 'live' }]">View plagiarism cases</router-link>
                    <button v-else-if="exam.status === 'ended'" class="check-btn" :disabled="checking" @click="runCheck">
                        {{ checking ? 'Checking…' : 'Run plagiarism check' }}
                    </button>
                    <p v-else class="check-note">Plagiarism check runs when the exam ends</p>
                    <p v-if="checkNote" class="check-note">{{ checkNote }}</p>
                </div>
            </div>
        </div>

        <!-- back from deciding a case opened on this report -->
        <div v-if="caseNotice" class="done-banner" role="status">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>
            {{ caseNotice }}
        </div>

        <div v-if="loading" class="state-msg">Loading exam details...</div>
        <div v-else-if="!exam" class="state-msg">Exam not found.</div>

        <template v-else>
            <ExamPublishCard v-if="exam.status === 'draft'" :exam-id="exam.exam_id" :notice="notice" @changed="loadExam" />

            <!-- KPI Strip -->
            <div class="kpi-strip">
                <div class="kpi">
                    <div class="kpi-val">{{ exam.took }}<span class="kpi-denom">/{{ exam.enrolled }}</span></div>
                    <div class="kpi-label" :title="METRIC_HELP.took">Took the exam</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-neutral" :style="{ width: Math.min(exam.took_rate || 0, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ formatPct(exam.took_rate) }} of enrolled</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="passClass(exam.accepted_rate)">{{ formatPct(exam.accepted_rate) }}</div>
                    <div class="kpi-label" :title="METRIC_HELP.accepted">Success rate</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar" :class="exam.accepted_rate !== null ? 'bar-' + passClass(exam.accepted_rate) : ''" :style="{ width: (exam.accepted_rate || 0) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.passed_students }} of {{ plural(exam.took, 'student') }} passed</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="integrityClass(exam.integrity_health)">{{ formatPct(exam.flagged_students_rate) }}</div>
                    <div class="kpi-label" :title="METRIC_HELP.flagged">Flagged students</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-red" :style="{ width: (exam.flagged_students_rate || 0) + '%' }"/></div>
                    <div class="kpi-sub">{{ plural(exam.flagged_students, 'student') }}, {{ plural(exam.flags_to_review, 'flag') }} to review</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val" :class="exam.similarity_pairs > 0 ? 'text-red' : 'text-muted'">{{ exam.similarity_pairs }}</div>
                    <div class="kpi-label">Similarity pairs</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-yellow" :style="{ width: Math.min(exam.similarity_pairs * 10, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.confirmed_plagiarism }} confirmed</div>
                </div>
                <div class="kpi">
                    <div class="kpi-val">{{ fmtTime(exam.avg_solve_s) }}</div>
                    <div class="kpi-label">Avg solve time</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar bar-neutral" :style="{ width: Math.min((exam.avg_solve_s || 0) / (exam.duration_minutes * 60) * 100, 100) + '%' }"/></div>
                    <div class="kpi-sub">{{ exam.avg_exec_ms ? formatMs(exam.avg_exec_ms) + ' exec' : '—' }}</div>
                </div>
                <div class="kpi" v-if="exam.hardest_question">
                    <div class="kpi-val kpi-val-sm">{{ exam.hardest_question }}</div>
                    <div class="kpi-label">Hardest question</div>
                    <div class="kpi-bar-wrap"><div class="kpi-bar" :class="'bar-' + passClass(exam.hardest_accepted_rate)" :style="{ width: (exam.hardest_accepted_rate || 0) + '%' }"/></div>
                    <div class="kpi-sub">{{ formatPct(exam.hardest_accepted_rate) }} success rate</div>
                </div>
            </div>

            <!-- Questions -->
            <div class="panel">
                <div class="panel-header">Questions</div>
                <div class="table-scroll">
                <div class="q-header q-grid">
                    <span>Question</span>
                    <span>Difficulty</span>
                    <span>Attempts</span>
                    <span :title="METRIC_HELP.acceptedQuestion">Success rate</span>
                    <span>Avg solve</span>
                    <span>Flags</span>
                </div>
                <div v-for="q in exam.questions" :key="q.question_id" class="q-row q-grid">
                    <span class="q-title">{{ q.title }}</span>
                    <span :class="['diff-chip', q.difficulty]">{{ q.difficulty }}</span>
                    <span class="cell-muted">{{ q.total_attempts }}</span>
                    <span>
                        <div class="inline-bar-wrap">
                            <div class="inline-bar" :class="'bar-' + passClass(q.accepted_rate)" :style="{ width: (q.accepted_rate || 0) + '%' }"/>
                        </div>
                        <span :class="['pct', passClass(q.accepted_rate)]" :title="solvedCaption(q)">{{ formatPct(q.accepted_rate) }}</span>
                    </span>
                    <span class="cell-muted">{{ fmtTime(q.avg_solve_s) }}</span>
                    <span :class="q.flag_count > 0 ? 'text-red' : 'cell-muted'">
                        {{ q.flag_count > 0 ? plural(q.flag_count, 'flag') : '—' }}
                    </span>
                </div>
                </div>
            </div>

            <!-- All Students -->
            <div class="panel" style="margin-top: 16px;">
                <div class="panel-header">
                    All students
                    <span class="panel-count">{{ exam.students.length }} enrolled</span>
                </div>
                <div v-if="exam.students.length === 0" class="empty-state">No students enrolled yet. Students are enrolled when the exam goes live.</div>
                <div v-else class="table-scroll">
                <div class="st-header st-grid">
                    <span :title="RANK_HELP">Rank, all sections</span>
                    <span>Student</span>
                    <span title="Submissions that couldn't run are refunded and not counted">Attempts</span>
                    <span>Last submission</span>
                    <span>Solved</span>
                    <span :title="METRIC_HELP.passed">Result</span>
                    <span>Avg solve</span>
                    <span>Behavioural flags</span>
                    <span>Similarity flags</span>
                </div>
                <!-- the row opens the student; the name is the keyboard link, the badge opens their case -->
                <div v-for="s in exam.students" :key="s.student_id"
                     class="st-row st-grid"
                     @click="router.push('/dashboard/students/' + s.student_id)">
                    <span v-if="s.submitted && s.rank" class="cell-muted" :title="plural(s.points, 'point')">#{{ s.rank }}</span>
                    <span v-else-if="s.submitted" class="cell-muted" title="No points on this exam, so not ranked">Not ranked</span>
                    <span v-else class="cell-muted" title="Not ranked until they submit">—</span>
                    <span class="st-name">
                        <router-link :to="'/dashboard/students/' + s.student_id" class="st-link" @click.stop>{{ s.username }}</router-link>
                        <span v-if="s.full_name && s.full_name !== s.username" class="st-fullname">{{ s.full_name }}</span>
                        <!-- confirmed plagiarism withholds points (already out of rank and points); a pending flag changes nothing yet -->
                        <component :is="s.case_key ? RouterLink : 'span'" v-if="s.integrity_status === 'withheld'"
                                   :to="s.case_key ? caseLink(s.case_key) : undefined" class="integrity-badge withheld"
                                   :title="WITHHELD_HELP" @click.stop>Points withheld · plagiarism confirmed<template v-if="s.points_withheld"> · −{{ s.points_withheld }}</template><template v-if="s.case_key"> · View case →</template></component>
                        <component :is="s.case_key ? RouterLink : 'span'" v-else-if="s.integrity_status === 'under_review'"
                                   :to="s.case_key ? caseLink(s.case_key) : undefined" class="integrity-badge review"
                                   :title="REVIEW_HELP" @click.stop>Under review<template v-if="s.case_key"> · Open case →</template></component>
                    </span>
                    <span class="cell-muted">{{ s.attempts }}</span>
                    <span>
                        <span v-if="s.last_submitted_at" class="cell-muted">{{ submissionStatusLabel(s.last_status) }}, {{ formatDateTime(s.last_submitted_at) }}</span>
                        <span v-else class="cell-muted">—</span>
                    </span>
                    <span :class="resultClass(s.passed)">{{ s.questions_solved }}/{{ s.total_questions }}</span>
                    <span>
                        <span v-if="s.passed === null" class="cell-muted">—</span>
                        <!-- a question voided for confirmed plagiarism is not solved: say when that is why -->
                        <template v-else-if="s.questions_voided">
                            <span :class="s.passed ? 'badge-yes' : 'badge-no voided'" :title="NOT_COUNTED_HELP">{{ s.passed ? 'Passed' : 'Not passed · plagiarism' }}</span>
                            <small v-if="s.passed" class="result-note">{{ notCountedNote(s.questions_voided) }}</small>
                        </template>
                        <span v-else :class="s.passed ? 'badge-yes' : 'badge-no'">{{ s.passed ? 'Passed' : 'Not passed' }}</span>
                    </span>
                    <span class="cell-muted">{{ fmtTime(s.avg_solve_s) }}</span>
                    <span :class="s.behavioural_flags > 0 ? 'text-red' : 'cell-muted'">
                        {{ s.behavioural_flags > 0 ? plural(s.behavioural_flags, 'flag') : '—' }}
                    </span>
                    <span :class="s.similarity_flags > 0 ? 'text-red' : 'cell-muted'">
                        {{ s.similarity_flags > 0 ? plural(s.similarity_flags, 'flag') : '—' }}
                    </span>
                </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute, RouterLink } from 'vue-router'
import api from '../api'
import { formatDate, formatDateTime, formatSeconds, formatPct, formatMs, plural, submissionStatusLabel } from '../utils/format'
import { METRIC_HELP, NOT_COUNTED_HELP, integrityClass, notCountedNote, solvedCaption } from '../utils/metrics'
import { caseFileLink } from '../utils/caseFile'
import EndExamButton from '../components/EndExamButton.vue'
import ExamPublishCard from '../components/ExamPublishCard.vue'

const router = useRouter()
const route  = useRoute()

// The report ranks everyone enrolled, across sections; My results ranks within the student's section
const RANK_HELP = 'Ranked by points on this exam among every enrolled student, all sections. Tied students share a rank. A student with no points on it is not ranked.'
const WITHHELD_HELP = 'A confirmed plagiarism case cost this student the points for that question, so their rank dropped.'
const REVIEW_HELP = 'A flag on this student is waiting for review. Points and rank are unchanged until it is confirmed.'

const exam    = ref<any>(null)
const loading = ref(true)
// Set by Create exam when the exam saved but going live or scheduling it failed
const pushed  = router.options.history.state?.notice
const notice  = typeof pushed === 'string' ? pushed : ''
// Set by the case file when a case opened from this report was decided
const pushedCase = router.options.history.state?.caseNotice
const caseNotice = typeof pushedCase === 'string' ? pushedCase : ''

/** The student's case on this exam, opened from this report so it leads back here. */
function caseLink(key: string): string {
    return caseFileLink(Number(route.params.id), key, `report:${route.params.id}`)
}

async function loadExam(): Promise<void> {
    const res = await api.get(`/dashboard/exams/${route.params.id}/`)
    exam.value = res.data
}

onMounted(async () => {
    try {
        await loadExam()
        lastRun.value = await latestRun().catch(() => null)   // decides Run check vs View cases
    } finally {
        loading.value = false
    }
})

// Run plagiarism check: works on a live exam too, so the trainer never waits for the clock.
const checking = ref(false)
const checkNote = ref('')
const lastRun = ref<any | null>(null)
// Checked = a completed check exists, or the exam already has flags (seeded history has no run records)
const checked = computed(() => lastRun.value?.status === 'completed'
    || (exam.value?.similarity_pairs ?? 0) > 0 || (exam.value?.flagged_students ?? 0) > 0)
let checkTimer: ReturnType<typeof setTimeout> | null = null
onUnmounted(() => { if (checkTimer) clearTimeout(checkTimer) })

async function latestRun(): Promise<any | null> {
    const res = await api.get('/plagiarism/runs/', { params: { exam_id: route.params.id } })
    return Array.isArray(res.data) && res.data.length ? res.data[0] : null
}

async function runCheck(): Promise<void> {
    checking.value = true
    checkNote.value = ''
    try {
        const before = (await latestRun())?.id ?? 0
        await api.post(`/plagiarism/cohorts/${route.params.id}/rerun/`)
        checkNote.value = 'Comparing submissions…'
        pollRun(before, Date.now())
    } catch (e: any) {
        checkNote.value = e.response?.data?.error || 'Could not start the check'
        checking.value = false
    }
}

async function pollRun(beforeId: number, startedAt: number): Promise<void> {
    const run = await latestRun().catch(() => null)
    if (run && run.id > beforeId) {
        if (run.status === 'completed') {
            checking.value = false
            lastRun.value = run
            checkNote.value = `Done · ${plural(run.b_flags_total ?? 0, 'behaviour flag')}, ${plural(run.s_flags_total ?? 0, 'similar pair')}`
            await loadExam()
            return
        }
        if (run.status === 'failed') {
            checking.value = false
            checkNote.value = 'The check failed. Try again.'
            return
        }
        checkNote.value = `Comparing submissions… ${run.questions_done ?? 0} of ${plural(run.questions_total ?? 0, 'question')}`
    }
    if (Date.now() - startedAt > 180000) {
        checking.value = false
        checkNote.value = 'Still running. Refresh in a minute to see the flags.'
        return
    }
    checkTimer = setTimeout(() => pollRun(beforeId, startedAt), 2000)
}

/** Colour for a student's questions-solved count: green when it is a pass. */
function resultClass(passed: boolean | null) {
    return passed === null || passed === undefined ? 'text-muted' : passed ? 'good' : 'low'
}

function passClass(rate: number | null) {
    if (rate === null || rate === undefined) return 'text-muted'
    return rate >= 65 ? 'good' : rate >= 40 ? 'mid' : 'low'
}

function fmtDate(d: string) {
    return formatDate(d)
}

function fmtTime(s: number | null) {
    return formatSeconds(s)
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

.header-main { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.check-box { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: flex-end; gap: 10px; flex-shrink: 0; max-width: 100%; }
.check-btn { display: inline-flex; align-items: center; text-decoration: none; min-height: 40px; padding: 0 20px; font-family: var(--font-display); font-size: 14px; font-weight: 600; border-radius: var(--radius-pill); border: 1px solid var(--accent); background: var(--accent); color: var(--accent-ink); cursor: pointer; }
.check-btn.secondary { background: var(--surface); color: var(--red-ink); border-color: var(--border2); }
.check-btn.secondary:hover:not(:disabled) { border-color: var(--accent); }
.check-btn:disabled { opacity: 0.7; cursor: default; }
.check-note { flex-basis: 100%; font-size: 12px; color: var(--text-dim); margin: 0; text-align: right; }
.title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.title-row h1 { font-size: 24px; font-weight: 800; color: var(--text); }
.status-badge { font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 10px; }
.status-badge.ended { background: var(--surface3); color: var(--text-dim); }
.status-badge.live  { background: var(--green-dim); color: var(--green-ink); }
.status-badge.draft { background: var(--yellow-dim); color: var(--amber-ink); }

.meta-row { display: flex; align-items: center; gap: 12px; font-size: 13px; color: var(--text-dim); flex-wrap: wrap; }
.lang-chip { font-size: 11px; font-family: var(--font-mono); background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 7px; color: var(--text-muted); }
.exam-desc { margin-top: 10px; margin-bottom: 20px; font-size: 13px; color: var(--text-dim); line-height: 1.5; max-width: 680px; }

/* KPI strip */
.kpi-strip {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    margin-bottom: 16px; overflow: hidden;
}
.kpi { padding: 18px 20px; border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 4px; }
.kpi:last-child { border-right: none; }
.kpi-val { font-size: 24px; font-weight: 700; color: var(--text); line-height: 1; font-variant-numeric: tabular-nums; }
.kpi-val-sm { font-size: 13px; font-weight: 600; color: var(--text); line-height: 1.3; }
.kpi-denom { font-size: 14px; color: var(--text-dim); font-weight: 400; }
.kpi-label { font-size: 10px; font-weight: 700; color: var(--text-dim); }
.kpi-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin: 4px 0; }
.kpi-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.kpi-sub { font-size: 11px; color: var(--text-dim); }

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
.table-scroll { overflow-x: auto; }
.q-grid { display: grid; grid-template-columns: 2fr 90px 70px 150px 80px 60px; gap: 10px; padding: 10px 20px; align-items: center; min-width: 560px; }
.q-header { font-size: 10px; font-weight: 700; color: var(--text-dim); background: var(--surface3); border-bottom: 1px solid var(--border); }
.q-row { font-size: 13px; border-bottom: 1px solid var(--border); }
.q-row:last-child { border-bottom: none; }
.q-title { font-weight: 500; color: var(--text); }

/* All Students table */
.st-grid { display: grid; grid-template-columns: 50px minmax(140px, 1fr) 70px minmax(150px, 1fr) 60px 100px 80px 100px 90px; gap: 10px; padding: 10px 20px; align-items: center; min-width: 900px; }
.st-header { font-size: 10px; font-weight: 700; color: var(--text-dim); background: var(--surface3); border-bottom: 1px solid var(--border); }
.st-row { font-size: 13px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.12s; text-decoration: none; min-height: 40px; }
.st-row:last-child { border-bottom: none; }
.st-row:hover { background: var(--surface2); }
.st-name { font-weight: 500; color: var(--text); display: flex; flex-direction: column; min-width: 0; line-height: 1.4; }
.st-fullname { font-weight: 400; font-size: 11px; color: var(--text-dim); white-space: normal; }
.integrity-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; width: fit-content; max-width: 100%; margin-top: 3px; white-space: normal; line-height: 1.35; }
.integrity-badge.withheld { background: var(--red-dim); color: var(--red-ink); }
.integrity-badge.review   { background: var(--yellow-dim); color: var(--amber-ink); }
a.integrity-badge { display: inline-flex; align-items: center; min-height: 28px; text-decoration: none; }
a.integrity-badge.withheld:hover { border-color: var(--red-ink); box-shadow: inset 0 0 0 1px var(--red-ink); }
a.integrity-badge.review:hover   { box-shadow: inset 0 0 0 1px var(--amber-ink); }
.st-link { color: var(--text); font-weight: 500; text-decoration: none; }
.st-link:hover { color: var(--accent); text-decoration: underline; }
.done-banner {
    display: flex; align-items: center; gap: 10px; margin-bottom: 16px; padding: 14px 18px;
    border-radius: var(--radius); background: var(--green-dim); color: var(--green-ink); font-size: 14px; font-weight: 600;
}
.done-banner svg { flex-shrink: 0; }

/* Shared */
.inline-bar-wrap { height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; margin-bottom: 3px; }
.inline-bar { height: 100%; border-radius: 2px; }
.pct { font-size: 12px; font-weight: 700; }

.diff-chip { font-size: 10px; font-weight: 700; text-transform: capitalize; padding: 2px 8px; border-radius: 10px; width: fit-content; }
.diff-chip.easy   { background: var(--green-dim); color: var(--green-ink); }
.diff-chip.medium { background: var(--yellow-dim);  color: var(--amber-ink); }
.diff-chip.hard   { background: var(--red-dim);         color: var(--red-ink); }

.badge-yes { font-size: 11px; font-weight: 700; background: var(--green-dim); color: var(--green-ink); padding: 2px 8px; border-radius: 10px; }
.badge-no  { font-size: 11px; font-weight: 700; background: var(--surface3); color: var(--text-muted); padding: 2px 8px; border-radius: 10px; }
.badge-no.voided { background: var(--red-dim); color: var(--red-ink); }
.result-note { display: block; margin-top: 2px; font-size: 11px; line-height: 1.3; color: var(--red-ink); font-weight: 600; }

.bar-neutral { background: var(--text-dim); }
.bar-red    { background: var(--red); }
.bar-yellow { background: var(--yellow); }
.bar-good   { background: var(--green); }
.bar-mid    { background: var(--yellow); }
.bar-low    { background: var(--red); }

.good { color: var(--green-ink); }
.mid  { color: var(--amber-ink); }
.low  { color: var(--red-ink); }
.text-red    { color: var(--red-ink) !important; }
.text-yellow, .text-amber { color: var(--amber-ink) !important; }
.text-muted  { color: var(--text-muted) !important; }
.cell-muted  { color: var(--text-muted); }
.state-msg   { color: var(--text-muted); padding: 40px 0; }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .kpi-strip { grid-template-columns: repeat(3, 1fr); }
    .kpi { border-bottom: 1px solid var(--border); }
    .title-row { flex-wrap: wrap; }
    .meta-row { gap: 8px 12px; }
}

@media (max-width: 600px) {
    .kpi-strip { grid-template-columns: repeat(2, 1fr); }
    .page-header { flex-wrap: wrap; }
    .header-main { flex-direction: column; }
    .check-box { justify-items: start; }
    .check-note { text-align: left; }
}
</style>
