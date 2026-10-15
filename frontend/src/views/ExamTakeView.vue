<template>
    <div class="take-container">
        <header class="top-bar">
            <span class="exam-title">{{ examTitle || 'Loading…' }}</span>
            <nav class="q-nav" aria-label="Questions">
                <button
                    v-for="(q, i) in questions"
                    :key="q.id"
                    class="q-tab"
                    :class="{ active: currentIndex === i }"
                    :aria-current="currentIndex === i ? 'page' : undefined"
                    :aria-label="acceptedQuestions[q.id] ? `Q${i + 1}, accepted` : undefined"
                    @click="switchQuestion(i)"
                >
                    Q{{ i + 1 }}
                    <span v-if="acceptedQuestions[q.id]" class="q-tab-dot"></span>
                </button>
            </nav>
            <div class="top-bar-spacer"></div>
            <span class="attempts-text">{{ attemptsText }}</span>
            <button type="button" class="end-btn" @click="confirmEnd = true">Submit exam</button>
            <span
                class="timer"
                :class="{ warning: timeLeft <= 300 }"
                aria-label="Time left"
            >{{ formatTime(timeLeft) }}</span>
        </header>

        <!-- Submit exam: in-page confirmation (a browser confirm() would block the page) -->
        <div v-if="confirmEnd" class="end-overlay" @click.self="confirmEnd = false">
            <div class="end-dialog" role="dialog" aria-modal="true" aria-labelledby="end-title">
                <h2 id="end-title" class="end-title">Submit the exam?</h2>
                <p class="end-text">This finishes your exam: you won't be able to submit any more code. Your results and reviews stay in My results.</p>
                <p v-if="isRunning" class="end-text">An attempt is still being graded; it will still count.</p>
                <p v-if="endError" class="submit-error" role="alert">{{ endError }}</p>
                <div class="end-actions">
                    <button type="button" class="end-cancel" @click="confirmEnd = false">Keep working</button>
                    <button type="button" class="end-confirm" :disabled="ending" @click="endExam">{{ ending ? 'Submitting…' : 'Submit exam' }}</button>
                </div>
            </div>
        </div>

        <div class="main">
            <!-- Problem Panel -->
            <section class="question-panel" aria-label="Problem">
                <div v-if="currentQuestion" class="q-head">
                    <h1 class="q-title">{{ currentQuestion.title }}</h1>
                    <div class="q-meta">
                        <span class="q-difficulty" :class="currentQuestion.difficulty">{{ difficultyLabel }}</span>
                        <span>{{ currentQuestion.test_cases?.length || 0 }} test cases</span>
                        <span>{{ currentQuestion.points }} marks</span>
                    </div>
                </div>
                <QuestionStatement v-if="currentQuestion" :description="currentQuestion.description" :test-cases="currentQuestion.test_cases" />

            </section>

            <!-- Editor + Judge Panel -->
            <section class="editor-panel" aria-label="Solution">
                <div class="editor-header">
                    <label for="lang" class="lang-label">Language</label>
                    <select id="lang" v-model="language">
                        <option value="javascript">JavaScript</option>
                        <option value="python">Python</option>
                    </select>
                    <div class="editor-header-spacer"></div>
                    <button
                        class="submit-btn"
                        @click="submitCode"
                        :disabled="submitting || isRunning || !canSubmit"
                    >
                        {{ submitting || isRunning ? 'Grading…' : outOfAttempts ? 'No attempts left' : 'Submit solution' }}
                    </button>
                </div>

                <codemirror
                    v-model="code"
                    :extensions="editorExtensions"
                    class="editor-cm"
                    style="font-size: 14px;"
                    placeholder="Write your solution here..."
                />

            </section>

            <!-- Results column: attempts, live steps while grading, then Result | Review -->
            <aside class="results-col" aria-label="Results">
                <div v-if="questionAttempts.length" class="attempts-row">
                    <span class="attempts-label">Your attempts</span>
                    <span class="attempts-spacer"></span>
                    <button
                        v-for="a in questionAttempts" :key="a.id" type="button" class="attempt-chip"
                        :class="{ active: a.id === shownSubmissionId }"
                        :aria-pressed="a.id === shownSubmissionId"
                        :disabled="isRunning && a.id !== shownSubmissionId"
                        :aria-label="`Attempt ${a.attempt}: ${a.status === 'passed' ? 'passed' : a.status === 'failed' ? 'failed' : 'grading'}`"
                        @click="viewAttempt(a)"
                    >
                        {{ a.attempt }}
                        <span v-if="a.status === 'passed'" class="chip-mark pass" aria-hidden="true">✓</span>
                        <span v-else-if="a.status === 'failed'" class="chip-mark fail" aria-hidden="true">✕</span>
                        <span v-else class="chip-running" aria-hidden="true"></span>
                    </button>
                    <span v-if="attemptsLeft > 0" class="attempts-left">{{ attemptsLeft }} left</span>
                </div>

                <p v-if="submitError" class="submit-error" role="alert">{{ submitError }}</p>

                <!-- Before the first submit, or out of attempts with nothing to show -->
                <div v-if="!isRunning && !results.length" class="results-empty">
                    <p class="results-empty-title">{{ outOfAttempts ? 'No attempts left' : 'Ready' }}</p>
                    <p class="results-empty-text">
                        <template v-if="outOfAttempts">You have used every attempt on this question.</template>
                        <template v-else>Submit to run your code against {{ testCount }} test cases. Your result shows here, and a review of your code follows a few seconds later.</template>
                    </p>
                </div>

                <!-- While grading: each step as a checklist -->
                <template v-else-if="isRunning">
                    <div class="run-head">
                        <span class="run-title">Running your tests</span>
                        <span class="run-sub">Attempt {{ shownAttempt }}<template v-if="elapsedMs != null"> · {{ (elapsedMs / 1000).toFixed(1) }} s so far</template></span>
                    </div>
                    <ol class="steps" aria-live="polite">
                        <li v-for="st in steps" :key="st.key" class="step" :class="st.state">
                            <span class="step-mark" aria-hidden="true">{{ st.state === 'done' ? '✓' : '' }}</span>
                            <span class="step-label">
                                <svg v-if="st.key === 'feedback'" class="step-spark" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Generated by AI"><title>Generated by AI</title><path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z"/></svg>
                                {{ st.label }}
                            </span>
                            <span v-if="st.key === 'execute'" class="test-dots" :aria-label="`${testDots.length} tests`">
                                <span v-for="(d, i) in testDots" :key="i" class="test-dot" :class="d.state"></span>
                            </span>
                            <span v-else-if="st.key === 'feedback'" class="step-note">a few seconds after</span>
                            <span v-else class="step-note"></span>
                        </li>
                    </ol>
                    <p class="pipeline-note" aria-live="polite">{{ pipelineNote }}</p>
                </template>

                <!-- Graded: verdict, folded steps, Result | Review -->
                <template v-else>
                    <div class="verdict">
                        <span class="verdict-inline" :class="verdict.passed ? 'pass' : 'fail'">{{ verdict.headline }}</span>
                        <span class="verdict-sub">
                            <template v-if="shownAttempt">Attempt {{ shownAttempt }} · </template>{{ passedCount }} of {{ results.length }} passed<template v-if="runMs"> · {{ runMs }} ms</template>
                        </span>
                    </div>

                    <button type="button" class="steps-toggle" :aria-expanded="stepsOpen" @click="stepsOpen = !stepsOpen">
                        <span class="steps-check" aria-hidden="true">✓</span>
                        Graded<template v-if="gradedMs != null"> in {{ (gradedMs / 1000).toFixed(1) }} s</template>
                        <span class="attempts-spacer"></span>
                        <span class="steps-more">Steps {{ stepsOpen ? '▴' : '▾' }}</span>
                    </button>
                    <ol v-if="stepsOpen" class="steps">
                        <li v-for="st in steps" :key="st.key" class="step" :class="st.state">
                            <span class="step-mark" aria-hidden="true">{{ st.state === 'done' ? '✓' : '' }}</span>
                            <span class="step-label">{{ st.label }}</span>
                            <span v-if="st.key === 'execute'" class="test-dots">
                                <span v-for="(d, i) in testDots" :key="i" class="test-dot" :class="d.state"></span>
                            </span>
                            <span v-else class="step-note"></span>
                        </li>
                    </ol>

                    <div class="result-tabs" role="tablist" :aria-label="`Attempt ${shownAttempt ?? ''}`">
                        <button
                            id="result-tab-tests" type="button" role="tab" class="result-tab"
                            :class="{ active: resultTab === 'tests' }"
                            :aria-selected="resultTab === 'tests'" aria-controls="result-panel-tests"
                            @click="selectTab('tests')"
                        >
                            Result
                            <span class="tab-badge" :class="verdict.passed ? 'pass' : 'fail'">{{ passedCount }}/{{ results.length }}</span>
                        </button>
                        <button
                            id="result-tab-review" type="button" role="tab" class="result-tab"
                            :class="{ active: resultTab === 'review' }"
                            :aria-selected="resultTab === 'review'" aria-controls="result-panel-review"
                            @click="selectTab('review')"
                        >
                            <svg class="tab-spark" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label="Generated by AI"><title>Generated by AI</title><path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z"/></svg>
                            Review
                            <span v-if="rubric" class="tab-badge" :class="scoreClass(rubric.total_score, 8)">{{ rubric.total_score }}/8</span>
                            <span v-else-if="!rubricGaveUp" class="tab-pending">reviewing…</span>
                            <span v-if="reviewIsNew" class="new-dot" aria-label="New"></span>
                        </button>
                    </div>

                    <div v-show="resultTab === 'tests'" id="result-panel-tests" role="tabpanel" aria-labelledby="result-tab-tests" class="result-panel">
                        <div v-for="(r, i) in results" :key="r.id" class="test-card" :class="r.passed ? 'pass' : 'fail'">
                            <div class="test-card-top">
                                <b>Test {{ i + 1 }}</b>
                                <span v-if="r.is_hidden && r.passed" class="dim">Hidden</span>
                                <span class="attempts-spacer"></span>
                                <span v-if="r.passed" class="test-out">{{ r.actual_output }}</span>
                                <b :class="r.passed ? 'text-pass' : 'text-fail'">{{ r.passed ? 'Pass' : 'Fail' }}</b>
                            </div>
                            <dl v-if="!r.passed" class="test-detail">
                                <dt>Input</dt><dd :class="r.is_hidden ? 'dim' : 'mono'">{{ r.is_hidden ? 'Hidden' : r.test_case_input }}</dd>
                                <dt>Expected</dt><dd :class="r.is_hidden ? 'dim' : 'mono'">{{ r.is_hidden ? 'Hidden' : r.test_case_expected }}</dd>
                                <dt>You printed</dt><dd class="mono">{{ r.actual_output || '—' }}</dd>
                                <template v-if="r.execution_time_ms != null"><dt>Time</dt><dd>{{ r.execution_time_ms }} ms</dd></template>
                            </dl>
                            <p v-if="r.error_message" class="row-error">{{ r.error_message }}</p>
                        </div>

                        <!-- Socratic hint: failed attempts only, shown on demand -->
                        <template v-if="submissionStatus === 'failed'">
                            <AiGlow v-if="hint && hintVisible" title="Hint" compact>
                                <p class="hint-text">{{ hint }}</p>
                            </AiGlow>
                            <button v-else-if="hint" type="button" class="hint-btn" @click="hintVisible = true">
                                <svg class="tab-spark" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M12 2l2.2 6.3L20.5 10l-6.3 2.2L12 18.5l-2.2-6.3L3.5 10l6.3-1.7z"/></svg>
                                Show a hint
                            </button>
                            <p v-else-if="!hintGaveUp" class="hint-pending">A hint is on its way</p>
                        </template>
                    </div>

                    <div v-show="resultTab === 'review'" id="result-panel-review" role="tabpanel" aria-labelledby="result-tab-review" class="result-panel">
                        <p v-if="!rubric && !rubricGaveUp" class="rubric-pending">
                            <span class="pending-dot"></span>
                            Reviewing your code. This takes a few seconds.
                        </p>
                        <p v-else-if="!rubric" class="rubric-pending">No review for this attempt. The test results are the grade.</p>
                        <template v-else>
                            <AiGlow compact>
                                <p class="rubric-overall">{{ rubric.overall_feedback }}</p>
                            </AiGlow>
                            <div class="rubric-grid">
                                <div v-for="dim in rubricDimensions" :key="dim.label" class="rubric-dim">
                                    <div class="rubric-dim-top">
                                        <span class="rubric-dim-label">{{ dim.label }}</span>
                                        <span class="rubric-dim-score" :class="scoreClass(dim.score, 2)">{{ dim.score }}/2</span>
                                    </div>
                                    <div class="rubric-bar"><div class="rubric-bar-fill" :class="scoreClass(dim.score, 2)" :style="{ width: (dim.score / 2 * 100) + '%' }"></div></div>
                                    <p class="rubric-dim-note">{{ dim.note }}</p>
                                </div>
                            </div>
                            <p class="rubric-caption">A second opinion. The test results are the grade.</p>
                        </template>
                    </div>
                </template>
            </aside>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Codemirror } from 'vue-codemirror'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { oneDark } from '@codemirror/theme-one-dark'
