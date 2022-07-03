<template>
    <div class="take-container">
        <div class="top-bar">
            <h2>{{ currentQuestion?.title || 'Loading...' }}</h2>
            <div class="timer" :class="{ warning: timeLeft <= 60 }">
                Time Left: {{ formatTime(timeLeft) }}
            </div>
        </div>

        <div class="main">
            <!-- Question Panel -->
            <div class="question-panel">
                <p>{{ currentQuestion?.description }}</p>
                <div class="nav">
                    <button
                        v-for="(q, i) in questions"
                        :key="q.id"
                        :class="{ active: currentIndex === i }"
                        @click="switchQuestion(i)"
                    >
                        Q{{ i + 1 }}
                    </button>
                </div>
                <p class="attempts-info" v-if="currentQuestion">
                    Attempts: {{ attemptsUsed[currentQuestion.id] || 0 }} / {{ currentQuestion.max_attempts }}
                </p>
            </div>

            <!-- Editor Panel -->
            <div class="editor-panel">
                <div class="editor-header">
                    <select v-model="language">
                        <option value="python">Python</option>
                        <option value="javascript">JavaScript</option>
                        <option value="java">Java</option>
                        <option value="cpp">C++</option>
                    </select>
                    <button
                        class="submit-btn"
                        @click="submitCode"
                        :disabled="submitting || !canSubmit"
                    >
                        {{ submitting ? 'Submitting...' : 'Submit' }}
                    </button>
                </div>

                <codemirror
                    v-model="code"
                    :extensions="editorExtensions"
                    style="height: 400px; font-size: 14px;"
                />

            </div>

            <div class="results-area">
                <div v-if="submissionStatus" class="result-box" :class="submissionStatus">
                    <p v-if="submissionStatus === 'running'">Running tests...</p>
                    <p v-else-if="submissionStatus === 'passed'">All tests passed!</p>
                    <p v-else-if="submissionStatus === 'failed'">Some tests failed.</p>

                    <div v-if="results.length > 0" class="results-list">
                        <div v-for="r in results" :key="r.id" class="result-row" :class="r.passed ? 'pass' : 'fail'">
                            <span>{{ r.passed ? '✓' : '✗' }}</span>
                            <span>Input: {{ r.test_case_input }}</span>
                            <span>Expected: {{ r.test_case_expected }}</span>
                            <span>Got: {{ r.actual_output }}</span>
                            <span v-if="r.error_message" class="err">{{ r.error_message }}</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Codemirror } from 'vue-codemirror'
import { python } from '@codemirror/lang-python'
import { javascript } from '@codemirror/lang-javascript'
import { oneDark } from '@codemirror/theme-one-dark'
import api from '../api'

interface Question {
    id: number
    title: string
    description: string
    max_attempts: number
    time_limit_minutes: number
}

interface TestResult {
    id: number
    test_case_input: string
    test_case_expected: string
    passed: boolean
    actual_output: string
    error_message: string
}

const route = useRoute()
const router = useRouter()

const questions = ref<Question[]>([])
const currentIndex = ref<number>(0)
const code = ref<string>('')
const language = ref<string>('python')
const timeLeft = ref<number>(0)
const examDuration = ref<number>(0)
const submitting = ref<boolean>(false)
const submissionStatus = ref<string>('')
const results = ref<TestResult[]>([])
const attemptsUsed = ref<Record<number, number>>({})

// behaviour tracking
const hadPasteEvent = ref<boolean>(false)
const pasteCharCount = ref<number>(0)
const tabSwitchCount = ref<number>(0)

let timerInterval: ReturnType<typeof setInterval> | null = null
let eventSource: EventSource | null = null

const currentQuestion = computed<Question | null>(() =>
    questions.value[currentIndex.value] ?? null
)

const canSubmit = computed<boolean>(() => {
    if (!currentQuestion.value) return false
    const used = attemptsUsed.value[currentQuestion.value.id] || 0
    return used < currentQuestion.value.max_attempts && code.value.trim().length > 0
})

const editorExtensions = computed(() => {
    const langMap: Record<string, any> = { python: python(), javascript: javascript() }
    const lang = langMap[language.value]
    return lang ? [lang, oneDark] : [oneDark]
})

onMounted(async () => {
    try {
        const res = await api.get(`/exams/${route.params.id}/`)
        questions.value = res.data.questions
        const durationSeconds = res.data.duration_minutes * 60
        examDuration.value = durationSeconds
        timeLeft.value = durationSeconds
        startTimer()
        attachPasteListener()
        attachTabSwitchListener()
    } catch {
        router.push('/exams')
    }
})

