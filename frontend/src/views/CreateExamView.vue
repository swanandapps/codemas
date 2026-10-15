<template>
    <div class="create-page" :class="`step-${step}`">
        <p v-if="restoredAt" class="restored-note" role="status">
            Restored your unsaved draft from {{ formatDateTime(restoredAt) }}.
            <button type="button" class="text-btn" @click="startOver">Start over</button>
        </p>

        <!-- A · Start: describe the exam and generate a draft, or write it yourself -->
        <section v-if="step === 'start'" class="start" aria-labelledby="start-title">
            <button type="button" class="text-btn back-link" @click="router.push('/dashboard')">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
                Back to dashboard
            </button>
            <h1 id="start-title" ref="stepHeading" tabindex="-1" class="page-title">Create exam</h1>
            <p class="page-sub">Describe the exam and get a full draft: questions, examples and hidden test cases. You review every question before students see anything.</p>

            <form class="card gen-card" @submit.prevent="generate">
                <label for="gen-topic" class="field-label big">What should this exam test?</label>
                <p id="gen-topic-hint" class="hint">Name the topic and level. The more specific, the better the questions.</p>
                <textarea
                    id="gen-topic" v-model="gen.topic" rows="4" aria-describedby="gen-topic-hint"
                    placeholder="e.g. Beginner JavaScript arrays: loops, filtering and two-pointer problems"
                    :disabled="genLoading"
                />

                <div class="gen-row">
                    <div class="field">
                        <label for="gen-lang" class="field-label">Language</label>
                        <select id="gen-lang" v-model="gen.language" :disabled="genLoading">
                            <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
                        </select>
                    </div>
                    <div class="field">
                        <label for="gen-count" class="field-label">Questions</label>
                        <select id="gen-count" v-model.number="gen.num_questions" :disabled="genLoading">
                            <option v-for="n in 10" :key="n" :value="n">{{ n }}</option>
                        </select>
                    </div>
                    <div class="field">
                        <label for="gen-duration" class="field-label">Duration</label>
                        <select id="gen-duration" v-model.number="gen.duration_minutes" :disabled="genLoading">
                            <option v-for="m in DURATIONS" :key="m" :value="m">{{ m }} min</option>
                        </select>
                    </div>
                </div>

                <fieldset class="field" :disabled="genLoading">
                    <legend class="field-label">Difficulty</legend>
                    <div class="segmented">
                        <label v-for="d in DIFFICULTIES" :key="d.value" class="seg">
                            <input v-model="gen.difficulty" type="radio" name="gen-difficulty" :value="d.value" class="sr-only" />
                            <span>{{ d.label }}</span>
                        </label>
                    </div>
                </fieldset>

                <p v-if="genError" class="error" role="alert">{{ genError }}</p>

                <div class="gen-foot">
                    <p class="hint">Takes about 20 seconds. Nothing is published until you activate the exam.</p>
                    <button type="submit" class="btn-primary" :disabled="genLoading">
                        <span v-if="genLoading" class="spinner" aria-hidden="true"></span>
                        <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15v5M16.5 17.5h5"/></svg>
                        {{ genLoading ? 'Generating draft…' : 'Generate draft' }}
                    </button>
                </div>
                <p class="sr-only" aria-live="polite">{{ genLoading ? 'Generating the draft. This takes about 20 seconds.' : '' }}</p>
            </form>

            <div class="or-divider" role="separator"><span>or</span></div>

            <button type="button" class="card link-card" :disabled="genLoading" @click="writeYourself">
                <span class="link-card-text">
                    <span class="link-card-title">Write it yourself</span>
                    <span class="link-card-sub">Start with an empty exam and add your own questions and test cases.</span>
                </span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="9 18 15 12 9 6"/></svg>
            </button>
        </section>

        <!-- B · Review draft: every question as students will read it, plus the save checklist -->
        <section v-else-if="step === 'review' && draft" class="review" aria-labelledby="review-title">
            <div class="review-main">
                <span class="chip chip-draft"><span class="dot" aria-hidden="true"></span>Draft · students can't see this</span>
                <h1 id="review-title" ref="stepHeading" tabindex="-1" class="sr-only">Review draft</h1>
                <label for="exam-title" class="sr-only">Exam title</label>
                <input id="exam-title" :value="examTitleValue" class="title-input" :placeholder="examTitleFallback" @input="onExamTitle" />
                <label for="exam-desc" class="sr-only">Exam description</label>
                <textarea id="exam-desc" v-model="draft.description" class="desc-input" rows="2" placeholder="Add a short description for students" />

                <div class="q-list-head">
                    <h2 class="section-title">Questions <span class="count">{{ draft.questions.length }}</span></h2>
                    <span class="hint">Shown below as students will read them</span>
                </div>

                <!-- Generation came back with no questions: keep the inputs, offer a retry or manual entry -->
                <div v-if="!draft.questions.length" class="card empty-card">
                    <svg class="empty-icon" width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                    <h3 class="empty-title">The draft came back without questions</h3>
                    <p class="empty-text">The exam title and description were written, but no questions came with them, so there's nothing to save yet. Your topic and settings are kept.</p>
                    <p v-if="genError" class="error" role="alert">{{ genError }}</p>
                    <div class="btn-row">
                        <button type="button" class="btn-primary" :disabled="genLoading" @click="generate">
                            <span v-if="genLoading" class="spinner" aria-hidden="true"></span>
                            {{ genLoading ? 'Generating draft…' : 'Try again' }}
                        </button>
                        <button type="button" class="btn-secondary" :disabled="genLoading" @click="addQuestion">Write the questions yourself</button>
                    </div>
                </div>

                <article v-for="(q, qi) in draft.questions" :key="q.key" class="card q-card" :class="{ open: openCard === qi }">
                    <div class="q-card-head">
                        <span class="chip chip-q">Q{{ qi + 1 }}</span>
                        <h3 class="q-card-title">{{ questionTitle(q, qi) }}</h3>
                        <span class="chip" :class="`diff-${q.difficulty}`">{{ difficultyLabel(q.difficulty) }} · {{ DIFFICULTY_POINTS[q.difficulty] }} marks</span>
                        <div class="q-card-actions">
                            <button type="button" class="icon-btn" :aria-label="`Edit Q${qi + 1}`" @click="openEditor(qi)">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>
                            </button>
                            <button type="button" class="icon-btn danger" :aria-label="`Delete Q${qi + 1}`" @click="deleteQuestion(qi)">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/></svg>
                            </button>
                        </div>
                    </div>

                    <div v-if="openCard === qi" :id="`q-card-body-${qi}`" class="q-card-body">
                        <QuestionStatement :description="composeDescription(q.fields)" :test-cases="filledCases(q)" />
                        <!-- the trainer checks every test here, hidden ones included (students only see the shown ones) -->
                        <section v-if="filledCases(q).length" class="all-cases" :aria-labelledby="`all-cases-h-${qi}`">
                            <h4 :id="`all-cases-h-${qi}`" class="all-cases-h">All test cases <span>· only you see this</span></h4>
                            <div class="all-cases-scroll">
                                <table class="all-cases-table">
                                    <thead><tr><th scope="col">#</th><th scope="col">Input</th><th scope="col">Expected output</th><th scope="col">Students</th></tr></thead>
                                    <tbody>
                                        <tr v-for="(tc, ci) in filledCases(q)" :key="ci">
                                            <td>{{ ci + 1 }}</td>
                                            <td><pre>{{ tc.input_data }}</pre></td>
                                            <td><pre>{{ tc.expected_output }}</pre></td>
                                            <td><span :class="tc.is_hidden ? 'tc-hidden' : 'tc-shown'">{{ tc.is_hidden ? 'Hidden' : 'Shown' }}</span></td>
                                        </tr>
                                    </tbody>
                                </table>
                            </div>
                        </section>
                    </div>
                    <div v-else class="q-card-summary">{{ q.fields.problem.split('\n')[0] || 'No problem statement yet' }}</div>

                    <div class="q-card-foot">
                        <span>{{ caseSummary(q) }}</span>
                        <button
                            type="button" class="text-btn"
                            :aria-expanded="openCard === qi" :aria-controls="`q-card-body-${qi}`"
                            :aria-label="`${openCard === qi ? 'Hide' : 'Show'} Q${qi + 1} as students see it`"
                            @click="openCard = openCard === qi ? null : qi"
                        >{{ openCard === qi ? 'Hide' : 'Show' }}</button>
                    </div>
                </article>

                <button v-if="draft.questions.length" type="button" class="add-dashed" @click="addQuestion">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    Add a question
                </button>
            </div>

            <aside class="review-side" aria-label="Exam settings and save">
                <div class="card side-card">
                    <h2 class="side-title">Exam settings</h2>
                    <div class="field">
                        <label for="set-duration" class="field-label">Duration</label>
                        <select id="set-duration" v-model.number="draft.duration_minutes">
                            <option v-for="m in DURATIONS" :key="m" :value="m">{{ m }} min</option>
                        </select>
                    </div>
                    <div class="field">
                        <label for="set-lang" class="field-label">Language</label>
                        <select id="set-lang" v-model="draft.language">
                            <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
                        </select>
                    </div>
                    <dl class="stats">
                        <div><dt>Questions</dt><dd>{{ draft.questions.length }}</dd></div>
                        <div><dt>Total marks</dt><dd>{{ totalMarks }}</dd></div>
                    </dl>
                </div>

                <div class="card side-card">
                    <h2 class="side-title">Ready to save</h2>
                    <PublishChoice
                        v-model:when="when" v-model:start="schedStart" v-model:end="schedEnd" v-model:picked="picked"
                        id-prefix="review" :sections="sections" :problems="schedProblems"
                    />
                    <ul class="checklist">
                        <li v-for="(c, i) in checklist" :key="i" :class="c.kind">
                            <svg v-if="c.kind === 'ok'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>
                            <svg v-else-if="c.kind === 'warn'" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                            <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                            <span><span class="sr-only">{{ CHECK_PREFIX[c.kind] }}</span>{{ c.text }}</span>
                        </li>
                    </ul>
                    <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
                    <div class="side-actions">
                        <button type="button" class="btn-primary" :disabled="saveLoading || blockers.length > 0" @click="save">
                            {{ saveLoading ? 'Saving…' : saveLabel }}
                        </button>
                        <button type="button" class="btn-secondary" :disabled="saveLoading" @click="discard">Discard</button>
                    </div>
                    <p class="hint">{{ saveNote }}</p>
                </div>
            </aside>
        </section>

        <!-- C · Editor: structured fields on the left, the student's view on the right -->
        <section v-else-if="step === 'editor' && draft && currentQ" class="editor" aria-labelledby="editor-title">
            <div class="editor-bar">
                <div class="editor-bar-title">
                    <h1 id="editor-title" ref="stepHeading" tabindex="-1" class="sr-only">Edit questions</h1>
                    <label for="editor-exam-title" class="sr-only">Exam title</label>
                    <input id="editor-exam-title" :value="examTitleValue" class="title-input small" :placeholder="examTitleFallback" @input="onExamTitle" />
                    <div class="editor-bar-meta">
                        <span class="chip chip-draft"><span class="dot" aria-hidden="true"></span>Draft</span>
                        <span class="hint">{{ examSummary }}</span>
                    </div>
                </div>
                <div class="editor-bar-actions">
                    <button type="button" class="btn-secondary" @click="backToReview">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="15 18 9 12 15 6"/></svg>
                        Back to review
                    </button>
                    <button type="button" class="btn-primary" :disabled="saveLoading || blockers.length > 0" aria-describedby="editor-save-reason" @click="save">
                        {{ saveLoading ? 'Saving…' : saveLabel }}
                    </button>
                </div>
                <PublishChoice
                    v-model:when="when" v-model:start="schedStart" v-model:end="schedEnd" v-model:picked="picked"
                    class="editor-publish" id-prefix="editor" compact
                    :sections="sections" :problems="schedProblems"
                />
                <p v-if="blockers.length" id="editor-save-reason" class="save-reason">Can't save yet: {{ blockers.join('; ') }}</p>
                <p v-if="saveError" class="error" role="alert">{{ saveError }}</p>
            </div>

            <nav class="q-tabs" aria-label="Questions">
                <button
                    v-for="(q, qi) in draft.questions" :key="q.key" type="button" class="q-tab"
                    :class="{ active: current === qi }" :aria-current="current === qi ? 'true' : undefined"
                    @click="current = qi"
                >Q{{ qi + 1 }} · {{ questionTitle(q, qi) }}</button>
                <button type="button" class="q-tab add" @click="addQuestion">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                    Add question
                </button>
            </nav>

            <div class="editor-grid">
                <form class="card editor-form" :aria-label="`Q${current + 1} details`" @submit.prevent>
                    <div class="field">
                        <label for="q-title" class="field-label">Question title</label>
                        <p id="q-title-hint" class="hint">Filled in from the problem until you type your own</p>
                        <input id="q-title" :value="questionTitleValue(currentQ)" :placeholder="questionTitle(currentQ, current)" aria-describedby="q-title-hint" @input="onQuestionTitle(currentQ, $event)" />
                    </div>

                    <fieldset class="field">
                        <legend class="field-label">Difficulty</legend>
                        <div class="segmented">
                            <label v-for="d in DIFFICULTIES" :key="d.value" class="seg">
                                <input v-model="currentQ.difficulty" type="radio" name="q-difficulty" :value="d.value" class="sr-only" />
                                <span>{{ d.label }} · {{ DIFFICULTY_POINTS[d.value] }}</span>
                            </label>
                        </div>
                    </fieldset>

                    <div class="field">
                        <label for="q-problem" class="field-label">Problem</label>
                        <textarea id="q-problem" v-model="currentQ.fields.problem" rows="6" placeholder="What the student has to do. Leave a blank line between paragraphs." />
                    </div>
                    <div class="field">
                        <label for="q-input" class="field-label">Input format</label>
                        <p id="q-input-hint" class="hint">One line per line of input</p>
                        <textarea id="q-input" v-model="currentQ.fields.inputFormat" rows="3" aria-describedby="q-input-hint" placeholder="e.g. First line: n, the number of elements" />
                    </div>
                    <div class="field">
                        <label for="q-output" class="field-label">Output format</label>
                        <textarea id="q-output" v-model="currentQ.fields.outputFormat" rows="2" placeholder="e.g. Print the reversed string" />
                    </div>
                    <div class="field">
                        <label for="q-constraints" class="field-label">Constraints</label>
                        <textarea id="q-constraints" v-model="currentQ.fields.constraints" rows="3" placeholder="e.g. 1 <= n <= 1000" />
                    </div>

                    <div class="field">
                        <h2 id="tc-title" class="field-label">Test cases</h2>
                        <p class="hint">Checked cases are shown to students as examples. The rest stay hidden and are used for grading.</p>
                        <div class="tc-table" role="group" aria-labelledby="tc-title">
                            <div class="tc-head" aria-hidden="true">
                                <span>Input</span><span>Expected output</span><span>Example</span><span></span>
                            </div>
                            <!-- textareas, not inputs: a text input drops the line breaks multi-line stdin needs -->
                            <div v-for="(tc, ti) in currentQ.test_cases" :key="ti" class="tc-row">
                                <textarea
                                    v-model="tc.input_data" :rows="lineCount(tc.input_data)" class="mono" spellcheck="false"
                                    :aria-label="`Test case ${ti + 1} input`" placeholder="Input"
                                />
                                <textarea
                                    v-model="tc.expected_output" :rows="lineCount(tc.expected_output)" class="mono" spellcheck="false"
                                    :aria-label="`Test case ${ti + 1} expected output`" placeholder="Expected output"
                                />
                                <label class="tc-example">
                                    <input
                                        type="checkbox" :checked="!tc.is_hidden"
                                        :aria-label="`Show test case ${ti + 1} to students as an example`"
                                        @change="setShown(tc, $event)"
                                    />
                                    <span :class="tc.is_hidden ? 'tc-hidden' : 'tc-shown'">{{ tc.is_hidden ? 'Hidden' : 'Shown' }}</span>
                                </label>
                                <button type="button" class="icon-btn danger" :aria-label="`Remove test case ${ti + 1}`" @click="currentQ.test_cases.splice(ti, 1)">
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                                </button>
                            </div>
                        </div>
                        <button type="button" class="add-dashed small" @click="addTestCase">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                            Add test case
                        </button>
                    </div>

                    <details class="more">
                        <summary>More options</summary>
                        <div class="more-body">
                            <div class="field">
                                <label for="q-tags" class="field-label">Tags</label>
                                <p id="q-tags-hint" class="hint">Comma-separated, e.g. string, two-pointer</p>
                                <input id="q-tags" v-model="currentQ.tags" aria-describedby="q-tags-hint" placeholder="e.g. string, palindrome" />
                            </div>
                            <div class="field">
                                <label for="q-lang" class="field-label">Language</label>
                                <select id="q-lang" v-model="currentQ.language">
                                    <option value="">Same as the exam ({{ languageLabel(draft.language) }})</option>
                                    <option v-for="l in LANGUAGES" :key="l.value" :value="l.value">{{ l.label }}</option>
                                </select>
                            </div>
                            <div class="field">
                                <label for="q-note" class="field-label">Note</label>
                                <p id="q-note-hint" class="hint">Shown to students under its own heading, after the constraints</p>
                                <textarea id="q-note" v-model="currentQ.fields.note" rows="2" aria-describedby="q-note-hint" />
                            </div>
                            <p class="hint">Starter code is optional: leave it empty for the default that hands the student every input line.</p>
                            <div class="field">
                                <label for="q-starter-js" class="field-label">Starter code · JavaScript</label>
                                <textarea id="q-starter-js" v-model="currentQ.starter_code.javascript" rows="8" class="mono" spellcheck="false"
                                    placeholder="Read the input, then call a function the student completes, e.g. countOccurrences(arr, target)" />
                            </div>
                            <div class="field">
                                <label for="q-starter-py" class="field-label">Starter code · Python</label>
                                <textarea id="q-starter-py" v-model="currentQ.starter_code.python" rows="8" class="mono" spellcheck="false" />
                            </div>
                        </div>
                    </details>
                </form>

                <aside class="card preview" aria-label="Student preview">
                    <p class="preview-label">Student preview, updates as you type</p>
                    <!-- Same head and statement as the exam page -->
                    <div class="preview-head">
                        <h2 class="preview-title">{{ questionTitle(currentQ, current) }}</h2>
                        <div class="preview-meta">
                            <span :class="`ink-${currentQ.difficulty}`">{{ difficultyLabel(currentQ.difficulty) }}</span>
                            <span>{{ filledCases(currentQ).length }} test cases</span>
                            <span>{{ DIFFICULTY_POINTS[currentQ.difficulty] }} marks</span>
                        </div>
                    </div>
                    <QuestionStatement :description="composeDescription(currentQ.fields)" :test-cases="filledCases(currentQ)" />
                </aside>
            </div>
        </section>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { saveDraft, loadDraft, clearDraft } from '../utils/createExamDraft'