import api from '../api'
import { useAuthStore } from '../stores/auth'
import AiGlow from '../components/AiGlow.vue'
import QuestionStatement from '../components/QuestionStatement.vue'

type Stage = 'idle' | 'submit' | 'queue' | 'execute' | 'grade' | 'feedback' | 'done'

interface TestCaseMeta {
    id: number
    is_hidden: boolean
    input_data?: string        // sent only for visible (sample) tests
    expected_output?: string
}

interface Question {
    id: number
    title: string
    description: string
    max_attempts: number
    time_limit_minutes: number
    difficulty: string
    points: number
    test_cases: TestCaseMeta[]
    starter_code?: { javascript: string; python: string }   // input reading done; the student writes the function
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

interface RubricScore {
    correctness_score: number
    correctness_note: string
    code_quality_score: number
    code_quality_note: string
    approach_score: number
    approach_note: string
    edge_case_score: number
    edge_case_note: string
    overall_feedback: string
    total_score: number
}

const route = useRoute()
const router = useRouter()

// Submit exam (finish early)
const confirmEnd = ref<boolean>(false)
const ending = ref<boolean>(false)
const endError = ref<string>('')
async function endExam(): Promise<void> {
    ending.value = true
    endError.value = ''
    try {
        flushDraft()
        await api.post(`/exams/${route.params.id}/finish/`)
        router.push('/results')
    } catch {
        endError.value = "Couldn't submit the exam. Check your connection and try again."
    } finally {
        ending.value = false
    }
}
const auth = useAuthStore()

const examTitle = ref<string>('')
const questions = ref<Question[]>([])
const currentIndex = ref<number>(0)
const code = ref<string>('')
const language = ref<string>('javascript')   // JavaScript first; Python is the other option
const timeLeft = ref<number>(0)
const submitting = ref<boolean>(false)
const submissionStatus = ref<string>('')
const submitError = ref<string>('')  // shown inline in the results panel
const results = ref<TestResult[]>([])
const attemptsUsed = ref<Record<number, number>>({})
// Every attempt per question (oldest first), for the attempt chips in the results column
interface AttemptRow { id: number; status: string; attempt: number }
const attemptsByQuestion = ref<Record<number, AttemptRow[]>>({})
const shownAttempt = ref<number | null>(null)          // which attempt the results column shows
const shownSubmissionId = ref<number | null>(null)
const gradedMs = ref<number | null>(null)              // time from Submit to the result, this session only
const stepsOpen = ref<boolean>(false)
const questionAttempts = computed<AttemptRow[]>(() =>
    (currentQuestion.value && attemptsByQuestion.value[currentQuestion.value.id]) || [])
const latestGraded = computed<Record<number, AttemptRow>>(() => {
    const out: Record<number, AttemptRow> = {}
    for (const [qid, rows] of Object.entries(attemptsByQuestion.value)) {
        const graded = rows.filter((r) => r.status === 'passed' || r.status === 'failed')
        if (graded.length) out[Number(qid)] = graded[graded.length - 1]
    }
    return out
})
const acceptedQuestions = ref<Record<number, boolean>>({})

// AI rubric (Feature 1) — fetched async after the result is shown
const rubric = ref<RubricScore | null>(null)
// Result tabs (Tests | Review). The review arrives a few seconds after the result.
const resultTab = ref<'tests' | 'review'>('tests')
const tabTouched = ref<boolean>(false)      // the student picked a tab: never switch it for them
const reviewSeen = ref<boolean>(false)
const rubricGaveUp = ref<boolean>(false)    // polling ended without a review
let rubricPollTimer: ReturnType<typeof setTimeout> | null = null

// AI hint (Feature 2) — fetched async after a FAILED result, shown on demand
const hint = ref<string | null>(null)
const hintVisible = ref<boolean>(false)
let hintPollTimer: ReturnType<typeof setTimeout> | null = null
const hintGaveUp = ref<boolean>(false)

// behaviour tracking: pastes per question, kept for the tab session so a refresh doesn't reset it
interface Behaviour { startedAt: number; paste: Record<number, number>; tabs: number }
const behaviour = ref<Behaviour>({ startedAt: Date.now(), paste: {}, tabs: 0 })

let timerInterval: ReturnType<typeof setInterval> | null = null

// Pipeline tracker state — driven only by real signals from the status endpoint below.
const stage = ref<Stage>('idle')
// Plain-language line under the tracker while a run is retrying or waiting a long time.
const pipelineNote = ref<string>('')
const elapsedMs = ref<number | null>(null)
let elapsedStart = 0
let elapsedTimer: ReturnType<typeof setInterval> | null = null

function startElapsedClock(): void {
    stopElapsedClock()
    elapsedStart = Date.now()
    elapsedMs.value = 0
    elapsedTimer = setInterval(() => {
        elapsedMs.value = Date.now() - elapsedStart
    }, 100)
}

function stopElapsedClock(): void {
    if (elapsedTimer) {
        clearInterval(elapsedTimer)
        elapsedTimer = null
    }
}

const currentQuestion = computed<Question | null>(() =>
    questions.value[currentIndex.value] ?? null
)

const difficultyLabel = computed(() => {
    const d = currentQuestion.value?.difficulty || ''
    return d ? d.charAt(0).toUpperCase() + d.slice(1) : ''
})

const testCount = computed<number>(() => currentQuestion.value?.test_cases?.length || 0)


// null until results are known, then mapped to {passed} for the tracker's dots

const attemptsText = computed(() => {
    if (!currentQuestion.value) return ''
    const used = attemptsUsed.value[currentQuestion.value.id] || 0
    return `${used} of ${currentQuestion.value.max_attempts} attempts used`
})

const attemptsLeft = computed<number>(() => {
    if (!currentQuestion.value) return 0
    return Math.max(0, currentQuestion.value.max_attempts - (attemptsUsed.value[currentQuestion.value.id] || 0))
})

// Grading is in flight: the column shows the step checklist instead of a result
const isRunning = computed<boolean>(() => ['submit', 'queue', 'execute', 'grade'].includes(stage.value))
const runMs = computed<number>(() => results.value.reduce((t, r) => t + (r.execution_time_ms || 0), 0))

// Submitted → In line → Running tests → Grading → Review, as a vertical checklist
const STEP_ROWS = [
    { key: 'submit', label: 'Submitted' },
    { key: 'queue', label: 'In line' },
    { key: 'execute', label: 'Running tests' },
    { key: 'grade', label: 'Grading' },
    { key: 'feedback', label: 'Review' },
] as const
const steps = computed(() => {
    const order = STEP_ROWS.map((r) => r.key as string)
    const at = order.indexOf(stage.value === 'done' ? 'feedback' : stage.value)
    return STEP_ROWS.map((row, i) => {
        let state: 'done' | 'current' | 'waiting'
        if (row.key === 'feedback') state = rubric.value ? 'done' : at === i ? 'current' : 'waiting'
        else if (results.value.length || i < at) state = 'done'
        else state = i === at ? 'current' : 'waiting'
        return { ...row, state }
    })
})
// One dot per test while they run; coloured once results are in
const testDots = computed<{ state: 'pass' | 'fail' | 'waiting' }[]>(() =>
    results.value.length
        ? results.value.map((r) => ({ state: r.passed ? 'pass' : 'fail' }))
        : Array.from({ length: testCount.value }, () => ({ state: 'waiting' as const })))

const outOfAttempts = computed<boolean>(() => {
    if (!currentQuestion.value) return false
    return (attemptsUsed.value[currentQuestion.value.id] || 0) >= currentQuestion.value.max_attempts
})

const canSubmit = computed<boolean>(() => {
    if (!currentQuestion.value) return false
    const used = attemptsUsed.value[currentQuestion.value.id] || 0
    return used < currentQuestion.value.max_attempts && code.value.trim().length > 0
})

// Map a score to a quality band so badges/bars colour by performance
const passedCount = computed(() => results.value.filter((r) => r.passed).length)
const reviewIsNew = computed(() => !!rubric.value && resultTab.value !== 'review' && !reviewSeen.value)

function selectTab(tab: 'tests' | 'review'): void {
    resultTab.value = tab
    tabTouched.value = true
    if (tab === 'review') reviewSeen.value = true
}

function scoreClass(score: number, max: number): string {
    if (max === 8) return score >= 7 ? 'good' : 'mid'
    return score >= max ? 'good' : 'mid'
}

// Flatten the rubric into rows for the score grid
const rubricDimensions = computed(() => {
    const r = rubric.value
    if (!r) return []
    return [
        { label: 'Correctness', score: r.correctness_score, note: r.correctness_note },
        { label: 'Code Quality', score: r.code_quality_score, note: r.code_quality_note },
        { label: 'Approach', score: r.approach_score, note: r.approach_note },
        { label: 'Edge Cases', score: r.edge_case_score, note: r.edge_case_note },
    ]
})

// Verdict headline derived from real results only.
const verdict = computed(() => {
    const list = results.value
    if (list.length === 0) return { headline: '', secondary: '', passed: true }
    const passedCount = list.filter((r) => r.passed).length
    const failedCount = list.length - passedCount
    if (failedCount === 0) {
        return { headline: 'Accepted', secondary: `${passedCount} passed, ${failedCount} failed`, passed: true }
    }
    const idx = list.findIndex((r) => !r.passed)
    const r = list[idx]
    if (!r) return { headline: '', secondary: '', passed: true }
    let headline: string
    if (r.error_message && r.error_message.toLowerCase().includes('time limit')) {
        headline = `Time limit exceeded on test ${idx + 1}`
    } else if (r.error_message && !r.actual_output) {
        headline = `Error on test ${idx + 1}`
    } else {
        headline = `Wrong answer on test ${idx + 1} of ${list.length}`
    }
    return { headline, secondary: `${passedCount} passed, ${failedCount} failed`, passed: false }
})

const editorExtensions = computed(() => {
    const langMap: Record<string, any> = { python: python(), javascript: javascript() }
    const lang = langMap[language.value]
    return lang ? [lang, oneDark] : [oneDark]
})

onMounted(async () => {
    try {
        const res = await api.get(`/exams/${route.params.id}/`)
        // Already ended: nothing more to submit here
        if (res.data.finished_at) {
            router.replace('/results')
            return
        }
        examTitle.value = res.data.title
        questions.value = res.data.questions
        const durationSeconds = res.data.duration_minutes * 60
        loadBehaviour()
        // Count down from when this student started, capped by the exam's end time,
        // so a page refresh doesn't reset the clock.
        const endMs = res.data.end_time ? new Date(res.data.end_time).getTime() : NaN
        const left = durationSeconds - elapsedSeconds()
        timeLeft.value = Math.max(0, Number.isNaN(endMs) ? left : Math.min(left, Math.floor((endMs - Date.now()) / 1000)))
        startTimer()
        attachPasteListener()
        attachTabSwitchListener()
        await loadAttemptsUsed()
        // After a refresh, go back to the question whose submission was still being graded.
        const pendingIndex = questions.value.findIndex((q) => {
            try { return !!sessionStorage.getItem(pollKey(q.id)) } catch { return false }
        })
        if (pendingIndex > 0) currentIndex.value = pendingIndex
        loadDraft()
        window.addEventListener('pagehide', flushDraft)
        if (!resumePending()) showLatestResult()
    } catch {
        router.push('/exams')
    }
})

// Load the student's existing attempts + accepted state per question so the
// counter, the Submit button and the accepted dot reflect reality (attempts
// and status persist across sessions server-side).
async function loadAttemptsUsed(): Promise<void> {
    try {
        // every page: the list is paginated (20 rows), and a long exam can pass that
        const subs: any[] = []
        for (let page = 1; ; page++) {
            const res = await api.get('/submissions/', { params: { exam: route.params.id, page } })
            subs.push(...(res.data.results ?? res.data))
            if (!res.data.next) break
        }
        const counts: Record<number, number> = {}
        const accepted: Record<number, boolean> = {}
        const byQuestion: Record<number, AttemptRow[]> = {}
        for (const s of subs) {
            // A submission that couldn't be graded (status 'error') is refunded server-side.
            if (s.status === 'error') continue
            counts[s.question] = (counts[s.question] || 0) + 1
            if (s.status === 'passed') accepted[s.question] = true
            ;(byQuestion[s.question] ??= []).push({ id: s.id, status: s.status, attempt: s.attempt_number })
        }
        for (const rows of Object.values(byQuestion)) rows.sort((a, b) => a.attempt - b.attempt)
        attemptsUsed.value = counts
        acceptedQuestions.value = accepted
        attemptsByQuestion.value = byQuestion
    } catch {
        // non-fatal — counter just starts at 0
    }
}

onUnmounted(() => {
    flushDraft()
    window.removeEventListener('pagehide', flushDraft)
    document.removeEventListener('paste', onPaste)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    if (timerInterval) clearInterval(timerInterval)
    stopPolling()
    if (rubricPollTimer) clearTimeout(rubricPollTimer)
    if (hintPollTimer) clearTimeout(hintPollTimer)
    stopElapsedClock()
})

function startTimer(): void {
    timerInterval = setInterval(() => {
        if (timeLeft.value <= 0) {
            clearInterval(timerInterval!)
            router.push('/exams')
            return
        }
        timeLeft.value--
    }, 1000)
}

function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60).toString().padStart(2, '0')
    const s = (seconds % 60).toString().padStart(2, '0')
    return `${m}:${s}`
}

