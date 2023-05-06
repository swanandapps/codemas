<template>
    <div class="page">
        <div class="breadcrumb">
            <router-link to="/dashboard/support/disputes" class="bc-link">← Dispute Queue</router-link>
        </div>

        <div v-if="loading" class="loading">Loading case…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else-if="data">
            <!-- Case header -->
            <div class="case-header">
                <div class="case-title-row">
                    <h1 class="case-title">Dispute #{{ data.id }}</h1>
                    <span class="badge" :class="statusClass(data.status)">{{ data.status }}</span>
                </div>
                <div class="case-meta">
                    <router-link :to="`/dashboard/support/student/${data.student}`" class="meta-student">
                        {{ data.student_username }}
                    </router-link>
                    <span class="meta-sep">·</span>
                    <span class="meta-type">{{ data.flag_type }} flag</span>
                    <span class="meta-sep">·</span>
                    <span class="meta-time">Filed {{ fmtDate(data.created_at) }}</span>
                </div>
            </div>

            <div class="layout">
                <!-- Left: flag + submission context -->
                <div class="left-col">
                    <!-- Submission context -->
                    <div v-if="data.submission" class="card">
                        <h2 class="card-title">Submission</h2>
                        <div class="sub-meta">
                            <div class="sub-meta-row">
                                <span class="sub-label">Exam</span>
                                <span class="sub-val">{{ data.submission.exam }}</span>
                            </div>
                            <div class="sub-meta-row">
                                <span class="sub-label">Question</span>
                                <span class="sub-val">{{ data.submission.question }}</span>
                            </div>
                            <div class="sub-meta-row">
                                <span class="sub-label">Language</span>
                                <span class="lang-chip">{{ data.submission.language }}</span>
                            </div>
                            <div class="sub-meta-row">
                                <span class="sub-label">Attempt</span>
                                <span class="sub-val">#{{ data.submission.attempt }}</span>
                            </div>
                            <div class="sub-meta-row">
                                <span class="sub-label">Result</span>
                                <span class="badge" :class="statusClass(data.submission.status)">{{ data.submission.status }}</span>
                            </div>
                            <div class="sub-meta-row">
                                <span class="sub-label">Submitted</span>
                                <span class="sub-val muted">{{ fmtDate(data.submission.submitted_at) }}</span>
                            </div>
                        </div>

                        <!-- Behaviour metrics -->
                        <div v-if="data.flag_type === 'behavioural'" class="behaviour-metrics">
                            <div class="metric">
                                <div class="metric-label">Paste events</div>
                                <div class="metric-val" :class="data.submission.had_paste ? 'red' : 'green'">
                                    {{ data.submission.had_paste ? 'Yes' : 'No' }}
                                    <span v-if="data.submission.paste_chars" class="metric-sub">({{ data.submission.paste_chars }} chars)</span>
                                </div>
                            </div>
                            <div class="metric">
                                <div class="metric-label">Tab switches</div>
                                <div class="metric-val" :class="data.submission.tab_switches > 3 ? 'red' : 'green'">
                                    {{ data.submission.tab_switches }}
                                </div>
                            </div>
                            <div class="metric">
                                <div class="metric-label">Time to complete</div>
                                <div class="metric-val">{{ fmtSeconds(data.submission.time_to_complete_s) }}</div>
                            </div>
                        </div>

                        <!-- Question description -->
                        <div v-if="data.submission.description" class="question-desc">
                            <div class="qdesc-label">Question</div>
                            <p class="qdesc-text">{{ data.submission.description }}</p>
                        </div>

                        <!-- Code -->
                        <div class="code-section">
                            <div class="code-label">
                                Student's Code
                                <router-link :to="`/dashboard/submissions/${data.submission.id}`" class="link-btn">Full view →</router-link>
                            </div>
                            <pre class="code-block">{{ data.submission.code }}</pre>
                        </div>
                    </div>

                    <!-- Matched submission (similarity disputes) -->
                    <div v-if="data.matched_submission" class="card">
                        <h2 class="card-title">Matched Submission</h2>
                        <div class="sub-meta-row" style="margin-bottom:8px">
                            <span class="sub-label">Student</span>
                            <router-link :to="`/dashboard/support/student/${data.matched_submission.id}`" class="meta-student">
                                {{ data.matched_submission.student }}
                            </router-link>
                        </div>
                        <pre class="code-block">{{ data.matched_submission.code }}</pre>
                    </div>
                </div>

                <!-- Right: flag verdict + student rebuttal + resolution -->
                <div class="right-col">
                    <!-- Flag verdict -->
                    <div v-if="data.flag_detail" class="card">
                        <h2 class="card-title">Flag Details</h2>

                        <template v-if="data.flag_type === 'behavioural'">
                            <div class="risk-row">
                                <span class="risk-label-text">Risk Score</span>
                                <span class="risk-pct" :class="riskClass(data.flag_detail.risk_score)">
                                    {{ (data.flag_detail.risk_score * 100).toFixed(0) }}%
                                </span>
                            </div>
                            <div class="risk-bar-wrap">
                                <div class="risk-bar" :style="{ width: (data.flag_detail.risk_score * 100) + '%' }" :class="riskClass(data.flag_detail.risk_score)"></div>
                            </div>
                            <div class="conf-row">
                                <span class="badge" :class="confClass(data.flag_detail.confidence)">{{ data.flag_detail.confidence }} confidence</span>
                            </div>
                            <div class="signal-list">
                                <div class="signal-label">Signals Triggered</div>
                                <div v-for="sig in data.flag_detail.signals" :key="sig" class="signal-item">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                                    {{ sig }}
                                </div>
                            </div>
                            <div class="score-breakdown">
                                <div class="score-row"><span>Paste score</span><span>{{ (data.flag_detail.paste_score * 100).toFixed(0) }}%</span></div>
                                <div class="score-row"><span>Time score</span><span>{{ (data.flag_detail.time_score * 100).toFixed(0) }}%</span></div>
                                <div class="score-row"><span>Snapshot score</span><span>{{ (data.flag_detail.snapshot_score * 100).toFixed(0) }}%</span></div>
                            </div>
                        </template>

                        <template v-else>
                            <div class="risk-row">
                                <span class="risk-label-text">Similarity</span>
                                <span class="risk-pct red">{{ (data.flag_detail.similarity_score * 100).toFixed(1) }}%</span>
                            </div>
                            <div class="risk-bar-wrap">
                                <div class="risk-bar risk-high" :style="{ width: (data.flag_detail.similarity_score * 100) + '%' }"></div>
                            </div>
                            <div class="conf-row muted">Method: {{ data.flag_detail.detection_method }}</div>
                        </template>

                        <div v-if="data.flag_detail.review_status !== 'pending'" class="flag-review-status">
                            <span class="badge" :class="reviewClass(data.flag_detail.review_status)">{{ data.flag_detail.review_status }}</span>
                            <span v-if="data.flag_detail.reviewed_by" class="muted small"> by {{ data.flag_detail.reviewed_by }}</span>
                            <p v-if="data.flag_detail.review_note" class="review-note">"{{ data.flag_detail.review_note }}"</p>
                        </div>
                    </div>

                    <!-- Student rebuttal -->
                    <div class="card rebuttal-card">
                        <h2 class="card-title">Student's Case</h2>
                        <blockquote class="rebuttal-text">"{{ data.student_note }}"</blockquote>
                    </div>

                    <!-- Prior resolution (if resolved) -->
                    <div v-if="data.resolution_note" class="card">
                        <h2 class="card-title">Resolution</h2>
                        <p class="resolution-text">{{ data.resolution_note }}</p>
                        <div class="muted small" v-if="data.resolved_by_username">
                            Resolved by {{ data.resolved_by_username }} · {{ fmtDate(data.resolved_at) }}
                        </div>
                    </div>

                    <!-- Resolve form (if open) -->
                    <div v-if="data.status === 'open'" class="card resolve-card">
                        <h2 class="card-title">Trainer Decision</h2>
                        <textarea v-model="resolutionNote" placeholder="Write your resolution note…" class="resolution-input"></textarea>
                        <div class="resolve-actions">
                            <button class="btn-resolve" @click="resolve('resolved')" :disabled="saving">
                                {{ saving ? 'Saving…' : 'Mark Resolved' }}
                            </button>
                            <button class="btn-escalate" @click="resolve('escalated')" :disabled="saving">Escalate</button>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route          = useRoute()
