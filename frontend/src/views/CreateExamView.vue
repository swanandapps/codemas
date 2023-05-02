<template>
    <div class="create-container">
        <div class="header">
            <button class="back-btn" @click="router.push('/dashboard')">← Dashboard</button>
            <h1>Create Exam</h1>
        </div>

        <!-- Step Indicator -->
        <div class="steps">
            <div :class="['step', step >= 1 ? 'done' : '', step === 1 ? 'active' : '']">
                <span>1</span> Exam Details
            </div>
            <div class="step-line" />
            <div :class="['step', step >= 2 ? 'done' : '', step === 2 ? 'active' : '']">
                <span>2</span> Questions
            </div>
            <div class="step-line" />
            <div :class="['step', step >= 3 ? 'done' : '', step === 3 ? 'active' : '']">
                <span>3</span> Test Cases
            </div>
        </div>

        <!-- Step 1: Exam Details -->
        <div v-if="step === 1" class="step-content">
            <h2>Step 1 — Exam Details</h2>
            <form @submit.prevent="createExam">
                <label>Title</label>
                <input v-model="exam.title" placeholder="e.g. Python Basics" required />

                <label>Description</label>
                <textarea v-model="exam.description" placeholder="What is this exam about?" rows="3" />

                <label>Duration (minutes)</label>
                <input v-model.number="exam.duration_minutes" type="number" min="1" required />

                <label class="checkbox-label">
                    <input v-model="exam.is_active" type="checkbox" />
                    Make active immediately
                </label>

                <p v-if="error" class="error">{{ error }}</p>
                <button type="submit" :disabled="loading">
                    {{ loading ? 'Creating...' : 'Create Exam & Continue →' }}
                </button>
            </form>
        </div>

        <!-- Step 2: Questions -->
        <div v-if="step === 2" class="step-content">
            <h2>Step 2 — Add Questions</h2>
            <p class="subtitle">Exam: <strong>{{ createdExam?.title }}</strong></p>

            <!-- Added questions so far -->
            <div v-if="questions.length > 0" class="added-list">
                <div v-for="(q, i) in questions" :key="q.id" class="added-item">
                    <span>Q{{ i + 1 }}: {{ q.title }}</span>
                    <span class="lang-badge">{{ q.language }}</span>
                </div>
            </div>

            <form @submit.prevent="addQuestion">
                <label>Question Title</label>
                <input v-model="newQuestion.title" placeholder="e.g. Reverse a String" required />

                <label>Description</label>
                <textarea
                    v-model="newQuestion.description"
                    placeholder="Full problem statement shown to student..."
                    rows="4"
                    required
                />

                <label>Language</label>
                <select v-model="newQuestion.language">
                    <option value="python">Python</option>
                    <option value="javascript">JavaScript</option>
                    <option value="java">Java</option>
                </select>

                <label>Difficulty</label>
                <select v-model="newQuestion.difficulty">
                    <option value="easy">Easy (10 pts)</option>
                    <option value="medium">Medium (20 pts)</option>
                    <option value="hard">Hard (30 pts)</option>
                </select>

                <label>Tags <span style="font-weight:normal;color:#aaa">(comma-separated, e.g. string,two-pointer)</span></label>
                <input v-model="newQuestion.tags" placeholder="e.g. string, palindrome" />

                <label>Max Attempts</label>
                <input v-model.number="newQuestion.max_attempts" type="number" min="1" max="10" />

                <p v-if="qError" class="error">{{ qError }}</p>
                <div class="btn-row">
                    <button type="submit" :disabled="qLoading">
                        {{ qLoading ? 'Adding...' : '+ Add Question' }}
                    </button>
                    <button
                        type="button"
                        class="next-btn"
                        :disabled="questions.length === 0"
                        @click="step = 3"
                    >
                        Next: Add Test Cases →
                    </button>
                </div>
            </form>
        </div>

        <!-- Step 3: Test Cases -->
        <div v-if="step === 3" class="step-content">
            <h2>Step 3 — Add Test Cases</h2>
            <p class="subtitle">Exam: <strong>{{ createdExam?.title }}</strong></p>

            <!-- Question selector -->
            <div class="question-tabs">
                <button
                    v-for="(q, i) in questions"
                    :key="q.id"
                    :class="['q-tab', selectedQuestionIndex === i ? 'active' : '']"
                    @click="selectedQuestionIndex = i"
                >
                    Q{{ i + 1 }}: {{ q.title }}
                    <span class="tc-count">({{ testCases[q.id]?.length || 0 }} cases)</span>
                </button>
            </div>

            <!-- Test cases for selected question -->
            <div v-if="currentQuestion" class="tc-section">
                <h3>{{ currentQuestion.title }}</h3>

                <div v-if="testCases[currentQuestion.id]?.length" class="added-list">
                    <div
                        v-for="(tc, i) in testCases[currentQuestion.id]"
                        :key="tc.id"
                        class="added-item tc-row"
                    >
                        <span>Case {{ i + 1 }}</span>
                        <span>Input: <code>{{ tc.input_data }}</code></span>
                        <span>Expected: <code>{{ tc.expected_output }}</code></span>
                        <span :class="tc.is_hidden ? 'hidden-badge' : 'visible-badge'">
                            {{ tc.is_hidden ? 'Hidden' : 'Visible' }}
                        </span>
                    </div>
                </div>

                <form @submit.prevent="addTestCase">
                    <label>Input Data</label>
                    <textarea v-model="newTestCase.input_data" placeholder="e.g. hello" rows="2" required />

                    <label>Expected Output</label>
                    <textarea v-model="newTestCase.expected_output" placeholder="e.g. olleh" rows="2" required />

                    <label class="checkbox-label">
                        <input v-model="newTestCase.is_hidden" type="checkbox" />
                        Hidden (student won't see input/output)
                    </label>

                    <p v-if="tcError" class="error">{{ tcError }}</p>
                    <button type="submit" :disabled="tcLoading">
                        {{ tcLoading ? 'Adding...' : '+ Add Test Case' }}
                    </button>
                </form>
            </div>

            <div class="finish-row">
                <button class="finish-btn" @click="finish">
                    Finish & Go to Dashboard
                </button>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

interface CreatedExam {
    id: number
    title: string
}

interface Question {
    id: number
    title: string
    description: string
    language: string
    max_attempts: number
}

interface TestCase {
    id: number
    input_data: string
    expected_output: string
    is_hidden: boolean
}

const router = useRouter()

const step = ref<number>(1)

// Step 1
const exam = ref({ title: '', description: '', duration_minutes: 60, is_active: true })
const createdExam = ref<CreatedExam | null>(null)
const loading = ref<boolean>(false)
const error = ref<string>('')

// Step 2
const questions = ref<Question[]>([])
const newQuestion = ref({ title: '', description: '', language: 'python', difficulty: 'medium', tags: '', max_attempts: 3 })
const qLoading = ref<boolean>(false)
const qError = ref<string>('')

// Step 3
const testCases = ref<Record<number, TestCase[]>>({})
const selectedQuestionIndex = ref<number>(0)
const newTestCase = ref({ input_data: '', expected_output: '', is_hidden: false })
const tcLoading = ref<boolean>(false)
const tcError = ref<string>('')

const currentQuestion = computed<Question | null>(() =>
    questions.value[selectedQuestionIndex.value] ?? null
)

async function createExam(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
        const res = await api.post('/exams/', exam.value)
        createdExam.value = res.data
        step.value = 2
    } catch (e: any) {
        error.value = e.response?.data?.error || 'Failed to create exam'
    } finally {
        loading.value = false
    }
}

