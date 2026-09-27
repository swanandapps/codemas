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
            <!-- AI exam generation (HITL: generate → review/edit → save) -->
            <div class="ai-gen-card">
                <div class="ai-gen-head">
                    <span class="ai-gen-icon">✦</span>
                    <span class="ai-gen-title">Generate with AI</span>
                    <span class="ai-gen-chip">GPT</span>
                </div>

                <div v-if="!draft" class="ai-gen-form">
                    <input v-model="gen.topic" placeholder="Topic — e.g. Python string manipulation, recursion, SQL joins" />
                    <div class="ai-gen-row">
                        <select v-model="gen.language">
                            <option value="python">Python</option>
                            <option value="javascript">JavaScript</option>
                            <option value="java">Java</option>
                            <option value="cpp">C++</option>
                        </select>
                        <select v-model="gen.difficulty">
                            <option value="easy">Easy</option>
                            <option value="medium">Medium</option>
                            <option value="hard">Hard</option>
                        </select>
                        <input v-model.number="gen.num_questions" type="number" min="1" max="10" title="Number of questions" />
                    </div>
                    <button type="button" class="gen-btn" :disabled="genLoading || !gen.topic.trim()" @click="generate">
                        {{ genLoading ? 'Generating…' : '✦ Generate Draft' }}
                    </button>
                    <p v-if="genError" class="error">{{ genError }}</p>
                </div>

                <!-- Review & edit the generated draft before saving -->
                <div v-else class="ai-draft">
                    <p class="ai-draft-note">Review and edit before saving — you have full control.</p>
                    <label>Exam Title</label>
                    <input v-model="draft.title" />
                    <label>Description</label>
                    <textarea v-model="draft.description" rows="2" />
                    <label>Duration (minutes)</label>
                    <input v-model.number="draft.duration_minutes" type="number" min="1" />

                    <div v-for="(q, qi) in draft.questions" :key="qi" class="draft-q">
                        <div class="draft-q-head">
                            <span class="draft-q-num">Q{{ qi + 1 }}</span>
                            <input v-model="q.title" class="draft-q-title" />
                            <select v-model="q.difficulty" class="draft-q-diff">
                                <option value="easy">Easy</option>
                                <option value="medium">Medium</option>
                                <option value="hard">Hard</option>
                            </select>
                            <button type="button" class="del-btn" @click="draft.questions.splice(qi, 1)">✕</button>
                        </div>
                        <textarea v-model="q.description" rows="3" class="draft-q-desc" />
                        <div class="draft-tcs">
                            <div v-for="(tc, ti) in q.test_cases" :key="ti" class="draft-tc">
                                <input v-model="tc.input_data" placeholder="input (stdin)" />
                                <span class="tc-arrow">→</span>
                                <input v-model="tc.expected_output" placeholder="expected output" />
                                <button type="button" class="del-btn" @click="q.test_cases.splice(ti, 1)">✕</button>
                            </div>
                            <button type="button" class="add-tc-btn" @click="q.test_cases.push({ input_data: '', expected_output: '' })">+ test case</button>
                        </div>
                    </div>

                    <p v-if="genError" class="error">{{ genError }}</p>
                    <div class="draft-actions">
                        <button type="button" class="discard-btn" @click="draft = null">Discard</button>
                        <button type="button" class="save-draft-btn" :disabled="saveLoading || !draft.questions.length" @click="saveDraft">
                            {{ saveLoading ? 'Saving…' : `Save Exam (${draft.questions.length} questions)` }}
                        </button>
                    </div>
                </div>
            </div>

            <div class="or-divider"><span>or create manually</span></div>

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

// AI exam generation (HITL: generate draft → review/edit → save)
interface DraftTestCase { input_data: string; expected_output: string }
interface DraftQuestion { title: string; description: string; difficulty: string; language?: string; test_cases: DraftTestCase[] }
interface ExamDraft { title: string; description: string; duration_minutes: number; questions: DraftQuestion[] }

const gen = ref({ topic: '', language: 'python', difficulty: 'medium', num_questions: 3 })
const genLoading = ref<boolean>(false)
const genError = ref<string>('')
const draft = ref<ExamDraft | null>(null)
const saveLoading = ref<boolean>(false)