const loading        = ref(true)
const error          = ref('')
const data           = ref<any>(null)
const resolutionNote = ref('')
const saving         = ref(false)

onMounted(async () => {
    try {
        const res = await api.get(`/support/disputes/${route.params.id}/`)
        data.value = res.data
    } catch {
        error.value = 'Failed to load dispute.'
    } finally {
        loading.value = false
    }
})

async function resolve(newStatus: string) {
    saving.value = true
    try {
        const res = await api.patch(`/support/disputes/${route.params.id}/`, {
            status:          newStatus,
            resolution_note: resolutionNote.value,
        })
        data.value = res.data
    } catch {
        alert('Failed to update dispute.')
    } finally {
        saving.value = false
    }
}

function fmtDate(iso: string): string {
    if (!iso) return ''
    return new Date(iso).toLocaleString()
}
function fmtSeconds(s: number): string {
    if (!s) return '—'
    const m = Math.floor(s / 60)
    const sec = s % 60
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`
}
function statusClass(s: string): string {
    return s === 'open' ? 'badge-yellow' : s === 'escalated' ? 'badge-red' : s === 'passed' ? 'badge-green' : s === 'failed' ? 'badge-red' : 'badge-dim'
}
function confClass(c: string): string {
    return c === 'high' ? 'badge-red' : c === 'medium' ? 'badge-yellow' : 'badge-dim'
}
function reviewClass(s: string): string {
    return s === 'confirmed' ? 'badge-red' : s === 'dismissed' ? 'badge-green' : 'badge-yellow'
}
function riskClass(r: number): string {
    return r >= 0.7 ? 'red' : r >= 0.4 ? 'warn' : 'green'
}
</script>

<style scoped>
.page { padding: 32px 40px; max-width: 1200px; }
.breadcrumb { margin-bottom: 20px; }
.bc-link { font-size: 13px; color: var(--text-dim); text-decoration: none; }
.bc-link:hover { color: var(--red); }

.loading   { color: var(--text-dim); padding: 40px 0; }
.error-msg { color: var(--red); padding: 20px 0; }

/* Case header */
.case-header { margin-bottom: 28px; }
.case-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.case-title { font-size: 22px; font-weight: 700; color: var(--text); margin: 0; }
.case-meta { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.meta-student { font-weight: 600; color: var(--red); text-decoration: none; }
.meta-student:hover { text-decoration: underline; }
.meta-sep { color: var(--text-dim); }
.meta-type { color: var(--text-dim); text-transform: capitalize; }
.meta-time { color: var(--text-dim); }

/* Layout */
.layout { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; align-items: start; }
.left-col, .right-col { display: flex; flex-direction: column; gap: 16px; }

/* Cards */
.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 22px 24px;
}
.card-title { font-size: 14px; font-weight: 600; color: var(--text); margin: 0 0 14px; text-transform: uppercase; letter-spacing: 0.3px; font-size: 11px; color: var(--text-dim); }

/* Submission meta */
.sub-meta { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.sub-meta-row { display: flex; align-items: center; gap: 12px; font-size: 13px; }
.sub-label { min-width: 90px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); }
.sub-val { color: var(--text); }
.sub-val.muted { color: var(--text-dim); }
.lang-chip { font-family: monospace; font-size: 12px; background: var(--surface2); padding: 2px 8px; border-radius: 4px; color: var(--text-muted); }

/* Behaviour metrics */
.behaviour-metrics {
    display: flex; gap: 20px;
    background: var(--surface2); border-radius: var(--radius-sm);
    padding: 12px 16px; margin-bottom: 16px;
}
.metric { flex: 1; }
.metric-label { font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }
.metric-val { font-size: 16px; font-weight: 700; color: var(--text); }
.metric-val.red   { color: var(--red); }
.metric-val.green { color: #22c55e; }
.metric-sub { font-size: 11px; font-weight: 400; color: var(--text-dim); }

/* Question description */
.question-desc { margin-bottom: 16px; }
.qdesc-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; }
.qdesc-text { font-size: 13px; color: var(--text-muted); line-height: 1.6; margin: 0; }

/* Code */
.code-section { }
.code-label { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 8px; }
.code-block {
    background: #0d1117; border: 1px solid #30363d;
    border-radius: var(--radius-sm); padding: 16px;
    font-family: 'JetBrains Mono', 'Fira Code', monospace;
    font-size: 12px; color: #e6edf3; line-height: 1.6;
    overflow-x: auto; white-space: pre; max-height: 400px; overflow-y: auto;
    margin: 0;
}

/* Flag detail */
.risk-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.risk-label-text { font-size: 13px; color: var(--text-muted); }
.risk-pct { font-size: 24px; font-weight: 700; }
.risk-pct.red  { color: var(--red); }
.risk-pct.warn { color: #f59e0b; }
.risk-pct.green { color: #22c55e; }
.risk-bar-wrap { height: 6px; background: var(--surface2); border-radius: 3px; margin-bottom: 12px; }
.risk-bar { height: 100%; border-radius: 3px; }
.risk-bar.red, .risk-bar.risk-high { background: var(--red); }
.risk-bar.warn { background: #f59e0b; }
.risk-bar.green { background: #22c55e; }
.conf-row { margin-bottom: 16px; }
.conf-row.muted { font-size: 12px; color: var(--text-dim); }

.signal-list { margin-bottom: 16px; }
.signal-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 8px; }
.signal-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-muted); padding: 4px 0; }
.signal-item svg { color: #f59e0b; flex-shrink: 0; }

.score-breakdown { border-top: 1px solid var(--border); padding-top: 12px; }
.score-row { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-dim); padding: 3px 0; }
.score-row span:last-child { font-weight: 600; color: var(--text); }

.flag-review-status { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }
.review-note { font-style: italic; font-size: 13px; color: var(--text-dim); margin: 8px 0 0; }

/* Rebuttal */
.rebuttal-card { border-left: 3px solid var(--red); }
.rebuttal-text {
    font-style: italic; font-size: 14px; color: var(--text-muted);
    line-height: 1.7; margin: 0;
    border-left: none; padding: 0;
}

/* Resolution */
.resolution-text { font-size: 14px; color: var(--text-muted); margin: 0 0 8px; line-height: 1.6; }

/* Resolve form */
.resolve-card { border: 1px solid rgba(230,57,70,0.25); }
.resolution-input {
    width: 100%; padding: 10px 12px; font-size: 13px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text);
    resize: vertical; min-height: 80px; margin-bottom: 12px;
    box-sizing: border-box;
}
.resolution-input::placeholder { color: var(--text-dim); }
.resolve-actions { display: flex; gap: 8px; }
.btn-resolve {
    flex: 1; padding: 10px; font-size: 13px; font-weight: 600;
    background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3);
    border-radius: var(--radius-sm); color: #22c55e; cursor: pointer;
    transition: all 0.15s;
}
.btn-resolve:hover:not(:disabled) { background: rgba(34,197,94,0.2); }
.btn-resolve:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-escalate {
    padding: 10px 20px; font-size: 13px; font-weight: 600;
    background: var(--red-dim); border: 1px solid rgba(230,57,70,0.3);
    border-radius: var(--radius-sm); color: var(--red); cursor: pointer;
    transition: all 0.15s;
}
.btn-escalate:hover:not(:disabled) { background: rgba(230,57,70,0.2); }
.btn-escalate:disabled { opacity: 0.5; cursor: not-allowed; }

/* Shared */
.badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-yellow { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-red    { background: rgba(230,57,70,0.12);  color: var(--red); }
.badge-dim    { background: var(--surface2);        color: var(--text-dim); }
.muted { color: var(--text-dim); }
.small { font-size: 12px; }
.link-btn { font-size: 12px; color: var(--red); text-decoration: none; font-weight: 600; }
.link-btn:hover { text-decoration: underline; }
</style>