async function addQuestion(): Promise<void> {
    if (!createdExam.value) return
    qLoading.value = true
    qError.value = ''
    try {
        const res = await api.post(`/exams/${createdExam.value.id}/questions/`, newQuestion.value)
        questions.value.push(res.data)
        testCases.value[res.data.id] = []
        newQuestion.value = { title: '', description: '', language: 'python', difficulty: 'medium', tags: '', max_attempts: 3 }
    } catch (e: any) {
        qError.value = e.response?.data?.error || 'Failed to add question'
    } finally {
        qLoading.value = false
    }
}

async function addTestCase(): Promise<void> {
    if (!createdExam.value || !currentQuestion.value) return
    tcLoading.value = true
    tcError.value = ''
    try {
        const res = await api.post(
            `/exams/${createdExam.value.id}/questions/${currentQuestion.value.id}/testcases/`,
            newTestCase.value
        )
        testCases.value[currentQuestion.value.id].push(res.data)
        newTestCase.value = { input_data: '', expected_output: '', is_hidden: false }
    } catch (e: any) {
        tcError.value = e.response?.data?.error || 'Failed to add test case'
    } finally {
        tcLoading.value = false
    }
}

function finish(): void {
    router.push('/dashboard')
}
</script>

<style scoped>
.create-container { max-width: 700px; margin: 0 auto; }
.header {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-bottom: 28px;
}
.back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
}
.back-btn:hover { border-color: var(--border2); color: var(--text); }

