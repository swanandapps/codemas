<template>
  <div>
    <div class="detail">
        <!-- back from deciding a case: what was decided, on the page the trainer started from -->
        <div v-if="caseNotice" class="done-banner" role="status">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>
            {{ caseNotice }}
        </div>
        <div class="page-header">
            <button class="back-btn" @click="router.back()">Back</button>
            <div v-if="student">
                <h1>{{ student.username }}</h1>
                <span class="cohort-tag">{{ student.cohort || 'No section' }}</span>
                <span v-if="student.email" class="student-email">{{ student.email }}</span>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading...</div>

        <template v-else-if="student">
            <!-- KPI row -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">
                        Success rate
                        <span class="tip" :data-tip="METRIC_HELP.acceptedStudent">?</span>
                    </div>
                    <div class="kpi-value" :class="rateColor(student.accepted_rate)">{{ formatPct(student.accepted_rate) }}</div>
                    <div v-if="student.exams_taken" class="kpi-sub">{{ student.exams_passed }} of {{ plural(student.exams_taken, 'exam') }} passed</div>
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
                        {{ METRIC_LABEL.confidence }}
                        <span class="tip" :data-tip="`${METRIC_HELP.confidence} Shows this student's most suspicious flag; Clean means no flags.`">?</span>
                    </div>
                    <div :class="['kpi-value', 'conf-value', maxConfidence ? confidenceTextClass(maxConfidence) : 'clean']">
                        {{ maxConfidence ? humanize(maxConfidence) : 'Clean' }}
                    </div>
                    <div class="kpi-sub">{{ plural(countedBehavioural.length, 'flag') }}<template v-if="behaviouralFlags.length > countedBehavioural.length">, {{ behaviouralFlags.length - countedBehavioural.length }} dismissed not counted</template></div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">
                        Section rank
                        <span class="tip" data-tip="Ranking by score (points) within this student's section, the rank the student sees on Home and My results. Tied students share a rank; #1 is the highest.">?</span>
                    </div>
                    <div class="kpi-value">
                        {{ student.cohort_rank ? `#${student.cohort_rank} / ${student.cohort_size}` : '—' }}
                    </div>
                    <div v-if="student.score !== undefined" class="kpi-sub">
                        {{ plural(student.score, 'point') }}<span v-if="student.points_withheld" class="withheld-text"> · {{ student.points_withheld }} withheld, plagiarism confirmed</span>
                    </div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="tab-row">
                <button :class="['tab-btn', activeTab === 'overview' ? 'active' : '']" @click="activeTab = 'overview'">Overview</button>
                <button :class="['tab-btn', activeTab === 'integrity' ? 'active' : '']" @click="activeTab = 'integrity'">
                    Integrity
                    <span v-if="pendingCases > 0" class="tab-chip">{{ plural(pendingCases, 'case') }} pending</span>
                </button>
                <button :class="['tab-btn', activeTab === 'disputes' ? 'active' : '']" @click="activeTab = 'disputes'">
                    Disputes
                    <span class="tab-badge" v-if="student.open_disputes > 0" :title="`${student.open_disputes} open`">
                        {{ student.open_disputes }}
                    </span>
                </button>
            </div>

            <!-- ── OVERVIEW TAB ── -->
            <template v-if="activeTab === 'overview'">
            <!-- Performance trend chart -->
            <div class="chart-card" v-if="performanceTrend.length > 0">
                <h3>Weekly contest performance &nbsp;<span class="legend-dot passed">passed</span><span class="legend-dot failed">not passed</span></h3>
                <apexchart type="line" height="220" :options="trendOptions" :series="trendSeries" />
            </div>

            <!-- Per question breakdown -->
            <h2 class="section-title">Attempts by question</h2>
            <div v-for="q in questions" :key="q.question_id" class="question-block">
                <div class="question-header">
                    <span class="q-title">{{ q.question_title }}<span v-if="q.exam" class="q-exam">{{ q.exam }}</span></span>
                    <span class="q-side">
                        <span v-if="q.points_withheld" class="withheld-badge" title="A confirmed plagiarism case cost the student these points, so their rank dropped">Points withheld · −{{ q.points_withheld }}</span>
                        <span class="q-meta" title="Submissions that couldn't run are refunded and not counted">{{ q.attempts_used }} / {{ q.max_attempts }} attempts</span>
                    </span>
                </div>
                <div class="table-scroll">
                <table class="attempt-table">
                    <thead>
                        <tr>
                            <th>#</th>
                            <th>Status</th>
                            <th>Language</th>
                            <th>Run time</th>
                            <th>Solve time</th>
                            <th>Time used</th>
                            <th>Paste</th>
                            <th>Plagiarism</th>
                            <th>Submitted</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="a in q.attempts" :key="a.attempt_number" class="attempt-row" @click="openDrawer(a, q.question_title)">
                            <td>#{{ a.attempt_number }}</td>
                            <td><span :class="['status', a.status]">{{ submissionStatusLabel(a.status) }}</span></td>
                            <td>{{ a.language }}</td>
                            <td>{{ formatMs(a.execution_time_ms) }}</td>
                            <td>{{ a.solve_time_seconds ? formatSolveTime(a.solve_time_seconds) : '—' }}</td>
                            <td>
                                <div class="pct-bar">
                                    <div
                                        class="pct-fill"
                                        :style="{ width: (a.percent_time_used || 0) + '%' }"
                                        :class="pctClass(a.percent_time_used)"
                                    />
                                    <span>{{ formatPct(a.percent_time_used) }}</span>
                                </div>
                            </td>
                            <td>
                                <span v-if="a.paste_char_count > 0" class="badge warn">Pasted {{ plural(a.paste_char_count, 'char') }}</span>
                                <span v-else class="badge ok">None</span>
                            </td>
                            <td>
                                <span v-if="a.plagiarism" :class="['badge', a.plagiarism.review_status === 'confirmed' ? 'danger' : 'warn']">
                                    {{ formatPct(a.plagiarism.score * 100) }}
                                </span>
                                <span v-else class="badge ok">Clean</span>
                            </td>
                            <td class="date">{{ formatDateTime(a.submitted_at) }}</td>
                            <td>
                                <button type="button" class="view-code-btn" @click.stop="openDrawer(a, q.question_title)">
                                    View details
                                </button>
                            </td>
                        </tr>
                    </tbody>
                </table>
                </div>
            </div>

            </template><!-- end overview tab -->

            <!-- ── INTEGRITY TAB ── -->
            <!-- one group per exam with a flag: what is decided there, and the way into its case -->
            <template v-if="activeTab === 'integrity'">
                <div v-if="integrityCases.length === 0" class="empty-state">No integrity flags for this student.</div>
                <section v-for="g in integrityCases" :key="g.exam_id" class="exam-case" :aria-labelledby="`exam-case-${g.exam_id}`">
                    <div class="case-head">
                        <h2 :id="`exam-case-${g.exam_id}`" class="case-title">{{ g.exam_title }}</h2>
                        <span :class="['case-status', g.status]">{{ CASE_STATUS[g.status] }}</span>
                        <span v-if="g.points_withheld" class="withheld-chip">Points withheld · −{{ g.points_withheld }}</span>
                        <span v-if="g.appeal?.status === 'open'" class="appeal-chip">Appeal pending</span>
                        <span v-else-if="g.appeal" class="appeal-chip ruled">Appeal {{ g.appeal.status }}</span>
                        <span class="case-meta">{{ caseMeta(g) }}</span>
                        <span class="grow"></span>
                        <router-link v-if="g.status === 'pending'" :to="caseLink(g)" class="open-case">Open case →</router-link>
                        <router-link v-else :to="caseLink(g)" class="view-case">View case →</router-link>
                    </div>
                    <div class="case-body">
                        <div class="case-behaviour">
                            <span class="case-label">Behaviour</span> <span class="sig">{{ behaviourLine(g) }}</span>
                        </div>
                        <div v-if="g.code_matches.length" class="case-matches">
                            <span class="case-label">Code matches</span>
                            <router-link v-for="m in g.code_matches" :key="m.student_id" :to="`/dashboard/students/${m.student_id}`" class="sig match-chip">{{ m.username }} · <span class="mono">{{ scorePct(m.score) }}</span></router-link>
                        </div>
                        <p v-if="g.status === 'pending'" class="case-hint">Decide in the case: it shows everyone's code and behaviour side by side, so the decision is fair to everyone in it.</p>
                        <p v-if="g.appeal?.status === 'open'" class="case-appeal">
                            <strong>The student responded:</strong> “{{ g.appeal.student_note }}”
                            <router-link :to="`/dashboard/support/disputes/${g.appeal.id}`" class="flag-link">Open appeal →</router-link>
                        </p>
                        <div v-if="g.review" class="case-review">
                            <p v-if="g.review.note" class="case-note"><strong>Your note to the student:</strong> “{{ g.review.note }}”</p>
                            <p class="reviewed-by">{{ REVIEWED_VERB[g.status] }}<template v-if="g.review.reviewed_by"> by {{ g.review.reviewed_by }}</template><template v-if="g.review.reviewed_at"> · {{ formatDateTime(g.review.reviewed_at) }}</template></p>
                        </div>

                        <!-- every flag on this exam, as before: scores, signals, notes, links -->
                        <details class="flag-details">
                            <summary>Flag details · {{ flagCountLine(g.exam_id) }}</summary>
                            <div v-for="f in behaviouralFlags.filter(x => x.exam_id === g.exam_id)" :key="`b${f.id}`" class="flag-card">
                                <div class="flag-card-top">
                                    <div class="flag-card-left">
                                        <span class="flag-question">{{ f.question }}</span>
                                        <span class="flag-exam">Behaviour flag</span>
                                    </div>
                                    <div class="flag-card-right">
                                        <span :class="['conf-badge', confidenceClass(f.confidence)]" :title="METRIC_HELP.confidence">{{ confidenceLabel(f.confidence) }}</span>
                                        <span class="risk-score" :title="METRIC_HELP.risk">Risk {{ formatRisk(f.risk_score) }}</span>
                                        <span :class="['badge', f.review_status]">{{ humanize(f.review_status) }}</span>
                                    </div>
                                </div>
                                <div class="score-bars">
                                    <div class="score-bar-row">
                                        <span class="score-label">Paste</span>
                                        <div class="score-track"><div class="score-fill paste-fill" :style="{ width: (f.paste_score * 100) + '%' }"/></div>
                                        <span class="score-val">{{ formatPct(f.paste_score * 100) }}</span>
                                    </div>
                                    <div class="score-bar-row">
                                        <span class="score-label">Speed</span>
                                        <div class="score-track"><div class="score-fill time-fill" :style="{ width: (f.time_score * 100) + '%' }"/></div>
                                        <span class="score-val">{{ formatPct(f.time_score * 100) }}</span>
                                    </div>
                                </div>
                                <div class="signals-list" v-if="f.signals?.length">
                                    <span v-for="sig in f.signals" :key="sig" class="signal-chip">{{ sig }}</span>
                                </div>
                                <div class="flag-footer">
                                    <span v-if="f.review_note" class="review-note">"{{ f.review_note }}"</span>
                                    <span v-if="f.reviewed_by" class="reviewed-by">Reviewed by {{ f.reviewed_by }}</span>
                                    <router-link :to="`/dashboard/submissions/${f.submission_id}`" class="flag-link">View submission</router-link>
                                </div>
                            </div>
                            <div v-for="f in plagiarismFlags.filter(x => x.exam_id === g.exam_id)" :key="`s${f.id}`" class="flag-card">
                                <div class="flag-card-top">
                                    <div class="flag-card-left">
                                        <span class="flag-question">{{ f.question }}</span>
                                        <span class="flag-exam">Matched with <router-link :to="`/dashboard/students/${f.matched_student_id}`" class="matched-link">{{ f.matched_student }}</router-link></span>
                                    </div>
                                    <div class="flag-card-right">
                                        <span class="sim-score-badge">{{ formatPct(f.similarity_score * 100) }} similar</span>
                                        <span :class="['badge', f.review_status]">{{ humanize(f.review_status) }}</span>
                                    </div>
                                </div>
                                <div class="flag-footer">
                                    <span v-if="f.review_note" class="review-note">"{{ f.review_note }}"</span>
                                    <span v-if="f.reviewed_by" class="reviewed-by">Reviewed by {{ f.reviewed_by }}</span>
                                    <router-link :to="`/dashboard/submissions/${f.submission_id}`" class="flag-link">View submission</router-link>
                                </div>
                            </div>
                        </details>
                    </div>
                </section>

            </template><!-- end integrity tab -->

            <!-- ── DISPUTES TAB ── -->
            <template v-if="activeTab === 'disputes'">
                <h2 class="section-title">Disputes <span class="section-count">{{ disputes.length }}</span></h2>
                <div v-if="disputes.length === 0" class="empty-state">No disputes filed by this student.</div>
                <div v-for="d in disputes" :key="d.id" class="flag-card">
                    <div class="flag-card-top">
                        <div class="flag-card-left">
                            <span class="flag-question">{{ d.exam_title ?? (d.flag_type ? `${humanize(d.flag_type)} flag` : 'Appeal') }}</span>
                            <span class="flag-exam">Filed {{ formatDateTime(d.created_at) }}</span>
                        </div>
                        <div class="flag-card-right">
                            <span :class="['badge', disputeClass(d.status)]">{{ TRAINER_APPEAL_STATUS[d.status as AppealStatus] ?? humanize(d.status) }}</span>
                        </div>
                    </div>
                    <p class="dispute-note">"{{ d.student_note }}"</p>
                    <p v-if="d.resolution_note" class="resolution"><strong>Your reply:</strong> {{ d.resolution_note }}</p>
                    <div class="flag-footer">
                        <router-link :to="`/dashboard/support/disputes/${d.id}`" class="flag-link">Open appeal</router-link>
                    </div>
                </div>
            </template><!-- end disputes tab -->
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
                            <span>Attempt #{{ drawer.attempt?.attempt_number }}</span>
                            <span :class="['status', drawer.attempt?.status]">{{ drawer.attempt?.status }}</span>
                            <span>{{ drawer.attempt ? formatDateTime(drawer.attempt.submitted_at) : '' }}</span>
                            <router-link v-if="drawer.attempt" :to="`/dashboard/submissions/${drawer.attempt.submission_id}`" class="flag-link">Open submission</router-link>
                        </div>
                    </div>
                    <button class="drawer-close" @click="drawer.open = false">Close</button>
                </div>

                <div class="drawer-body">
                    <!-- Raw metrics row -->
                    <div class="drawer-metrics">
                        <div class="metric-chip">
                            <span class="metric-label">Run time</span>
                            <span class="metric-val">{{ formatMs(drawer.attempt?.execution_time_ms) }}</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Solve time</span>
                            <span class="metric-val">{{ drawer.attempt?.solve_time_seconds ? formatSolveTime(drawer.attempt.solve_time_seconds) : '—' }}</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Time used</span>
                            <span class="metric-val">{{ formatPct(drawer.attempt?.percent_time_used) }}</span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Pasted</span>
                            <span :class="['metric-val', (drawer.attempt?.paste_char_count ?? 0) > 0 ? 'val-warn' : '']">
                                {{ plural(drawer.attempt?.paste_char_count ?? 0, 'char') }}
                            </span>
                        </div>
                        <div class="metric-chip">
                            <span class="metric-label">Tab switches</span>
                            <span :class="['metric-val', (drawer.attempt?.tab_switch_count ?? 0) >= 3 ? 'val-warn' : '']">
                                {{ drawer.attempt?.tab_switch_count ?? 0 }}
                            </span>
                        </div>
                    </div>

                    <!-- Behavioural analysis -->
                    <div v-if="drawer.attempt?.behavioural" class="drawer-section">
                        <div class="drawer-section-title">
                            Behavioural analysis
                            <span :class="['conf-pill', confidenceClass(drawer.attempt.behavioural.confidence)]" :title="METRIC_HELP.confidence">
                                {{ confidenceLabel(drawer.attempt.behavioural.confidence) }}
                            </span>
                            <span class="risk-num" :title="METRIC_HELP.risk">Risk {{ formatRisk(drawer.attempt.behavioural.risk_score) }}</span>
                        </div>
                        <div class="signal-bars">
                            <div class="signal-row">
                                <span class="signal-name">Paste</span>
                                <div class="signal-track">
                                    <div class="signal-fill paste-fill" :style="{ width: (drawer.attempt.behavioural.paste_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ formatPct(drawer.attempt.behavioural.paste_score * 100) }}</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Speed</span>
                                <div class="signal-track">
                                    <div class="signal-fill time-fill" :style="{ width: (drawer.attempt.behavioural.time_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ formatPct(drawer.attempt.behavioural.time_score * 100) }}</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Tab switches</span>
                                <div class="signal-track">
                                    <div class="signal-fill tab-fill" :style="{ width: (drawer.attempt.behavioural.tab_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ formatPct(drawer.attempt.behavioural.tab_score * 100) }}</span>
                            </div>
                            <div class="signal-row">
                                <span class="signal-name">Unusual code change</span>
                                <div class="signal-track">
                                    <div class="signal-fill surprise-fill" :style="{ width: (drawer.attempt.behavioural.surprise_score * 100) + '%' }"/>
                                </div>
                                <span class="signal-pct">{{ formatPct(drawer.attempt.behavioural.surprise_score * 100) }}</span>
                            </div>
                        </div>
                        <div v-if="drawer.attempt.behavioural.signals?.length" class="signal-chips">
                            <span v-for="sig in drawer.attempt.behavioural.signals" :key="sig" class="signal-chip">{{ sig }}</span>
                        </div>
                    </div>
                    <div v-else class="drawer-section">
                        <div class="drawer-section-title">Behavioural Analysis</div>
                        <p class="no-flags">No behavioural flags on this submission.</p>
                    </div>

                    <!-- Similarity match -->
                    <div v-if="drawer.attempt?.plagiarism" class="drawer-section">
                        <div class="drawer-section-title">Similarity match</div>
                        <div class="sim-match-row">
                            <span class="sim-label">Matched with</span>
                            <strong class="sim-student">{{ drawer.attempt.plagiarism.matched_student }}</strong>
                            <span :class="['badge', drawer.attempt.plagiarism.review_status === 'confirmed' ? 'danger' : 'warn']">
                                {{ formatPct(drawer.attempt.plagiarism.score * 100) }} similar
                            </span>
                            <span :class="['badge', drawer.attempt.plagiarism.review_status]">
                                {{ humanize(drawer.attempt.plagiarism.review_status) }}
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
import { formatDate, formatDateTime, formatMs, formatSeconds, formatPct, formatRisk, humanize, plural, submissionStatusLabel } from '../utils/format'
import { METRIC_HELP, METRIC_LABEL, confidenceClass, confidenceLabel, confidenceTextClass, countsAsFlagged, maxConfidence as mostSuspicious, questionsNotCounted } from '../utils/metrics'
import { caseFileLink, type CaseStatus } from '../utils/caseFile'
import { scorePct } from '../utils/similarityGrid'
import { TRAINER_APPEAL_STATUS, type AppealStatus } from '../utils/appeals'

