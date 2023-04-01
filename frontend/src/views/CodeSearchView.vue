<template>
    <div class="search-page">
        <div class="page-header">
            <div>
                <h1>Code Similarity Search</h1>
                <p class="page-sub">Paste any code — find similar submissions across all exams</p>
            </div>
        </div>

        <div class="search-layout">
            <!-- ── Left: query panel ───────────────────────────────────────── -->
            <div class="query-panel">
                <div class="card">
                    <div class="card-title">Query Code</div>

                    <div class="lang-row">
                        <label class="field-label">Language filter</label>
                        <select v-model="language" class="lang-select">
                            <option value="">All languages</option>
                            <option value="python">Python</option>
                            <option value="javascript">JavaScript</option>
                            <option value="java">Java</option>
                            <option value="cpp">C++</option>
                        </select>
                    </div>

                    <div class="editor-wrap">
                        <textarea
                            v-model="queryCode"
                            class="code-editor"
                            placeholder="Paste code here..."
                            spellcheck="false"
                        />
                    </div>

                    <div class="search-footer">
                        <span class="char-count">{{ queryCode.length }} chars</span>
                        <button
                            class="search-btn"
                            :disabled="!queryCode.trim() || loading"
                            @click="search"
                        >
                            <svg v-if="!loading" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                            <span v-if="loading" class="spinner" />
                            {{ loading ? 'Searching...' : 'Find Similar' }}
                        </button>
                    </div>
                </div>
            </div>

            <!-- ── Right: results panel ───────────────────────────────────── -->
            <div class="results-panel">
                <div v-if="!searched" class="empty-state">
                    <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.3"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
                    <p>Results will appear here</p>
                </div>

                <template v-else>
                    <div class="results-meta">
                        <span class="results-count">{{ results.length }} matches</span>
                        <span class="results-sub">searched {{ totalSearched }} submissions</span>
                    </div>

                    <div v-if="results.length === 0" class="empty-state">
                        <p>No similar submissions found</p>
                    </div>

                    <div v-for="r in results" :key="r.submission_id" class="result-card clickable" @click="router.push(`/dashboard/submissions/${r.submission_id}`)" >
                        <div class="result-header">
                            <div class="result-meta">
                                <span class="result-student">{{ r.student }}</span>
                                <span class="result-dot">·</span>
                                <span class="result-question">{{ r.question }}</span>
                                <span class="result-dot">·</span>
                                <span class="result-exam">{{ r.exam }}</span>
                            </div>
                            <div class="result-right">
                                <span :class="['lang-badge', r.language]">{{ r.language }}</span>
                                <span :class="['status-badge', r.status]">{{ r.status }}</span>
                                <span :class="['sim-badge', simClass(r.similarity)]">
                                    {{ (r.similarity * 100).toFixed(1) }}% match
                                </span>
                            </div>
                        </div>

                        <div class="sim-bar-wrap">
                            <div class="sim-bar" :class="simClass(r.similarity)" :style="{ width: (r.similarity * 100) + '%' }" />
                        </div>

                        <pre class="code-preview">{{ r.code_preview }}{{ r.code_preview.length >= 300 ? '...' : '' }}</pre>

                        <div class="result-footer">
                            <span class="result-date">{{ formatDate(r.submitted_at) }}</span>
                            <span class="result-id">sub #{{ r.submission_id }}</span>
                        </div>
                    </div>
                </template>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()

const queryCode   = ref('')
const language    = ref('')
const loading     = ref(false)
const searched    = ref(false)
const results     = ref<any[]>([])
const totalSearched = ref(0)

async function search() {
    loading.value = true
    try {
        const res = await api.post('/plagiarism/search/', {
            code:     queryCode.value,
            language: language.value,
            top_k:    15,
        })
        results.value      = res.data.results
        totalSearched.value = res.data.total_searched
        searched.value     = true
    } finally {
        loading.value = false
    }
}

function simClass(score: number) {
    if (score >= 0.8) return 'high'
    if (score >= 0.5) return 'mid'
    return 'low'
}

function formatDate(iso: string) {
    return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-sub { color: var(--text-dim); font-size: 13px; margin-top: 4px; }

.search-layout {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 16px;
    align-items: start;
}

/* Query panel */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }
.card-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 16px; }

.lang-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.field-label { font-size: 12px; color: var(--text-muted); }
.lang-select {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-size: 12px;
    padding: 5px 10px;
}

.editor-wrap { margin-bottom: 12px; }
.code-editor {
    width: 100%;
    min-height: 340px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text);
    font-family: monospace;
    font-size: 12px;
    line-height: 1.6;
    padding: 12px;
    resize: vertical;
    box-sizing: border-box;
}
.code-editor:focus { outline: none; border-color: var(--red); }

.search-footer { display: flex; align-items: center; justify-content: space-between; }
.char-count { font-size: 11px; color: var(--text-dim); }
.search-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 9px 18px;
    background: var(--red);
    border: none;
    border-radius: var(--radius-sm);
    color: white;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity 0.15s;
}
.search-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.search-btn:not(:disabled):hover { opacity: 0.85; }

.spinner {
    width: 12px; height: 12px;
    border: 2px solid rgba(255,255,255,0.3);
    border-top-color: white;
    border-radius: 50%;
    animation: spin 0.7s linear infinite;
    display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Results panel */
.results-panel { display: flex; flex-direction: column; gap: 10px; }

.empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    padding: 80px 0;
    color: var(--text-dim);
    font-size: 13px;
}

.results-meta {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-bottom: 4px;
}
.results-count { font-size: 14px; font-weight: 700; color: var(--text); }
.results-sub { font-size: 12px; color: var(--text-dim); }

.result-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 16px;
    transition: border-color 0.15s;
}
.result-card.clickable { cursor: pointer; }
.result-card.clickable:hover { border-color: var(--red); }

.result-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
}
.result-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.result-student { font-size: 13px; font-weight: 600; color: var(--text); }
.result-question { font-size: 12px; color: var(--text-muted); }
.result-exam { font-size: 12px; color: var(--text-dim); }
.result-dot { color: var(--border2); font-size: 12px; }

.result-right { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

.lang-badge {
    font-size: 10px; font-weight: 700; padding: 2px 7px;
    border-radius: 10px; text-transform: uppercase;
    background: var(--surface3); color: var(--text-dim);
}
.status-badge {
    font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 10px; text-transform: uppercase;
}
.status-badge.passed { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.failed { background: var(--red-dim); color: var(--red); }
.status-badge.running,.status-badge.pending { background: var(--surface3); color: var(--text-dim); }

.sim-badge {
    font-size: 11px; font-weight: 700; padding: 3px 9px; border-radius: 10px;
}
.sim-badge.high { background: var(--red-dim); color: var(--red); }
.sim-badge.mid  { background: rgba(241,196,15,0.12); color: var(--yellow); }
.sim-badge.low  { background: rgba(46,204,113,0.1); color: var(--green); }

.sim-bar-wrap { height: 3px; background: var(--surface3); border-radius: 2px; margin-bottom: 12px; overflow: hidden; }
.sim-bar { height: 100%; border-radius: 2px; transition: width 0.4s; }
.sim-bar.high { background: var(--red); }
.sim-bar.mid  { background: var(--yellow); }
.sim-bar.low  { background: var(--green); }

.code-preview {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    font-size: 11px;
    font-family: monospace;
    color: var(--text-muted);
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-all;
    margin-bottom: 10px;
    max-height: 140px;
    overflow: hidden;
}

.result-footer { display: flex; justify-content: space-between; font-size: 11px; color: var(--text-dim); }
</style>
