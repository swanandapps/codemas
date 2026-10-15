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
            <!-- ── Header ─────────────────────────────────────────────────── -->
            <div class="sub-header">
                <h1 class="sub-title">{{ sub.question_title }}</h1>
                <div class="sub-meta-row">
                    <span class="meta-item">{{ sub.student_username }}</span>
                    <span class="meta-item">{{ sub.exam_title }}</span>
                    <span class="meta-item">{{ sub.language }}</span>
                    <span class="meta-item">{{ formatDateTime(sub.submitted_at) }}</span>
                    <span class="meta-item">Attempt {{ sub.attempt_number }}</span>
                </div>
            </div>

            <!-- ── KPI strip ──────────────────────────────────────────────── -->
            <div class="kpi-row">
                <div class="kpi">
                    <div class="kpi-label">Exec time</div>
                    <div class="kpi-val mono">{{ formatMs(sub.execution_time_ms) }}</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Time used</div>
                    <div class="kpi-val mono">{{ formatPct(sub.percent_time_used) }}</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Test cases</div>
                    <div class="kpi-val mono">{{ passedCount }}/{{ results.length }} passed</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Plagiarism score</div>
                    <div class="kpi-val mono" :class="sub.plagiarism_score > 0.8 ? 'text-fail' : ''">
                        {{ formatPct(sub.plagiarism_score != null ? sub.plagiarism_score * 100 : null) }}
                    </div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">IP address</div>
                    <div class="kpi-val mono">{{ sub.ip_address ?? '—' }}</div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Behavioural check</div>
                    <div class="kpi-val" :class="sub.behavioural_check_done ? 'text-pass' : 'text-pending'">
                        {{ sub.behavioural_check_done ? 'Done' : 'Pending' }}
                    </div>
                </div>
                <div class="kpi">
                    <div class="kpi-label">Similarity check</div>
                    <div class="kpi-val" :class="similarityCheck.cls" :title="similarityCheck.hint">
                        {{ similarityCheck.text }}
                    </div>
                </div>
            </div>

            <!-- ── Verdict + pipeline + results table ───────────────────── -->
            <div class="card verdict-card">
                <div v-if="resultsLoading" class="mini-state">Loading...</div>
                <template v-else>
                    <div v-if="results.length > 0" class="verdict-block">
                        <div class="verdict-head">
                            <span class="verdict-headline" :class="verdict.passed ? 'pass' : 'fail'">{{ verdict.headline }}</span>
                            <span class="verdict-sub">{{ verdict.secondary }}</span>
                        </div>

                        <PipelineTracker
                            :stage="pipelineStage"
                            :tests="trackerTests"
                            :test-count="results.length"
                            :rubric-ready="!!rubric"
                            :hint-expected="sub.status === 'failed'"
                            :hint-ready="!!hint"
                            :elapsed-ms="null"
                            :show-banner="false"
                        />

                        <div class="table-scroll">
                        <div role="table" aria-label="Test results" class="results-table">
                            <div role="row" class="results-row results-head">
                                <span role="columnheader">Test</span>
                                <span role="columnheader">Input</span>
                                <span role="columnheader">Expected</span>
                                <span role="columnheader">Output</span>
                                <span role="columnheader">Time</span>
                                <span role="columnheader">Result</span>
                            </div>
                            <template v-for="(r, i) in results" :key="r.id">
                                <div role="row" class="results-row" :class="{ 'row-fail': !r.passed }">
                                    <span role="cell" class="dim">{{ i + 1 }}</span>
                                    <span role="cell">{{ r.test_case_input || '(none)' }}</span>
                                    <span role="cell">{{ r.test_case_expected }}</span>
                                    <span role="cell" :class="{ 'text-fail': !r.passed }">{{ r.actual_output || '(no output)' }}</span>
                                    <span role="cell" class="dim">{{ formatMs(r.execution_time_ms) }}</span>
                                    <span role="cell" class="result-label" :class="r.passed ? 'text-pass' : 'text-fail'">{{ r.passed ? 'Pass' : 'Fail' }}</span>
                                </div>
                                <p v-if="r.error_message" class="row-error">{{ r.error_message }}</p>
                            </template>
                        </div>
                        </div>
                    </div>
                    <div v-else class="mini-state">No results yet</div>
                </template>
            </div>

            <div class="main-grid">
                <!-- ── Code panel ─────────────────────────────────────────── -->
                <div class="card code-card">
                    <div class="card-title">Submitted code</div>
                    <pre class="code-block">{{ sub.code }}</pre>
                </div>

                <!-- ── Right column ───────────────────────────────────────── -->
                <div class="right-col">

                    <!-- AI evaluation (rubric + hint) — read-only trainer view -->
                    <AiGlow title="Rubric review" class="ai-card">
                        <p class="ai-caption">Check it before acting on it.</p>
                        <div v-if="aiLoading" class="mini-state">Loading...</div>
                        <template v-else>
                            <!-- Rubric -->
                            <div v-if="rubric">
                                <div class="ai-total-row">
                                    <span class="ai-total-label">Rubric score</span>
                                    <span class="ai-total-badge mono" :class="scoreClass(rubric.total_score, 8)">
                                        {{ rubric.total_score }}<span class="ai-total-max">/8</span>
                                    </span>
                                </div>
                                <div v-for="dim in rubricDimensions" :key="dim.label" class="ai-dim">
                                    <div class="ai-dim-top">
                                        <span class="ai-dim-label">{{ dim.label }}</span>
                                        <span class="ai-dim-score mono" :class="scoreClass(dim.score, 2)">{{ dim.score }}/2</span>
                                    </div>
                                    <div class="ai-bar"><div class="ai-bar-fill" :class="scoreClass(dim.score, 2)" :style="{ width: (dim.score / 2 * 100) + '%' }" /></div>
                                    <p class="ai-dim-note">{{ dim.note }}</p>
                                </div>
                                <p class="ai-overall">{{ rubric.overall_feedback }}</p>
                            </div>
                            <div v-else class="mini-state">No rubric score available</div>

                            <!-- Hint (only present on failed submissions) -->
                            <template v-if="hint">
                                <div class="ai-hint-head">
                                    Socratic hint shown to student
                                </div>
                                <p class="ai-hint">{{ hint }}</p>
                            </template>
                        </template>
                    </AiGlow>

                    <!-- Plagiarism flags -->
                    <div class="card">
                        <div class="card-title">Integrity flags</div>
                        <div v-if="plagLoading" class="mini-state">Loading...</div>
                        <template v-else>

                            <!-- Behavioural -->
                            <div v-if="plagData.behavioural" class="flag-section">
                                <div class="flag-section-title">
                                    Behavioural analysis
                                    <span :class="['conf-badge', confidenceClass(plagData.behavioural.confidence)]" :title="METRIC_HELP.confidence">
                                        {{ confidenceLabel(plagData.behavioural.confidence) }}
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
                                <div class="risk-score-label">Risk {{ formatRisk(plagData.behavioural.risk_score) }}</div>
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
                            <div v-else-if="sub.behavioural_check_done" class="clean-flag">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                                No behavioural flags
                            </div>
                            <div v-else class="pending-flag">
                                Behaviour check hasn't run yet
                            </div>

                            <div class="flag-divider" />

                            <!-- Similarity -->
                            <div class="flag-section-title">Similarity flags</div>
                            <div v-if="plagData.similarity?.length === 0 && sub.similarity_check_done" class="clean-flag">
                                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                                No similarity flags
                            </div>
                            <div v-else-if="plagData.similarity?.length === 0" class="pending-flag">
                                {{ similarityCheck.hint || "Similarity check hasn't run yet" }}
                            </div>
                            <div v-for="f in plagData.similarity" :key="f.flag_id" class="sim-flag-row">
                                <div class="sim-flag-left">
                                    <span class="sim-flag-score mono" :class="f.similarity_score >= 0.9 ? 'text-fail' : 'text-pending'">
                                        {{ (f.similarity_score * 100).toFixed(1) }}% match
                                    </span>
                                    <span class="sim-flag-student">vs {{ f.other_student }}</span>
                                </div>
                                <div class="sim-flag-right">
                                    <span :class="['rev-badge', f.review_status]">{{ f.review_status }}</span>
                                    <button class="view-btn" @click.stop="router.push(`/dashboard/submissions/${f.other_submission}`)">
                                        View
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
import PipelineTracker from '../components/PipelineTracker.vue'
import AiGlow from '../components/AiGlow.vue'
import { formatDateTime, formatMs, formatPct, formatRisk } from '../utils/format'
import { METRIC_HELP, confidenceClass, confidenceLabel } from '../utils/metrics'