/** One exam where the student has a flag (dashboard StudentDetailView `integrity_cases`). */
interface IntegrityCase {
    exam_id: number
    exam_title: string
    exam_date: string | null
    questions: string[]
    status: CaseStatus   // the student's own flags on this exam
    points_withheld: number
    case_key: string | null
    behaviour_flags: number
    top_signals: string[]
    code_matches: { student_id: number; username: string; score: number }[]
    review: { note: string; reviewed_by: string | null; reviewed_at: string | null } | null
    appeal?: { id: number; status: 'open' | 'upheld' | 'overturned'; student_note: string } | null
}

const CASE_STATUS: Record<CaseStatus, string> = {
    pending: 'Under review',
    confirmed: 'Plagiarism confirmed',
    dismissed: 'Dismissed',
    mixed: 'Partly decided',
}
const REVIEWED_VERB: Record<CaseStatus, string> = {
    pending: 'Reviewed', confirmed: 'Confirmed', dismissed: 'Dismissed', mixed: 'Reviewed',
}

const route = useRoute()
const router = useRouter()
const loading = ref<boolean>(true)
const student = ref<any>(null)
const questions = ref<any[]>([])
const performanceTrend = ref<any[]>([])
const plagiarismFlags = ref<any[]>([])
const behaviouralFlags = ref<any[]>([])
const disputes = ref<any[]>([])
const integrityCases = ref<IntegrityCase[]>([])
// Back from deciding a case (CohortDetailView), the Integrity tab opens with what was decided
const activeTab = ref<'overview' | 'integrity' | 'disputes'>(route.query.tab === 'integrity' ? 'integrity' : 'overview')
const pushedNotice = router.options.history.state?.caseNotice
const caseNotice = typeof pushedNotice === 'string' ? pushedNotice : ''

