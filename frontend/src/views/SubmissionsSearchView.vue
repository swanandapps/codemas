<template>
    <div class="search-page">
        <div class="page-header">
            <div>
                <h1>Submissions</h1>
                <p class="page-sub">Search and filter all student submissions</p>
            </div>
        </div>

        <div class="filters-card">
            <div class="filters-row">
                <input
                    v-model="filters.search"
                    placeholder="Search student, question, exam..."
                    @keydown.enter="load"
                    class="search-input"
                />
                <select v-model="filters.language">
                    <option value="">All languages</option>
                    <option value="javascript">JavaScript</option>
                    <option value="python">Python</option>
                </select>
                <select v-model="filters.status">
                    <option value="">All statuses</option>
                    <option value="passed">Passed</option>
                    <option value="failed">Failed</option>
                    <option value="running">Running</option>
                    <option value="pending">Pending</option>
                </select>
                <button class="search-btn" @click="load" :disabled="loading">
                    {{ loading ? 'Searching...' : 'Search' }}
                </button>
                <button class="reset-btn" @click="reset">Reset</button>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Searching...</div>
        <div v-else-if="!loaded" class="state-msg hint">Enter a search term or choose filters and press Search</div>
        <div v-else-if="submissions.length === 0" class="state-msg">No submissions match your filters.</div>

        <div v-else>
            <div class="results-meta">{{ plural(totalCount, 'submission') }} found</div>
            <div class="table-scroll">
            <div class="submissions-table">
                <div class="table-header">
                    <span>Student</span>
                    <span>Question</span>
                    <span>Exam</span>
                    <span>Language</span>
                    <span>Status</span>
                    <span>Submitted</span>
                    <span>Code</span>
                </div>
                <div v-for="s in submissions" :key="s.id" class="table-row">
                    <button type="button" class="col-student" @click="$router.push(`/dashboard/students/${s.student_id}`)">
                        {{ s.student_username }}
                    </button>
                    <span class="col-question">{{ s.question_title }}</span>
                    <span class="col-exam">{{ s.exam_title }}</span>
                    <span class="col-lang">
                        <span class="lang-chip">{{ s.language }}</span>
                    </span>
                    <span class="col-status">
                        <span :class="['status-chip', s.status]">{{ s.status }}</span>
                    </span>
                    <span class="col-time">{{ formatDateTime(s.submitted_at) }}</span>
                    <span class="col-code">
                        <button class="code-btn" @click="openCode(s.id)">View</button>
                        <button class="code-btn details-btn" @click="$router.push(`/dashboard/submissions/${s.id}`)">Details</button>
                    </span>
                </div>
            </div>
            </div>

            <div class="pagination-row" v-if="totalCount > 20">
                <button class="page-btn" @click="prevPage" :disabled="page === 1">Prev</button>
                <span class="page-info">Page {{ page }}</span>
                <button class="page-btn" @click="nextPage" :disabled="!hasNext">Next</button>
            </div>
        </div>

        <!-- Code modal -->
        <div v-if="codeModal" class="modal-overlay" @click.self="codeModal = null">
            <div class="code-modal">
                <div class="modal-header">
                    <span class="modal-header-meta">
                        <span>{{ codeModal.student_username }}</span>
                        <span>{{ codeModal.question_title }}</span>
                    </span>
                    <button class="close-btn" @click="codeModal = null" aria-label="Close">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                    </button>
                </div>
                <div class="modal-meta">
                    <span :class="['status-chip', codeModal.status]">{{ codeModal.status }}</span>
                    <span class="lang-chip">{{ codeModal.language }}</span>
                    <span class="meta-info">Attempt #{{ codeModal.attempt_number }}</span>
                    <span class="meta-info" v-if="codeModal.had_paste_event">Paste detected</span>
                </div>
                <pre class="code-pre">{{ codeModal.code }}</pre>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import api from '../api'
import { formatDateTime, plural } from '../utils/format'

interface Submission {
    id: number
    student_username: string
    student_id?: number
    question_title: string
    exam_title: string
    language: string
    status: string
    submitted_at: string
    attempt_number: number
    code: string
    had_paste_event?: boolean
}

const submissions = ref<Submission[]>([])
const loading = ref(false)
const loaded = ref(false)
const totalCount = ref(0)
const hasNext = ref(false)
const page = ref(1)
const codeModal = ref<Submission | null>(null)

const filters = reactive({ search: '', language: '', status: '' })

onMounted(load)