import { formatDateTime } from '../utils/format'
import api from '../api'
import QuestionStatement from '../components/QuestionStatement.vue'
import PublishChoice, { type PublishWhen } from '../components/PublishChoice.vue'
import { composeDescription, decomposeDescription, emptyFields, shortTitle, type QuestionFields } from '../utils/questionFields'
import { DIFFICULTY_POINTS, scheduleProblems, toLocalInput, type Difficulty, type ScheduleProblems } from '../utils/exams'

type Step = 'start' | 'review' | 'editor'
type Language = 'javascript' | 'python'

interface DraftTestCase { input_data: string; expected_output: string; is_hidden: boolean }
interface DraftQuestion {
    key: number                       // stable v-for key; questions have no id until saved
    title: string
    titleAuto: boolean                // title follows the problem text until the trainer types one
    difficulty: Difficulty
    fields: QuestionFields            // joined into the one description field on save
    language: '' | Language           // '' = the exam's language
    tags: string
    starter_code: { javascript: string; python: string }
    test_cases: DraftTestCase[]
}
interface ExamDraft {
    title: string
    titleAuto: boolean                // title follows the first question until the trainer types one
    description: string
    duration_minutes: number
    language: Language
    questions: DraftQuestion[]
}

// Shape returned by /ai/generate-exam/
interface GeneratedQuestion {
    title?: string; description?: string; difficulty?: string; language?: string
    test_cases?: { input_data?: string; expected_output?: string; is_hidden?: boolean }[]
    starter_code?: { javascript?: string; python?: string }
}

