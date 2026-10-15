<template>
    <div class="results-page">
        <h1>My results</h1>

        <div v-if="loading" class="loading">Loading...</div>

        <template v-else>
            <!-- Personal KPIs -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Score</div>
                    <div class="kpi-value">
                        {{ myStats?.score ?? 0 }}
                        <span v-if="myStats?.score_available" class="kpi-sub">of {{ myStats.score_available }} points</span>
                    </div>
                    <div class="kpi-note">10 per easy, 20 per medium and 30 per hard question solved</div>
                    <div v-if="myStats?.points_withheld" class="kpi-note withheld">{{ plural(myStats.points_withheld, 'point') }} withheld: plagiarism confirmed by your trainer</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Section rank</div>
                    <div class="kpi-value">
                        {{ myStats?.rank ? `#${myStats.rank}` : '—' }}
                        <span class="kpi-sub">of {{ myStats?.cohort_size }}</span>
                    </div>
                    <div v-if="myStats && myStats.cohort_size > 1" class="kpi-note">
                        Ahead of {{ myStats.ahead_of }} of {{ myStats.cohort_size - 1 }} classmates in {{ myStats.cohort || 'your section' }}, by score
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label" :title="METRIC_HELP.acceptedStudent">{{ METRIC_LABEL.accepted }}</div>
                    <div class="kpi-value" :class="rateColor(myStats?.accepted_rate ?? null)">{{ formatPct(myStats?.accepted_rate ?? null) }}</div>
                    <div v-if="myStats" class="kpi-note">{{ myStats.exams_passed }} of {{ plural(myStats.exams_taken, 'exam') }} passed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cohort rank</div>
                    <div class="kpi-value">
                        {{ myStats?.overall_rank ? `#${myStats.overall_rank}` : '—' }}
                        <span class="kpi-sub">of {{ myStats?.overall_size }}</span>
                    </div>
                    <div class="kpi-note">Across all sections, by score</div>
                </div>
            </div>

            <!-- Weekly recommendation (written every Monday from all exams together) -->
            <AiGlow class="rec" title="This week's recommendation">
                <template v-if="rec" #aside>
                    <time class="rec-dates" :datetime="rec.created_at">
                        Updated {{ shortDay(rec.created_at) }} · next {{ shortDay(rec.next_update) }}
                    </time>
                </template>
                <template v-if="rec">
                    <p class="rec-headline">{{ rec.headline }}</p>
                    <div class="rec-grid">
                        <div v-for="card in rec.cards" :key="card.kind" class="rec-card">
                            <span :class="['rec-tag', card.kind]">{{ REC_LABEL[card.kind] ?? card.kind }}</span>
                            <p>{{ card.text }}</p>
                            <span v-if="card.evidence" class="rec-ev">{{ card.evidence }}</span>
                        </div>
                    </div>
                </template>
                <p v-else class="rec-empty">Your first weekly recommendation arrives the Monday after your first exam is graded.</p>
            </AiGlow>

            <!-- Questions solved by difficulty -->
            <section v-if="myStats" class="diff-section" aria-labelledby="diff-title">
                <h2 id="diff-title" class="section-heading">Questions solved by difficulty</h2>
                <div class="diff-row">
                    <div v-for="d in difficultyRows" :key="d.key" class="diff-card">
                        <span class="diff-label">{{ d.label }}</span>
                        <span class="diff-count">{{ d.solved }} <span class="diff-of">of {{ d.available }}</span></span>
                        <span class="diff-pts">{{ plural(d.points, 'point') }}, {{ d.each }} each<template v-if="d.withheld"> · <span class="withheld">{{ d.withheld }} withheld</span></template></span>
                    </div>
                </div>
            </section>

            <!-- Exams → questions → attempts -->
            <div class="section-title">
                <h2 class="section-heading">Exams</h2>
                <span v-if="exams.length">{{ plural(exams.length, 'exam') }} · newest first</span>
            </div>
            <div v-if="exams.length === 0" class="empty">No submissions yet.</div>

            <article v-for="exam in exams" :id="`exam-${exam.exam_id}`" :key="exam.exam_id" class="exam" :class="{ open: openExam[exam.exam_id] }">
                <button
                    type="button"
                    class="exam-head"
                    :aria-expanded="!!openExam[exam.exam_id]"
                    @click="openExam[exam.exam_id] = !openExam[exam.exam_id]"
                >
                    <div class="exam-title">
                        <span class="eyebrow">Exam</span>
                        <span class="exam-name">{{ exam.exam_title }}</span>
                        <small>
                            {{ formatDate(exam.exam_date) }} · {{ plural(exam.questions.length, 'question') }}
                            <template v-if="!openExam[exam.exam_id] && exam.passed !== undefined">
                                · {{ exam.questions_solved }} / {{ exam.questions_total }} solved
                                · {{ exam.passed ? 'Passed' : 'Not passed' }}<template v-if="!exam.passed && exam.questions_voided"> · plagiarism confirmed</template>
                            </template>
                        </small>
                    </div>
                    <span v-if="exam.integrity" :class="['pill', REVIEW_PILL[exam.integrity.outcome]]">Trainer review</span>
                    <span v-if="exam.rank" class="pill rank">Section rank #{{ exam.rank }} of {{ exam.cohort_size }}</span>
                    <!-- ranked among the section's students who took it; no points on it (incl. withheld) is not ranked -->
                    <span v-else-if="exam.cohort_size" class="pill rank" title="No points on this exam, so not ranked">Not ranked</span>
                    <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                </button>

                <div v-if="openExam[exam.exam_id]" class="exam-body">
                    <!-- one block per exam: the outcome, the trainer's note once, then the one-round appeal -->
                    <section
                        v-if="exam.integrity"
                        :id="`review-${exam.exam_id}`"
                        class="review-box"
                        :class="REVIEW_TONE[exam.integrity.outcome]"
                        tabindex="-1"
                        :aria-labelledby="`review-h-${exam.exam_id}`"
                    >
                        <div class="review-head">Trainer review · academic integrity</div>
                        <!-- withheld points are already out of the score and rank above -->
                        <p :id="`review-h-${exam.exam_id}`" class="review-headline">{{ outcomeHeadline(exam.integrity) }}</p>
                        <p v-for="n in decisionNotes(exam.exam_id)" :key="n" class="review-note">“{{ n }}”</p>

                        <div v-for="a in appealOf(exam.exam_id)" :key="a.id" class="appeal-area">
                            <p :class="['appeal-status', a.status]">{{ STUDENT_APPEAL_STATUS[a.status] }}</p>
                            <p class="appeal-text"><span class="appeal-label">Your response</span> “{{ a.student_note }}”</p>
                            <p v-if="a.status !== 'open' && a.resolution_note" class="appeal-text">
                                <span class="appeal-label">Your trainer replied</span> “{{ a.resolution_note }}”
                            </p>
                        </div>
                        <div v-if="!appealByExam[exam.exam_id] && exam.integrity.can_appeal" class="appeal-area">
                            <button v-if="!drafts[exam.exam_id]" type="button" class="appeal-btn" @click="startAppeal(exam.exam_id)">Respond to this decision</button>
                            <div v-else class="appeal-form">
                                <label :for="`appeal-text-${exam.exam_id}`" class="appeal-label">Your response to your trainer</label>
                                <p :id="`appeal-hint-${exam.exam_id}`" class="appeal-hint">You can respond once per exam. Your trainer reads it alongside the evidence and replies.</p>
                                <textarea
                                    :id="`appeal-text-${exam.exam_id}`"
                                    v-model="drafts[exam.exam_id]!.text"
                                    class="appeal-input"
                                    rows="4"
                                    :maxlength="APPEAL_NOTE_MAX"
                                    :aria-describedby="`appeal-hint-${exam.exam_id} appeal-count-${exam.exam_id}${drafts[exam.exam_id]!.error ? ` appeal-error-${exam.exam_id}` : ''}`"
                                    :aria-invalid="!!drafts[exam.exam_id]!.error"
                                ></textarea>
                                <div class="appeal-actions">
                                    <span :id="`appeal-count-${exam.exam_id}`" class="appeal-count">{{ drafts[exam.exam_id]!.text.length }} / {{ APPEAL_NOTE_MAX }}</span>
                                    <button type="button" class="appeal-cancel" :disabled="drafts[exam.exam_id]!.sending" @click="delete drafts[exam.exam_id]">Cancel</button>
                                    <button type="button" class="appeal-submit" :disabled="drafts[exam.exam_id]!.sending" @click="submitAppeal(exam)">
                                        {{ drafts[exam.exam_id]!.sending ? 'Sending…' : 'Submit' }}
                                    </button>
                                </div>
                                <p v-if="drafts[exam.exam_id]!.error" :id="`appeal-error-${exam.exam_id}`" class="appeal-error" role="alert">{{ drafts[exam.exam_id]!.error }}</p>
                            </div>
                        </div>

                        <details v-if="reviewsByExam[exam.exam_id]?.length || exam.points_withheld" class="review-details">
                            <summary>Details</summary>
                            <p v-for="q in exam.questions.filter(x => x.points_withheld)" :key="`withheld-${q.question_id}`" class="review-meta">
                                <b>{{ q.title }}</b> · −{{ q.points_withheld }} points withheld
                            </p>
                            <p v-for="r in reviewsByExam[exam.exam_id] ?? []" :key="`${r.kind}-${r.submission_id}`" class="review-meta">
                                <b>{{ r.question_title }}</b> · attempt {{ r.attempt_number }} · {{ reviewLabel(r) }}
                            </p>
                        </details>
                    </section>
                    <div v-if="exam.passed !== undefined" class="stats">
                        <!-- a question voided for confirmed plagiarism is not solved: it can fail the exam -->
                        <div>
                            <b>{{ exam.questions_solved }} / {{ exam.questions_total }}</b><small>Questions solved</small>
                            <span v-if="exam.questions_voided" class="stat-note withheld" :title="NOT_COUNTED_HELP">{{ notCountedNote(exam.questions_voided) }}</span>
                        </div>
                        <div><b>{{ exam.points }}</b><small>Points<template v-if="exam.points_withheld">, <span class="withheld">{{ exam.points_withheld }} withheld</span></template></small></div>
                        <div>
                            <b>{{ exam.passed ? 'Passed' : 'Not passed' }}</b><small :title="METRIC_HELP.passed">Result</small>
                            <span v-if="exam.questions_voided" class="stat-note withheld" :title="NOT_COUNTED_HELP">
                                {{ exam.passed ? `${questionsNotCounted(exam.questions_voided)}: plagiarism confirmed` : 'Plagiarism confirmed by your trainer' }}
                            </span>
                        </div>
                        <div><b>{{ exam.attempts }}</b><small>Attempts</small></div>
                    </div>

                    <AiGlow v-if="exam.passed !== undefined" title="Exam summary">
                        <p v-if="!exam.summary_ready" class="ai-muted">Your summary is available after you submit the exam.</p>
                        <p v-else-if="examSummaries[exam.exam_id]?.loading" class="ai-muted">Writing your summary…</p>
                        <p v-else-if="examSummaries[exam.exam_id]?.text" class="ai-text">{{ examSummaries[exam.exam_id].text }}</p>
                        <p v-else class="ai-muted">Summary unavailable.</p>
                    </AiGlow>

                    <div class="qs-label">Questions in this exam · {{ exam.questions.length }}</div>
                    <div class="qlist">
                        <div v-for="q in exam.questions" :key="q.question_id" class="q" :class="{ open: openQuestion[q.question_id] }">
                            <button
                                type="button"
                                class="q-row"
                                :aria-expanded="!!openQuestion[q.question_id]"
                                @click="openQuestion[q.question_id] = !openQuestion[q.question_id]"
                            >
                                <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                                <span class="q-name">{{ q.title }}</span>
                                <span v-if="q.difficulty" class="diffchip">{{ humanize(q.difficulty) }}</span>
                                <span class="meta">{{ plural(q.attempts, 'attempt') }}</span>
                                <span :class="['pill', q.voided ? 'fail' : QUESTION_PILL[q.status]]" :title="q.voided ? NOT_COUNTED_HELP : undefined">{{ questionStatus(q) }}</span>
                                <span v-if="q.points_withheld" class="pill fail">Points withheld · −{{ q.points_withheld }}</span>
                            </button>

                            <div v-if="openQuestion[q.question_id]" class="q-body">
                                <p v-if="attemptsByQuestion[q.question_id]?.[0]?.question_description" class="question-desc">
                                    {{ attemptsByQuestion[q.question_id][0].question_description }}
                                </p>
                                <p v-if="!attemptsByQuestion[q.question_id]?.length" class="loading-inline">No attempts yet.</p>

                                <div v-for="sub in attemptsByQuestion[q.question_id]" :key="sub.id" class="att" :class="{ open: expanded[sub.id] }">
                                    <button
                                        type="button"
                                        class="att-row"
                                        :aria-expanded="!!expanded[sub.id]"
                                        @click="toggleExpand(sub.id)"
                                    >
                                        <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                                        <span class="att-n">Attempt {{ sub.attempt_number }}</span>
                                        <span class="meta">
                                            {{ LANGUAGE_LABEL[sub.language] ?? sub.language }}
                                            <template v-if="sub.execution_time_ms"> · {{ formatMs(sub.execution_time_ms) }}</template>
                                            · {{ formatDateTime(sub.submitted_at) }}
                                        </span>
                                        <span :class="['pill', 'att-pill', ATTEMPT_PILL[sub.status] ?? 'idle']">{{ attemptStatus(sub) }}</span>
                                    </button>

                                    <div v-if="expanded[sub.id]" class="att-body">
                                        <h4 class="att-h">Tests</h4>
                                        <div v-if="!results[sub.id]" class="loading-inline">Loading...</div>
                                        <div v-else-if="results[sub.id].length === 0" class="loading-inline">No test results.</div>
                                        <div v-else class="tests">
                                            <table>
                                                <thead>
                                                    <tr><th>Test</th><th>Input</th><th>Expected</th><th>Your output</th><th>Time</th><th>Result</th></tr>
                                                </thead>
                                                <tbody>
                                                    <tr v-for="(r, i) in results[sub.id]" :key="r.id">
                                                        <td>{{ i + 1 }}</td>
                                                        <td :class="r.is_hidden ? 'hidden-cell' : 'mono'">{{ r.is_hidden ? 'Hidden' : r.test_case_input }}</td>
                                                        <td :class="r.is_hidden ? 'hidden-cell' : 'mono'">{{ r.is_hidden ? 'Hidden' : r.test_case_expected }}</td>
                                                        <td class="mono">
                                                            {{ r.actual_output || '—' }}
                                                            <span v-if="r.error_message" class="err">{{ r.error_message }}</span>
                                                        </td>
                                                        <td class="mono">{{ r.execution_time_ms != null ? formatMs(r.execution_time_ms) : '—' }}</td>
                                                        <td><span :class="['pill', r.passed ? 'pass' : 'fail']">{{ r.passed ? 'Pass' : 'Fail' }}</span></td>
                                                    </tr>
                                                </tbody>
                                            </table>
                                        </div>

                                        <h4 class="att-h">Your code</h4>
                                        <pre class="code-block">{{ sub.code }}</pre>

                                        <div v-if="!aiData[sub.id]?.loaded" class="loading-inline">Loading review...</div>
                                        <template v-else>
                                            <AiGlow v-if="aiData[sub.id].rubric" title="Rubric review">
                                                <template #aside>
                                                    <span class="ai-fb-total" :class="scoreClass(aiData[sub.id].rubric.total_score, 8)">{{ aiData[sub.id].rubric.total_score }} / 8</span>
                                                    <span class="meta rubric-note">The tests above are the grade</span>
                                                </template>
                                                <div v-for="dim in rubricDims(aiData[sub.id].rubric)" :key="dim.label" class="ai-fb-dim">
                                                    <div class="ai-fb-dim-top">
                                                        <span>{{ dim.label }}</span>
                                                        <span :class="scoreClass(dim.score, 2)">{{ dim.score }}/2</span>
                                                    </div>
                                                    <div class="ai-fb-bar"><div class="ai-fb-bar-fill" :class="scoreClass(dim.score, 2)" :style="{ width: (dim.score / 2 * 100) + '%' }"></div></div>
                                                    <p class="ai-fb-note">{{ dim.note }}</p>
                                                </div>
                                                <p class="ai-fb-overall">{{ aiData[sub.id].rubric.overall_feedback }}</p>
                                            </AiGlow>
                                            <AiGlow v-if="aiData[sub.id].hint" title="Hint" compact>
                                                <p class="ai-text">{{ aiData[sub.id].hint }}</p>
                                            </AiGlow>
                                            <div v-if="!aiData[sub.id].rubric && !aiData[sub.id].hint" class="loading-inline">No rubric review for this attempt.</div>
                                        </template>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </article>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import AiGlow from '../components/AiGlow.vue'