// Dismissed flags stay listed on the Integrity tab but don't count (same rule as the students list)
const countedBehavioural = computed(() => behaviouralFlags.value.filter(countsAsFlagged))
const pendingCases = computed(() => integrityCases.value.filter(g => g.status === 'pending').length)

function caseLink(g: IntegrityCase): string {
    return caseFileLink(g.exam_id, g.case_key, `student:${route.params.id}`)
}
function caseMeta(g: IntegrityCase): string {
    return [g.exam_date ? formatDate(g.exam_date) : '', g.questions.join(', ')].filter(Boolean).join(' · ')
}
function behaviourLine(g: IntegrityCase): string {
    if (!g.behaviour_flags) return 'No behaviour flags'
    return [plural(g.behaviour_flags, 'flag'), ...g.top_signals].join(' · ')
}
function flagCountLine(examId: number): string {
    const b = behaviouralFlags.value.filter(f => f.exam_id === examId).length
    const p = plagiarismFlags.value.filter(f => f.exam_id === examId).length
    return [b ? plural(b, 'behaviour flag') : '', p ? plural(p, 'similarity flag') : ''].filter(Boolean).join(', ')
}
// most suspicious flag: high (3+ signals) beats medium beats low
const maxConfidence = computed(() => mostSuspicious(countedBehavioural.value.map(f => f.confidence)))

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
        disputes.value = res.data.disputes ?? []
        integrityCases.value = res.data.integrity_cases ?? []
    } finally {
        loading.value = false
    }
})