type Stage = 'idle' | 'submit' | 'queue' | 'execute' | 'grade' | 'feedback' | 'done'

const route  = useRoute()
const router = useRouter()

const loading        = ref(true)
const resultsLoading = ref(true)
const plagLoading    = ref(true)
const sub      = ref<any>(null)
const results  = ref<any[]>([])
const plagData = ref<any>({ behavioural: null, similarity: [] })

// AI evaluation (rubric + hint) — populated async, may be absent for older submissions
const aiLoading = ref(true)
const rubric    = ref<any>(null)
const hint      = ref<string | null>(null)

const passedCount = computed(() => results.value.filter(r => r.passed).length)

// This is a historical/finished (or in-flight) submission, not a live run — map
// the stored submission.status honestly onto the pipeline's stages rather than
// pretending we observed every step.
const pipelineStage = computed<Stage>(() => {
    const status = sub.value?.status
    if (status === 'pending') return 'queue'
    if (status === 'running') return 'execute'
    if (status === 'passed' || status === 'failed') return 'done'
    return 'idle'
})

const trackerTests = computed(() => {
    if (results.value.length === 0) return null
    return results.value.map(r => ({ passed: r.passed }))
})

// Similarity check has three real states, not two. similarity_check_done=false
// can mean "exam run hasn't happened" OR "run happened but this submission wasn't
// a behavioural suspect, so it was never cross-compared" (by design). We use
// behavioural_check_done as the proxy for "the exam's plagiarism run executed".
const similarityCheck = computed(() => {
    const s = sub.value
    if (!s) return { text: '—', cls: 'text-dim', hint: '' }
    if (s.similarity_check_done) {
        return { text: 'Done', cls: 'text-pass', hint: 'This submission was cross-compared via TF-IDF similarity.' }
    }
    if (s.behavioural_check_done) {
        return {
            text: 'Out of scope', cls: 'text-dim',
            hint: 'The exam\'s plagiarism run completed, but this submission was not a high-risk behavioural suspect, so it was not cross-compared (by design).',
        }
    }
    return { text: 'Pending', cls: 'text-pending', hint: 'The exam\'s plagiarism run has not run yet for this submission.' }
})