async function generate(): Promise<void> {
    genLoading.value = true
    genError.value = ''
    try {
        const res = await api.post('/ai/generate-exam/', gen.value)
        draft.value = { ...res.data, duration_minutes: 60 }
    } catch (e: any) {
        genError.value = e.response?.data?.error || 'Generation failed'
    } finally {
        genLoading.value = false
    }
}

async function saveDraft(): Promise<void> {
    if (!draft.value) return
    saveLoading.value = true
    genError.value = ''
    try {
        const res = await api.post('/exams/create-full/', { ...draft.value, language: gen.value.language })
        router.push(`/exams/${res.data.id}`)
    } catch (e: any) {
        genError.value = e.response?.data?.error || 'Save failed'
    } finally {
        saveLoading.value = false
    }
}

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

/* AI exam generation */
.ai-gen-card {
    border: 1px solid var(--blue);
    border-radius: var(--radius);
    background: linear-gradient(180deg, var(--blue-dim), var(--surface) 70px);
    padding: 18px 20px;
    margin-bottom: 8px;
}
.ai-gen-head { display: flex; align-items: center; gap: 9px; margin-bottom: 14px; }
.ai-gen-icon {
    display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; border-radius: 7px; background: var(--blue); color: #fff;
}
.ai-gen-title { font-size: 15px; font-weight: 700; color: var(--text); }
.ai-gen-chip {
    font-size: 10px; font-weight: 700; letter-spacing: 0.5px; padding: 2px 8px;
    border-radius: 10px; background: var(--blue-dim); color: var(--blue); border: 1px solid var(--blue);
}
.ai-gen-form { display: flex; flex-direction: column; gap: 10px; }
.ai-gen-form input, .ai-gen-form select { margin: 0; }
.ai-gen-row { display: flex; gap: 10px; }
.ai-gen-row select, .ai-gen-row input { flex: 1; }
.gen-btn {
    align-self: flex-start; padding: 10px 22px; background: var(--blue); color: #fff;
    border: none; border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; cursor: pointer;
}
.gen-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.ai-draft { display: flex; flex-direction: column; gap: 8px; }
.ai-draft-note { font-size: 12px; color: var(--blue); margin: 0 0 4px; font-weight: 600; }
.draft-q {
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    background: var(--surface2); padding: 12px; margin-top: 10px;
}
.draft-q-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.draft-q-num { font-size: 12px; font-weight: 700; color: var(--text-dim); }
.draft-q-title { flex: 1; margin: 0; font-weight: 600; }
.draft-q-diff { width: auto; margin: 0; }
.draft-q-desc { margin: 0 0 8px; }
.draft-tcs { display: flex; flex-direction: column; gap: 6px; }
.draft-tc { display: flex; align-items: center; gap: 6px; }
.draft-tc input { margin: 0; font-family: monospace; font-size: 12px; }
.tc-arrow { color: var(--text-dim); }
.del-btn {
    background: transparent; border: 1px solid var(--border); color: var(--text-dim);
    border-radius: var(--radius-sm); width: 28px; height: 28px; cursor: pointer; flex-shrink: 0;
}
.del-btn:hover { border-color: var(--red); color: var(--red); }
.add-tc-btn {
    align-self: flex-start; background: transparent; border: 1px dashed var(--border);
    color: var(--text-muted); border-radius: var(--radius-sm); padding: 5px 12px; font-size: 12px; cursor: pointer;
}
.add-tc-btn:hover { border-color: var(--blue); color: var(--blue); }
.draft-actions { display: flex; gap: 12px; margin-top: 14px; }
.discard-btn {
    padding: 10px 20px; background: transparent; border: 1px solid var(--border);
    color: var(--text-muted); border-radius: var(--radius-sm); cursor: pointer; font-size: 14px;
}
.save-draft-btn {
    padding: 10px 24px; background: var(--blue); color: #fff; border: none;
    border-radius: var(--radius-sm); font-size: 14px; font-weight: 600; cursor: pointer;
}
.save-draft-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.or-divider {
    text-align: center; border-top: 1px solid var(--border);
    margin: 20px 0 8px; position: relative;
}
.or-divider span {
    position: relative; top: -10px; background: var(--bg); padding: 0 12px;
    font-size: 12px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 0.5px;
}
</style>
