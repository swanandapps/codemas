<template>
    <div class="detail-page">
        <div class="page-header">
            <button class="back-btn" @click="router.back()">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="15 18 9 12 15 6"/></svg>
                Back
            </button>
        </div>

        <div v-if="loading" class="state-msg">Loading submission...</div>
        <div v-else-if="!sub" class="state-msg">Submission not found.</div>

        <template v-else>
            <!-- ── Header strip ───────────────────────────────────────────── -->
            <div class="sub-header">
                <div class="sub-identity">
                    <div class="sub-avatar">{{ sub.student_username.slice(0,2).toUpperCase() }}</div>
                    <div>
                        <div class="sub-student">{{ sub.student_username }}</div>
                        <div class="sub-meta">
                            {{ sub.exam_title }} · {{ sub.question_title }} · attempt {{ sub.attempt_number }}
                        </div>
                    </div>
                </div>
                <div class="sub-badges">
                    <span :class="['lang-badge', sub.language]">{{ sub.language }}</span>
                    <span :class="['status-badge', sub.status]">{{ sub.status }}</span>
                    <span class="sub-date">{{ formatDate(sub.submitted_at) }}</span>
                </div>
            </div>

            <!-- ── KPI strip ──────────────────────────────────────────────── -->
            <div class="kpi-row">
                <div class="kpi">
                    <div class="kpi-label">Exec Time</div>
                    <div class="kpi-val">{{ sub.execution_time_ms ?? '—' }}ms</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Time Used</div>
                    <div class="kpi-val">{{ sub.percent_time_used?.toFixed(1) ?? '—' }}%</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Test Cases</div>
                    <div class="kpi-val">{{ passedCount }}/{{ results.length }} passed</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Plagiarism Score</div>
                    <div class="kpi-val" :class="sub.plagiarism_score > 0.8 ? 'text-red' : ''">
                        {{ sub.plagiarism_score != null ? (sub.plagiarism_score * 100).toFixed(1) + '%' : '—' }}
                    </div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">IP Address</div>
                    <div class="kpi-val mono">{{ sub.ip_address ?? '—' }}</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Behavioural Check</div>
                    <div class="kpi-val" :class="sub.behavioural_check_done ? 'text-green' : 'text-yellow'">
                        {{ sub.behavioural_check_done ? 'Done' : 'Pending' }}
                    </div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Similarity Check</div>
                    <div class="kpi-val" :class="sub.similarity_check_done ? 'text-green' : 'text-yellow'">
                        {{ sub.similarity_check_done ? 'Done' : 'Pending' }}
                    </div>
                </div>
            </div>

            <div class="main-grid">
                <!-- ── Code panel ─────────────────────────────────────────── -->
                <div class="card code-card">
                    <div class="card-title">Submitted Code</div>
                    <pre class="code-block">{{ sub.code }}</pre>
                </div>

                <!-- ── Right column ───────────────────────────────────────── -->
                <div class="right-col">

                    <!-- Test case results -->
                    <div class="card">
                        <div class="card-title">Test Case Results</div>
                        <div v-if="resultsLoading" class="mini-state">Loading...</div>
                        <div v-else-if="results.length === 0" class="mini-state">No results yet</div>
                        <div v-else class="tc-list">
                            <div v-for="(r, i) in results" :key="r.id" class="tc-row">
                                <div class="tc-header">
                                    <span :class="['tc-badge', r.passed ? 'pass' : 'fail']">
                                        {{ r.passed ? '✓' : '✗' }} Test {{ i + 1 }}
                                    </span>
                                    <span class="tc-time">{{ r.execution_time_ms }}ms</span>
                                </div>
                                <div class="tc-grid">
                                    <div class="tc-block">
                                        <div class="tc-block-label">Input</div>
                                        <pre class="tc-pre">{{ r.test_case_input || '(none)' }}</pre>
                                    </div>
                                    <div class="tc-block">
                                        <div class="tc-block-label">Expected</div>
                                        <pre class="tc-pre expected">{{ r.test_case_expected }}</pre>
                                    </div>
                                    <div class="tc-block">
                                        <div class="tc-block-label">Actual</div>
                                        <pre class="tc-pre" :class="r.passed ? 'actual-pass' : 'actual-fail'">{{ r.actual_output || r.error_message || '(no output)' }}</pre>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Plagiarism flags -->
                    <div class="card">
                        <div class="card-title">Integrity Flags</div>
                        <div v-if="plagLoading" class="mini-state">Loading...</div>
                        <template v-else>

                            <!-- Behavioural -->
                            <div v-if="plagData.behavioural" class="flag-section">
                                <div class="flag-section-title">
                                    Behavioural Analysis
                                    <span :class="['conf-badge', plagData.behavioural.confidence]">
                                        {{ plagData.behavioural.confidence }} risk
                                    </span>
                                    <span :class="['rev-badge', plagData.behavioural.review_status]">
                                        {{ plagData.behavioural.review_status }}
                                    </span>
                                </div>
                                <div class="risk-bar-wrap">
                                    <div class="risk-bar"
                                        :style="{ width: (plagData.behavioural.risk_score * 100) + '%' }"
                                        :class="plagData.behavioural.confidence" />
                                </div>
                                <div class="risk-score-label">Risk score: {{ (plagData.behavioural.risk_score * 100).toFixed(1) }}%</div>
                                <div class="signals-list">
                                    <div v-for="(sig, i) in plagData.behavioural.signals" :key="i" class="signal-item">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/></svg>
                                        {{ sig }}
                                    </div>
                                </div>
                                <div v-if="plagData.behavioural.review_note" class="review-note">
                                    Note: {{ plagData.behavioural.review_note }}
                                </div>
                            </div>
                            <div v-else class="clean-flag">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                                No behavioural flags
                            </div>

                            <div class="flag-divider" />

                            <!-- Similarity -->
                            <div class="flag-section-title">Similarity Flags</div>
                            <div v-if="plagData.similarity?.length === 0" class="clean-flag">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                                No similarity flags
                            </div>
                            <div v-for="f in plagData.similarity" :key="f.flag_id" class="sim-flag-row">
                                <div class="sim-flag-left">
                                    <span class="sim-flag-score" :class="f.similarity_score >= 0.9 ? 'text-red' : 'text-yellow'">
                                        {{ (f.similarity_score * 100).toFixed(1) }}% match
                                    </span>
                                    <span class="sim-flag-student">vs {{ f.other_student }}</span>
                                </div>
                                <div class="sim-flag-right">
                                    <span :class="['rev-badge', f.review_status]">{{ f.review_status }}</span>
                                    <button class="view-btn" @click.stop="router.push(`/dashboard/submissions/${f.other_submission}`)">
                                        View →
                                    </button>
                                </div>
                            </div>

                        </template>
                    </div>

                    <!-- Question -->
                    <div class="card">
                        <div class="card-title">Question</div>
                        <div class="q-title">{{ sub.question_title }}</div>
                        <div class="q-desc">{{ sub.question_description }}</div>
                    </div>

                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route  = useRoute()