import { APPEAL_NOTE_MAX, STUDENT_APPEAL_STATUS, outcomeHeadline, type ExamIntegrity, type IntegrityOutcome, type MyAppeal } from '../utils/appeals'
import { markIntegritySeen } from '../utils/attention'
import { formatDate, formatDateTime, formatPct, formatMs, plural, humanize, submissionStatusLabel } from '../utils/format'
import { METRIC_HELP, METRIC_LABEL, NOT_COUNTED_HELP, notCountedNote, questionsNotCounted } from '../utils/metrics'

interface Submission {
    id: number
    exam: number
    exam_title: string
    question: number
    question_title: string
    question_description: string
    attempt_number: number
    status: string
    language: string
    code: string
    execution_time_ms: number | null
    submitted_at: string
    tests_passed: number | null
    tests_total: number | null
}

interface TestResult {
    id: number
    // null for a hidden test: its input and expected output never reach the student
    test_case_input: string | null
    test_case_expected: string | null
    is_hidden?: boolean
    passed: boolean
    actual_output: string
    execution_time_ms: number | null
    error_message: string
}

interface MyStats {
    score: number
    cohort: string          // the student's section, e.g. "Section A"
    rank: number | null     // within the section
    cohort_size: number
    overall_rank: number | null
    overall_size: number
    total_submissions: number
    exams_passed: number
    accepted_rate: number | null   // shown as "Success rate": exams passed / exams taken
    exams_taken: number
    score_available: number
    points_withheld?: number   // lost to confirmed plagiarism, already out of the score and ranks
    ahead_of: number
    activity_calendar: Record<string, number>
    difficulty_progress: Record<'easy' | 'medium' | 'hard', { solved: number; available: number; points: number; withheld?: number }>
}