.steps {
    display: flex;
    align-items: center;
    margin-bottom: 32px;
}
.step {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 14px;
    color: var(--text-dim);
    white-space: nowrap;
}
.step span {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-dim);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 13px;
}
.step.active { color: var(--text); }
.step.active span { background: var(--red); border-color: var(--red); color: white; }
.step.done span { background: rgba(46,204,113,0.15); border-color: var(--green); color: var(--green); }
.step-line { flex: 1; height: 1px; background: var(--border); margin: 0 12px; }

.step-content { display: flex; flex-direction: column; gap: 4px; }
.step-content h2 { margin-bottom: 4px; }
.subtitle { color: var(--text-dim); font-size: 14px; margin-bottom: 16px; }
form { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
label { font-size: 13px; font-weight: 600; color: var(--text-muted); margin-top: 4px; }
.checkbox-label {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: normal;
    color: var(--text-muted);
}
.checkbox-label input { width: auto; }

button[type="submit"] {
    padding: 10px 24px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    margin-top: 8px;
    align-self: flex-start;
    transition: background 0.15s;
}
button[type="submit"]:hover { background: var(--red-hover); }
button[type="submit"]:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-row { display: flex; gap: 12px; margin-top: 8px; }
.next-btn {
    padding: 10px 24px;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-muted);
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 14px;
    font-weight: 600;
    transition: all 0.15s;
}
.next-btn:hover:not(:disabled) { border-color: var(--border2); color: var(--text); }
.next-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.added-list { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.added-item {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: rgba(46,204,113,0.06);
    border: 1px solid rgba(46,204,113,0.2);
    border-radius: var(--radius-sm);
    font-size: 13px;
    color: var(--text-muted);
}
.lang-badge {
    padding: 2px 8px;
    background: rgba(46,204,113,0.15);
    color: var(--green);
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
}
.tc-row { flex-wrap: wrap; }
code {
    background: var(--surface3);
    padding: 2px 6px;
    border-radius: 3px;
    font-family: monospace;
    color: var(--text-muted);
}
.hidden-badge { color: var(--yellow); font-size: 11px; font-weight: 700; }
.visible-badge { color: var(--green); font-size: 11px; font-weight: 700; }

.question-tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.q-tab {
    padding: 7px 14px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
}
.q-tab:hover { border-color: var(--border2); color: var(--text); }
.q-tab.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.tc-count { font-size: 11px; opacity: 0.8; margin-left: 4px; }
.tc-section { margin-top: 8px; }

.finish-row { margin-top: 32px; border-top: 1px solid var(--border); padding-top: 24px; }
.finish-btn {
    padding: 12px 32px;
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text);
    border-radius: var(--radius-sm);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
}
.finish-btn:hover { border-color: var(--red); color: var(--red); }
.error { color: var(--red); font-size: 13px; padding: 8px 12px; background: var(--red-dim); border-radius: var(--radius-sm); }
</style>