function behaviourKey(): string {
    return `codemas:behaviour:${route.params.id}`
}

function loadBehaviour(): void {
    try {
        const saved = sessionStorage.getItem(behaviourKey())
        if (saved) behaviour.value = JSON.parse(saved)
        else sessionStorage.setItem(behaviourKey(), JSON.stringify(behaviour.value))
    } catch { /* storage unavailable: track in memory only */ }
}

function saveBehaviour(): void {
    try { sessionStorage.setItem(behaviourKey(), JSON.stringify(behaviour.value)) } catch { /* storage unavailable */ }
}

function elapsedSeconds(): number {
    return Math.floor((Date.now() - behaviour.value.startedAt) / 1000)
}

// A paste counts toward the question on screen, so pasting in one question never flags another.
function onPaste(e: ClipboardEvent): void {
    const pasted = e.clipboardData?.getData('text') ?? ''
    const qid = currentQuestion.value?.id
    if (!pasted.length || !qid) return
    behaviour.value.paste[qid] = (behaviour.value.paste[qid] || 0) + pasted.length
    saveBehaviour()
}

function onVisibilityChange(): void {
    if (!document.hidden) return
    behaviour.value.tabs++
    saveBehaviour()
}

function attachPasteListener(): void {
    document.addEventListener('paste', onPaste)
}