// One question of an exam, attempted or not (from /leaderboard/me/exams/)
type QuestionState = 'passed' | 'failed' | 'not_attempted'
interface ExamQuestion {
    question_id: number
    title: string
    difficulty: string
    attempts: number
    passed_on: number | null
    status: QuestionState
    points_withheld?: number   // solved, but the points were withheld for confirmed plagiarism
    voided?: boolean           // tests passed, but not counted as solved: plagiarism confirmed
}

// Per-exam metrics, cohort rank and question list. The stats fields are
// undefined in the fallback built from submissions when that endpoint fails.
interface ExamStat {
    exam_id: number
    exam_title: string
    exam_date: string | null
    questions_total?: number
    questions_solved?: number   // counted: questions voided for confirmed plagiarism are left out
    questions_voided?: number   // solved, but not counted: plagiarism confirmed
    points?: number
    points_withheld?: number
    attempts?: number
    passed?: boolean   // solved (counted) at least half of the questions: what the success rate counts
    rank?: number | null      // null: no points on this exam, not ranked
    cohort_size?: number      // the section's students who took this exam
    summary_ready?: boolean   // results are final (exam ended or submitted): the AI summary can be written
    integrity?: ExamIntegrity | null   // the trainer's plagiarism decision on this exam, if any
    questions: ExamQuestion[]
}