const router = useRouter()

const loading        = ref(true)
const resultsLoading = ref(true)
const plagLoading    = ref(true)
const sub      = ref<any>(null)
const results  = ref<any[]>([])
const plagData = ref<any>({ behavioural: null, similarity: [] })

const passedCount = computed(() => results.value.filter(r => r.passed).length)

onMounted(async () => {
    const id = route.params.id
    const [subRes, resRes, plagRes] = await Promise.all([
        api.get(`/submissions/${id}/`),
        api.get(`/results/${id}/`),
        api.get(`/plagiarism/submission/${id}/`),
    ])
    sub.value      = subRes.data
    results.value  = resRes.data
    plagData.value = plagRes.data
    loading.value        = false
    resultsLoading.value = false
    plagLoading.value    = false
})

function formatDate(iso: string) {
    return new Date(iso).toLocaleString('en-IN', {
        day: 'numeric', month: 'short', year: 'numeric',
        hour: '2-digit', minute: '2-digit',
    })
}
</script>

<style scoped>
.page-header { margin-bottom: 20px; }
.back-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 7px 14px;
    color: var(--text-muted); font-size: 13px; cursor: pointer;
    transition: all 0.15s;
}
.back-btn:hover { background: var(--surface2); color: var(--text); }
.state-msg { color: var(--text-dim); padding: 60px 0; text-align: center; }