const LANGUAGES: { value: Language; label: string }[] = [
    { value: 'javascript', label: 'JavaScript' },
    { value: 'python', label: 'Python' },
]
const DIFFICULTIES: { value: Difficulty; label: string }[] = [
    { value: 'easy', label: 'Easy' },
    { value: 'medium', label: 'Medium' },
    { value: 'hard', label: 'Hard' },
]
const DURATIONS = [15, 30, 45, 60, 90, 120, 180]
const CHECK_PREFIX = { ok: 'Done: ', warn: 'Warning: ', block: 'Needed before saving: ' }

const router = useRouter()

const step = ref<Step>('start')
const stepHeading = ref<HTMLElement | null>(null)
const draft = ref<ExamDraft | null>(null)
const openCard = ref<number | null>(0)   // review card shown in full
const current = ref<number>(0)           // question open in the editor
let nextKey = 1

// 30 minutes per question by default; the trainer can pick another length
function suggestedDuration(questions: number): number {
    return DURATIONS.find(m => m >= 30 * questions) ?? 180
}

const gen = ref({ topic: '', language: 'javascript' as Language, difficulty: 'medium' as Difficulty, num_questions: 3, duration_minutes: 90 })
watch(() => gen.value.num_questions, n => { gen.value.duration_minutes = suggestedDuration(n) })
const genLoading = ref<boolean>(false)
const genError = ref<string>('')
const saveLoading = ref<boolean>(false)
const saveError = ref<string>('')

