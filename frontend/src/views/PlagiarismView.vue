<template>
    <div class="plagiarism-page">
        <div class="page-header">
            <div>
                <h1>Plagiarism Detection</h1>
                <p class="page-sub">Review behavioural flags and similarity pairs</p>
            </div>
        </div>

        <!-- Tab switcher -->
        <div class="tab-row">
            <button
                :class="['tab-btn', activeTab === 'behavioural' ? 'active' : '']"
                @click="setTab('behavioural')"
            >
                Behavioural Flags
                <span class="count">{{ behaviouralFlags.length }}</span>
            </button>
            <button
                :class="['tab-btn', activeTab === 'similarity' ? 'active' : '']"
                @click="setTab('similarity')"
            >
                Similarity Pairs
                <span class="count">{{ pairFlags.length }}</span>
            </button>
            <button
                :class="['tab-btn', activeTab === 'audit' ? 'active' : '']"
                @click="loadAudit(); setTab('audit')"
            >
                Audit Trail
            </button>
        </div>

        <!-- ── BEHAVIOURAL TAB ───────────────────────────────────────────── -->
        <template v-if="activeTab === 'behavioural'">
            <div class="exam-filter-row">
                <button
                    :class="['exam-filter-btn', bExamFilter === null ? 'active' : '']"
                    @click="bExamFilter = null"
                >All Exams</button>
                <button
                    v-for="ex in bExams"
                    :key="ex.id"
                    :class="['exam-filter-btn', bExamFilter === ex.id ? 'active' : '']"
                    @click="bExamFilter = ex.id"
                >{{ ex.title }}</button>
            </div>
            <div class="search-filter-row">
                <div class="search-wrap">
                    <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <input
                        v-model="searchQuery"
                        class="search-input"
                        placeholder="Search by username…"
                        @input="void 0"
                    />
                    <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</button>
                </div>
                <div class="filter-row">
                    <button
                        v-for="f in filters"
                        :key="f.value"
                        :class="['filter-btn', bFilter === f.value ? 'active' : '']"
                        @click="bFilter = f.value"
                    >
                        {{ f.label }}
                        <span class="count">{{ bCountByStatus(f.value) }}</span>
                    </button>
                </div>
            </div>

            <div v-if="loadingB" class="state-msg">Loading...</div>
            <div v-else-if="filteredB.length === 0" class="state-msg">No behavioural flags.</div>

            <div v-else class="flags-list">
                <div v-for="flag in filteredB" :key="flag.id" class="flag-card">

                    <!-- Row 1: identity + badges -->
                    <div class="flag-header">
                        <div class="flag-identity">
                            <div class="flag-title-row">
                                <span class="student-name link" @click="router.push('/dashboard/students/' + flag.student_id)">{{ flag.student }}</span>
                                <span class="mid-dot">·</span>
                                <span :class="['diff-chip', flag.question_difficulty]">{{ flag.question_difficulty }}</span>
                                <span class="question-name">{{ flag.question_title }}</span>
                            </div>
                            <div class="flag-meta-row">
                                <span class="exam-link" @click="router.push('/dashboard/history/' + flag.exam_id)">
                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                                    {{ flag.exam_title }}
                                </span>
                                <span class="meta-sep">·</span>
                                <span class="meta-chip">Attempt {{ flag.attempt_number }}</span>
                                <span class="meta-sep">·</span>
                                <span class="meta-chip lang">{{ flag.language }}</span>
                                <span class="meta-sep">·</span>
                                <span :class="['meta-status', flag.submission_status]">{{ flag.submission_status }}</span>
                                <span class="meta-sep">·</span>
                                <span class="meta-time">{{ fmtDate(flag.submitted_at) }}</span>
                            </div>
                        </div>
                        <div class="flag-right">
                            <span :class="['confidence-badge', flag.confidence]">{{ flag.confidence }}</span>
                            <span :class="['risk-score', riskClass(flag.risk_score)]">{{ (flag.risk_score * 100).toFixed(0) }}%</span>
                            <span :class="['review-badge', flag.review_status]">{{ flag.review_status }}</span>
                        </div>
                    </div>

                    <!-- Signal chips -->
                    <div class="signals-row">
                        <div v-for="signal in flag.signals_triggered" :key="signal" class="signal-chip">{{ signal }}</div>
                        <div v-if="flag.signals_triggered.length === 0" class="signal-chip muted">No strong signals</div>
                    </div>

                    <!-- Score bars -->
                    <div class="score-bars">
                        <div class="score-bar-row">
                            <span class="score-label">Paste</span>
                            <div class="score-track"><div class="score-fill" :style="{ width: (flag.paste_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (flag.paste_score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="score-bar-row">
                            <span class="score-label">Time</span>
                            <div class="score-track"><div class="score-fill" :style="{ width: (flag.time_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (flag.time_score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="score-bar-row">
                            <span class="score-label">Snapshot</span>
                            <div class="score-track"><div class="score-fill" :style="{ width: (flag.snapshot_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (flag.snapshot_score * 100).toFixed(0) }}%</span>
                        </div>
                        <div class="score-bar-row">
                            <span class="score-label">Submission</span>
                            <div class="score-track"><div class="score-fill" :style="{ width: (flag.submission_score * 100) + '%' }"/></div>
                            <span class="score-val">{{ (flag.submission_score * 100).toFixed(0) }}%</span>
                        </div>
                    </div>

                    <div v-if="flag.review_note" class="review-note">{{ flag.review_note }}</div>

                    <div v-if="flag.review_status === 'pending'" class="actions">
                        <input v-model="bNotes[flag.id]" placeholder="Add review note (optional)" />
                        <button class="confirm-btn" @click="reviewB(flag.id, 'confirmed')">Confirm</button>
                        <button class="dismiss-btn" @click="reviewB(flag.id, 'dismissed')">Dismiss</button>
                    </div>
                </div>
            </div>
        </template>

        <!-- ── AUDIT TRAIL TAB ─────────────────────────────────────────── -->
        <template v-if="activeTab === 'audit'">
            <div v-if="loadingAudit" class="state-msg">Loading audit log...</div>
            <div v-else-if="auditLogs.length === 0" class="state-msg">No review actions yet.</div>
            <div v-else class="audit-table">
                <div class="audit-header">
                    <span>Reviewer</span>
                    <span>Type</span>
                    <span>Flag ID</span>
                    <span>Decision</span>
                    <span>Note</span>
                    <span>When</span>
                </div>
                <div v-for="log in auditLogs" :key="log.id" class="audit-row">
                    <span class="audit-reviewer">{{ log.reviewed_by_username }}</span>
                    <span class="audit-type">{{ log.flag_type }}</span>
                    <span class="audit-id">#{{ log.flag_id }}</span>
                    <span :class="['audit-action', log.action]">{{ log.action }}</span>
                    <span class="audit-note">{{ log.note || '—' }}</span>
                    <span class="audit-time">{{ fmtDate(log.created_at) }}</span>
                </div>
            </div>
        </template>

        <!-- ── SIMILARITY TAB ───────────────────────────────────────────── -->
        <template v-if="activeTab === 'similarity'">
            <div class="exam-filter-row">
                <button
                    :class="['exam-filter-btn', pExamFilter === null ? 'active' : '']"
                    @click="pExamFilter = null"
                >All Exams</button>
                <button
                    v-for="ex in pExams"
                    :key="ex.id"
                    :class="['exam-filter-btn', pExamFilter === ex.id ? 'active' : '']"
                    @click="pExamFilter = ex.id"
                >{{ ex.title }}</button>
            </div>
            <div class="search-filter-row">
                <div class="search-wrap">
                    <svg class="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <input
                        v-model="searchQuery"
                        class="search-input"
                        placeholder="Search by username…"
                    />
                    <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</button>
                </div>
                <div class="filter-row">
                    <button
                        v-for="f in filters"
                        :key="f.value"
                        :class="['filter-btn', pFilter === f.value ? 'active' : '']"
                        @click="pFilter = f.value"
                    >
                        {{ f.label }}
                        <span class="count">{{ pCountByStatus(f.value) }}</span>
                    </button>
                </div>
            </div>

            <div v-if="loadingP" class="state-msg">Loading...</div>
            <div v-else-if="filteredP.length === 0" class="state-msg">No similarity pairs flagged.</div>

            <div v-else class="flags-list">
                <div v-for="flag in filteredP" :key="flag.id" class="flag-card">

                    <!-- Row 1: students + similarity score -->
                    <div class="flag-header">
                        <div class="flag-identity">
                            <div class="flag-title-row">
                                <span class="student-name link" @click="router.push('/dashboard/students/' + flag.submission_1_student_id)">{{ flag.submission_1_student }}</span>
                                <span class="vs">vs</span>
                                <span class="student-name link" @click="router.push('/dashboard/students/' + flag.submission_2_student_id)">{{ flag.submission_2_student }}</span>
                            </div>
                            <div class="flag-meta-row">
                                <span :class="['diff-chip', flag.question_difficulty]">{{ flag.question_difficulty }}</span>
                                <span class="question-name">{{ flag.question_title }}</span>
                                <span class="meta-sep">·</span>
                                <span class="exam-link" @click="router.push('/dashboard/history/' + flag.exam_id)">
                                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                                    {{ flag.exam_title }}
                                </span>
                            </div>
                            <!-- Per-submission detail row -->
                            <div class="pair-submissions">
                                <span class="pair-sub">
                                    <strong>{{ flag.submission_1_student }}</strong>
                                    — attempt {{ flag.submission_1_attempt }}
                                    · {{ flag.submission_1_language }}
                                    · <span :class="['meta-status', flag.submission_1_status]">{{ flag.submission_1_status }}</span>
                                </span>
                                <span class="pair-divider">|</span>
                                <span class="pair-sub">
                                    <strong>{{ flag.submission_2_student }}</strong>
                                    — attempt {{ flag.submission_2_attempt }}
                                    · {{ flag.submission_2_language }}
                                    · <span :class="['meta-status', flag.submission_2_status]">{{ flag.submission_2_status }}</span>
                                </span>
                            </div>
                        </div>
                        <div class="flag-right">
                            <div class="similarity-bar">
                                <div class="similarity-fill" :style="{ width: (flag.similarity_score * 100) + '%' }" :class="similarityClass(flag.similarity_score)"/>
                            </div>
                            <span :class="['similarity-pct', similarityClass(flag.similarity_score)]">{{ (flag.similarity_score * 100).toFixed(1) }}%</span>
                            <span :class="['review-badge', flag.review_status]">{{ flag.review_status }}</span>
                            <button class="view-code-btn" @click="toggleCode(flag)">
                                {{ codeExpanded.has(flag.id) ? 'Hide Code' : 'View Code' }}
                            </button>
                            <button class="view-code-btn ai-btn" @click="toggleExplanation(flag)">
                                {{ explExpanded.has(flag.id) ? 'Hide AI Explanation' : 'AI Explanation' }}
                            </button>
                        </div>
                    </div>

                    <!-- Code comparison panel -->
                    <div v-if="codeExpanded.has(flag.id)" class="code-panel">
                        <div v-if="codeLoading.has(flag.id)" class="code-loading">Loading code...</div>
                        <div v-else-if="codeData[flag.id]" class="code-columns">
                            <div class="code-col">
                                <div class="code-col-header">{{ flag.submission_1_student }} — attempt {{ flag.submission_1_attempt }}</div>
                                <div class="code-body">
                                    <div
                                        v-for="(line, i) in codeData[flag.id].lines1"
                                        :key="i"
                                        :class="['code-line', codeData[flag.id].matched1.has(i) ? 'match' : '']"
                                    >
                                        <span class="line-num">{{ i + 1 }}</span>
                                        <span class="line-text">{{ line || ' ' }}</span>
                                    </div>
                                </div>
                            </div>
                            <div class="code-col">
                                <div class="code-col-header">{{ flag.submission_2_student }} — attempt {{ flag.submission_2_attempt }}</div>
                                <div class="code-body">
                                    <div
                                        v-for="(line, i) in codeData[flag.id].lines2"
                                        :key="i"
                                        :class="['code-line', codeData[flag.id].matched2.has(i) ? 'match' : '']"
                                    >
                                        <span class="line-num">{{ i + 1 }}</span>
                                        <span class="line-text">{{ line || ' ' }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- AI explanation panel (Feature 3) — evidence for the trainer, not a verdict -->
                    <div v-if="explExpanded.has(flag.id)" class="ai-expl-panel">
                        <div v-if="explLoading.has(flag.id)" class="code-loading">Loading explanation...</div>
                        <div v-else-if="explData[flag.id]" class="ai-expl-body">
                            <div class="ai-expl-head">
                                <span class="ai-expl-title">AI Explanation</span>
                                <span :class="['confidence-badge', explData[flag.id].confidence]">{{ explData[flag.id].confidence }}</span>
                            </div>
                            <p class="ai-expl-summary">{{ explData[flag.id].summary }}</p>
                            <ul class="ai-expl-matches">
                                <li v-for="(m, i) in explData[flag.id].matches" :key="i">{{ m }}</li>
                            </ul>
                            <p class="ai-expl-disclaimer">AI-generated evidence — the trainer makes the final call.</p>
                        </div>
                        <div v-else-if="explPending.has(flag.id)" class="ai-expl-empty">
                            No AI explanation available for this pair yet.
                        </div>
                    </div>

                    <div v-if="flag.review_note" class="review-note">{{ flag.review_note }}</div>

                    <div v-if="flag.review_status === 'pending'" class="actions">
                        <input v-model="pNotes[flag.id]" placeholder="Add review note (optional)" />
                        <button class="confirm-btn" @click="reviewP(flag.id, 'confirmed')">Confirm</button>
                        <button class="dismiss-btn" @click="reviewP(flag.id, 'dismissed')">Dismiss</button>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

interface BehaviouralFlag {
    id: number
    submission_id: number
    student: string
    student_id: number
    question_title: string
    question_difficulty: string
    exam_title: string
    exam_id: number
    attempt_number: number
    submission_status: string
    language: string
    submitted_at: string
    risk_score: number
    confidence: 'low' | 'medium' | 'high'
    paste_score: number
    time_score: number
    snapshot_score: number
    submission_score: number
    signals_triggered: string[]
    review_status: string
    review_note: string
}

interface PairFlag {
    id: number
    submission_1: number
    submission_2: number
    submission_1_student: string
    submission_1_student_id: number
    submission_1_attempt: number
    submission_1_language: string
    submission_1_status: string
    submission_2_student: string
    submission_2_student_id: number
    submission_2_attempt: number
    submission_2_language: string
    submission_2_status: string
    question_title: string
    question_difficulty: string
    exam_title: string
    exam_id: number
    similarity_score: number
    review_status: string
    review_note: string
}

interface AuditLog {
    id: number
    flag_type: string
    flag_id: number
    action: string
    note: string
    reviewed_by_username: string
    created_at: string
}

function setTab(tab: 'behavioural' | 'similarity' | 'audit') {
    activeTab.value = tab
    searchQuery.value = ''
    bExamFilter.value = null
    pExamFilter.value = null
}
const activeTab = ref<'behavioural' | 'similarity' | 'audit'>('behavioural')
const auditLogs = ref<AuditLog[]>([])
const loadingAudit = ref(false)
let auditLoaded = false

const behaviouralFlags = ref<BehaviouralFlag[]>([])
const pairFlags = ref<PairFlag[]>([])
const loadingB = ref<boolean>(true)
const loadingP = ref<boolean>(true)

const bFilter = ref<string>('pending')
const pFilter = ref<string>('pending')

const bNotes = ref<Record<number, string>>({})
const pNotes = ref<Record<number, string>>({})

interface CodeComparison {
    lines1: string[]
    lines2: string[]
    matched1: Set<number>
    matched2: Set<number>
}
const codeExpanded = ref<Set<number>>(new Set())
const codeLoading = ref<Set<number>>(new Set())
const codeData = ref<Record<number, CodeComparison>>({})

// AI plagiarism explanation (Feature 3) — lazy-loaded per flag on demand
interface PlagiarismExplanation {
    summary: string
    matches: string[]
    confidence: 'low' | 'medium' | 'high'
}
const explExpanded = ref<Set<number>>(new Set())
const explLoading = ref<Set<number>>(new Set())
const explData = ref<Record<number, PlagiarismExplanation>>({})
const explPending = ref<Set<number>>(new Set())  // flags whose explanation isn't ready yet

const searchQuery = ref('')
const bExamFilter = ref<number | null>(null)
const pExamFilter = ref<number | null>(null)

const filters = [
    { label: 'Pending',   value: 'pending'   },
    { label: 'Confirmed', value: 'confirmed' },
    { label: 'Dismissed', value: 'dismissed' },
    { label: 'All',       value: 'all'       },
]

const bExams = computed(() => {
    const seen = new Map<number, string>()
    behaviouralFlags.value.forEach(f => { if (!seen.has(f.exam_id)) seen.set(f.exam_id, f.exam_title) })
    return [...seen.entries()].map(([id, title]) => ({ id, title })).sort((a, b) => a.title.localeCompare(b.title))
})

const pExams = computed(() => {
    const seen = new Map<number, string>()
    pairFlags.value.forEach(f => { if (!seen.has(f.exam_id)) seen.set(f.exam_id, f.exam_title) })
    return [...seen.entries()].map(([id, title]) => ({ id, title })).sort((a, b) => a.title.localeCompare(b.title))
})

const filteredB = computed<BehaviouralFlag[]>(() => {
    const q = searchQuery.value.trim().toLowerCase()
    return behaviouralFlags.value.filter(f => {
        const statusOk = bFilter.value === 'all' || f.review_status === bFilter.value
        const searchOk = !q || f.student.toLowerCase().includes(q)
        const examOk = !bExamFilter.value || f.exam_id === bExamFilter.value
        return statusOk && searchOk && examOk
    })
})

const filteredP = computed<PairFlag[]>(() => {
    const q = searchQuery.value.trim().toLowerCase()
    return pairFlags.value.filter(f => {
        const statusOk = pFilter.value === 'all' || f.review_status === pFilter.value
        const searchOk = !q ||
            f.submission_1_student.toLowerCase().includes(q) ||
            f.submission_2_student.toLowerCase().includes(q)
        const examOk = !pExamFilter.value || f.exam_id === pExamFilter.value
        return statusOk && searchOk && examOk
    })
})

function bCountByStatus(s: string): number {
    if (s === 'all') return behaviouralFlags.value.length
    return behaviouralFlags.value.filter(f => f.review_status === s).length
}

function pCountByStatus(s: string): number {
    if (s === 'all') return pairFlags.value.length
    return pairFlags.value.filter(f => f.review_status === s).length
}

function riskClass(score: number): string {
    if (score >= 0.7) return 'high'
    if (score >= 0.4) return 'medium'
    return 'low'
}

function similarityClass(score: number): string {
    if (score >= 0.9) return 'high'
    if (score >= 0.8) return 'medium'
    return 'low'
}

onMounted(async () => {
    await Promise.all([
        api.get('/plagiarism/behavioural/').then(r => { behaviouralFlags.value = r.data }).catch(() => {}),
        api.get('/plagiarism/').then(r => { pairFlags.value = r.data }).catch(() => {}),
    ])
    loadingB.value = false
    loadingP.value = false
})

async function reviewB(flagId: number, decision: string): Promise<void> {
    const res = await api.patch(`/plagiarism/behavioural/${flagId}/review/`, {
        review_status: decision,
        review_note: bNotes.value[flagId] || '',
    })
    const idx = behaviouralFlags.value.findIndex(f => f.id === flagId)
    if (idx !== -1) behaviouralFlags.value[idx] = res.data
    auditLoaded = false
}

async function reviewP(flagId: number, decision: string): Promise<void> {
    const res = await api.patch(`/plagiarism/${flagId}/review/`, {
        review_status: decision,
        review_note: pNotes.value[flagId] || '',
    })
    const idx = pairFlags.value.findIndex(f => f.id === flagId)
    if (idx !== -1) pairFlags.value[idx] = res.data
    auditLoaded = false
}

function findMatchedLines(lines1: string[], lines2: string[]): { matched1: Set<number>, matched2: Set<number> } {
    const normalized2 = lines2.map(l => l.trim())
    const set2 = new Map<string, number[]>()
    normalized2.forEach((l, i) => {
        if (l.length > 2) {
            if (!set2.has(l)) set2.set(l, [])
            set2.get(l)!.push(i)
        }
    })
    const matched1 = new Set<number>()
    const matched2 = new Set<number>()
    lines1.forEach((raw, i) => {
        const norm = raw.trim()
        if (norm.length > 2 && set2.has(norm)) {
            matched1.add(i)
            set2.get(norm)!.forEach(j => matched2.add(j))
        }
    })
    return { matched1, matched2 }
}

async function toggleCode(flag: PairFlag): Promise<void> {
    const id = flag.id
    if (codeExpanded.value.has(id)) {
        codeExpanded.value.delete(id)
        codeExpanded.value = new Set(codeExpanded.value)
        return
    }
    codeExpanded.value.add(id)
    codeExpanded.value = new Set(codeExpanded.value)
    if (codeData.value[id]) return

    codeLoading.value.add(id)
    codeLoading.value = new Set(codeLoading.value)
    try {
        const [r1, r2] = await Promise.all([
            api.get(`/submissions/${flag.submission_1}/`),
            api.get(`/submissions/${flag.submission_2}/`),
        ])
        const lines1 = (r1.data.code || '').split('\n')
        const lines2 = (r2.data.code || '').split('\n')
        const { matched1, matched2 } = findMatchedLines(lines1, lines2)
        codeData.value[id] = { lines1, lines2, matched1, matched2 }
    } finally {
        codeLoading.value.delete(id)
        codeLoading.value = new Set(codeLoading.value)
    }
}

async function toggleExplanation(flag: PairFlag): Promise<void> {
    const id = flag.id
    if (explExpanded.value.has(id)) {
        explExpanded.value.delete(id)
        explExpanded.value = new Set(explExpanded.value)
        return
    }
    explExpanded.value.add(id)
    explExpanded.value = new Set(explExpanded.value)
    if (explData.value[id]) return  // already loaded

    explLoading.value.add(id)
    explLoading.value = new Set(explLoading.value)
    explPending.value.delete(id)
    explPending.value = new Set(explPending.value)
    try {
        const res = await api.get(`/ai/plagiarism-explanation/${id}/`)
        if (res.data && res.data.summary) {
            explData.value[id] = res.data as PlagiarismExplanation
        } else {
            // {status: 'pending'} — explanation not generated yet (or unavailable)
            explPending.value.add(id)
            explPending.value = new Set(explPending.value)
        }
    } catch {
        explPending.value.add(id)
        explPending.value = new Set(explPending.value)
    } finally {
        explLoading.value.delete(id)
        explLoading.value = new Set(explLoading.value)
    }
}

async function loadAudit(): Promise<void> {
    if (auditLoaded) return
    loadingAudit.value = true
    try {
        const res = await api.get('/plagiarism/audit/')
        auditLogs.value = res.data
        auditLoaded = true
    } finally {
        loadingAudit.value = false
    }
}

function fmtDate(d: string): string {
    return new Date(d).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }

.tab-row { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--border); }
.tab-btn {
    padding: 9px 18px;
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-muted);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
    margin-bottom: -1px;
}
.tab-btn:hover { color: var(--text); }
.tab-btn.active { border-bottom-color: var(--red); color: var(--red); }

