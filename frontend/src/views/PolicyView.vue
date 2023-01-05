<template>
    <div class="policy-page">
        <div class="page-header">
            <div>
                <h1>Detection Policy</h1>
                <p class="page-sub">Configure plagiarism detection thresholds — changes apply to future checks</p>
            </div>
            <div style="display:flex;gap:10px;align-items:center">
                <button class="tab-btn" :class="{ active: activeTab === 'policy' }" @click="activeTab = 'policy'">Policy</button>
                <button class="tab-btn" :class="{ active: activeTab === 'changelog' }" @click="switchToChangelog">Changelog</button>
                <button class="tab-btn" :class="{ active: activeTab === 'runs' }" @click="switchToRuns">Run History</button>
            </div>
        </div>

        <!-- POLICY TAB -->
        <template v-if="activeTab === 'policy'">
            <div v-if="loading" class="state-msg">Loading...</div>

            <div v-else class="policy-grid">
                <!-- Signal Weights -->
                <div class="policy-card">
                    <div class="card-title">Signal Weights</div>
                    <p class="card-desc">How much each signal contributes to the behavioural risk score. Weights must sum to 1.0.</p>
                    <div class="weight-sum" :class="weightSumClass">
                        Sum: {{ weightSum.toFixed(2) }} {{ weightSum === 1.0 ? '✓' : '← must equal 1.0' }}
                    </div>

                    <div v-for="w in weightFields" :key="w.key" class="slider-row">
                        <div class="slider-header">
                            <span class="slider-label">{{ w.label }}</span>
                            <span class="slider-val">{{ (policy[w.key] * 100).toFixed(0) }}%</span>
                        </div>
                        <input
                            type="range"
                            min="0" max="1" step="0.05"
                            :value="policy[w.key]"
                            @input="onSlider(w.key, $event)"
                            class="slider"
                        />
                        <p class="slider-desc">{{ w.desc }}</p>
                    </div>
                </div>

                <!-- Risk Thresholds -->
                <div class="policy-card">
                    <div class="card-title">Risk Thresholds</div>
                    <p class="card-desc">Minimum scores needed to flag a submission.</p>

                    <div class="slider-row">
                        <div class="slider-header">
                            <span class="slider-label">Min Behavioural Risk Score</span>
                            <span class="slider-val">{{ (policy.min_risk_score * 100).toFixed(0) }}%</span>
                        </div>
                        <input type="range" min="0.05" max="0.8" step="0.05"
                            :value="policy.min_risk_score"
                            @input="onSlider('min_risk_score', $event)"
                            class="slider" />
                        <p class="slider-desc">Submissions below this score are not flagged. Lower = more flags.</p>
                    </div>

                    <div class="slider-row">
                        <div class="slider-header">
                            <span class="slider-label">Similarity Threshold (TF-IDF)</span>
                            <span class="slider-val">{{ (policy.similarity_threshold * 100).toFixed(0) }}%</span>
                        </div>
                        <input type="range" min="0.5" max="0.99" step="0.01"
                            :value="policy.similarity_threshold"
                            @input="onSlider('similarity_threshold', $event)"
                            class="slider" />
                        <p class="slider-desc">Cosine similarity above this creates a pair flag. Higher = fewer false positives.</p>
                    </div>
                </div>

                <!-- Exam Rules -->
                <div class="policy-card">
                    <div class="card-title">Exam Rules</div>
                    <p class="card-desc">Attempt limits applied globally to all questions across all exams.</p>

                    <div class="slider-row">
                        <div class="slider-header">
                            <span class="slider-label">Max Attempts per Question</span>
                            <span class="slider-val">{{ policy.max_attempts }}</span>
                        </div>
                        <input
                            type="range"
                            min="1" max="10" step="1"
                            :value="policy.max_attempts"
                            @input="onSlider('max_attempts', $event)"
                            class="slider"
                        />
                        <p class="slider-desc">How many times a student can submit code for any question. Enforced atomically in Redis.</p>
                    </div>
                </div>

                <!-- Time Baselines -->
                <div class="policy-card">
                    <div class="card-title">Time Baselines</div>
                    <p class="card-desc">Minimum expected solve time per difficulty. Solving faster than this triggers the time signal.</p>

                    <div v-for="b in baselineFields" :key="b.key" class="slider-row">
                        <div class="slider-header">
                            <span class="slider-label">{{ b.label }}</span>
                            <span class="slider-val">{{ fmtTime(policy[b.key]) }}</span>
                        </div>
                        <input type="range" :min="b.min" :max="b.max" step="30"
                            :value="policy[b.key]"
                            @input="onSlider(b.key, $event)"
                            class="slider" />
                        <p class="slider-desc">{{ b.desc }}</p>
                    </div>
                </div>

                <!-- Preview panel -->
                <div class="policy-card preview-card">
                    <div class="card-title">Policy Preview</div>
                    <div class="preview-grid">
                        <div class="preview-row">
                            <span class="pr-label">Paste ({{ (policy.paste_weight * 100).toFixed(0) }}%)</span>
                            <div class="pr-bar-wrap"><div class="pr-bar" :style="{ width: (policy.paste_weight * 100) + '%' }" /></div>
                        </div>
                        <div class="preview-row">
                            <span class="pr-label">Time ({{ (policy.time_weight * 100).toFixed(0) }}%)</span>
                            <div class="pr-bar-wrap"><div class="pr-bar" :style="{ width: (policy.time_weight * 100) + '%' }" /></div>
                        </div>
                        <div class="preview-row">
                            <span class="pr-label">Tab Switch ({{ (policy.tab_weight * 100).toFixed(0) }}%)</span>
                            <div class="pr-bar-wrap"><div class="pr-bar" :style="{ width: (policy.tab_weight * 100) + '%' }" /></div>
                        </div>
                        <div class="preview-row">
                            <span class="pr-label">Submission ({{ (policy.submission_weight * 100).toFixed(0) }}%)</span>
                            <div class="pr-bar-wrap"><div class="pr-bar" :style="{ width: (policy.submission_weight * 100) + '%' }" /></div>
                        </div>
                    </div>
                    <div class="preview-stat">
                        <span>Flag when risk ≥</span>
                        <span class="stat-val">{{ (policy.min_risk_score * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="preview-stat">
                        <span>Flag pairs when similarity ≥</span>
                        <span class="stat-val">{{ (policy.similarity_threshold * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="preview-stat">
                        <span>Easy baseline</span>
                        <span class="stat-val">{{ fmtTime(policy.easy_baseline_s) }}</span>
                    </div>
                    <div class="preview-stat">
                        <span>Medium baseline</span>
                        <span class="stat-val">{{ fmtTime(policy.medium_baseline_s) }}</span>
                    </div>
                    <div class="preview-stat">
                        <span>Hard baseline</span>
                        <span class="stat-val">{{ fmtTime(policy.hard_baseline_s) }}</span>
                    </div>
                    <div class="preview-stat">
                        <span>Max attempts per question</span>
                        <span class="stat-val">{{ policy.max_attempts }}</span>
                    </div>
                    <div v-if="policy.updated_at" class="updated-at">
                        Last updated {{ new Date(policy.updated_at).toLocaleString() }}
                    </div>
                </div>
            </div>

            <!-- Change reason + save — only visible after a slider moves -->
            <div v-if="isDirty && !loading" class="save-panel">
                <div class="save-panel-inner">
                    <div class="reason-block">
                        <label class="reason-label">Reason for change <span class="reason-req">(required)</span></label>
                        <textarea
                            v-model="changeReason"
                            class="reason-input"
                            placeholder="e.g. Increasing paste weight after semester 3 analysis showed low signal — 15% of flagged cases were false positives driven by time signal noise"
                            rows="2"
                        />
                    </div>
                    <div class="save-actions">
                        <button class="discard-btn" @click="discardChanges">Discard</button>
                        <button class="save-btn" @click="save" :disabled="saving || !changeReason.trim()">
                            {{ saving ? 'Saving...' : 'Save Policy' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- Re-run section — always visible on policy tab -->
            <div class="rerun-section">
                <div class="rerun-header">
                    <div>
                        <div class="rerun-title">Re-run Plagiarism Checks</div>
                        <div class="rerun-sub">Apply current policy to a past exam. Queues both Phase 1 (behavioural) and Phase 2 (similarity) — existing flags will be updated.</div>
                    </div>
                </div>
                <div v-if="rerunLoading" class="rerun-state">Loading exams...</div>
                <div v-else-if="rerunExams.length === 0" class="rerun-state">No closed exams found.</div>
                <div v-else class="rerun-list">
                    <div v-for="ex in rerunExams" :key="ex.id" class="rerun-row">
                        <div class="rerun-exam-info">
                            <span class="rerun-exam-name">{{ ex.title }}</span>
                            <span class="rerun-exam-date">{{ ex.end_time ? fmtDate(ex.end_time) : 'no end date' }}</span>
                        </div>
                        <div class="rerun-row-right">
                            <span v-if="rerunQueued.has(ex.id)" class="rerun-queued" @click="switchToRuns" style="cursor:pointer" title="Click to view Run History">Queued — view in Run History →</span>
                            <button
                                v-else
                                class="rerun-btn"
                                :disabled="rerunning.has(ex.id)"
                                @click="rerun(ex.id)"
                            >{{ rerunning.has(ex.id) ? 'Queuing...' : 'Re-run' }}</button>
                        </div>
                    </div>
                </div>
            </div>
        </template>

        <!-- CHANGELOG TAB -->
        <template v-if="activeTab === 'changelog'">
            <div v-if="clLoading" class="state-msg">Loading changelog...</div>
            <div v-else-if="!changelog.length" class="empty-cl">No policy changes recorded yet.</div>
            <div v-else class="changelog">
                <div v-for="(v, idx) in changelog" :key="v.id" class="cl-entry">
                    <div class="cl-spine">
                        <div class="cl-dot" />
                        <div v-if="idx < changelog.length - 1" class="cl-line" />
                    </div>
                    <div class="cl-body">
                        <div class="cl-header">
                            <span class="cl-who">{{ v.changed_by }}</span>
                            <span class="cl-when">{{ new Date(v.changed_at).toLocaleString() }}</span>
                        </div>
                        <p v-if="v.change_reason" class="cl-reason">"{{ v.change_reason }}"</p>
                        <div v-if="v.changes.length" class="cl-changes">
                            <div v-for="c in v.changes" :key="c.field" class="cl-change-row">
                                <span class="cl-field">{{ fmtField(c.field) }}</span>
                                <span class="cl-before">{{ fmtVal(c.field, c.before) }}</span>
                                <span class="cl-arrow">→</span>
                                <span class="cl-after">{{ fmtVal(c.field, c.after) }}</span>
                            </div>
                        </div>
                        <div v-else class="cl-nochange">No field values changed.</div>

                        <div v-if="v.affected_exams.length" class="cl-exams">
                            <div class="cl-exams-label">Exams active during this policy</div>
                            <div v-for="ex in v.affected_exams" :key="ex.id" class="cl-exam-row">
                                <router-link :to="`/dashboard/support/exam/${ex.id}`" class="cl-exam-link">{{ ex.title }}</router-link>
                                <span class="cl-exam-status" :class="ex.status === 'in-flight at change' ? 'status-inflight' : 'status-started'">
                                    {{ ex.status }}
                                </span>
                            </div>
                        </div>
                        <div v-else class="cl-nochange">No exams ran under this policy.</div>
                    </div>
                </div>
            </div>
        </template>

        <!-- RUN HISTORY TAB -->
        <template v-if="activeTab === 'runs'">
            <div v-if="runsLoading" class="state-msg">Loading run history...</div>
            <div v-else-if="runs.length === 0" class="empty-cl">No runs recorded yet. Re-run an exam from the Policy tab to create the first record.</div>
            <div v-else class="runs-list">
                <div v-for="run in runs" :key="run.id" class="run-card">
                    <!-- Run header -->
                    <div class="run-header">
                        <div class="run-meta">
                            <router-link :to="`/dashboard/plagiarism/cohorts/${run.exam_id}`" class="run-exam">{{ run.exam_title }}</router-link>
                            <span :class="['run-trigger', run.trigger]">{{ run.trigger === 'manual_rerun' ? 'Manual Re-run' : 'Auto (Exam Close)' }}</span>
                            <span :class="['run-status', run.status]">{{ run.status }}</span>
                        </div>
                        <div class="run-when-row">
                            <div class="run-when">
                                {{ new Date(run.ran_at).toLocaleString() }}
                                <span v-if="run.triggered_by" class="run-by">by {{ run.triggered_by }}</span>
                            </div>
                            <div class="run-nav-links">
                                <router-link :to="`/dashboard/plagiarism/cohorts/${run.exam_id}`" class="run-nav-link">Rings &amp; Risk →</router-link>
                                <router-link :to="`/dashboard/history/${run.exam_id}?from=runs`" class="run-nav-link">Exam Stats →</router-link>
                            </div>
                        </div>
                    </div>

                    <div class="run-body">
                        <!-- Detection results -->
                        <div class="run-results">
                            <!-- Behavioural -->
                            <div class="run-section">
                                <div class="run-section-title">Behavioural Flags</div>
                                <div class="run-kpis">
                                    <div class="run-kpi">
                                        <div class="run-kpi-val bad">{{ run.b_flags_total }}</div>
                                        <div class="run-kpi-label">Total Flags</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val bad">{{ run.b_high_confidence }}</div>
                                        <div class="run-kpi-label">High Confidence</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val mid">{{ run.b_medium_confidence }}</div>
                                        <div class="run-kpi-label">Medium</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val">{{ run.b_low_confidence }}</div>
                                        <div class="run-kpi-label">Low</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val">{{ run.b_avg_risk_score != null ? (run.b_avg_risk_score * 100).toFixed(0) + '%' : '—' }}</div>
                                        <div class="run-kpi-label">Avg Risk Score</div>
                                    </div>
                                </div>
                            </div>

                            <!-- Similarity -->
                            <div class="run-section">
                                <div class="run-section-title">
                                    Similarity Pairs
                                    <span v-if="run.status === 'running'" class="run-progress">{{ run.questions_done }}/{{ run.questions_total }} questions done</span>
                                </div>
                                <div class="run-kpis">
                                    <div class="run-kpi">
                                        <div class="run-kpi-val bad">{{ run.s_flags_total }}</div>
                                        <div class="run-kpi-label">Total Pairs</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val bad">{{ run.s_pairs_90_plus }}</div>
                                        <div class="run-kpi-label">≥90% Similar</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val mid">{{ run.s_pairs_80_90 }}</div>
                                        <div class="run-kpi-label">80–90%</div>
                                    </div>
                                    <div class="run-kpi">
                                        <div class="run-kpi-val">{{ run.s_avg_similarity != null ? (run.s_avg_similarity * 100).toFixed(1) + '%' : '—' }}</div>
                                        <div class="run-kpi-label">Avg Similarity</div>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Policy snapshot -->
                        <div class="run-section">
                            <div class="run-section-title">Policy Used</div>
                            <div class="policy-snap">
                                <span v-for="(val, key) in run.policy_snapshot" :key="key" class="snap-pill">
                                    {{ fmtField(String(key)) }}: <strong>{{ fmtVal(String(key), val) }}</strong>
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>

        <div v-if="saved" class="save-toast">Policy saved and change logged</div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()

interface Policy {
    paste_weight: number
    time_weight: number
    tab_weight: number
    submission_weight: number
    min_risk_score: number
    similarity_threshold: number
    easy_baseline_s: number
    medium_baseline_s: number
    hard_baseline_s: number
    max_attempts: number
    updated_at?: string
}

interface ChangeEntry {
    id: number
    changed_by: string
    changed_at: string
    change_reason: string
    changes: { field: string; before: number; after: number }[]
    affected_exams: { id: number; title: string; status: string }[]
}

const loading      = ref(true)
const saving       = ref(false)
const saved        = ref(false)
const isDirty      = ref(false)
const changeReason = ref('')
const activeTab    = ref<'policy' | 'changelog' | 'runs'>('policy')
const clLoading    = ref(false)
const changelog    = ref<ChangeEntry[]>([])

const policy = ref<Policy>({
    paste_weight: 0.40,
    time_weight: 0.30,
    tab_weight: 0.15,
    submission_weight: 0.15,
    min_risk_score: 0.20,
    similarity_threshold: 0.80,
    easy_baseline_s: 90,
    medium_baseline_s: 240,
    hard_baseline_s: 480,
    max_attempts: 3,
})
let savedPolicy: Policy = { ...policy.value }

const weightFields = [
    { key: 'paste_weight' as const, label: 'Paste Signal', desc: 'Code copied via paste events — direct, hard to misinterpret.' },
    { key: 'time_weight' as const, label: 'Time Signal', desc: 'Solved much faster than the difficulty baseline.' },
    { key: 'tab_weight' as const, label: 'Tab Switch Signal', desc: 'Left the exam tab — corroborating signal.' },
    { key: 'submission_weight' as const, label: 'Submission Surprise', desc: 'Code changed completely between attempts.' },
]

const baselineFields = [
    { key: 'easy_baseline_s' as const, label: 'Easy Baseline', min: 30, max: 600, desc: 'Minimum expected solve time for easy problems.' },
    { key: 'medium_baseline_s' as const, label: 'Medium Baseline', min: 60, max: 1800, desc: 'Minimum expected solve time for medium problems.' },
    { key: 'hard_baseline_s' as const, label: 'Hard Baseline', min: 120, max: 3600, desc: 'Minimum expected solve time for hard problems.' },
]

const weightSum = computed(() =>
    Math.round((policy.value.paste_weight + policy.value.time_weight + policy.value.tab_weight + policy.value.submission_weight) * 100) / 100
)
const weightSumClass = computed(() => weightSum.value === 1.0 ? 'sum-ok' : 'sum-err')

function onSlider(key: keyof Policy, event: Event) {
    const raw = (event.target as HTMLInputElement).value
    const val = (key.endsWith('_s') || key === 'max_attempts') ? parseInt(raw) : parseFloat(raw)
    ;(policy.value as any)[key] = val
    isDirty.value = true
}

function discardChanges() {
    policy.value = { ...savedPolicy }
    isDirty.value = false
    changeReason.value = ''
}

function fmtTime(s: number): string {
    const total = Math.round(s)
    const m = Math.floor(total / 60)
    const sec = total % 60
    return m > 0 ? `${m}m ${sec > 0 ? sec + 's' : ''}`.trim() : `${sec}s`
}

const FIELD_LABELS: Record<string, string> = {
    paste_weight: 'Paste weight',
    time_weight: 'Time weight',
    tab_weight: 'Tab weight',
    submission_weight: 'Submission weight',
    min_risk_score: 'Min risk score',
    similarity_threshold: 'Similarity threshold',
    easy_baseline_s: 'Easy baseline',
    medium_baseline_s: 'Medium baseline',
    hard_baseline_s: 'Hard baseline',
    max_attempts: 'Max attempts',
}
function fmtField(f: string): string { return FIELD_LABELS[f] ?? f }
function fmtVal(field: string, v: number): string {
    if (field === 'max_attempts') return String(v)
    if (field.endsWith('_s')) return fmtTime(v)
    return (v * 100).toFixed(0) + '%'
}

interface RerunExam { id: number; title: string; end_time: string | null }
const rerunExams   = ref<RerunExam[]>([])
const rerunLoading = ref(false)
const rerunning    = ref<Set<number>>(new Set())
const rerunQueued  = ref<Set<number>>(new Set())

function fmtDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

async function loadRerunExams() {
    rerunLoading.value = true
    try {
        const res = await api.get('/dashboard/exams/')
        rerunExams.value = (res.data as any[])
            .filter((e: any) => e.status === 'ended')
            .map((e: any) => ({ id: e.exam_id, title: e.title, end_time: e.end_time || null }))
    } finally {
        rerunLoading.value = false
    }
}

async function rerun(examId: number) {
    rerunning.value.add(examId)
    rerunning.value = new Set(rerunning.value)
    try {
        await api.post(`/plagiarism/cohorts/${examId}/rerun/`)
        rerunQueued.value.add(examId)
        rerunQueued.value = new Set(rerunQueued.value)
        runsLoaded = false  // force Run History to reload next visit
    } finally {
        rerunning.value.delete(examId)
        rerunning.value = new Set(rerunning.value)
    }
}

onMounted(async () => {
    const res = await api.get('/plagiarism/policy/')
    policy.value = res.data
    savedPolicy = { ...res.data }
    loading.value = false
    loadRerunExams()
    if (route.query.tab === 'runs') {
        switchToRuns()
    }
})

const runs        = ref<any[]>([])
const runsLoading = ref(false)
let runsLoaded = false
let pollTimer: ReturnType<typeof setInterval> | null = null

async function fetchRuns() {
    const res = await api.get('/plagiarism/runs/')
    runs.value = res.data
    runsLoaded = true
    // stop polling once no runs are running
    if (pollTimer && !res.data.some((r: any) => r.status === 'running')) {
        clearInterval(pollTimer)
        pollTimer = null
    }
}

function startPollingIfNeeded() {
    if (pollTimer) return
    if (runs.value.some(r => r.status === 'running')) {
        pollTimer = setInterval(fetchRuns, 5000)
    }
}

async function switchToRuns() {
    activeTab.value = 'runs'
    if (runsLoaded && !runs.value.some(r => r.status === 'running')) return
    runsLoading.value = !runsLoaded
    try {
        await fetchRuns()
        startPollingIfNeeded()
    } finally {
        runsLoading.value = false
    }
}

onUnmounted(() => {
    if (pollTimer) clearInterval(pollTimer)
})

async function switchToChangelog() {
    activeTab.value = 'changelog'
    if (changelog.value.length) return
    clLoading.value = true
    try {
        const res = await api.get('/plagiarism/policy/changelog/')
        changelog.value = res.data
    } finally {
        clLoading.value = false
    }
}

async function save() {
    saving.value = true
    try {
        const res = await api.put('/plagiarism/policy/', {
            ...policy.value,
            change_reason: changeReason.value,
        })
        policy.value = res.data
        savedPolicy = { ...res.data }
        isDirty.value = false
        changeReason.value = ''
        saved.value = true
        changelog.value = []  // force reload next time changelog tab is opened
        setTimeout(() => { saved.value = false }, 3000)
    } finally {
        saving.value = false
    }
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }

.tab-btn {
    padding: 7px 18px; font-size: 13px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer;
    transition: all 0.15s;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { background: var(--red-dim); border-color: rgba(230,57,70,0.3); color: var(--red); }

.state-msg { color: var(--text-muted); padding: 40px 0; }

.policy-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }

.policy-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
}
.card-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 6px; }
.card-desc { font-size: 13px; color: var(--text-muted); margin-bottom: 20px; }

.weight-sum {
    font-size: 13px; font-weight: 600;
    padding: 8px 14px; border-radius: var(--radius-sm); margin-bottom: 16px;
}
.weight-sum.sum-ok { background: rgba(46,204,113,0.1); color: var(--green); }
.weight-sum.sum-err { background: var(--red-dim); color: var(--red); }

.slider-row { margin-bottom: 20px; }
.slider-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.slider-label { font-size: 13px; font-weight: 600; color: var(--text); }
.slider-val { font-size: 14px; font-weight: 700; color: var(--red); }
.slider {
    width: 100%; height: 4px; appearance: none;
    background: var(--surface3); border-radius: 2px; outline: none; cursor: pointer;
}
.slider::-webkit-slider-thumb {
    appearance: none; width: 16px; height: 16px;
    border-radius: 50%; background: var(--red); cursor: pointer;
}
.slider-desc { font-size: 12px; color: var(--text-dim); margin-top: 6px; }

.preview-card { grid-column: 1 / -1; }
.preview-grid { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.preview-row { display: flex; align-items: center; gap: 12px; }
.pr-label { font-size: 13px; color: var(--text-muted); width: 160px; flex-shrink: 0; }
.pr-bar-wrap { flex: 1; height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.pr-bar { height: 100%; background: var(--red); border-radius: 3px; transition: width 0.2s; }
.preview-stat {
    display: flex; justify-content: space-between;
    padding: 8px 0; border-top: 1px solid var(--border);
    font-size: 13px; color: var(--text-muted);
}
.stat-val { font-weight: 700; color: var(--text); }
.updated-at { font-size: 12px; color: var(--text-dim); margin-top: 12px; }

/* Save panel */
.save-panel {
    margin-top: 24px;
    background: var(--surface);
    border: 1px solid rgba(230,57,70,0.3);
    border-radius: var(--radius);
    padding: 20px 24px;
}
.save-panel-inner { display: flex; gap: 20px; align-items: flex-end; }
.reason-block { flex: 1; }
.reason-label { font-size: 12px; font-weight: 600; color: var(--text-muted); display: block; margin-bottom: 6px; }
.reason-req { color: var(--red); font-weight: 400; }
.reason-input {
    width: 100%; padding: 10px 12px; font-size: 13px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text);
    resize: vertical; box-sizing: border-box;
    font-family: inherit;
}
.reason-input::placeholder { color: var(--text-dim); }
.reason-input:focus { border-color: rgba(230,57,70,0.4); outline: none; }
.save-actions { display: flex; flex-direction: column; gap: 8px; flex-shrink: 0; }
.discard-btn {
    padding: 9px 20px; font-size: 13px; font-weight: 500;
    background: transparent; border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer;
    transition: all 0.15s;
}
.discard-btn:hover { color: var(--text); border-color: var(--border2); }
.save-btn {
    padding: 9px 22px; background: var(--red); color: white;
    border: none; border-radius: var(--radius-sm);
    font-size: 13px; font-weight: 600; cursor: pointer; transition: opacity 0.15s;
}
.save-btn:disabled { opacity: 0.45; cursor: not-allowed; }

/* Changelog */
.empty-cl { color: var(--text-dim); padding: 60px 0; text-align: center; font-size: 14px; }
.changelog { padding-top: 4px; }

.cl-entry {
    display: flex;
    gap: 16px;
    padding-bottom: 28px;
}
.cl-spine {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 14px;
    flex-shrink: 0;
    padding-top: 4px;
}
.cl-dot {
    width: 10px; height: 10px;
    background: var(--red); border-radius: 50%; flex-shrink: 0;
}
.cl-line {
    flex: 1; width: 2px; background: var(--border); margin-top: 6px;
}
.cl-body { flex: 1; min-width: 0; }
.cl-header {
    display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
}
.cl-who { font-weight: 700; font-size: 14px; color: var(--text); }
.cl-when { font-size: 12px; color: var(--text-dim); }
.cl-reason {
    font-style: italic; color: var(--text-muted); font-size: 13px;
    border-left: 3px solid var(--border2); padding-left: 10px;
    margin: 6px 0 10px;
}
.cl-changes {
    display: flex; flex-direction: column; gap: 6px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 12px 16px;
}
.cl-change-row {
    display: flex; align-items: center; gap: 8px; font-size: 13px;
}
.cl-field { color: var(--text-muted); width: 160px; flex-shrink: 0; font-weight: 500; }
.cl-before { color: var(--text-dim); font-family: monospace; }
.cl-arrow { color: var(--text-dim); font-size: 11px; }
.cl-after { color: var(--red); font-family: monospace; font-weight: 600; }
.cl-nochange { font-size: 12px; color: var(--text-dim); }

.cl-exams { margin-top: 10px; }
.cl-exams-label {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.8px; color: var(--text-dim); margin-bottom: 6px;
}
.cl-exam-row {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 0; border-top: 1px solid var(--border);
    font-size: 13px;
}
.cl-exam-link { color: var(--text); text-decoration: none; font-weight: 500; flex: 1; }
.cl-exam-link:hover { color: var(--red); text-decoration: underline; }
.cl-exam-status {
    font-size: 11px; font-weight: 600; padding: 2px 8px;
    border-radius: 4px; white-space: nowrap; flex-shrink: 0;
}
.status-inflight  { background: rgba(245,158,11,0.12); color: #f59e0b; }
.status-started   { background: rgba(34,197,94,0.10);  color: #22c55e; }

.save-toast {
    position: fixed; bottom: 24px; right: 24px;
    background: var(--green); color: white;
    padding: 12px 20px; border-radius: var(--radius);
    font-size: 14px; font-weight: 600; z-index: 1000;
}

/* Run History */
.runs-list { display: flex; flex-direction: column; gap: 16px; }
.run-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.run-header {
    display: flex; justify-content: space-between; align-items: center;
    padding: 14px 20px; background: var(--surface2); border-bottom: 1px solid var(--border);
    flex-wrap: wrap; gap: 8px;
}
.run-meta { display: flex; align-items: center; gap: 10px; }
.run-exam {
    font-weight: 700; font-size: 14px; color: var(--text);
    text-decoration: none;
}
.run-exam:hover { color: var(--red); text-decoration: underline; }
.run-trigger {
    font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 20px;
}
.run-trigger.manual_rerun { background: rgba(99,102,241,0.15); color: #818cf8; }
.run-trigger.exam_close   { background: var(--surface3); color: var(--text-dim); }
.run-status { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 20px; text-transform: uppercase; }
.run-status.completed { background: rgba(34,197,94,0.12); color: #22c55e; }
.run-status.running   { background: rgba(245,158,11,0.12); color: #f59e0b; }
.run-status.failed    { background: var(--red-dim); color: var(--red); }
.run-when-row { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.run-when { font-size: 12px; color: var(--text-dim); }
.run-by   { color: var(--text-muted); margin-left: 4px; }
.run-nav-links { display: flex; gap: 12px; }
.run-nav-link {
    font-size: 12px; font-weight: 600; color: var(--text-muted);
    cursor: pointer; transition: color 0.15s;
}
.run-nav-link:hover { color: var(--red); }

.run-body { padding: 16px 20px; display: flex; flex-direction: column; gap: 16px; }
.run-results { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.run-section-title {
    font-size: 11px; font-weight: 700; text-transform: uppercase;
    letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 10px;
    display: flex; align-items: center; gap: 10px;
}
.run-progress { font-size: 11px; color: #f59e0b; font-weight: 600; text-transform: none; letter-spacing: 0; }
.run-kpis { display: flex; flex-wrap: wrap; gap: 12px; }
.run-kpi { min-width: 70px; }
.run-kpi-val { font-size: 20px; font-weight: 700; color: var(--text); line-height: 1; }
.run-kpi-val.good { color: var(--green); }
.run-kpi-val.mid  { color: #f59e0b; }
.run-kpi-val.bad  { color: var(--red); }
.run-kpi-label { font-size: 10px; color: var(--text-dim); margin-top: 3px; text-transform: uppercase; letter-spacing: 0.3px; }

.policy-snap { display: flex; flex-wrap: wrap; gap: 8px; }
.snap-pill {
    font-size: 12px; color: var(--text-muted);
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; padding: 3px 10px;
}
.snap-pill strong { color: var(--text); }

/* Re-run section */
.rerun-section {
    margin-top: 28px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.rerun-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    padding: 18px 20px 14px;
    border-bottom: 1px solid var(--border);
    background: var(--surface2);
}
.rerun-title { font-size: 14px; font-weight: 700; color: var(--text); margin-bottom: 3px; }
.rerun-sub { font-size: 12px; color: var(--text-dim); max-width: 600px; }
.rerun-state { padding: 20px; color: var(--text-dim); font-size: 13px; }
.rerun-list { display: flex; flex-direction: column; }
.rerun-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
    gap: 16px;
}
.rerun-row:last-child { border-bottom: none; }
.rerun-exam-info { display: flex; align-items: center; gap: 12px; min-width: 0; }
.rerun-exam-name { font-size: 13px; font-weight: 600; color: var(--text); }
.rerun-exam-date { font-size: 12px; color: var(--text-dim); flex-shrink: 0; }
.rerun-row-right { flex-shrink: 0; }
.rerun-btn {
    padding: 6px 16px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
}
.rerun-btn:hover:not(:disabled) { border-color: var(--red); color: var(--red); background: rgba(230,57,70,0.06); }
.rerun-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rerun-queued {
    font-size: 12px;
    font-weight: 600;
    color: var(--green);
    padding: 6px 10px;
}
</style>