function attachTabSwitchListener(): void {
    document.addEventListener('visibilitychange', onVisibilityChange)
}

function resetRubric(): void {
    rubric.value = null
    resultTab.value = 'tests'
    tabTouched.value = false
    reviewSeen.value = false
    rubricGaveUp.value = false
    if (rubricPollTimer) {
        clearTimeout(rubricPollTimer)
        rubricPollTimer = null
    }
    hint.value = null
    hintVisible.value = false
    hintGaveUp.value = false
    if (hintPollTimer) {
        clearTimeout(hintPollTimer)
        hintPollTimer = null
    }
}

function switchQuestion(index: number): void {
    flushDraft()  // save the question being left before its code is cleared
    currentIndex.value = index
    submissionStatus.value = ''
    results.value = []
    code.value = ''
    loadDraft()
    resetRubric()
    submitError.value = ''
    stopPolling()
    stage.value = 'idle'
    stopElapsedClock()
    elapsedMs.value = null
    shownAttempt.value = null
    shownSubmissionId.value = null
    gradedMs.value = null
    stepsOpen.value = false
    // A submission still being graded for this question picks up where it left off;
    // otherwise show its latest graded attempt.
    if (!resumePending()) showLatestResult()
}

// Bring back the latest graded attempt's results, review and hint (after a refresh or
// on returning to a question), so earlier results are never lost.
async function showLatestResult(): Promise<void> {
    const qid = currentQuestion.value?.id
    const latest = qid ? latestGraded.value[qid] : undefined
    if (latest) await viewAttempt(latest)
}