.exam-filter-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 12px;
}
.exam-filter-btn {
    padding: 5px 14px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: transparent;
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
}
.exam-filter-btn:hover { border-color: var(--border2); color: var(--text); }
.exam-filter-btn.active { background: var(--surface2); border-color: var(--border2); color: var(--text); font-weight: 600; }

.search-filter-row { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
.search-wrap {
    display: flex; align-items: center; gap: 8px;
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 0 12px; max-width: 320px; transition: border-color 0.15s;
}
.search-wrap:focus-within { border-color: var(--border2); }
.search-icon { color: var(--text-muted); flex-shrink: 0; }
.search-input {
    flex: 1; background: transparent; border: none; outline: none;
    color: var(--text); font-size: 13px; padding: 9px 0;
}
.search-input::placeholder { color: var(--text-muted); }
.search-clear {
    background: transparent; border: none; color: var(--text-muted); cursor: pointer;
    font-size: 12px; padding: 2px 4px; border-radius: 4px; line-height: 1;
}
.search-clear:hover { color: var(--text); }

.filter-row { display: flex; gap: 8px; }
.filter-btn {
    padding: 7px 16px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s;
}
.filter-btn:hover { border-color: var(--border2); color: var(--text); }
.filter-btn.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }
.count { background: var(--surface2); padding: 1px 7px; border-radius: 10px; font-size: 11px; }