async function load() {
    loading.value = true
    const params: Record<string, string | number> = { page: page.value }
    if (filters.search) params.search = filters.search
    if (filters.language) params.language = filters.language
    if (filters.status) params.status = filters.status

    try {
        const res = await api.get('/submissions/', { params })
        const data = res.data
        submissions.value = data.results ?? data
        totalCount.value = data.count ?? data.length
        hasNext.value = !!data.next
        loaded.value = true
    } finally {
        loading.value = false
    }
}

function reset() {
    filters.search = ''
    filters.language = ''
    filters.status = ''
    page.value = 1
    submissions.value = []
    loaded.value = false
}

async function prevPage() {
    if (page.value > 1) { page.value--; await load() }
}
async function nextPage() {
    if (hasNext.value) { page.value++; await load() }
}

async function openCode(id: number) {
    const res = await api.get(`/submissions/${id}/`)
    codeModal.value = res.data
}
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }

.filters-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 20px;
}
.filters-row { display: flex; gap: 12px; flex-wrap: wrap; align-items: center; }
.search-input { flex: 1; min-width: 200px; }
.filters-row select { width: 150px; }
.search-btn {
    padding: 10px 20px;
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    border-radius: var(--radius-pill);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
}
.search-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.reset-btn {
    padding: 10px 16px;
    background: var(--surface);
    border: 1px solid var(--border2);
    border-radius: var(--radius-pill);
    color: var(--text);
    font-size: 13px;
    cursor: pointer;
}
.reset-btn:hover { color: var(--text); }

.state-msg { color: var(--text-muted); padding: 40px 0; text-align: center; }
.state-msg.hint { color: var(--text-dim); }
.results-meta { font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }

.table-scroll { overflow-x: auto; }
.submissions-table {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
    min-width: 820px;
}
.table-header, .table-row {
    display: grid;
    grid-template-columns: 130px 1fr 120px 90px 90px 130px 140px;
    gap: 12px;
    padding: 11px 18px;
    align-items: center;
}
.table-header {
    font-size: 11px;
    font-weight: 700;
    color: var(--text-dim);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
}
.table-row { border-bottom: 1px solid var(--border); font-size: 13px; }
.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--surface2); }
.col-student { font-weight: 600; color: var(--accent-hover); cursor: pointer; background: none; border: none; padding: 0; font-size: 13px; text-align: left; font-family: inherit; min-height: 40px; }
.col-student:hover { text-decoration: underline; }
.col-question { color: var(--text); }
.col-exam { color: var(--text-muted); font-size: 12px; }
.col-time { color: var(--text-muted); font-size: 12px; }

.lang-chip {
    font-size: 11px;
    padding: 2px 8px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
}
.status-chip {
    font-size: 11px;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 10px;
}
.status-chip.passed { background: var(--green-dim); color: var(--green-ink); }
.status-chip.failed { background: var(--red-dim); color: var(--red-ink); }
.status-chip.running { background: var(--yellow-dim); color: var(--amber-ink); }
.status-chip.pending { background: var(--surface3); color: var(--text-dim); }

.code-btn {
    padding: 4px 10px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    color: var(--text-muted);
    font-size: 12px;
    cursor: pointer;
}
.code-btn:hover { color: var(--text); }
.col-code { display: flex; gap: 6px; }
.details-btn { border-color: var(--accent); color: var(--accent-hover); }
.details-btn:hover { background: var(--accent-tint); color: var(--accent-hover); }

.pagination-row { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.page-btn {
    padding: 7px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
}
.page-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--text-muted); }

.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(33,25,27,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}
.code-modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    width: 700px;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    box-shadow: var(--shadow-lg);
}
.modal-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--border);
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
}
.modal-header-meta { display: flex; align-items: center; gap: 8px; }
.close-btn {
    background: transparent;
    border: none;
    color: var(--text-muted);
    font-size: 16px;
    cursor: pointer;
    padding: 2px 6px;
}
.modal-meta {
    display: flex;
    gap: 10px;
    align-items: center;
    padding: 12px 20px;
    border-bottom: 1px solid var(--border);
}
.meta-info { font-size: 12px; color: var(--text-dim); }
.code-pre {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    font-size: 13px;
    line-height: 1.6;
    background: var(--code-bg);
    color: var(--code-text);
    font-family: var(--font-mono);
    white-space: pre-wrap;
    word-break: break-all;
}

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .filters-row { flex-direction: column; align-items: stretch; }
    .filters-row select { width: 100%; }
    .search-input { min-width: 0; }
}

@media (max-width: 600px) {
    .code-modal { width: calc(100vw - 32px); }
}
</style>