// Each step starts at the top, with focus on its heading for screen readers
watch(step, async () => {
    await nextTick()
    window.scrollTo(0, 0)
    stepHeading.value?.focus()
})

function difficultyLabel(d: Difficulty): string {
    return DIFFICULTIES.find(x => x.value === d)?.label ?? d
}
function languageLabel(l: Language): string {
    return LANGUAGES.find(x => x.value === l)?.label ?? l
}

// Show every line of a test case (n / array / target) without scrolling
function lineCount(text: string): number {
    return Math.max(1, text.replace(/\n+$/, '').split('\n').length)
}

function blankQuestion(): DraftQuestion {
    return {
        key: nextKey++, title: '', titleAuto: true, difficulty: 'medium', fields: emptyFields(), language: '', tags: '',
        starter_code: { javascript: '', python: '' },
        test_cases: [{ input_data: '', expected_output: '', is_hidden: false }],
    }
}

function fromGenerated(q: GeneratedQuestion, examLanguage: Language): DraftQuestion {
    const difficulty = (q.difficulty && q.difficulty in DIFFICULTY_POINTS ? q.difficulty : 'medium') as Difficulty
    return {
        key: nextKey++,
        title: q.title || '',
        titleAuto: !q.title,
        difficulty,
        fields: decomposeDescription(q.description),
        language: q.language && q.language !== examLanguage ? (q.language as Language) : '',
        tags: '',
        starter_code: { javascript: q.starter_code?.javascript || '', python: q.starter_code?.python || '' },
        test_cases: (q.test_cases || []).map(tc => ({
            input_data: tc.input_data ?? '', expected_output: tc.expected_output ?? '', is_hidden: tc.is_hidden ?? true,
        })),
    }
}

// ── Titles: filled in for the trainer, never required ───────────────────────

/** The title a question is saved and shown with: the trainer's own, else from the problem, else "Question N". */
function questionTitle(q: DraftQuestion, index: number): string {
    return (q.titleAuto ? '' : q.title.trim()) || shortTitle(q.fields.problem) || `Question ${index + 1}`
}
function questionTitleValue(q: DraftQuestion): string {
    return q.titleAuto ? shortTitle(q.fields.problem) : q.title
}
function onQuestionTitle(q: DraftQuestion, e: Event): void {
    q.title = (e.target as HTMLInputElement).value
    q.titleAuto = false   // typed by the trainer: stop following the problem (left empty, it falls back again)
}

// First question's title, unless that would only be the "Question 1" fallback
const firstQuestionTitle = computed<string>(() => {
    const q = draft.value?.questions[0]
    return q ? (q.titleAuto ? '' : q.title.trim()) || shortTitle(q.fields.problem) : ''
})
const examTitleFallback = computed<string>(() => firstQuestionTitle.value || 'Untitled exam')
const examTitleValue = computed<string>(() => draft.value?.titleAuto ? firstQuestionTitle.value : draft.value?.title ?? '')
const examTitle = computed<string>(() => (draft.value?.titleAuto ? '' : draft.value?.title.trim()) || examTitleFallback.value)
function onExamTitle(e: Event): void {
    if (!draft.value) return
    draft.value.title = (e.target as HTMLInputElement).value
    draft.value.titleAuto = false
}

/** Test cases with something in them; a row left fully blank is not saved. */
function filledCases(q: DraftQuestion): DraftTestCase[] {
    return q.test_cases.filter(tc => tc.input_data.trim() || tc.expected_output.trim())
}

function caseSummary(q: DraftQuestion): string {
    const cases = filledCases(q)
    if (!cases.length) return 'No test cases yet'
    const shown = cases.filter(tc => !tc.is_hidden).length
    const plural = cases.length === 1 ? '' : 's'
    const shownText = shown === 0 ? 'none shown as an example' : `${shown} shown as ${shown === 1 ? 'the example' : 'examples'}`
    return `${cases.length} test case${plural}: ${shownText}, ${cases.length - shown} hidden for grading`
}