.state-msg { color: var(--text-muted); padding: 40px 0; }
.flags-list { display: flex; flex-direction: column; gap: 12px; }
.flag-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    transition: border-color 0.15s;
}
.flag-card:hover { border-color: var(--border2); }
.flag-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px; gap: 16px; }

.flag-identity { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.flag-title-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.flag-meta-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12px; }

.student-name { font-weight: 700; font-size: 15px; color: var(--text); }
.student-name.link { cursor: pointer; }
.student-name.link:hover { color: var(--red); text-decoration: underline; }

.mid-dot { color: var(--border2); }
.question-name { font-size: 13px; color: var(--text-dim); }

.exam-link {
    display: inline-flex; align-items: center; gap: 4px;
    color: var(--text-muted); font-size: 12px; cursor: pointer;
    transition: color 0.15s;
}
.exam-link:hover { color: var(--text); }

.meta-sep { color: var(--border2); }
.meta-chip { color: var(--text-muted); }
.meta-chip.lang { font-family: monospace; font-size: 11px; background: var(--surface2); border: 1px solid var(--border); border-radius: 6px; padding: 1px 6px; }
.meta-time { color: var(--text-dim); }

.meta-status { font-weight: 600; font-size: 11px; }
.meta-status.passed  { color: var(--green); }
.meta-status.failed  { color: var(--red); }
.meta-status.pending { color: var(--yellow); }
.meta-status.running { color: var(--blue, #3498db); }
.meta-status.error   { color: var(--red); }

.pair-submissions { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--text-dim); flex-wrap: wrap; }
.pair-sub { display: flex; align-items: center; gap: 4px; }
.pair-divider { color: var(--border2); }

.vs { color: var(--text-dim); font-size: 12px; font-style: italic; }
.flag-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; justify-content: flex-end; flex-shrink: 0; }