interface IntegrityReview {
    kind: 'similarity' | 'behaviour'
    exam_id: number
    question_id: number
    question_title: string
    submission_id: number
    attempt_number: number
    review_status: 'confirmed' | 'dismissed'
    review_note: string
}

interface RecCard { kind: string; text: string; evidence: string }
interface WeeklyRec { headline: string; cards: RecCard[]; week_start: string; next_update: string; created_at: string }

const REC_LABEL: Record<string, string> = { keep: 'Keep doing', work: 'Work on', next: 'Next step' }
const QUESTION_PILL: Record<QuestionState, string> = { passed: 'pass', failed: 'fail', not_attempted: 'idle' }
const ATTEMPT_PILL: Record<string, string> = { passed: 'pass', failed: 'fail', error: 'idle' }
const LANGUAGE_LABEL: Record<string, string> = { python: 'Python', javascript: 'JavaScript', java: 'Java', cpp: 'C++' }

const submissions = ref<Submission[]>([])
const results = ref<Record<number, TestResult[]>>({})
const expanded = ref<Record<number, boolean>>({})
const openExam = ref<Record<number, boolean>>({})
const openQuestion = ref<Record<number, boolean>>({})
const loading = ref<boolean>(true)
const myStats = ref<MyStats | null>(null)
const examStats = ref<ExamStat[]>([])
const rec = ref<WeeklyRec | null>(null)
const reviews = ref<IntegrityReview[]>([])
const appeals = ref<MyAppeal[]>([])
const route = useRoute()