// ── A · Start ────────────────────────────────────────────────────────────────

async function generate(): Promise<void> {
    if (!gen.value.topic.trim()) {
        genError.value = 'Describe what the exam should test first.'
        return
    }
    genLoading.value = true
    genError.value = ''
    const { topic, language, difficulty, num_questions, duration_minutes } = gen.value
    try {
        const res = await api.post('/ai/generate-exam/', { topic, language, difficulty, num_questions })
        // A missing title comes from the topic the trainer typed
        const title = res.data.title || shortTitle(topic)
        draft.value = {
            title,
            titleAuto: !title,
            description: res.data.description || '',
            duration_minutes,
            language,
            questions: ((res.data.questions || []) as GeneratedQuestion[]).map(q => fromGenerated(q, language)),
        }
        openCard.value = 0
        step.value = 'review'
    } catch (e: any) {
        genError.value = e.response?.data?.error || "Couldn't generate the draft. Check your connection and try again."
    } finally {
        genLoading.value = false
    }
}

function writeYourself(): void {
    draft.value = {
        title: '', titleAuto: true, description: '', duration_minutes: gen.value.duration_minutes, language: gen.value.language,
        questions: [blankQuestion()],
    }
    current.value = 0
    step.value = 'editor'
}

// ── B · Review ───────────────────────────────────────────────────────────────

const totalMarks = computed<number>(() =>
    (draft.value?.questions || []).reduce((sum, q) => sum + DIFFICULTY_POINTS[q.difficulty], 0))

const examSummary = computed<string>(() => {
    const n = draft.value?.questions.length || 0
    return `${n} question${n === 1 ? '' : 's'} · ${totalMarks.value} marks · ${draft.value?.duration_minutes} min`
})

// ── Publishing: go live, schedule or keep as a draft (same calls as the exam report's publish card) ──

// Owner's choice: saving goes live by default (the button says "Save and go live", so it's never a surprise)
const when = ref<PublishWhen>('live')
const schedStart = ref<string>('')
const schedEnd = ref<string>('')
const picked = ref<string[]>([])   // none = the whole cohort
const sections = ref<{ name: string; students: number }[]>([])

// ── Unsaved work survives a reload: kept in this browser per trainer until saved or started over ──
const trainer = useAuthStore().user?.username
const restoredAt = ref<number | null>(null)
const freshGen = () => ({ topic: '', language: 'javascript' as Language, difficulty: 'medium' as Difficulty, num_questions: 3, duration_minutes: 90 })

function snapshot() {
    return { step: step.value, gen: gen.value, draft: draft.value, current: current.value, openCard: openCard.value,
             when: when.value, schedStart: schedStart.value, schedEnd: schedEnd.value, picked: picked.value }
}

const saved = loadDraft(trainer)
if (saved && (saved.draft || saved.gen?.topic)) {
    gen.value = { ...freshGen(), ...saved.gen }
    draft.value = saved.draft ?? null
    step.value = saved.draft ? saved.step : 'start'
    current.value = saved.current ?? 0
    openCard.value = saved.openCard ?? 0
    schedStart.value = saved.schedStart ?? ''
    schedEnd.value = saved.schedEnd ?? ''
    when.value = saved.when ?? when.value
    picked.value = saved.picked ?? []
    nextKey = Math.max(0, ...(saved.draft?.questions ?? []).map((q: DraftQuestion) => q.key)) + 1
    restoredAt.value = saved.savedAt
    // the question-count watcher re-suggests a duration when the count changes: keep the saved one
    nextTick(() => { gen.value.duration_minutes = saved.gen?.duration_minutes ?? gen.value.duration_minutes })
}

watch(snapshot, s => {
    if (s.step === 'start' && !s.draft && !s.gen.topic.trim()) clearDraft(trainer)
    else saveDraft(trainer, s)
}, { deep: true })

function startOver(): void {
    clearDraft(trainer)
    restoredAt.value = null
    gen.value = freshGen()
    draft.value = null
    current.value = 0
    openCard.value = 0
    when.value = 'live'
    schedStart.value = ''
    schedEnd.value = ''
    picked.value = []
    genError.value = ''
    saveError.value = ''
    step.value = 'start'
}

onMounted(async () => {
    const res = await api.get('/exams/sections/').catch(() => null)
    sections.value = Array.isArray(res?.data) ? res.data : []
})

// Picking Schedule fills in the next full hour, closing one exam length later; both stay editable
watch(when, w => {
    if (w !== 'schedule' || schedStart.value) return
    const opens = new Date()
    opens.setHours(opens.getHours() + 1, 0, 0, 0)
    schedStart.value = toLocalInput(opens)
    if (!schedEnd.value) schedEnd.value = toLocalInput(new Date(opens.getTime() + (draft.value?.duration_minutes ?? 60) * 60_000))
})

const schedProblems = computed<ScheduleProblems>(() =>
    when.value === 'schedule' ? scheduleProblems(schedStart.value, schedEnd.value) : {})

const saveLabel = computed<string>(() =>
    ({ live: 'Save and go live', schedule: 'Save and schedule', draft: 'Save draft' })[when.value])

const audienceLabel = computed<string>(() => picked.value.length ? picked.value.join(', ') : 'the whole cohort')
const saveNote = computed<string>(() => ({
    live: `Every student in ${audienceLabel.value} sees it as soon as you save.`,
    schedule: 'It opens and closes at those times on its own.',
    draft: "Saved drafts stay hidden. Activate the exam from its page when you're ready, and pick which sections take it.",
})[when.value])

// Reasons Save stays disabled: only what would leave students with a question they can't attempt
const blockers = computed<string[]>(() => {
    const d = draft.value
    if (!d) return []
    const out: string[] = []
    if (!d.questions.length) out.push('Add at least one question')
    d.questions.forEach((q, i) => {
        if (!q.fields.problem.trim()) out.push(`Q${i + 1} needs a problem statement`)
        if (!filledCases(q).length) out.push(`Q${i + 1} has no test cases`)
    })
    const sp = schedProblems.value
    if (sp.start) out.push(sp.start)
    if (sp.end) out.push(sp.end)
    return out
})