.diff-chip { font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 8px; border-radius: 10px; }
.diff-chip.easy   { background: rgba(46,204,113,0.12); color: var(--green); }
.diff-chip.medium { background: rgba(241,196,15,0.1);  color: var(--yellow); }
.diff-chip.hard   { background: var(--red-dim);         color: var(--red); }

/* Confidence badge — mirrors risk level */
.confidence-badge {
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.confidence-badge.high { background: var(--red-dim); color: var(--red); }
.confidence-badge.medium { background: rgba(241,196,15,0.12); color: var(--yellow); }
.confidence-badge.low { background: rgba(52,152,219,0.12); color: var(--blue); }

.risk-score { font-size: 13px; font-weight: 700; }
.risk-score.high { color: var(--red); }
.risk-score.medium { color: var(--yellow); }
.risk-score.low { color: var(--text-muted); }

/* Triggered signal pills */
.signals-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.signal-chip {
    padding: 4px 10px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 11px;
    color: var(--text-muted);
}
.signal-chip.muted { color: var(--text-dim); border-style: dashed; }

/* Four-signal breakdown bars */
.score-bars { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.score-bar-row { display: flex; align-items: center; gap: 8px; }
.score-label { font-size: 11px; color: var(--text-dim); width: 72px; flex-shrink: 0; }
.score-track { flex: 1; height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; }
.score-fill { height: 100%; background: var(--red); border-radius: 2px; }
.score-val { font-size: 11px; color: var(--text-muted); width: 32px; text-align: right; }

.similarity-bar { width: 80px; height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.similarity-fill { height: 100%; border-radius: 3px; }
.similarity-fill.high { background: var(--red); }
.similarity-fill.medium { background: var(--yellow); }
.similarity-fill.low { background: var(--green); }
.similarity-pct { font-weight: 700; font-size: 14px; }
.similarity-pct.high { color: var(--red); }
.similarity-pct.medium { color: var(--yellow); }
.similarity-pct.low { color: var(--green); }

.review-badge {
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}
.review-badge.pending   { background: rgba(241,196,15,0.12);  color: var(--yellow); }
.review-badge.confirmed { background: var(--red-dim);          color: var(--red);    }
.review-badge.dismissed { background: rgba(46,204,113,0.12);   color: var(--green);  }

.review-note {
    font-size: 13px;
    color: var(--text-dim);
    margin-bottom: 12px;
    font-style: italic;
    padding: 8px 12px;
    background: var(--surface2);
    border-radius: var(--radius-sm);
}
.actions { display: flex; gap: 8px; align-items: center; margin-top: 12px; }
.actions input { flex: 1; }
.confirm-btn, .dismiss-btn {
    padding: 7px 16px;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    transition: opacity 0.15s;
}
.confirm-btn { background: var(--red); color: white; }
.confirm-btn:hover { opacity: 0.85; }
.dismiss-btn { background: rgba(46,204,113,0.15); color: var(--green); border: 1px solid rgba(46,204,113,0.3); }
.dismiss-btn:hover { background: rgba(46,204,113,0.25); }

.audit-table {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.audit-header, .audit-row {
    display: grid;
    grid-template-columns: 120px 100px 70px 90px 1fr 140px;
    gap: 12px;
    padding: 11px 18px;
    align-items: center;
}
.audit-header {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
}
.audit-row { border-bottom: 1px solid var(--border); font-size: 13px; }
.audit-row:last-child { border-bottom: none; }
.audit-reviewer { font-weight: 600; color: var(--text); }
.audit-type { color: var(--text-muted); }
.audit-id { color: var(--text-dim); font-family: monospace; }
.audit-action {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    padding: 2px 8px;
    border-radius: 10px;
    width: fit-content;
}
.audit-action.confirmed { background: var(--red-dim); color: var(--red); }
.audit-action.dismissed { background: rgba(46,204,113,0.12); color: var(--green); }
.audit-note { color: var(--text-dim); font-size: 12px; font-style: italic; }
.audit-time { color: var(--text-dim); font-size: 12px; }

/* View Code button */
.view-code-btn {
    padding: 4px 12px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 11px;
    cursor: pointer;
    transition: all 0.15s;
    white-space: nowrap;
}
.view-code-btn:hover { border-color: var(--border2); color: var(--text); }
.view-code-btn.ai-btn { border-color: var(--blue); color: var(--blue); }
.view-code-btn.ai-btn:hover { background: rgba(52,152,219,0.1); }

/* AI explanation panel (Feature 3) */
.ai-expl-panel {
    margin-top: 12px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface2);
    padding: 14px 16px;
}
.ai-expl-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ai-expl-title { font-size: 12px; font-weight: 700; color: var(--text); }
.ai-expl-summary { font-size: 13px; color: var(--text); line-height: 1.6; margin-bottom: 8px; }
.ai-expl-matches { margin: 0 0 8px; padding-left: 18px; }
.ai-expl-matches li { font-size: 12px; color: var(--text-muted); line-height: 1.6; }
.ai-expl-disclaimer { font-size: 11px; color: var(--text-dim); font-style: italic; }
.ai-expl-empty { font-size: 12px; color: var(--text-muted); }

/* Code comparison panel */
.code-panel {
    margin: 12px -20px -20px;
    border-top: 1px solid var(--border);
    background: #0a0d14;
}
.code-loading { padding: 20px; color: var(--text-muted); font-size: 13px; }
.code-columns { display: grid; grid-template-columns: 1fr 1fr; }
.code-col { min-width: 0; }
.code-col:first-child { border-right: 1px solid var(--border); }
.code-col-header {
    padding: 8px 14px;
    font-size: 11px;
    font-weight: 700;
    color: var(--text-dim);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
    font-family: monospace;
    letter-spacing: 0.3px;
}
.code-body { overflow-x: auto; max-height: 420px; overflow-y: auto; }
.code-line {
    display: flex;
    align-items: flex-start;
    gap: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    line-height: 1.6;
    white-space: pre;
}
.code-line.match { background: rgba(16, 185, 129, 0.08); border-left: 2px solid var(--green); }
.code-line:not(.match) { border-left: 2px solid transparent; }
.line-num {
    flex-shrink: 0;
    width: 38px;
    padding: 0 8px 0 6px;
    color: var(--text-dim);
    text-align: right;
    font-size: 11px;
    user-select: none;
    border-right: 1px solid var(--border);
    background: rgba(0,0,0,0.2);
}
.line-text {
    padding: 0 12px;
    color: var(--text);
    flex: 1;
}
.code-line.match .line-text { color: #d1fae5; }
</style>