// Trainer integrity reviews grouped by exam (only exams that have one get a key)
const reviewsByExam = computed(() => {
    const map: Record<number, IntegrityReview[]> = {}
    for (const r of reviews.value) (map[r.exam_id] ??= []).push(r)
    return map
})

// The student's appeal on each exam (at most one per exam)
const appealByExam = computed(() => {
    const map: Record<number, MyAppeal> = {}
    for (const a of appeals.value) if (a.exam_id && !map[a.exam_id]) map[a.exam_id] = a
    return map
})

// [the appeal] or []: lets the template name it without repeating the lookup
function appealOf(examId: number): MyAppeal[] {
    const a = appealByExam.value[examId]
    return a ? [a] : []
}

const REVIEW_TONE: Record<IntegrityOutcome, string> = { withheld: 'confirmed', confirmed: 'confirmed', overturned: 'restored', dismissed: '' }
const REVIEW_PILL: Record<IntegrityOutcome, string> = { withheld: 'fail', confirmed: 'fail', overturned: 'pass', dismissed: 'rank' }

/** The trainer's note on the decision, each once. With an appeal, the note it answered: an
 *  overturn rewrites the flags' notes with the ruling, which shows as the reply instead. */
function decisionNotes(examId: number): string[] {
    const appeal = appealByExam.value[examId]
    if (appeal) return appeal.decision_note ? [appeal.decision_note] : []
    return [...new Set((reviewsByExam.value[examId] ?? []).map(r => r.review_note.trim()).filter(Boolean))]
}

// One-round appeal: a draft per exam while the student writes it
const drafts = ref<Record<number, { text: string; sending: boolean; error: string }>>({})
function startAppeal(examId: number): void {
    drafts.value[examId] = { text: '', sending: false, error: '' }
    nextTick(() => document.getElementById(`appeal-text-${examId}`)?.focus())
}
async function submitAppeal(exam: ExamStat): Promise<void> {
    const draft = drafts.value[exam.exam_id]
    if (!draft || draft.sending) return
    const text = draft.text.trim()
    if (!text) {
        draft.error = 'Write your response before sending it.'
        return
    }
    draft.sending = true
    draft.error = ''
    try {
        const res = await api.post('/support/disputes/', { exam_id: exam.exam_id, student_note: text })
        appeals.value = [res.data as MyAppeal, ...appeals.value]
        if (exam.integrity) exam.integrity = { ...exam.integrity, appeal: 'open', can_appeal: false }
        delete drafts.value[exam.exam_id]
    } catch (e: any) {
        draft.error = e?.response?.data?.error ?? "Couldn't send your response. Try again."
        draft.sending = false
    }
}

function reviewLabel(r: IntegrityReview): string {
    if (r.review_status === 'dismissed') return 'Reviewed, no action taken'
    return r.kind === 'similarity'
        ? 'Your code closely matched another student\'s submission'
        : 'Flagged for how this answer was written'
}

// "Easy 3 of 5, 30 points, 10 each" rows for the difficulty section
const DIFFICULTY_ROWS = [
    { key: 'easy', label: 'Easy', each: 10 },
    { key: 'medium', label: 'Medium', each: 20 },
    { key: 'hard', label: 'Hard', each: 30 },
] as const
const difficultyRows = computed(() => DIFFICULTY_ROWS.map(d => ({
    ...d,
    ...(myStats.value?.difficulty_progress?.[d.key] ?? { solved: 0, available: 0, points: 0, withheld: 0 }),
})))

// Attempts of each question, oldest first
const attemptsByQuestion = computed(() => {
    const map: Record<number, Submission[]> = {}
    for (const sub of submissions.value) (map[sub.question] ??= []).push(sub)
    for (const list of Object.values(map)) list.sort((a, b) => a.attempt_number - b.attempt_number)
    return map
})

// Exams from the stats endpoint; if it failed, rebuild a bare list from submissions
// so a stats failure never hides the history.
const exams = computed<ExamStat[]>(() => {
    if (examStats.value.length) return examStats.value
    const byExam: Record<number, ExamStat> = {}
    for (const sub of submissions.value) {
        const exam = (byExam[sub.exam] ??= { exam_id: sub.exam, exam_title: sub.exam_title, exam_date: sub.submitted_at, questions: [] })
        if (sub.submitted_at > (exam.exam_date ?? '')) exam.exam_date = sub.submitted_at
        if (exam.questions.some(q => q.question_id === sub.question)) continue
        const attempts = attemptsByQuestion.value[sub.question] ?? []
        const passed = attempts.find(a => a.status === 'passed')
        exam.questions.push({
            question_id: sub.question, title: sub.question_title, difficulty: '',
            attempts: attempts.filter(a => a.status !== 'error').length,   // 'error' attempts are refunded
            passed_on: passed?.attempt_number ?? null,
            status: passed ? 'passed' : 'failed',
        })
    }
    return Object.values(byExam).sort((a, b) => (b.exam_date ?? '').localeCompare(a.exam_date ?? ''))
})