// open = waiting on a trainer; upheld = the decision stands; overturned = points restored
function disputeClass(status: string): string {
    return status === 'open' ? 'pending' : status === 'upheld' ? 'danger' : 'ok'
}

function rateColor(rate: number | null): string {
    if (rate === null || rate === undefined) return ''
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
function formatSolveTime(seconds: number): string {
    return formatSeconds(seconds)
}

// Trend chart — one point per weekly contest exam, sorted oldest to newest so the
// x-axis reads in order; green dot = passed the exam (solved at least half its questions), red = not.
// A question voided for confirmed plagiarism is not solved, so it can turn the dot red; the tooltip says so.
const sortedTrend = computed(() =>
    [...performanceTrend.value].sort((a: any, b: any) => new Date(a.date).getTime() - new Date(b.date).getTime())
)

// Only show the year in axis labels when the points span more than one year —
// otherwise it's just repeated noise.
const trendSpansYears = computed(() => {
    const years = new Set(sortedTrend.value.map((p: any) => new Date(p.date).getFullYear()))
    return years.size > 1
})

function trendAxisLabel(dateStr: string): string {
    const d = formatDate(dateStr) // "26 Jun 2026"
    if (trendSpansYears.value) return d
    return d.replace(/ \d{4}$/, '') // drop the year when every point is the same year
}

const trendSeries = computed(() => [{
    name: '% time used',
    data: sortedTrend.value.map((p: any) => p.pct_time_used ?? null),
}])
const trendOptions = computed(() => ({
    chart: { toolbar: { show: false }, background: 'transparent' },
    theme: { mode: 'light' },
    colors: ['#21191B'],
    foreColor: '#544D4F',
    stroke: { curve: 'smooth', width: 2 },
    fontFamily: 'Inter, system-ui, sans-serif',
    markers: {
        size: 8,
        strokeWidth: 0,
        hover: { size: 10 },
        discrete: sortedTrend.value.map((p: any, i: number) => ({
            seriesIndex: 0,
            dataPointIndex: i,
            fillColor: p.status === 'passed' ? '#16A34A' : '#ED0331',
            strokeColor: 'transparent',
            size: 8,
        })),
    },
    xaxis: {
        categories: sortedTrend.value.map((p: any) => trendAxisLabel(p.date)),
        labels: { style: { fontSize: '11px' } },
    },
    yaxis: { min: 0, max: 100, labels: { formatter: (v: number) => v + '%' } },
    dataLabels: { enabled: false },
    tooltip: {
        theme: 'light',
        custom: ({ series, seriesIndex, dataPointIndex }: any) => {
            const p = sortedTrend.value[dataPointIndex]
            const color = p.status === 'passed' ? '#16A34A' : '#ED0331'
            const pct = series[seriesIndex][dataPointIndex]
            const statusLabel = p.status === 'passed' ? 'Passed' : 'Not passed'
            return `<div style="padding:8px 12px;font-size:12px;background:#FFFFFF;border:1px solid #EDE4E4;border-radius:6px">
                <div style="color:#544D4F;margin-bottom:6px;font-size:11px">${p.exam}</div>
                <span style="color:${color};font-weight:700">${statusLabel}</span>
                <span>, solved ${p.questions_solved} of ${p.questions_total} questions</span><br/>
                ${p.questions_voided ? `<span style="color:#C8022B;font-size:11px;font-weight:600">plagiarism confirmed: ${questionsNotCounted(p.questions_voided)}</span><br/>` : ''}
                ${p.points_withheld ? `<span style="color:#C8022B;font-size:11px;font-weight:600">${p.points_withheld} points withheld, plagiarism confirmed</span><br/>` : ''}
                <span style="color:#6B6365;font-size:11px">Avg ${pct}% of exam time used</span>
            </div>`
        }
    },
    grid: { borderColor: '#EDE4E4' },
}))

</script>

<style scoped>
.detail { max-width: 1000px; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.back-btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 7px 14px; background: var(--surface); border: 1px solid var(--border2);
    border-radius: var(--radius-pill); color: var(--text); font-size: 13px;
    cursor: pointer; transition: all 0.15s;
}
.back-btn:hover { border-color: var(--border2); color: var(--text); }
h1 { margin: 0 0 4px; }
.cohort-tag { font-size: 12px; background: var(--surface2); color: var(--text-muted); padding: 2px 10px; border-radius: 10px; }
.student-email { font-size: 12px; color: var(--text-dim); margin-left: 8px; }

.kpi-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.kpi-label {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--text-dim);
    font-weight: 600; margin-bottom: 8px;
}
.kpi-value { font-size: 28px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }

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
    background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow-lg);
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
    font-size: 10px; font-weight: 700;
}
.conf-value.clean  { color: var(--green-ink); }
.kpi-sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.kpi-value.good { color: var(--green-ink); }
.kpi-value.mid { color: var(--amber-ink); }
.kpi-value.bad { color: var(--red-ink); }
.kpi-value.warn { color: var(--red-ink); }