// Live checklist: passed checks, then warnings (don't block), then blockers
const checklist = computed<{ kind: 'ok' | 'warn' | 'block'; text: string }[]>(() => {
    const qs = draft.value?.questions || []
    const items: { kind: 'ok' | 'warn' | 'block'; text: string }[] = []
    const noExample = qs.filter(q => !filledCases(q).some(tc => !tc.is_hidden))
    const noHidden = qs.filter(q => !filledCases(q).some(tc => tc.is_hidden))
    const label = (q: DraftQuestion) => `Q${qs.indexOf(q) + 1}`
    if (qs.length) {
        if (!noExample.length) items.push({ kind: 'ok', text: 'Every question has an example' })
        if (!noHidden.length) items.push({ kind: 'ok', text: 'Every question has hidden test cases' })
    }
    // A question with no test cases at all is already a blocker; don't repeat it as a warning
    noExample.filter(q => filledCases(q).length).forEach(q => items.push({ kind: 'warn', text: `${label(q)} has no example shown to students` }))
    noHidden.filter(q => filledCases(q).length).forEach(q => items.push({ kind: 'warn', text: `${label(q)} has no hidden test cases` }))
    qs.filter(q => !q.fields.constraints.trim()).forEach(q => items.push({ kind: 'warn', text: `${label(q)} has no constraints yet` }))
    // A closing time sooner than the exam length cuts students short
    const d = draft.value
    if (d && when.value === 'schedule' && schedEnd.value && !blockers.value.length) {
        const openMinutes = (new Date(schedEnd.value).getTime() - new Date(schedStart.value).getTime()) / 60_000
        if (openMinutes < d.duration_minutes) items.push({ kind: 'warn', text: `It closes ${Math.round(openMinutes)} min after opening, before students could use all ${d.duration_minutes} min` })
    }
    blockers.value.forEach(text => items.push({ kind: 'block', text }))
    return items
})

function addQuestion(): void {
    if (!draft.value) return
    draft.value.questions.push(blankQuestion())
    current.value = draft.value.questions.length - 1
    step.value = 'editor'
}

function deleteQuestion(qi: number): void {
    if (!draft.value) return
    draft.value.questions.splice(qi, 1)
    if (openCard.value === qi) openCard.value = draft.value.questions.length ? Math.min(qi, draft.value.questions.length - 1) : null
    else if (openCard.value !== null && openCard.value > qi) openCard.value--
}

function discard(): void {
    // Topic and settings stay filled in on the start step
    draft.value = null
    genError.value = ''
    saveError.value = ''
    step.value = 'start'
}

async function save(): Promise<void> {
    const d = draft.value
    if (!d || blockers.value.length) return
    // Time moves on while the page is open: check the schedule again now
    if (when.value === 'schedule') {
        const sp = scheduleProblems(schedStart.value, schedEnd.value)
        if (sp.start || sp.end) { saveError.value = sp.start || sp.end || ''; return }
    }
    saveLoading.value = true
    saveError.value = ''
    let examId: number
    try {
        const res = await api.post('/exams/create-full/', {
            title: examTitle.value,
            description: d.description,
            duration_minutes: d.duration_minutes,
            language: d.language,
            sections: picked.value,
            questions: d.questions.map((q, i) => ({
                title: questionTitle(q, i),
                description: composeDescription(q.fields),
                difficulty: q.difficulty,
                language: q.language || d.language,
                tags: q.tags.trim(),
                starter_code: q.starter_code,
                test_cases: filledCases(q),
            })),
        })
        examId = res.data.id
    } catch (e: any) {
        saveError.value = e.response?.data?.error || "Couldn't save the exam. Check your connection and try again."
        saveLoading.value = false
        return
    }

    // Same PATCH the exam report's publish card sends: going live enrolls the audience; a schedule opens it on time
    let notice = ''
    if (when.value !== 'draft') {
        try {
            await api.patch(`/exams/${examId}/`, when.value === 'live'
                ? { is_active: true, sections: picked.value }
                : {
                    start_time: new Date(schedStart.value).toISOString(),
                    end_time: schedEnd.value ? new Date(schedEnd.value).toISOString() : null,
                    sections: picked.value,
                })
        } catch {
            // The exam itself is saved: say so on its report's publish card, where it can be activated or scheduled again
            notice = when.value === 'live'
                ? "The exam was saved as a draft, but it couldn't go live. Activate it below."
                : "The exam was saved as a draft, but the schedule couldn't be set. Set it below."
        }
    }
    saveLoading.value = false
    clearDraft(trainer)   // saved for real: nothing left to restore
    router.push({ path: `/dashboard/history/${examId}`, state: notice ? { notice } : undefined })
}

// ── C · Editor ───────────────────────────────────────────────────────────────

const currentQ = computed<DraftQuestion | null>(() => draft.value?.questions[current.value] ?? null)

function openEditor(qi: number): void {
    current.value = qi
    step.value = 'editor'
}

function backToReview(): void {
    openCard.value = current.value
    step.value = 'review'
}

// Checked = shown to students as an example
function setShown(tc: DraftTestCase, e: Event): void {
    tc.is_hidden = !(e.target as HTMLInputElement).checked
}

function addTestCase(): void {
    currentQ.value?.test_cases.push({ input_data: '', expected_output: '', is_hidden: true })
}
</script>

<style scoped>
.create-page { margin: 0 auto; }
.create-page.step-start { max-width: 760px; }
.create-page.step-review { max-width: 1120px; }
.create-page.step-editor { max-width: 1320px; }

.sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
[tabindex="-1"]:focus { outline: none; }

/* Shared pieces */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}
.field { display: flex; flex-direction: column; gap: 6px; min-width: 0; border: 0; }
.field-label { font-family: var(--font-display); font-size: var(--fs-sm); font-weight: 600; color: var(--text); padding: 0; }
.field-label.big { font-size: var(--fs-md); }
.hint { font-size: var(--fs-sm); color: var(--text-dim); margin: 0; }
.mono { font-family: var(--font-mono); font-size: var(--fs-sm); line-height: 1.5; }
textarea { resize: vertical; }
.error { color: var(--red-ink); font-size: var(--fs-sm); padding: 10px 12px; background: var(--red-dim); border-radius: var(--radius-sm); margin: 0; }