// Show one graded attempt's result, review and hint (an attempt chip, or the latest on load).
async function viewAttempt(row: AttemptRow): Promise<void> {
    const qid = currentQuestion.value?.id
    if (!qid || isRunning.value || row.id === shownSubmissionId.value) return
    if (row.status !== 'passed' && row.status !== 'failed') return
    resetRubric()
    results.value = []
    submitError.value = ''
    submissionStatus.value = row.status
    shownAttempt.value = row.attempt
    shownSubmissionId.value = row.id
    gradedMs.value = null
    stepsOpen.value = false
    stopElapsedClock()
    elapsedMs.value = null
    stage.value = 'idle'
    try {
        await finalizeResult(row.id, row.status,
            () => currentQuestion.value?.id === qid && shownSubmissionId.value === row.id, 0)
    } catch {
        // results unavailable: the column stays empty
    }
}

async function submitCode(): Promise<void> {
    if (!currentQuestion.value || !canSubmit.value) return
    // Everything question-scoped is captured now: the student may switch question during the POST.
    const qid = currentQuestion.value.id
    submitting.value = true
    submitError.value = ''
    submissionStatus.value = 'running'
    results.value = []
    resetRubric()
    stage.value = 'submit'
    startElapsedClock()

    try {
        const res = await api.post('/submissions/create/', {
            question: qid,
            code: code.value,
            language: language.value,
            time_remaining_seconds: timeLeft.value,
            had_paste_event: (behaviour.value.paste[qid] || 0) > 0,
            paste_char_count: behaviour.value.paste[qid] || 0,
            time_to_complete_seconds: elapsedSeconds(),
            tab_switch_count: behaviour.value.tabs,
        })

        const submissionId: number = res.data.id
        attemptsUsed.value[qid] = (attemptsUsed.value[qid] || 0) + 1
        ;(attemptsByQuestion.value[qid] ??= []).push({ id: submissionId, status: 'running', attempt: res.data.attempt_number ?? attemptsUsed.value[qid] })
        shownAttempt.value = res.data.attempt_number ?? attemptsUsed.value[qid]
        shownSubmissionId.value = submissionId
        gradedMs.value = null
        stepsOpen.value = false

        if (currentQuestion.value?.id !== qid) {
            // They moved on while it was saving: remember it, and resumePending picks it up on return.
            savePending(qid, submissionId)
            return
        }
        stage.value = 'queue'
        listenForResult(submissionId, qid)
    } catch (e: any) {
        if (currentQuestion.value?.id !== qid) return  // don't paint the error onto another question
        // The submission never reached grading, so don't show it as a failed test run
        submissionStatus.value = ''
        stage.value = 'idle'
        stopElapsedClock()
        elapsedMs.value = null
        submitError.value = e.response?.data?.error
            ? `Your code wasn't submitted: ${String(e.response.data.error).replace(/[.!?]+$/, '')}.`
            : "Your code wasn't submitted. Check your connection and try again."
    } finally {
        submitting.value = false
    }
}

// Autosave each question's code per user + exam + question, so a refresh doesn't lose it.
// Kept after submitting so the student can edit and resubmit. Keyed by user id so a
// second account on the same browser never sees someone else's draft.
const DRAFT_SAVE_MS = 500
let draftTimer: ReturnType<typeof setTimeout> | null = null
let draftQid: number | null = null  // the question the pending save belongs to

function draftKey(questionId: number): string | null {
    const userId = auth.user?.id
    if (!userId) return null  // no signed-in user known: don't save or restore
    return `codemas:draft:${userId}:${route.params.id}:${questionId}`
}

function writeDraft(questionId: number): void {
    const key = draftKey(questionId)
    if (!key) return
    try {
        localStorage.setItem(key, JSON.stringify({ code: code.value, language: language.value }))
    } catch { /* storage unavailable or full */ }
}

function flushDraft(): void {
    if (draftTimer) {
        clearTimeout(draftTimer)
        draftTimer = null
    }
    if (draftQid !== null) writeDraft(draftQid)
    draftQid = null
}

// Put the current question's saved draft (if any) into the editor.
function loadDraft(): void {
    const qid = currentQuestion.value?.id
    if (!qid) return
    const key = draftKey(qid)
    try {
        const raw = key ? localStorage.getItem(key) : null
        const draft = raw ? JSON.parse(raw) : null
        if (draft?.language === 'javascript' || draft?.language === 'python') language.value = draft.language
        if (typeof draft?.code === 'string') code.value = draft.code
    } catch { /* storage unavailable or bad JSON: start from the starter code */ }
    if (!code.value.trim()) code.value = starterFor(language.value)
}

function starterFor(lang: string): string {
    const starters = currentQuestion.value?.starter_code
    return (starters && starters[lang as 'javascript' | 'python']) || ''
}

// Switching language swaps in that language's starter, unless the student has changed the code
watch(language, (next, prev) => {
    if (!code.value.trim() || code.value === starterFor(prev)) code.value = starterFor(next)
})

watch([code, language], () => {
    const qid = currentQuestion.value?.id
    if (!qid) return
    if (draftQid !== null && draftQid !== qid) flushDraft()
    draftQid = qid
    if (draftTimer) clearTimeout(draftTimer)
    draftTimer = setTimeout(flushDraft, DRAFT_SAVE_MS)
})

// Poll the submission's status until it is graded. Works the same for the job pipeline and the
// legacy path (job: null), and resumes after a page refresh (the id is kept in sessionStorage per question).
interface StatusResponse {
    id: number
    status: string
    results_ready: boolean
    job: { status: string; attempt: number } | null
}

const STAGE_ORDER: Stage[] = ['idle', 'submit', 'queue', 'execute', 'grade', 'feedback', 'done']
const POLL_DELAYS_MS = [1000, 1000, 1000, 1000, 1000, 2000, 2000, 3000]
const LONG_WAIT_MS = 10000
const SLOW_POLL_AFTER_MS = 120000  // after 2 minutes, check every 10 s
const SLOW_POLL_MS = 10000
let statusTimer: ReturnType<typeof setTimeout> | null = null
let pollRun = 0  // bumped on every stop, so a response for an abandoned poll is ignored

function pollKey(questionId: number): string {
    return `codemas:pending-submission:${route.params.id}:${questionId}`
}

// The tracker only moves forward. A retry sends the run back to the queue server-side,
// but the student keeps seeing the furthest stage reached.
function advanceStage(next: Stage): void {
    if (STAGE_ORDER.indexOf(next) > STAGE_ORDER.indexOf(stage.value)) stage.value = next
}

function stopPolling(): void {
    pollRun += 1
    if (statusTimer) {
        clearTimeout(statusTimer)
        statusTimer = null
    }
    pipelineNote.value = ''
}

function savePending(questionId: number, submissionId: number): void {
    try { sessionStorage.setItem(pollKey(questionId), String(submissionId)) } catch { /* storage unavailable */ }
}