/* ── Tabs ── */
.tab-row { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 20px; }
.tab-btn {
    padding: 7px 18px; background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-pill); color: var(--text-muted); font-size: 13px;
    font-weight: 600; cursor: pointer; display: flex; align-items: center; gap: 6px;
    transition: all 0.15s;
}
.tab-btn:hover { color: var(--text); border-color: var(--border2); }
.tab-btn.active { background: var(--accent-tint); border-color: var(--accent); color: var(--accent); }
.tab-badge {
    background: var(--red); color: #fff; font-size: 10px; font-weight: 700;
    padding: 1px 6px; border-radius: 10px;
}
.tab-chip { background: var(--yellow-dim); color: #92400E; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 10px; }

.done-banner {
    display: flex; align-items: center; gap: 10px; margin-bottom: 20px; padding: 14px 18px;
    border-radius: var(--radius); background: var(--green-dim); color: var(--green-ink); font-size: 14px; font-weight: 600;
}
.done-banner svg { flex-shrink: 0; }

/* ── Integrity tab: one group per exam ── */
.grow { flex-grow: 1; }
.mono { font-family: var(--font-mono); }
.exam-case { background: var(--surface); border: 1px solid var(--border); border-radius: 18px; margin-bottom: 16px; overflow: hidden; }
.case-head { display: flex; align-items: center; gap: 10px 12px; flex-wrap: wrap; padding: 18px 22px; border-bottom: 1px solid #F1E9E9; }
.case-title { margin: 0; font-size: 18px; overflow-wrap: anywhere; min-width: 0; }
.case-status, .withheld-chip {
    display: inline-flex; align-items: center; height: 26px; padding: 0 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
}
.case-status.pending   { background: var(--yellow-dim); color: #92400E; }
.case-status.confirmed { background: var(--red-dim); color: var(--red-ink); }
.case-status.dismissed { background: var(--green-dim); color: var(--green-ink); }
.case-status.mixed     { background: var(--surface2); color: var(--text-muted); }
.withheld-chip { background: var(--red-dim); color: var(--red-ink); }
.appeal-chip {
    display: inline-flex; align-items: center; padding: 3px 10px; border-radius: var(--radius-pill);
    font-size: 12px; font-weight: 600; white-space: nowrap; background: var(--yellow-dim); color: #92400E;
}
.appeal-chip.ruled { background: var(--surface2); color: var(--text-muted); text-transform: none; }
.case-appeal { margin: 0; padding: 10px 14px; border-left: 3px solid var(--yellow); background: var(--surface2);
    border-radius: var(--radius-sm); font-size: 14px; color: var(--text); overflow-wrap: anywhere; }
.case-appeal .flag-link { display: inline-flex; align-items: center; min-height: 44px; margin-left: 6px; }
.case-meta { font-size: 13px; color: var(--text-dim); overflow-wrap: anywhere; }
.open-case {
    display: inline-flex; align-items: center; min-height: 44px; padding: 0 20px;
    border-radius: var(--radius-pill); background: var(--accent); color: var(--accent-ink);
    font-size: 14px; font-weight: 600; white-space: nowrap;
}
.open-case:hover { background: var(--accent-hover); color: var(--accent-ink); text-decoration: none; }
.view-case { display: inline-flex; align-items: center; min-height: 44px; font-size: 14px; font-weight: 600; color: var(--red-ink); white-space: nowrap; }
.case-body { display: flex; flex-direction: column; gap: 12px; padding: 16px 22px 18px; }
.case-behaviour, .case-matches { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.case-label { font-size: 13px; font-weight: 600; color: var(--text-muted); min-width: 104px; }
.sig {
    display: inline-flex; align-items: center; gap: 4px; min-height: 28px; padding: 4px 10px;
    border-radius: var(--radius-pill); background: #F7F1EE; font-size: 12px; color: #3B3435; max-width: 100%;
}
.match-chip { color: #3B3435; }
.match-chip:hover { color: var(--red-ink); text-decoration: none; }
.case-hint { margin: 0; font-size: 13px; color: var(--text-dim); }
.case-review { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border-radius: var(--radius-sm); background: var(--surface2); }
.case-review p { margin: 0; font-size: 13px; }
.case-note { color: var(--text); line-height: 1.5; }
.flag-details { border-top: 1px solid #F1E9E9; padding-top: 10px; }
.flag-details summary { padding: 12px 0; cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text-muted); }
.flag-details summary:hover { color: var(--text); }
.flag-details .flag-card { margin: 8px 0 0; }

/* ── Legend dots in chart heading ── */
.legend-dot { font-size: 12px; font-weight: 600; margin-left: 8px; }
.legend-dot.passed { color: var(--green-ink); }
.legend-dot.failed { color: var(--red-ink); }

/* ── Integrity and Disputes tabs ── */
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
.sim-score-badge { font-size: 13px; font-weight: 700; color: var(--amber-ink); }

.conf-badge { font-size: 10px; font-weight: 700; padding: 2px 10px; border-radius: 10px; }

.score-bars { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
.score-bar-row { display: flex; align-items: center; gap: 10px; }
.score-label { font-size: 11px; color: var(--text-dim); width: 36px; flex-shrink: 0; }
.score-track { flex: 1; height: 5px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; }
.paste-fill { background: var(--yellow); }
.time-fill  { background: var(--red); }
.score-val { font-size: 11px; color: var(--text-dim); width: 30px; text-align: right; flex-shrink: 0; }

.signals-list { display: flex; flex-wrap: wrap; gap: 6px; }
.flag-footer { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-top: 12px; font-size: 12px; }
.flag-footer:empty { display: none; }
.review-note { font-style: italic; color: var(--text-muted); }
.reviewed-by { color: var(--text-dim); }
.flag-link { margin-left: auto; font-weight: 600; color: var(--red-ink); text-decoration: none; }
.flag-link:hover { text-decoration: underline; }
.matched-link { font-weight: 700; color: var(--text); }
.dispute-note { font-style: italic; color: var(--text-muted); margin: 0 0 8px; font-size: 13px; }
.resolution { font-size: 12px; color: var(--text-dim); background: var(--surface2); padding: 8px 12px; border-radius: var(--radius-sm); margin: 0; }
.signal-chip {
    font-size: 11px; padding: 3px 10px; border-radius: 10px;
    background: var(--yellow-dim); color: var(--amber-ink); font-weight: 500;
}

.chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
h3 { margin: 0 0 12px; font-size: 13px; font-weight: 600; color: var(--text-muted); }
.section-title { font-size: 16px; font-weight: 700; margin: 24px 0 12px; color: var(--text); }

.question-block { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 16px; }
.question-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
.q-title { font-weight: 700; font-size: 15px; color: var(--text); }
.q-exam { font-weight: 400; font-size: 12px; color: var(--text-dim); margin-left: 8px; }
.q-meta { font-size: 12px; color: var(--text-dim); }
.q-side { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 6px 10px; }
.withheld-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; background: var(--red-dim); color: var(--red-ink); }
.withheld-text { color: var(--red-ink); font-weight: 600; }

.table-scroll { overflow-x: auto; }
.attempt-table { width: 100%; min-width: 760px; border-collapse: collapse; font-size: 13px; }
.attempt-table th { padding: 8px 10px; font-size: 11px; color: var(--text-dim); border-bottom: 1px solid var(--border); text-align: left; }
.attempt-table td { padding: 10px 10px; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--text-muted); }
.attempt-table tr:last-child td { border-bottom: none; }
.attempt-row { cursor: pointer; }
.attempt-row:hover td { background: var(--surface2); }

.status { padding: 3px 10px; border-radius: 10px; font-size: 11px; font-weight: 700; }
.status.passed { background: var(--green-dim); color: var(--green-ink); }
.status.failed { background: var(--red-dim); color: var(--red-ink); }
.status.running { background: var(--yellow-dim); color: var(--amber-ink); }

.pct-bar { display: flex; align-items: center; gap: 6px; }
.pct-fill { height: 6px; border-radius: 3px; min-width: 2px; }
.pct-fill.high { background: var(--red); }
.pct-fill.mid { background: var(--yellow); }
.pct-fill.low { background: var(--green); }

.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px; font-weight: 600; }
.badge.ok { background: var(--green-dim); color: var(--green-ink); }
.badge.warn { background: var(--yellow-dim); color: var(--amber-ink); }
.badge.danger { background: var(--red-dim); color: var(--red-ink); }
.badge.confirmed { background: var(--red-dim); color: var(--red-ink); }
.badge.pending { background: var(--yellow-dim); color: var(--amber-ink); }
.badge.dismissed { background: var(--green-dim); color: var(--green-ink); }

.date { color: var(--text-dim); font-size: 12px; white-space: nowrap; }

.flag-row { display: flex; gap: 16px; align-items: center; padding: 12px 16px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm); margin-bottom: 8px; font-size: 14px; color: var(--text-muted); }
.sim-score { color: var(--amber-ink); font-weight: 600; }
.loading { color: var(--text-muted); }

.view-code-btn {
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    color: var(--text-dim);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s;
}
.view-code-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── Drawer ── */
.drawer-backdrop {
    position: fixed; inset: 0; background: rgba(33,25,27,0.4); z-index: 1000;
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
.drawer-meta { font-size: 12px; color: var(--text-dim); display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.drawer-close {
    background: transparent; border: 1px solid var(--border); color: var(--text-dim);
    font-size: 12px; font-weight: 600; cursor: pointer; padding: 5px 12px; border-radius: var(--radius-sm); transition: color 0.15s;
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
.metric-label { font-size: 10px; color: var(--text-dim); font-weight: 600; }
.metric-val { font-size: 15px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.metric-val.val-warn { color: var(--amber-ink); }

.drawer-section { padding: 16px 20px; border-bottom: 1px solid var(--border); }
.drawer-section:last-child { border-bottom: none; }
.drawer-section-title {
    font-size: 11px;
    font-weight: 700; color: var(--text-dim); margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
}
.risk-num { font-size: 12px; font-weight: 700; color: var(--text-muted); margin-left: auto; }

.signal-bars { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.signal-row { display: flex; align-items: center; gap: 10px; }
.signal-name { font-size: 11px; color: var(--text-dim); width: 110px; flex-shrink: 0; }
.signal-track { flex: 1; height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.signal-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.paste-fill    { background: var(--yellow); }
.time-fill     { background: var(--red); }
.tab-fill      { background: var(--text-dim); } /* neutral: distinct from paste/speed bars but not a semantic status color */
.surprise-fill { background: var(--text-dim); }
.signal-pct { font-size: 11px; color: var(--text-dim); width: 32px; text-align: right; flex-shrink: 0; }

.signal-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.signal-chip { font-size: 11px; padding: 3px 10px; border-radius: 10px; background: var(--yellow-dim); color: var(--amber-ink); font-weight: 500; }

.no-flags { font-size: 13px; color: var(--text-dim); }

.sim-match-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.sim-label { font-size: 12px; color: var(--text-dim); }
.sim-student { font-size: 14px; color: var(--text); }

.drawer-code {
    margin: 0; padding: 16px; overflow-x: auto;
    font-family: var(--font-mono); font-size: 12px;
    line-height: 1.6;
    background: var(--code-bg); border-radius: var(--radius-sm);
    white-space: pre; max-height: 400px; overflow-y: auto;
    color: var(--code-text);
}

/* Drawer slide-in transition */
.drawer-enter-active, .drawer-leave-active { transition: opacity 0.2s; }
.drawer-enter-active .drawer, .drawer-leave-active .drawer { transition: transform 0.25s ease; }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer, .drawer-leave-to .drawer { transform: translateX(100%); }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .kpi-grid { grid-template-columns: repeat(2, 1fr); }
    .page-header { flex-wrap: wrap; }
}

@media (max-width: 600px) {
    .kpi-grid { grid-template-columns: 1fr; }
    .question-header { flex-wrap: wrap; gap: 6px; }
    .flag-card-top { flex-wrap: wrap; gap: 8px; }
    .flag-card-right { flex-wrap: wrap; }
    .drawer-metrics { gap: 8px; }
    .metric-chip { min-width: 72px; }
}
</style>