.btn-primary, .btn-secondary {
    display: inline-flex; align-items: center; justify-content: center; gap: 8px;
    min-height: 44px; padding: 0 22px; border-radius: var(--radius-pill);
    font-family: var(--font-display); font-size: 14px; font-weight: 600; white-space: nowrap;
    transition: background 0.15s, border-color 0.15s, color 0.15s;
}
.btn-primary { background: var(--accent); color: var(--accent-ink); }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-primary:disabled { background: var(--surface2); color: var(--text-dim); cursor: not-allowed; }
.btn-secondary { background: var(--surface); color: var(--text); border: 1px solid var(--border2); }
.btn-secondary:hover:not(:disabled) { background: var(--surface2); }
.btn-secondary:disabled { opacity: 0.5; cursor: not-allowed; }
.text-btn {
    display: inline-flex; align-items: center; gap: 4px; min-height: 44px; padding: 0 8px;
    background: transparent; color: var(--red-ink); font-size: var(--fs-sm); font-weight: 600;
}
.text-btn:hover { color: var(--accent-hover); text-decoration: underline; }
.icon-btn {
    display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
    width: 44px; height: 44px; border-radius: var(--radius-sm);
    background: transparent; color: var(--text-muted);
}
.icon-btn:hover { background: var(--surface2); color: var(--text); }
.icon-btn.danger:hover { background: var(--red-dim); color: var(--red-ink); }

.chip {
    display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0;
    padding: 4px 10px; border-radius: var(--radius-pill);
    font-family: var(--font-display); font-size: var(--fs-xs); font-weight: 600; white-space: nowrap;
    background: var(--surface2); color: var(--text-muted);
}
.chip-draft { background: var(--yellow-dim); color: var(--amber-ink); align-self: flex-start; }
.chip-draft .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.chip-q { background: var(--text); color: var(--surface); }
.diff-easy { background: var(--green-dim); color: var(--green-ink); }
.diff-medium { background: var(--yellow-dim); color: var(--amber-ink); }
.diff-hard { background: var(--red-dim); color: var(--red-ink); }
.ink-easy { color: var(--green-ink); }
.ink-medium { color: var(--amber-ink); }
.ink-hard { color: var(--red-ink); }

/* Segmented control: native radios, styled as one pill row */
.segmented {
    display: inline-flex; flex-wrap: wrap; gap: 4px; padding: 4px; align-self: flex-start;
    background: var(--surface2); border-radius: var(--radius-pill);
}
.seg { position: relative; cursor: pointer; }
.seg span {
    display: inline-flex; align-items: center; min-height: 40px; padding: 0 18px;
    border-radius: var(--radius-pill); font-family: var(--font-display); font-size: 14px; font-weight: 500;
    color: var(--text-muted); transition: background 0.15s, color 0.15s;
}
.seg:hover span { color: var(--text); }
.seg input:checked + span { background: var(--surface); color: var(--text); font-weight: 600; box-shadow: 0 1px 3px rgba(33, 25, 27, 0.12); }
.seg input:focus-visible + span { outline: 2px solid var(--accent); outline-offset: 2px; }
fieldset:disabled .seg { cursor: not-allowed; opacity: 0.6; }