function clearPending(questionId: number | undefined): void {
    if (!questionId) return
    try { sessionStorage.removeItem(pollKey(questionId)) } catch { /* storage unavailable */ }
}

// Pick up a submission for the current question that was still being graded when the page was left.
function resumePending(): boolean {
    const qid = currentQuestion.value?.id
    if (!qid) return false
    let saved: string | null = null
    try { saved = sessionStorage.getItem(pollKey(qid)) } catch { return false }
    const id = Number(saved)
    if (!saved || !Number.isInteger(id) || id <= 0) return false
    shownSubmissionId.value = id
    shownAttempt.value = questionAttempts.value.find((a) => a.id === id)?.attempt ?? null
    submissionStatus.value = 'running'
    stage.value = 'queue'
    startElapsedClock()
    listenForResult(id, qid)
    return true
}

// Stop tracking a run that will never produce a grade, and say why (or say nothing).
function abandonRun(questionId: number | undefined, message: string): void {
    stopPolling()
    stopElapsedClock()
    elapsedMs.value = null
    stage.value = 'idle'
    submissionStatus.value = ''
    submitError.value = message
    clearPending(questionId)
}

function listenForResult(submissionId: number, qid: number): void {
    stopPolling()
    const run = pollRun
    savePending(qid, submissionId)
    const waitStart = Date.now()
    let polls = 0

    const poll = async (): Promise<void> => {
        statusTimer = null
        try {
            const { data } = await api.get<StatusResponse>(`/submissions/${submissionId}/status/`)
            if (run !== pollRun) return  // question changed or page left while this was in flight
            const job = data.job

            // Infrastructure gave up on this run: the server refunds the attempt.
            if (job?.status === 'dead') {
                abandonRun(qid, "We couldn't grade this submission because of a problem on our side. It doesn't count as an attempt, so please submit again.")
                void loadAttemptsUsed()
                return
            }
            if (data.status === 'error' && data.results_ready) {
                abandonRun(qid, testCount.value === 0
                    ? "This question has no test cases yet, so it can't be graded. Tell your trainer."
                    : "This submission couldn't be graded. Please submit again, and tell your trainer if it happens again.")
                void loadAttemptsUsed()
                return
            }
            if (data.status === 'passed' || data.status === 'failed') {
                submissionStatus.value = data.status
                pipelineNote.value = ''
                advanceStage('grade')
                // if this throws, the next poll tries again
                await finalizeResult(submissionId, data.status, () => run === pollRun)
                if (run !== pollRun) return  // left mid-fetch: keep the key so the result resumes on return
                clearPending(qid)
                return
            }

            advanceStage(job?.status === 'running' || data.status === 'running' ? 'execute' : 'queue')
            // attempt counts claims, so a first run is 'running' with attempt 1; anything past that is a retry
            const retrying = !!job && job.attempt > (job.status === 'running' ? 1 : 0)
            if (retrying) {
                pipelineNote.value = 'Retrying… your code hit a problem on our side, so we are running it again. This does not use another attempt.'
            } else if (Date.now() - waitStart > LONG_WAIT_MS) {
                pipelineNote.value = stage.value === 'queue'
                    ? 'Taking longer than usual… you are still in line. Your code is saved and will run as soon as there is room.'
                    : 'Taking longer than usual… your code is still running. The result will show here as soon as it is ready.'
            } else {
                pipelineNote.value = ''
            }
        } catch (e: any) {
            if (run !== pollRun) return
            const code = e?.response?.status
            if (code === 401 || code === 403 || code === 404) {
                abandonRun(qid, '')  // signed out, not this student's submission, or gone: stop quietly
                return
            }
            // transient network error: keep polling
        }
        const delay = Date.now() - waitStart > SLOW_POLL_AFTER_MS
            ? SLOW_POLL_MS
            : POLL_DELAYS_MS[Math.min(polls, POLL_DELAYS_MS.length - 1)] ?? 3000
        polls += 1
        statusTimer = setTimeout(poll, delay)
    }
    void poll()
}

// Load test results and kick off AI polling for a finished submission. isCurrent guards against
// a question switch (or leaving the page) while the results were being fetched.
async function finalizeResult(
    submissionId: number, status: string, isCurrent: () => boolean = () => true, firstPollMs?: number,
): Promise<void> {
    const res = await api.get(`/results/${submissionId}/`)
    if (!isCurrent()) return
    results.value = res.data
    if (firstPollMs === undefined) gradedMs.value = elapsedMs.value  // a live run, not a restored one
    stage.value = 'feedback'
    pollRubric(submissionId, 0, firstPollMs)  // AI rubric arrives a few seconds later
    if (status === 'failed') {
        pollHint(submissionId, 0, firstPollMs)  // Socratic hint only on failed submissions
    }
    loadAttemptsUsed()  // keep the latest-graded map current for refreshes and question switches
}

// Rubric (and hint, when expected) are the last real signals we have — once
// they've resolved (or hint polling has given up), the pipeline is done.
function maybeFinish(): void {
    if (!rubric.value) return
    if (submissionStatus.value === 'failed' && !hint.value && !hintGaveUp.value) return
    stage.value = 'done'
    stopElapsedClock()
}

// Poll the rubric endpoint until the async GPT score is stored, then stop.
// Bounded so we give up quietly if scoring is unavailable (e.g. no API key).
function pollRubric(submissionId: number, attempt = 0, firstPollMs?: number): void {
    const MAX_ATTEMPTS = 15
    const INTERVAL_MS = 2000

    if (attempt >= MAX_ATTEMPTS) {
        rubricGaveUp.value = true
        return
    }

    rubricPollTimer = setTimeout(async () => {
        try {
            const res = await api.get(`/ai/rubric/${submissionId}/`)
            if (res.data && typeof res.data.total_score === 'number') {
                rubric.value = res.data as RubricScore
                // All tests passed: nothing to fix, so show the review (unless the student chose a tab)
                if (verdict.value.passed && !tabTouched.value) {
                    resultTab.value = 'review'
                    reviewSeen.value = true
                }
                maybeFinish()
                return  // got it — stop polling
            }
        } catch {
            // transient error — fall through and retry
        }
        pollRubric(submissionId, attempt + 1)
    }, attempt === 0 && firstPollMs !== undefined ? firstPollMs : INTERVAL_MS)  // a restored result asks at once
}

// Poll the hint endpoint until the async hint is stored, then stop.
function pollHint(submissionId: number, attempt = 0, firstPollMs?: number): void {
    const MAX_ATTEMPTS = 15
    const INTERVAL_MS = 2000

    if (attempt >= MAX_ATTEMPTS) {
        hintGaveUp.value = true
        maybeFinish()
        return
    }

    hintPollTimer = setTimeout(async () => {
        try {
            const res = await api.get(`/ai/hint/${submissionId}/`)
            if (res.data && typeof res.data.hint === 'string') {
                hint.value = res.data.hint
                maybeFinish()
                return  // got it — stop polling
            }
        } catch {
            // transient error — fall through and retry
        }
        pollHint(submissionId, attempt + 1)
    }, attempt === 0 && firstPollMs !== undefined ? firstPollMs : INTERVAL_MS)  // a restored result asks at once
}
</script>

<style scoped>
.take-container {
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
    background: var(--bg);
}