// Map a score to a quality band so bars/badges colour by performance
function scoreClass(score: number, max: number): string {
    const pct = score / max
    if (pct >= 0.75) return 'good'
    if (pct >= 0.4) return 'mid'
    return 'low'
}

const rubricDimensions = computed(() => {
    const r = rubric.value
    if (!r) return []
    return [
        { label: 'Correctness', score: r.correctness_score, note: r.correctness_note },
        { label: 'Code quality', score: r.code_quality_score, note: r.code_quality_note },
        { label: 'Approach', score: r.approach_score, note: r.approach_note },
        { label: 'Edge cases', score: r.edge_case_score, note: r.edge_case_note },
    ]
})

// Verdict headline derived from real results only — same rules as the student-
// facing exam view, so a trainer sees the identical verdict the student saw.
const verdict = computed(() => {
    const list = results.value
    if (list.length === 0) return { headline: '', secondary: '', passed: true }
    const passedN = list.filter((r) => r.passed).length
    const failedN = list.length - passedN
    if (failedN === 0) {
        return { headline: 'Accepted', secondary: `${passedN} passed, ${failedN} failed`, passed: true }
    }
    const idx = list.findIndex((r) => !r.passed)
    const r = list[idx]
    if (!r) return { headline: '', secondary: '', passed: true }
    let headline: string
    if (r.error_message && r.error_message.toLowerCase().includes('time limit')) {
        headline = `Time limit exceeded on test ${idx + 1}`
    } else if (r.error_message && !r.actual_output) {
        headline = `Error on test ${idx + 1}`
    } else {
        headline = `Wrong answer on test ${idx + 1} of ${list.length}`
    }
    return { headline, secondary: `${passedN} passed, ${failedN} failed`, passed: false }
})

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

    // AI evaluation — fetched separately and non-blocking; gracefully absent for
    // submissions that predate the feature or that scoring hasn't reached yet.
    try {
        const [rubricRes, hintRes] = await Promise.all([
            api.get(`/ai/rubric/${id}/`).catch(() => null),
            api.get(`/ai/hint/${id}/`).catch(() => null),
        ])
        if (rubricRes && typeof rubricRes.data?.total_score === 'number') rubric.value = rubricRes.data
        if (hintRes && typeof hintRes.data?.hint === 'string') hint.value = hintRes.data.hint
    } finally {
        aiLoading.value = false
    }
})

</script>