function questionStatus(q: ExamQuestion): string {
    if (q.status === 'passed' && q.voided) return `Tests passed on attempt ${q.passed_on} · Not counted: plagiarism`
    if (q.status === 'passed') return `Passed on attempt ${q.passed_on}`
    if (q.status === 'failed') return `Failed · ${plural(q.attempts, 'attempt')}`
    return 'Not attempted'
}

function attemptStatus(sub: Submission): string {
    const label = submissionStatusLabel(sub.status)
    return sub.tests_total ? `${label} · ${sub.tests_passed ?? 0} of ${sub.tests_total} tests` : label
}

/** "Mon, 12 Oct". Bare dates ("2026-10-12") are read as local days, not UTC midnight. */
function shortDay(value: string): string {
    const d = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T00:00:00` : value)
    if (Number.isNaN(d.getTime())) return '—'
    const weekday = d.toLocaleDateString('en-GB', { weekday: 'short' })
    return `${weekday}, ${d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`
}

// Rubric review + hint per attempt, lazy-loaded when the attempt opens
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

// Every page of the student's submissions (the list endpoint pages at 20)
async function loadAllSubmissions(): Promise<Submission[]> {
    const all: Submission[] = []
    let page = 1
    for (;;) {
        const res = await api.get('/submissions/', { params: { page } })
        const data = res.data
        all.push(...(data.results ?? data))
        if (!data.next) return all
        page++
    }
}

onMounted(async () => {
    try {
        // Submissions drive the history — load them first and independently so a
        // stats failure can never blank out the history list.
        submissions.value = await loadAllSubmissions()

        // Stats, per-exam metrics and the weekly recommendation are best-effort.
        const [statsRes, examRes, recRes, reviewRes, appealRes] = await Promise.all([
            api.get('/leaderboard/me/').catch(() => null),
            api.get('/leaderboard/me/exams/').catch(() => null),
            api.get('/ai/recommendation/me/').catch(() => null),
            api.get('/plagiarism/mine/').catch(() => null),
            api.get('/support/disputes/mine/').catch(() => null),
        ])
        reviews.value = Array.isArray(reviewRes?.data) ? reviewRes.data : []
        appeals.value = Array.isArray(appealRes?.data) ? appealRes.data : []
        myStats.value = statsRes?.data ?? null
        examStats.value = Array.isArray(examRes?.data) ? examRes.data : []
        rec.value = recRes?.status === 200 && recRes.data?.headline ? recRes.data : null

        // Newest exam open, the rest collapsed to their one-line summary; a link to one exam
        // (?exam=<id>, from Home or Disputes) opens that one at its review instead.
        const linked = Number(route.query.exam)
        const target = exams.value.find(e => e.exam_id === linked) ?? exams.value[0]
        if (target) openExam.value[target.exam_id] = true
        if (linked && target?.exam_id === linked) focusReview(linked)
        // only final results get a summary: a live exam the student hasn't submitted would freeze mid-exam
        examStats.value.filter(s => s.summary_ready).forEach(s => loadExamSummary(s.exam_id))
    } finally {
        loading.value = false
    }
    markIntegritySeen()   // the decisions here are seen: the sidebar badge and Home banner clear
})

async function focusReview(examId: number): Promise<void> {
    await nextTick()   // wait for the list to render
    await nextTick()
    const el = document.getElementById(`review-${examId}`) ?? document.getElementById(`exam-${examId}`)
    el?.scrollIntoView({ block: 'start' })
    el?.focus({ preventScroll: true })
}

async function loadResults(submissionId: number): Promise<void> {
    if (results.value[submissionId]) return  // already loaded
    try {
        const res = await api.get(`/results/${submissionId}/`)
        results.value[submissionId] = res.data
    } catch {
        results.value[submissionId] = []
    }
}

function toggleExpand(submissionId: number): void {
    expanded.value[submissionId] = !expanded.value[submissionId]
    if (expanded.value[submissionId]) {
        loadResults(submissionId)  // lazy — only when the attempt is opened
        loadAi(submissionId)
    }
}

function rateColor(rate: number | null): string {
    if (rate === null || rate === undefined) return ''
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'bad'
}
</script>

<style scoped>
.results-page { max-width: 900px; }
h1 { margin-bottom: 24px; }

.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 16px; margin-bottom: 20px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.kpi-label { font-size: 11px; color: var(--text-dim); font-weight: 600; margin-bottom: 8px; }
.kpi-value { font-size: 28px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.kpi-value.good { color: var(--green-ink); }
.kpi-value.mid { color: var(--amber-ink); }
.kpi-value.bad { color: var(--red-ink); }
.kpi-sub { font-size: 13px; color: var(--text-dim); font-weight: 400; margin-left: 4px; }
.kpi-note { margin-top: 6px; font-size: 13px; line-height: 1.4; color: var(--text-muted); }

/* Weekly recommendation */
.rec { margin-bottom: 24px; }
.rec-dates { margin-left: auto; font-size: 12px; color: var(--text-dim); white-space: nowrap; }
.rec-headline { margin: 0; font-size: 14px; line-height: 1.6; color: var(--text); max-width: 70ch; }
.rec-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }
.rec-card {
    display: grid; gap: 4px; align-content: start;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 10px 12px;
}
.rec-card p { margin: 0; font-size: 13px; line-height: 1.5; color: var(--text); }
.rec-tag { font-size: 11px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; }
.rec-tag.keep { color: var(--green-ink); }
.rec-tag.work { color: var(--red-ink); }
.rec-tag.next { color: var(--purple-ink); }
.rec-ev { font-size: 12px; color: var(--text-dim); line-height: 1.4; }
.rec-empty { margin: 0; font-size: 13px; color: var(--text-muted); }

/* Difficulty tiles */
.diff-section { margin-bottom: 20px; }
.section-heading { font-size: 18px; margin: 0 0 12px; }
.diff-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.diff-card {
    display: flex; flex-direction: column; gap: 4px;
    padding: 16px 20px; border-radius: var(--radius);
    background: var(--surface); border: 1px solid var(--border);
}
.diff-label { font-family: var(--font-display); font-weight: 600; font-size: 14px; color: var(--text-muted); }
.diff-count { font-family: var(--font-display); font-size: 26px; font-weight: 600; color: var(--text); }
.diff-of { font-size: 15px; font-weight: 400; color: var(--text-muted); }
.diff-pts { font-size: 13px; color: var(--text-muted); }

/* Exam containers */
.section-title { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
.section-title span { font-size: 13px; color: var(--text-muted); }
.exam { border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; background: var(--surface); margin-bottom: 14px; }
.exam-head, .q-row, .att-row {
    display: flex; flex-wrap: wrap; align-items: center;
    width: 100%; border: 0; font: inherit; color: inherit; text-align: left;
    cursor: pointer; transition: background 0.15s;
}
.exam-head { gap: 10px 14px; padding: 14px 18px; background: var(--surface2); }
.exam-head:hover { background: var(--surface3); }
.exam-head:focus-visible, .q-row:focus-visible, .att-row:focus-visible { outline: 2px solid var(--red); outline-offset: -2px; }
.exam-title { display: grid; min-width: 0; flex: 1; }
.eyebrow { font-size: 11px; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; color: var(--red); }
.exam-name { font-family: var(--font-display); font-size: 17px; font-weight: 600; color: var(--text); }
.exam-title small { font-size: 12px; color: var(--text-dim); }
.pill { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: var(--radius-pill); white-space: nowrap; }
.pill.rank { background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); }
.pill.pass { background: var(--green-dim); color: var(--green-ink); }
.pill.fail { background: var(--red-dim); color: var(--red-ink); }
.pill.idle { background: var(--surface2); color: var(--text-dim); }
.chev { width: 16px; height: 16px; flex: none; color: var(--text-dim); transition: transform 0.2s; }
.exam.open > .exam-head .chev, .q.open > .q-row .chev, .att.open > .att-row .chev { transform: rotate(90deg); }
@media (prefers-reduced-motion: reduce) { .chev { transition: none; } }

.exam-body { padding: 14px 18px 18px; display: grid; gap: 14px; }
.review-box { border: 1px solid var(--border); border-left: 3px solid var(--text-dim); border-radius: var(--radius-sm); padding: 10px 14px; display: grid; gap: 8px; }
.review-box.confirmed { border-left-color: var(--red); background: var(--red-dim); }
.review-head { font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.review-box.confirmed .review-head { color: var(--red-ink); }
.review-box.restored { border-left-color: var(--green); background: var(--green-dim); }
.review-box.restored .review-head { color: var(--green-ink); }
.review-box:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }
.review-headline { margin: 0; font-family: var(--font-display); font-size: 16px; font-weight: 600; color: var(--text); }
.review-box.confirmed .review-headline { color: var(--red-ink); }
.review-box.restored .review-headline { color: var(--green-ink); }
.review-meta { margin: 0; font-size: 13px; color: var(--text-muted); }
.review-meta b { color: var(--text); }
.review-note { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }

/* the one-round appeal under the decision */
.appeal-area { display: grid; gap: 6px; padding-top: 8px; border-top: 1px solid var(--border); }
.appeal-status { margin: 0; font-size: 14px; font-weight: 600; color: var(--text); }
.appeal-status.open { color: var(--amber-ink); }
.appeal-status.overturned { color: var(--green-ink); }
.appeal-text { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
.appeal-label { display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); }
.appeal-hint { margin: 0; font-size: 12px; color: var(--text-muted); }
.appeal-form { display: grid; gap: 6px; }
.appeal-input {
    width: 100%; box-sizing: border-box; min-height: 96px; padding: 10px 12px; resize: vertical;
    font: inherit; font-size: 14px; color: var(--text); background: var(--surface);
    border: 1px solid var(--border2); border-radius: var(--radius-sm);
}
.appeal-input:focus-visible { outline: 2px solid var(--red); outline-offset: 1px; }
.appeal-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.appeal-count { margin-right: auto; font-size: 12px; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.appeal-btn, .appeal-submit, .appeal-cancel {
    min-height: 44px; padding: 0 18px; border-radius: var(--radius-pill);
    font-family: var(--font-display); font-size: 14px; font-weight: 600; cursor: pointer;
}
.appeal-btn { justify-self: start; background: var(--surface); border: 1px solid var(--border2); color: var(--text); }
.appeal-btn:hover { background: var(--surface2); }
.appeal-submit { background: var(--accent); border: 1px solid var(--accent); color: var(--accent-ink); }
.appeal-cancel { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.appeal-submit:disabled, .appeal-cancel:disabled { opacity: 0.6; cursor: not-allowed; }
.appeal-error { margin: 0; font-size: 13px; color: var(--red-ink); }
.review-details { font-size: 13px; color: var(--text-muted); }
.review-details summary { display: flex; align-items: center; min-height: 44px; cursor: pointer; font-weight: 600; width: fit-content; }
.review-details[open] { display: grid; gap: 4px; }
.withheld, .kpi-note.withheld { color: var(--red-ink); font-weight: 600; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.stats div { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 12px; }
.stats b { display: block; font-family: var(--font-display); font-size: 18px; font-variant-numeric: tabular-nums; color: var(--text); }
.stats small { font-size: 12px; color: var(--text-dim); }
.stats .stat-note { display: block; margin-top: 2px; font-size: 12px; line-height: 1.35; }

.ai-text { margin: 0; font-size: 13px; line-height: 1.65; color: var(--text); max-width: 70ch; }
.ai-muted { margin: 0; font-size: 12px; font-style: italic; color: var(--text-dim); }

/* Questions, joined to the exam by a left rail */
.qs-label { display: flex; align-items: center; gap: 8px; font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.qs-label::after { content: ""; flex: 1; height: 1px; background: var(--border); }
.qlist { display: grid; gap: 8px; padding-left: 16px; margin-left: 6px; border-left: 2px solid var(--border); }
.q { position: relative; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); }
.q::before { content: ""; position: absolute; left: -18px; top: 22px; width: 16px; height: 2px; background: var(--border); }
.q-row { gap: 8px 12px; padding: 11px 14px; background: none; border-radius: var(--radius-sm); }
.q-row:hover, .att-row:hover { background: var(--surface2); }
.q-name { flex: 1; min-width: 160px; font-size: 15px; font-weight: 600; color: var(--text); }
.diffchip { font-size: 11px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--surface2); color: var(--text-muted); }
.meta { font-size: 12px; color: var(--text-dim); }
.q-body { padding: 0 14px 14px; display: grid; gap: 8px; }
.question-desc { margin: 0 0 4px; font-size: 13px; line-height: 1.6; color: var(--text-muted); }

/* Attempts inside their question */
.att { border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); }
.att-row { gap: 8px 12px; padding: 9px 12px; font-size: 13px; background: none; border-radius: var(--radius-sm); }
.att-n { width: 74px; font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }
.att-pill { margin-left: auto; }
.att-body { padding: 4px 12px 14px; display: grid; gap: 10px; }
.att-h { margin: 0; font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-muted); }
.tests { overflow-x: auto; }
.tests table { width: 100%; min-width: 460px; border-collapse: collapse; font-size: 13px; }
.tests th, .tests td { padding: 7px 8px; text-align: left; vertical-align: top; border-bottom: 1px solid var(--border); }
.tests th { font-size: 12px; font-weight: 500; color: var(--text-dim); }
.tests td.mono { font-family: var(--font-mono); font-size: 12px; white-space: pre-wrap; word-break: break-word; }
.hidden-cell { font-style: italic; color: var(--text-dim); }
.err { display: block; margin-top: 2px; font-family: var(--font-sans); font-size: 11px; font-style: italic; color: var(--red-ink); }
.code-block {
    margin: 0; padding: 12px 14px; overflow-x: auto; white-space: pre-wrap;
    background: var(--code-bg); color: var(--code-text);
    border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 12px; line-height: 1.6;
}
.loading-inline { font-size: 13px; color: var(--text-dim); }
.loading, .empty { color: var(--text-muted); }

/* Rubric review inside its glow */
.ai-fb-total { font-size: 14px; font-weight: 800; padding: 2px 10px; border-radius: var(--radius-sm); font-variant-numeric: tabular-nums; }
.ai-fb-total.good { background: var(--green-dim); color: var(--green-ink); }
.ai-fb-total.mid  { background: var(--yellow-dim); color: var(--amber-ink); }
.ai-fb-total.low  { background: var(--red-dim); color: var(--red-ink); }
.rubric-note { margin-left: auto; }
.ai-fb-dim { margin-bottom: 10px; }
.ai-fb-dim-top { display: flex; justify-content: space-between; align-items: center; font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.ai-fb-dim-top span:last-child { font-weight: 700; font-variant-numeric: tabular-nums; }
.ai-fb-dim-top .good { color: var(--green-ink); }
.ai-fb-dim-top .mid  { color: var(--amber-ink); }
.ai-fb-dim-top .low  { color: var(--red-ink); }
.ai-fb-bar { height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.ai-fb-bar-fill { height: 100%; border-radius: 3px; transition: width 0.3s; }
.ai-fb-bar-fill.good { background: var(--green); }
.ai-fb-bar-fill.mid  { background: var(--yellow); }
.ai-fb-bar-fill.low  { background: var(--red); }
.ai-fb-note { font-size: 11px; color: var(--text-muted); line-height: 1.5; margin: 4px 0 0; }
.ai-fb-overall {
    font-size: 12px; color: var(--text); line-height: 1.6;
    background: var(--surface2); border-radius: var(--radius-sm); padding: 9px 11px; margin: 12px 0 0;
}

@media (max-width: 720px) {
    .rec-grid { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 560px) {
    .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .att-pill { margin-left: 0; }
}
</style>