/* Top bar */
.top-bar {
    height: 60px;
    flex-shrink: 0;
    box-sizing: border-box;
    padding: 0 24px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
    display: flex;
    align-items: center;
    gap: 24px;
}
.exam-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
}
.q-nav { display: flex; gap: 4px; }
.q-tab {
    height: 36px;
    min-width: 44px;
    padding: 0 12px;
    border-radius: var(--radius-pill);
    border: 1px solid transparent;
    background: transparent;
    color: var(--text-muted);
    font: 500 14px var(--font-sans);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.q-tab.active {
    border-color: var(--text);
    background: var(--text);
    color: #fff;
}
.q-tab:hover:not(.active) { color: var(--text); }
.q-tab-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--green);
}
.top-bar-spacer { flex-grow: 1; }
.attempts-text { font-size: 14px; color: var(--text-muted); }
.timer {
    font-family: var(--font-mono);
    font-size: 22px;
    font-weight: 500;
    font-variant-numeric: tabular-nums;
    color: var(--text);
    background: var(--surface2);
    padding: 4px 14px;
    border-radius: var(--radius-pill);
}
.timer.warning { color: var(--amber-ink); }

/* Body grid */
.main {
    flex: 1;
    min-height: 0;
    display: grid;
    /* question · full-height code · results; each column scrolls inside the screen */
    grid-template-columns: minmax(260px, 320px) minmax(0, 1fr) minmax(340px, 430px);
    grid-template-rows: minmax(0, 1fr);
}
/* Narrower screens: results go under the code */
@media (max-width: 1200px) {
    .main {
        grid-template-columns: minmax(240px, 300px) minmax(0, 1fr);
        grid-template-rows: minmax(0, 3fr) minmax(0, 2fr);
    }
    .question-panel { grid-row: 1 / 3; }
    .results-col { grid-column: 2; border-left: 0; border-top: 1px solid var(--border); }
}

.question-panel {
    min-height: 0;
    border-right: 1px solid var(--border);
    background: var(--surface);
    padding: 26px;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 22px;
}
.q-head { display: flex; flex-direction: column; gap: 10px; }
.q-title {
    margin: 0;
    font-size: 28px;
    font-weight: 600;
    letter-spacing: -0.01em;
    color: var(--text);
}
.q-meta {
    display: flex;
    gap: 16px;
    font-size: 13px;
    color: var(--text-muted);
}
.q-difficulty.easy { color: var(--green-ink); }
.q-difficulty.medium { color: var(--amber-ink); }
.q-difficulty.hard { color: var(--red-ink); }
.attempts-info { font-size: 12px; color: var(--text-dim); margin: 0; }

/* Editor + judge column */
.editor-panel {
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
}
.editor-header {
    height: 56px;
    flex-shrink: 0;
    box-sizing: border-box;
    padding: 0 20px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 12px;
}
.lang-label { font-size: 13px; color: var(--text-muted); }
.editor-header select {
    height: 36px;
    padding: 0 10px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--text);
    font: 400 14px var(--font-sans);
    width: auto;
    min-width: 140px;
}
.editor-header-spacer { flex-grow: 1; }
.submit-btn {
    height: 40px;
    padding: 0 18px;
    border-radius: var(--radius-pill);
    border: none;
    font: 600 14px var(--font-display);
    background: var(--accent);
    color: var(--accent-ink);
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: var(--accent-hover); }
.submit-btn:disabled {
    background: var(--surface2);
    color: var(--text-dim);
    cursor: default;
}

.editor-cm { flex: 1; min-height: 0; overflow: hidden; }
/* vue-codemirror's wrapper is display: contents, so .cm-editor is the real flex item:
   it takes the space left above the results and scrolls long code inside itself. */
.editor-cm :deep(.cm-editor) { flex: 1 1 0; min-height: 0; height: auto; background: var(--code-bg) !important; }
.editor-cm :deep(.cm-gutters) { background: var(--code-bg) !important; border-right: none !important; color: #475069; }
.editor-cm :deep(.cm-activeLine), .editor-cm :deep(.cm-activeLineGutter) { background: rgba(148, 163, 184, 0.06) !important; }
.editor-cm :deep(.cm-scroller) { overflow: auto; }

/* Judge panel */
/* The editor gets most of the screen: before a submit the panel only fits its
   content; with results it takes 40% and scrolls inside. */
.results-col {
    min-height: 0;
    min-width: 0;
    overflow-y: auto;
    box-sizing: border-box;
    border-left: 1px solid var(--border);
    background: var(--surface);
    padding: 16px 20px 22px;
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.end-btn {
    height: 36px; padding: 0 16px;
    border: 1px solid var(--border2); border-radius: var(--radius-pill);
    background: var(--surface); color: var(--text);
    font: 600 14px var(--font-sans); cursor: pointer;
}
.end-btn:hover { border-color: var(--accent); color: var(--accent); }
.end-btn:focus-visible, .end-cancel:focus-visible, .end-confirm:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.end-overlay {
    position: fixed; inset: 0; z-index: 50;
    background: rgba(33, 25, 27, 0.4);
    display: flex; align-items: center; justify-content: center; padding: 16px;
}
.end-dialog {
    width: 100%; max-width: 420px; box-sizing: border-box;
    background: var(--surface); border-radius: var(--radius); padding: 24px;
    box-shadow: var(--shadow-lg); display: flex; flex-direction: column; gap: 12px;
}
.end-title { margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 600; color: var(--text); }
.end-text { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text-muted); }
.end-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 4px; }
.end-cancel, .end-confirm {
    height: 40px; padding: 0 18px; border-radius: var(--radius-pill);
    font: 600 14px var(--font-sans); cursor: pointer;
}
.end-cancel { border: 1px solid var(--border2); background: var(--surface); color: var(--text); }
.end-confirm { border: 0; background: var(--accent); color: var(--accent-ink); }
.end-confirm:disabled { opacity: 0.6; cursor: default; }