/* Header */
.sub-header {
    display: flex; align-items: center; justify-content: space-between;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px 22px; margin-bottom: 14px;
}
.sub-identity { display: flex; align-items: center; gap: 14px; }
.sub-avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--surface3); border: 1px solid var(--border2);
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 700; color: var(--red); flex-shrink: 0;
}
.sub-student { font-size: 15px; font-weight: 700; color: var(--text); }
.sub-meta { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.sub-badges { display: flex; align-items: center; gap: 8px; }
.sub-date { font-size: 11px; color: var(--text-dim); }

.lang-badge { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 10px; text-transform: uppercase; background: var(--surface3); color: var(--text-dim); }
.status-badge { font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 10px; text-transform: uppercase; }
.status-badge.passed { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.failed { background: var(--red-dim); color: var(--red); }
.status-badge.running,.status-badge.pending { background: var(--surface3); color: var(--text-dim); }

/* KPI row */
.kpi-row {
    display: flex; gap: 1px; background: var(--border);
    border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden; margin-bottom: 14px;
}
.kpi { flex: 1; background: var(--surface); padding: 14px 18px; }
.kpi-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 4px; }
.kpi-val { font-size: 18px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.kpi-val.mono { font-family: monospace; font-size: 13px; }
.text-red    { color: var(--red) !important; }
.text-yellow { color: var(--yellow) !important; }
.text-green  { color: var(--green) !important; }

/* Main grid */
.main-grid { display: grid; grid-template-columns: 1fr 420px; gap: 14px; align-items: start; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 14px; }
.card:last-child { margin-bottom: 0; }
.card-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 14px; }
.right-col { display: flex; flex-direction: column; }

/* Code */
.code-card { height: fit-content; }
.code-block {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 16px;
    font-family: monospace; font-size: 12px; line-height: 1.7;
    color: var(--text); white-space: pre-wrap; word-break: break-all;
    max-height: 600px; overflow-y: auto;
}

/* Test cases */
.mini-state { color: var(--text-dim); font-size: 13px; padding: 20px 0; text-align: center; }
.tc-list { display: flex; flex-direction: column; gap: 12px; }
.tc-row { border: 1px solid var(--border); border-radius: var(--radius-sm); overflow: hidden; }
.tc-header { display: flex; align-items: center; justify-content: space-between; padding: 8px 12px; background: var(--surface2); }
.tc-badge { font-size: 11px; font-weight: 700; }
.tc-badge.pass { color: var(--green); }
.tc-badge.fail { color: var(--red); }
.tc-time { font-size: 11px; color: var(--text-dim); font-family: monospace; }
.tc-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1px; background: var(--border); }
.tc-block { background: var(--surface); padding: 8px 10px; }
.tc-block-label { font-size: 9px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 4px; }
.tc-pre { font-family: monospace; font-size: 11px; color: var(--text-muted); white-space: pre-wrap; word-break: break-all; margin: 0; }
.tc-pre.expected { color: var(--text-muted); }
.tc-pre.actual-pass { color: var(--green); }
.tc-pre.actual-fail { color: var(--red); }

/* Question */
.q-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
.q-desc { font-size: 13px; color: var(--text-muted); line-height: 1.6; }

/* Plagiarism */
.flag-section { margin-bottom: 14px; }
.flag-section-title { font-size: 11px; font-weight: 700; color: var(--text-muted); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.flag-divider { height: 1px; background: var(--border); margin: 14px 0; }

.conf-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 10px; text-transform: uppercase; }
.conf-badge.high   { background: var(--red-dim); color: var(--red); }
.conf-badge.medium { background: rgba(241,196,15,0.12); color: var(--yellow); }
.conf-badge.low    { background: var(--surface3); color: var(--text-dim); }

.rev-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 10px; text-transform: uppercase; }
.rev-badge.pending   { background: rgba(241,196,15,0.12); color: var(--yellow); }
.rev-badge.confirmed { background: var(--red-dim); color: var(--red); }
.rev-badge.dismissed { background: var(--surface3); color: var(--text-dim); }

.risk-bar-wrap { height: 4px; background: var(--surface3); border-radius: 2px; margin-bottom: 4px; overflow: hidden; }
.risk-bar { height: 100%; border-radius: 2px; }
.risk-bar.high   { background: var(--red); }
.risk-bar.medium { background: var(--yellow); }
.risk-bar.low    { background: var(--green); }
.risk-score-label { font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }

.signals-list { display: flex; flex-direction: column; gap: 5px; margin-bottom: 8px; }
.signal-item { display: flex; align-items: flex-start; gap: 7px; font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.signal-item svg { flex-shrink: 0; margin-top: 2px; color: var(--yellow); }

.review-note { font-size: 11px; color: var(--text-dim); font-style: italic; background: var(--surface2); padding: 6px 10px; border-radius: var(--radius-sm); }

.clean-flag { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--green); padding: 6px 0; }

.sim-flag-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }
.sim-flag-row:last-child { border-bottom: none; }
.sim-flag-left { display: flex; align-items: center; gap: 10px; }
.sim-flag-score { font-size: 13px; font-weight: 700; }
.sim-flag-student { font-size: 12px; color: var(--text-dim); }
.sim-flag-right { display: flex; align-items: center; gap: 8px; }
.text-red    { color: var(--red); }
.text-yellow { color: var(--yellow); }

.view-btn {
    font-size: 11px; font-weight: 600; color: var(--red);
    background: var(--red-dim); border: none; border-radius: var(--radius-sm);
    padding: 3px 9px; cursor: pointer; transition: opacity 0.15s;
}
.view-btn:hover { opacity: 0.75; }
</style>