<style scoped>
.page-header { margin-bottom: 20px; }
.back-btn {
    display: inline-flex; align-items: center; gap: 6px;
    background: var(--surface); border: 1px solid var(--border2);
    border-radius: var(--radius-pill); padding: 8px 16px; min-height: 40px;
    color: var(--text); font-size: 13px; cursor: pointer;
    transition: all 0.15s;
}
.back-btn:hover { background: var(--surface2); color: var(--text); }
.state-msg { color: var(--text-dim); padding: 60px 0; text-align: center; }

/* Header */
.sub-header {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px 22px; margin-bottom: 14px;
}
.sub-title { font-size: 26px; font-weight: 600; color: var(--text); margin: 0 0 10px; line-height: 1.3; }
.sub-title-sep { color: var(--text-dim); font-weight: 400; }
.sub-meta-row { display: flex; align-items: center; gap: 18px; flex-wrap: wrap; }
.meta-item { font-size: 13px; color: var(--text-muted); }

/* KPI row */
.kpi-row {
    display: flex; gap: 1px; background: var(--border);
    border: 1px solid var(--border); border-radius: var(--radius);
    overflow: hidden; margin-bottom: 14px;
}
.kpi { flex: 1; background: var(--surface); padding: 14px 18px; }
.kpi-label { font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 4px; }
.kpi-val { font-size: 18px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.kpi-val.mono { font-family: var(--font-mono); font-size: 13px; }
.text-fail    { color: var(--red-ink) !important; }
.text-pending { color: var(--amber-ink) !important; }
.text-pass    { color: var(--green-ink) !important; }
.kpi-val.text-dim { color: var(--text-dim) !important; font-size: 14px; }

/* Verdict + pipeline + results table */
.verdict-card { margin-bottom: 14px; }
.verdict-block { display: flex; flex-direction: column; gap: 16px; }
.verdict-head { display: flex; align-items: baseline; gap: 14px; }
.verdict-headline { font-size: 20px; font-weight: 600; }
.verdict-headline.pass { color: var(--green-ink); }
.verdict-headline.fail { color: var(--red-ink); }
.verdict-sub { font-size: 14px; color: var(--text-muted); }

.results-table {
    font-size: 13px;
    border: 1px solid var(--border);
    border-radius: var(--radius);
    overflow: hidden;
}
.results-row {
    display: grid;
    grid-template-columns: 48px minmax(0, 1.6fr) minmax(0, 1fr) minmax(0, 1fr) 72px 80px;
    padding: 8px 14px;
    font-family: var(--font-mono);
}
.results-head {
    color: var(--text-muted);
    background: var(--surface2);
    font-weight: 500;
    font-family: var(--font-sans);
}
.results-row:not(.results-head) { border-top: 1px solid var(--border); }
.results-row.row-fail { background: var(--red-dim); }
.results-row:not(.results-head) > [role="cell"] { white-space: pre-line; align-self: start; }
.dim { color: var(--text-muted); }
.result-label { font-family: var(--font-sans); font-weight: 500; }
.row-error {
    margin: 0;
    padding: 6px 14px 10px;
    font-family: var(--font-mono);
    font-size: 12px;
    color: var(--red-ink);
}

/* Main grid */
.main-grid { display: grid; grid-template-columns: 1fr 420px; gap: 14px; align-items: start; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; margin-bottom: 14px; }
.card:last-child { margin-bottom: 0; }
.card-title { font-size: 12px; font-weight: 600; color: var(--text-dim); margin-bottom: 14px; }
.right-col { display: flex; flex-direction: column; }

/* Code */
.code-card { height: fit-content; }
.code-block {
    background: var(--code-bg); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 16px;
    font-family: var(--font-mono); font-size: 14px; line-height: 1.7; white-space: pre-wrap; word-break: break-all;
    max-height: 600px; overflow-y: auto;
    color: var(--code-text);
}

/* Shared states */
.mini-state { color: var(--text-dim); font-size: 13px; padding: 20px 0; text-align: center; }
.mono { font-family: var(--font-mono); }

/* Question */
.q-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 8px; }
.q-desc { font-size: 13px; color: var(--text-muted); line-height: 1.6; white-space: pre-line; }

/* Plagiarism */
.flag-section { margin-bottom: 14px; }
.flag-section-title { font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 8px; display: flex; align-items: center; gap: 8px; }
.flag-divider { height: 1px; background: var(--border); margin: 14px 0; }

.conf-badge { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 10px; }

.rev-badge { font-size: 11px; font-weight: 600; padding: 2px 7px; border-radius: 10px; }
.rev-badge.pending   { background: var(--yellow-dim); color: var(--amber-ink); }
.rev-badge.confirmed { background: var(--red-dim); color: var(--red-ink); }
.rev-badge.dismissed { background: var(--surface3); color: var(--text-dim); }