.spinner {
    width: 16px; height: 16px; border-radius: 50%;
    border: 2px solid currentColor; border-right-color: transparent;
    animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

.add-dashed {
    display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%;
    min-height: 52px; border: 1.5px dashed var(--border2); border-radius: var(--radius);
    background: transparent; color: var(--text-muted); font-size: 14px; font-weight: 600;
}
.add-dashed:hover { border-color: var(--accent); color: var(--red-ink); background: var(--surface); }
.add-dashed.small { width: auto; align-self: flex-start; min-height: 44px; padding: 0 16px; border-radius: var(--radius-pill); }

/* ── A · Start ───────────────────────────────────────────────────────────── */
.back-link { margin-left: -8px; margin-bottom: 8px; color: var(--text-muted); }
.page-title { margin-bottom: 8px; }
.page-sub { color: var(--text-muted); max-width: 60ch; margin-bottom: 28px; }
.gen-card { display: flex; flex-direction: column; gap: 18px; padding: 24px; }
.gen-card > .hint { margin-top: -14px; }
.gen-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.gen-foot {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    padding-top: 16px; border-top: 1px solid var(--border);
}
.or-divider { display: flex; align-items: center; gap: 12px; margin: 24px 0; color: var(--text-dim); font-size: var(--fs-sm); }
.or-divider::before, .or-divider::after { content: ''; flex: 1; height: 1px; background: var(--border); }
.link-card {
    display: flex; align-items: center; justify-content: space-between; gap: 16px; width: 100%;
    padding: 20px 24px; text-align: left; color: var(--text-muted);
    transition: border-color 0.15s, background 0.15s;
}
.link-card:hover:not(:disabled) { border-color: var(--accent); color: var(--red-ink); }
.link-card:disabled { opacity: 0.5; cursor: not-allowed; }
.link-card-text { display: flex; flex-direction: column; gap: 2px; }
.link-card-title { font-size: var(--fs-base); font-weight: 600; color: var(--text); }
.link-card-sub { font-family: var(--font-sans); font-size: var(--fs-sm); color: var(--text-muted); }

/* ── B · Review ──────────────────────────────────────────────────────────── */
.review { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 28px; align-items: start; }
.review-main { display: flex; flex-direction: column; gap: 14px; min-width: 0; }
.title-input {
    font-family: var(--font-display); font-size: 30px; font-weight: 600; letter-spacing: -0.01em;
    padding: 6px 10px; margin-left: -10px; width: calc(100% + 10px);
    border-color: transparent; background: transparent;
}
.title-input:hover { border-color: var(--border2); }
.title-input:focus { border-color: var(--accent); background: var(--surface); }
.title-input.small { font-size: 22px; }
.desc-input { border-color: transparent; background: transparent; padding: 6px 10px; margin-left: -10px; width: calc(100% + 10px); color: var(--text-muted); }
.desc-input:hover { border-color: var(--border2); }
.desc-input:focus { border-color: var(--accent); background: var(--surface); }
.q-list-head { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 12px; margin-top: 10px; }
.section-title { display: flex; align-items: center; gap: 8px; }
.count { font-size: var(--fs-sm); color: var(--text-dim); font-weight: 500; }

.q-card { padding: 16px 18px; display: flex; flex-direction: column; gap: 12px; }
.q-card.open { border-color: var(--border2); }
.q-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.q-card-title { flex: 1; min-width: 0; font-size: var(--fs-base); overflow-wrap: anywhere; }
.q-card-actions { display: flex; gap: 2px; margin: -8px -8px -8px 0; }
.q-card-body { padding: 4px 0 4px; border-top: 1px solid var(--border); padding-top: 16px; }
.q-card-summary {
    font-size: 14px; color: var(--text-muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.q-card-foot {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    font-size: var(--fs-sm); color: var(--text-dim); margin: -8px -8px -10px 0;
}

.empty-card { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 24px; }
.empty-icon { color: var(--amber-ink); }
.empty-title { font-size: var(--fs-md); }
.empty-text { color: var(--text-muted); max-width: 60ch; margin: 0; }
.btn-row { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }

.review-side { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 24px; }
.side-card { padding: 18px; display: flex; flex-direction: column; gap: 14px; }
.side-title { font-size: var(--fs-base); }
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 0; }
.stats div { background: var(--bg); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; }
.stats dt { font-size: var(--fs-xs); color: var(--text-dim); }
.stats dd { margin: 0; font-family: var(--font-display); font-size: var(--fs-md); font-weight: 600; font-variant-numeric: tabular-nums; }
.checklist { list-style: none; display: flex; flex-direction: column; gap: 8px; font-size: 14px; }
.checklist li { display: flex; gap: 8px; align-items: flex-start; line-height: 1.4; }
.checklist svg { flex-shrink: 0; margin-top: 1px; }
.checklist .ok svg { color: var(--green-ink); }
.checklist .warn { color: var(--text-muted); }
.checklist .warn svg { color: var(--amber-ink); }
.checklist .block { color: var(--red-ink); font-weight: 500; }
.side-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.side-actions .btn-primary { flex: 1; }

/* ── C · Editor ──────────────────────────────────────────────────────────── */
.editor { display: flex; flex-direction: column; gap: 16px; }
.editor-bar {
    display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 12px 20px;
    padding-bottom: 16px; border-bottom: 1px solid var(--border);
}
.editor-bar-title { flex: 1; min-width: 240px; display: flex; flex-direction: column; gap: 4px; }
.editor-bar-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.editor-bar-actions { display: flex; flex-wrap: wrap; gap: 10px; }
.editor-publish { flex-basis: 100%; }
.save-reason { flex-basis: 100%; margin: 0; font-size: var(--fs-sm); color: var(--red-ink); text-align: right; }

.q-tabs { display: flex; gap: 8px; overflow-x: auto; padding: 2px; }
.q-tab {
    flex-shrink: 0; display: inline-flex; align-items: center; gap: 6px;
    min-height: 44px; max-width: 260px; padding: 0 16px;
    border: 1px solid var(--border2); border-radius: var(--radius-pill);
    background: var(--surface); color: var(--text-muted); font-size: 14px; font-weight: 500;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.q-tab:hover { color: var(--text); border-color: var(--text-dim); }
.q-tab.active { background: var(--accent-tint); border-color: var(--accent); color: var(--red-ink); font-weight: 600; }
.q-tab.add { border-style: dashed; background: transparent; }
.q-tab.add:hover { border-color: var(--accent); color: var(--red-ink); }

.editor-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px; align-items: start; }
.editor-form { padding: 22px; display: flex; flex-direction: column; gap: 18px; }

.tc-table { display: flex; flex-direction: column; gap: 8px; }
.tc-head, .tc-row { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 96px 44px; gap: 8px; align-items: start; }
.tc-head span { font-family: var(--font-display); font-size: var(--fs-xs); font-weight: 600; color: var(--text-dim); }
.tc-example { display: flex; align-items: center; gap: 8px; min-height: 44px; cursor: pointer; font-size: var(--fs-sm); }
.tc-example input { width: 18px; height: 18px; padding: 0; accent-color: var(--accent); flex-shrink: 0; cursor: pointer; }
.tc-shown { color: var(--green-ink); font-weight: 600; }
.all-cases { margin-top: 18px; display: flex; flex-direction: column; gap: 8px; }
.all-cases-h { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text); }
.all-cases-h span { text-transform: none; letter-spacing: 0; font-weight: 500; color: var(--text-dim); }
.all-cases-scroll { overflow-x: auto; border: 1px solid var(--border); border-radius: 10px; }
.all-cases-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.all-cases-table th { text-align: left; font-weight: 600; color: var(--text-muted); padding: 8px 12px; background: var(--bg); border-bottom: 1px solid var(--border); white-space: nowrap; }
.all-cases-table td { padding: 8px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }
.all-cases-table tr:last-child td { border-bottom: 0; }
.all-cases-table pre { margin: 0; font-family: var(--font-mono); font-size: 13px; white-space: pre-wrap; word-break: break-word; }
.tc-hidden { color: var(--amber-ink); font-weight: 600; }

.more { border-top: 1px solid var(--border); padding-top: 4px; }
.more summary {
    display: flex; align-items: center; min-height: 44px; cursor: pointer;
    font-family: var(--font-display); font-size: 14px; font-weight: 600; color: var(--text-muted);
}
.more summary:hover { color: var(--text); }
.more-body { display: flex; flex-direction: column; gap: 16px; padding-top: 8px; }

.preview { padding: 22px; display: flex; flex-direction: column; gap: 20px; position: sticky; top: 24px; max-height: calc(100vh - 48px); overflow-y: auto; }
.preview-label {
    margin: -6px 0 0; font-family: var(--font-display); font-size: var(--fs-xs); font-weight: 600;
    letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-dim);
}
.preview-head { display: flex; flex-direction: column; gap: 10px; }
.preview-title { margin: 0; font-size: 28px; font-weight: 600; letter-spacing: -0.01em; overflow-wrap: anywhere; }
.preview-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: var(--text-muted); }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 1199px) {
    .editor-grid { grid-template-columns: minmax(0, 1fr); }
    .preview { position: static; max-height: none; }
}
@media (max-width: 899px) {
    .review { grid-template-columns: minmax(0, 1fr); }
    .review-side { position: static; }
}
@media (max-width: 600px) {
    .gen-card, .editor-form, .preview { padding: 16px; }
    .gen-row { grid-template-columns: minmax(0, 1fr); }
    .gen-foot { flex-direction: column; align-items: stretch; }
    .gen-foot .btn-primary { width: 100%; }
    .title-input { font-size: 24px; }
    .q-card { padding: 14px; }
    .editor-bar-actions { width: 100%; }
    .editor-bar-actions > * { flex: 1; }
    .save-reason { text-align: left; }
    /* Each test case becomes a small stacked card */
    .tc-head { display: none; }
    .tc-row {
        grid-template-columns: minmax(0, 1fr) 44px; padding: 10px;
        border: 1px solid var(--border); border-radius: var(--radius-sm);
    }
    .tc-row textarea { grid-column: 1 / -1; }
    .preview-title { font-size: 22px; }
    /* Three equal segments that fit the width instead of wrapping */
    .segmented { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-self: stretch; }
    .seg span { width: 100%; justify-content: center; padding: 0 6px; font-size: 13px; white-space: nowrap; }
}
.restored-note { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px; margin: 0 0 16px; padding: 10px 14px; border-radius: 12px; background: var(--blue-dim); color: var(--text); font-size: 14px; }
</style>