onUnmounted(() => {
    if (timerInterval) clearInterval(timerInterval)
    if (eventSource) eventSource.close()
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

function attachPasteListener(): void {
    document.addEventListener('paste', (e: ClipboardEvent) => {
        const pasted = e.clipboardData?.getData('text') ?? ''
        if (pasted.length > 0) {
            hadPasteEvent.value = true
            pasteCharCount.value += pasted.length
        }
    })
}

function attachTabSwitchListener(): void {
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) tabSwitchCount.value++
    })
}

function switchQuestion(index: number): void {
    currentIndex.value = index
    submissionStatus.value = ''
    results.value = []
    code.value = ''
    if (eventSource) {
        eventSource.close()
        eventSource = null
    }
}

async function submitCode(): Promise<void> {
    if (!currentQuestion.value || !canSubmit.value) return
    submitting.value = true
    submissionStatus.value = 'running'
    results.value = []

    try {
        const res = await api.post('/submissions/create/', {
            question: currentQuestion.value.id,
            code: code.value,
            language: language.value,
            time_remaining_seconds: timeLeft.value,
            had_paste_event: hadPasteEvent.value,
            paste_char_count: pasteCharCount.value,
            time_to_complete_seconds: examDuration.value - timeLeft.value,
            tab_switch_count: tabSwitchCount.value,
        })

        const submissionId: number = res.data.id
        const qid = currentQuestion.value.id
        attemptsUsed.value[qid] = (attemptsUsed.value[qid] || 0) + 1

        listenForResult(submissionId)
    } catch (e: any) {
        submissionStatus.value = 'failed'
        const msg = e.response?.data?.error || 'Submission failed'
        alert(msg)
    } finally {
        submitting.value = false
    }
}

function listenForResult(submissionId: number): void {
    const token = localStorage.getItem('access_token')
    if (eventSource) eventSource.close()

    // SSE doesn't support custom headers — pass token as query param
    eventSource = new EventSource(
        `http://localhost:8000/api/submissions/${submissionId}/stream/?token=${token}`
    )

    eventSource.onmessage = async (event: MessageEvent) => {
        const data = JSON.parse(event.data)
        submissionStatus.value = data.status

        if (data.status === 'passed' || data.status === 'failed') {
            eventSource?.close()
            const res = await api.get(`/results/${submissionId}/`)
            results.value = res.data
        }
    }

    eventSource.onerror = () => {
        eventSource?.close()
        submissionStatus.value = 'failed'
    }
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
.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0 20px;
    height: 52px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
}
.top-bar h2 { font-size: 14px; font-weight: 600; color: var(--text); }
.timer {
    font-size: 16px;
    font-weight: 700;
    color: var(--text);
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 5px 14px;
    border-radius: var(--radius-sm);
    font-variant-numeric: tabular-nums;
}
.timer.warning { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.main { display: flex; flex: 1; overflow: hidden; }
.question-panel {
    width: 320px;
    padding: 20px;
    border-right: 1px solid var(--border);
    overflow-y: auto;
    background: var(--surface);
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.question-panel p {
    font-size: 13px;
    color: var(--text-muted);
    line-height: 1.7;
}
.nav { display: flex; gap: 6px; flex-wrap: wrap; }
.nav button {
    padding: 5px 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface2);
    color: var(--text-muted);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
}
.nav button:hover { border-color: var(--border2); color: var(--text); }
.nav button.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.attempts-info { font-size: 12px; color: var(--text-dim); }
.editor-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: var(--bg);
    overflow: hidden;
}
.editor-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
}
.editor-header select {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 5px 10px;
    border-radius: var(--radius-sm);
    font-size: 13px;
    width: auto;
}
.submit-btn {
    padding: 8px 22px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s;
}
.submit-btn:hover:not(:disabled) { background: var(--red-hover); }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.results-area {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
}
.result-box {
    padding: 16px;
    border-radius: var(--radius);
    border: 1px solid var(--border);
    background: var(--surface);
}
.result-box.running { background: var(--yellow-dim); border-color: var(--yellow); }
.result-box.passed { background: rgba(46,204,113,0.08); border-color: var(--green); }
.result-box.failed { background: var(--red-dim); border-color: var(--red); }
.result-box p { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.result-box.running p { color: var(--yellow); }
.result-box.passed p { color: var(--green); }
.result-box.failed p { color: var(--red); }
.results-list { display: flex; flex-direction: column; gap: 8px; }
.result-row {
    padding: 10px 14px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
    font-family: monospace;
}
.result-row.pass { background: rgba(46,204,113,0.08); border: 1px solid rgba(46,204,113,0.2); color: var(--text-muted); }
.result-row.fail { background: var(--red-dim); border: 1px solid rgba(230,57,70,0.2); color: var(--text-muted); }
.result-row span:first-child { font-weight: 700; }
.result-row.pass span:first-child { color: var(--green); }
.result-row.fail span:first-child { color: var(--red); }
.err { color: var(--red); font-style: italic; }
</style>