/* Attempt chips */
.attempts-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.attempts-label { font-size: 12px; font-weight: 600; letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-dim); }
.attempts-spacer { flex: 1; }
.attempt-chip {
    display: inline-flex; align-items: center; gap: 6px;
    min-height: 34px; padding: 0 12px;
    border: 1px solid var(--border); border-radius: var(--radius-pill);
    background: var(--surface); color: var(--text-muted);
    font: 500 13px var(--font-sans); cursor: pointer;
}
.attempt-chip:hover:not(:disabled) { border-color: var(--border2); color: var(--text); }
.attempt-chip.active { background: var(--text); border-color: var(--text); color: var(--surface); font-weight: 600; }
.attempt-chip:disabled { cursor: default; opacity: 0.6; }
.attempt-chip:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.chip-mark { font-weight: 700; }
.chip-mark.pass { color: var(--green); }
.chip-mark.fail { color: var(--red); }
.attempt-chip.active .chip-mark.fail { color: #FF8FA6; }
.attempt-chip.active .chip-mark.pass { color: #7EE2A8; }
.chip-running { width: 7px; height: 7px; border-radius: 50%; background: var(--yellow); }
.attempts-left {
    display: inline-flex; align-items: center; min-height: 34px; padding: 0 12px;
    border: 1px dashed var(--border2); border-radius: var(--radius-pill);
    font-size: 13px; color: var(--text-dim);
}

/* Empty state */
.results-empty { display: flex; flex-direction: column; gap: 6px; padding: 14px 16px; border-radius: var(--radius-sm); background: var(--surface2); }
.results-empty-title { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: 16px; color: var(--text); }
.results-empty-text { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text-muted); }

/* While grading: step checklist */
.run-head, .verdict { display: flex; flex-direction: column; gap: 4px; }
.run-title { font-family: var(--font-display); font-size: 18px; font-weight: 600; color: var(--text); }
.run-sub { font-size: 13px; color: var(--text-dim); }
.steps { margin: 0; padding: 0; list-style: none; }
.step {
    display: grid; grid-template-columns: 28px minmax(0, 1fr) auto; align-items: center; gap: 10px;
    padding: 10px 0; border-bottom: 1px solid var(--border); font-size: 14px; color: var(--text-dim);
}
.step:last-child { border-bottom: 0; }
.step.done, .step.current { color: var(--text); }
.step.current .step-label { font-weight: 600; }
.step-mark {
    width: 22px; height: 22px; box-sizing: border-box; border-radius: 50%;
    border: 2px solid var(--border2);
    display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 700;
}
.step.done .step-mark { border: 0; background: var(--green-dim); color: var(--green-ink); }
.step.current .step-mark { border-color: var(--accent); animation: step-pulse 1.2s ease-in-out infinite; }
@keyframes step-pulse { 50% { opacity: 0.45; } }
@media (prefers-reduced-motion: reduce) { .step.current .step-mark { animation: none; } }
.step-label { display: flex; align-items: center; gap: 6px; }
.step-spark { width: 14px; height: 14px; color: var(--purple-ink); }
.step-note { font-size: 12px; color: var(--text-dim); }
.test-dots { display: flex; gap: 5px; }
.test-dot { width: 10px; height: 10px; box-sizing: border-box; border-radius: 50%; border: 2px solid var(--border2); }
.test-dot.pass { border: 0; background: var(--green); }
.test-dot.fail { border: 0; background: var(--red); }

/* Graded */
.verdict-sub { font-size: 13px; color: var(--text-dim); }
.steps-toggle {
    display: flex; align-items: center; gap: 8px; width: 100%;
    min-height: 40px; padding: 0 12px;
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    background: var(--bg); color: var(--text-muted);
    font: 500 13px var(--font-sans); text-align: left; cursor: pointer;
}
.steps-toggle:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.steps-check { color: var(--green-ink); font-weight: 700; }
.steps-more { color: var(--text-dim); }

/* Result tab: one card per test */
.test-card {
    display: flex; flex-direction: column; gap: 6px;
    padding: 10px 12px; border-radius: var(--radius-sm); font-size: 13px;
    border: 1px solid var(--border);
}
.test-card.pass { background: var(--green-dim); border-color: color-mix(in srgb, var(--green) 30%, transparent); }
.test-card.fail { background: var(--red-dim); border-color: color-mix(in srgb, var(--red) 25%, transparent); }
.test-card-top { display: flex; align-items: center; gap: 10px; }
.test-out { font-family: var(--font-mono); white-space: pre-wrap; word-break: break-word; }
.test-detail { margin: 0; display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 4px 8px; color: var(--text-muted); }
.test-detail dt { margin: 0; }
.test-detail dd { margin: 0; color: var(--text); white-space: pre-wrap; word-break: break-word; }
.test-detail dd.dim { color: var(--text-dim); font-style: italic; }
.mono { font-family: var(--font-mono); }
.dim { color: var(--text-dim); }
.text-fail { color: var(--red-ink); }
.text-pass { color: var(--green-ink); }
.hint-pending {
    margin: 0; padding: 10px 12px; border: 1px dashed var(--border2); border-radius: var(--radius-sm);
    font-size: 13px; color: var(--text-dim);
}
.row-error {
    margin: 0;
    padding: 6px 14px 10px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--red-ink);
}

/* Hint */
.hint-area { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
.hint-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    align-self: flex-start;
    height: 36px;
    padding: 0 14px;
    border-radius: var(--radius-pill);
    border: 1px solid var(--border2);
    background: var(--surface);
    color: var(--text);
    font: 500 14px var(--font-sans);
    cursor: pointer;
}
.hint-btn:hover { border-color: var(--border2); }
.hint-text {
    margin: 0;
    font-size: 14px;
    line-height: 1.6;
    color: var(--text-muted);
    max-width: 80ch;
}

/* Rubric pending */
.rubric-pending {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 0;
    color: var(--text-muted);
    font-size: 14px;
}
.pending-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent);
    animation: rubric-pulse 1s ease-in-out infinite;
}
@keyframes rubric-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.75); }
}
@media (prefers-reduced-motion: reduce) {
    .pending-dot { animation: none !important; }
}

/* Result tabs: Tests | Review */
.result-tabs {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 6px;
    border-bottom: 1px solid var(--border);
}
.result-tab {
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: 44px;
    padding: 0 14px;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    background: none;
    color: var(--text-muted);
    font: 500 14px var(--font-sans);
    cursor: pointer;
}
.result-tab:hover { color: var(--text); }
.result-tab.active { color: var(--text); font-weight: 600; border-bottom-color: var(--accent); }
.result-tab:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 6px; }
.tab-spark { width: 16px; height: 16px; color: var(--purple-ink); }
.tab-badge { font-size: 12px; font-weight: 600; padding: 2px 8px; border-radius: var(--radius-pill); }
.tab-badge.pass, .tab-badge.good { background: var(--green-dim); color: var(--green-ink); }
.tab-badge.fail { background: var(--red-dim); color: var(--red-ink); }
.tab-badge.mid { background: var(--yellow-dim); color: var(--amber-ink); }
.tab-pending { font-size: 12px; color: var(--text-dim); }
.new-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.verdict-inline { font-family: var(--font-display); font-size: 16px; font-weight: 600; }
.verdict-inline.pass { color: var(--green-ink); }
.verdict-inline.fail { color: var(--red-ink); }
.result-panel { display: flex; flex-direction: column; gap: 14px; }

/* Review tab */
.rubric-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px 28px;
}
.rubric-dim { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.rubric-dim-top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; }
.rubric-dim-label { font-size: 14px; font-weight: 600; color: var(--text); }
.rubric-dim-score { font-family: var(--font-mono); font-size: 14px; font-weight: 600; }
.rubric-dim-score.good { color: var(--green-ink); }
.rubric-dim-score.mid { color: var(--amber-ink); }
.rubric-bar { height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.rubric-bar-fill { height: 100%; border-radius: 3px; }
.rubric-bar-fill.good { background: var(--green); }
.rubric-bar-fill.mid { background: var(--yellow); }
.rubric-dim-note { margin: 0; font-size: 13px; line-height: 1.55; color: var(--text-muted); }
.rubric-overall { margin: 0; font-size: 14px; line-height: 1.6; color: var(--text); }
.rubric-caption { margin: 0; font-size: 12px; color: var(--text-dim); }
@media (max-width: 900px) {
    .rubric-grid { grid-template-columns: minmax(0, 1fr); }
}
.pipeline-note {
    margin: 0;
    font-size: 14px;
    color: var(--text-muted);
}
/* Always rendered so screen readers hear the text change; when empty it takes no space
   (the negative margin cancels the column's gap). */
.pipeline-note:empty { margin-top: -14px; }

.submit-error {
    margin: 0;
    padding: 12px 16px;
    border-radius: 12px;
    background: var(--red-dim);
    color: var(--red-ink);
    font-size: 14px;
}
</style>