.risk-bar-wrap { height: 4px; background: var(--surface3); border-radius: 2px; margin-bottom: 4px; overflow: hidden; }
.risk-bar { height: 100%; border-radius: 2px; }
.risk-bar.high   { background: var(--red); }
.risk-bar.medium { background: var(--yellow); }
.risk-bar.low    { background: var(--text-dim); } /* low flag confidence is neutral, never green */
.risk-score-label { font-size: 11px; color: var(--text-dim); margin-bottom: 10px; }

.signals-list { display: flex; flex-direction: column; gap: 5px; margin-bottom: 8px; }
.signal-item { display: flex; align-items: flex-start; gap: 7px; font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.signal-item svg { flex-shrink: 0; margin-top: 2px; color: var(--amber-ink); }

.review-note { font-size: 11px; color: var(--text-dim); font-style: italic; background: var(--surface2); padding: 6px 10px; border-radius: var(--radius-sm); }

.clean-flag { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--green-ink); padding: 6px 0; }
.pending-flag { font-size: 12px; color: var(--text-dim); padding: 6px 0; }

.sim-flag-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); }
.sim-flag-row:last-child { border-bottom: none; }
.sim-flag-left { display: flex; align-items: center; gap: 10px; }
.sim-flag-score { font-size: 13px; font-weight: 600; }
.sim-flag-student { font-size: 12px; color: var(--text-dim); }
.sim-flag-right { display: flex; align-items: center; gap: 8px; }

.view-btn {
    font-size: 12px; font-weight: 500; color: var(--text);
    background: transparent; border: 1px solid var(--border); border-radius: var(--radius-sm);
    padding: 3px 10px; cursor: pointer; transition: all 0.15s;
}
.view-btn:hover { border-color: var(--border2); background: var(--surface2); }

/* AI evaluation — plain card, no gradients/glow/chips */
.ai-card { padding: 20px; margin-bottom: 14px; }
.ai-caption { font-size: 12px; color: var(--text-dim); margin: 0 0 16px; }

.ai-total-row {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 12px; margin-bottom: 14px;
    background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm);
}
.ai-total-label { font-size: 11px; font-weight: 600; color: var(--text-dim); }
.ai-total-badge {
    font-size: 18px; font-weight: 600; padding: 3px 12px; border-radius: var(--radius-sm);
    font-variant-numeric: tabular-nums; line-height: 1;
}
.ai-total-max { font-size: 12px; font-weight: 600; opacity: 0.6; }
.ai-total-badge.good { background: var(--green-dim); color: var(--green-ink); }
.ai-total-badge.mid  { background: var(--yellow-dim); color: var(--amber-ink); }
.ai-total-badge.low  { background: var(--red-dim); color: var(--red-ink); }

.ai-dim { margin-bottom: 12px; }
.ai-dim-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px; }
.ai-dim-label { font-size: 12px; font-weight: 500; color: var(--text); }
.ai-dim-score { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.ai-dim-score.good { color: var(--green-ink); }
.ai-dim-score.mid  { color: var(--amber-ink); }
.ai-dim-score.low  { color: var(--red-ink); }
.ai-bar { height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; }
.ai-bar-fill { height: 100%; border-radius: 2px; }
.ai-bar-fill.good { background: var(--green); }
.ai-bar-fill.mid  { background: var(--yellow); }
.ai-bar-fill.low  { background: var(--red); }
.ai-dim-note { font-size: 12px; color: var(--text-muted); line-height: 1.5; margin: 5px 0 0; }
.ai-overall {
    font-size: 12px; color: var(--text); line-height: 1.6;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); padding: 10px 12px; margin-top: 14px;
}
.ai-hint-head {
    font-size: 11px; font-weight: 600; color: var(--amber-ink);
    margin: 16px 0 8px; padding-top: 14px; border-top: 1px solid var(--border);
}
.ai-hint { font-size: 12px; color: var(--text-muted); line-height: 1.6; background: var(--surface2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 10px 12px; margin: 0; }

.table-scroll { overflow-x: auto; }
.results-table { min-width: 640px; }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .main-grid { grid-template-columns: 1fr; }
    .kpi-row { flex-wrap: wrap; }
    .kpi { flex: 1 1 33%; min-width: 120px; }
}

@media (max-width: 600px) {
    .kpi { flex: 1 1 50%; }
    .sub-title { font-size: 22px; }
    .sub-meta-row { gap: 10px 14px; }
}
</style>
