<template>
    <div class="page">
        <div class="breadcrumb">
            <router-link to="/dashboard/support/disputes" class="back-btn">Back to disputes</router-link>
        </div>

        <div v-if="loading" class="loading">Loading appeal…</div>

        <div v-else-if="error" class="not-found">
            <h1>Appeal not found</h1>
            <p>The link may be wrong, or its exam was deleted.</p>
            <router-link to="/dashboard/support/disputes" class="back-btn">Back to disputes</router-link>
        </div>

        <template v-else-if="data">
            <div class="case-header">
                <div class="case-title-row">
                    <h1 class="case-title">Appeal on {{ examTitle }}</h1>
                    <span class="badge" :class="appealBadgeClass(data.status)">{{ TRAINER_APPEAL_STATUS[data.status as AppealStatus] ?? data.status }}</span>
                </div>
                <div class="case-meta">
                    <router-link :to="`/dashboard/students/${data.student}`" class="meta-student">
                        {{ data.student_username }}
                    </router-link>
                    <span v-if="data.flag_id" class="meta-type">{{ data.flag_type }} flag</span>
                    <span class="meta-time">Filed {{ fmtDate(data.created_at) }}</span>
                </div>
            </div>

            <div class="layout">
                <div class="left-col">
                    <!-- what the student is answering: the decision as it was when they filed -->
                    <section class="card" aria-labelledby="decision-h">
                        <div class="card-head">
                            <h2 id="decision-h" class="card-title">The decision</h2>
                            <router-link v-if="data.exam_id" :to="caseFileLink(data.exam_id, data.case_key, `dispute:${data.id}`)" class="link-btn">View case →</router-link>
                        </div>
                        <p v-if="data.decision_note" class="decision-text">“{{ data.decision_note }}”</p>
                        <p v-else class="muted small">Plagiarism confirmed. No note was left for the student.</p>
                    </section>

                    <section class="card rebuttal-card" aria-labelledby="response-h">
                        <h2 id="response-h" class="card-title">The student's response</h2>
                        <blockquote class="rebuttal-text">“{{ data.student_note }}”</blockquote>
                    </section>

                    <!-- filed on one flag before appeals were per exam: that flag and its code, as before -->
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
                                Student's code
                                <router-link :to="`/dashboard/submissions/${data.submission.id}`" class="link-btn">Full view</router-link>
                            </div>
                            <pre class="code-block">{{ data.submission.code }}</pre>
                        </div>
                    </div>

                    <!-- Matched submission (similarity disputes) -->
                    <div v-if="data.matched_submission" class="card">
                        <h2 class="card-title">Matched submission</h2>
                        <div class="sub-meta-row" style="margin-bottom:8px">
                            <span class="sub-label">Student</span>
                            <router-link :to="`/dashboard/students/${data.matched_submission.student_id}`" class="meta-student">
                                {{ data.matched_submission.student }}
                            </router-link>
                        </div>
                        <pre class="code-block">{{ data.matched_submission.code }}</pre>
                    </div>
                </div>

                <div class="right-col">
                    <!-- Flag verdict -->
                    <div v-if="data.flag_detail" class="card">
                        <h2 class="card-title">The flag it was filed on</h2>

                        <template v-if="data.flag_type === 'behavioural'">
                            <div class="risk-row">
                                <span class="risk-label-text">Risk</span>
                                <span class="risk-pct" :class="riskClass(data.flag_detail.risk_score)">
                                    {{ formatRisk(data.flag_detail.risk_score) }}
                                </span>
                            </div>
                            <div class="risk-bar-wrap">
                                <div class="risk-bar" :style="{ width: (data.flag_detail.risk_score * 100) + '%' }" :class="riskClass(data.flag_detail.risk_score)"></div>
                            </div>
                            <div class="conf-row">
                                <span class="badge" :class="confidenceClass(data.flag_detail.confidence)" :title="METRIC_HELP.confidence">{{ confidenceLabel(data.flag_detail.confidence) }}</span>
                            </div>
                            <div class="signal-list">
                                <div class="signal-label">Signals triggered</div>
                                <div v-for="sig in data.flag_detail.signals" :key="sig" class="signal-item">
                                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                                    {{ sig }}
                                </div>
                            </div>
                            <div class="score-breakdown">
                                <div class="score-row"><span>Paste score</span><span>{{ (data.flag_detail.paste_score * 100).toFixed(0) }}%</span></div>
                                <div class="score-row"><span>Time score</span><span>{{ (data.flag_detail.time_score * 100).toFixed(0) }}%</span></div>
                                <div class="score-row"><span>Tab-switch score</span><span>{{ (data.flag_detail.snapshot_score * 100).toFixed(0) }}%</span></div>
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

                    <section v-if="data.status !== 'open'" class="card" aria-labelledby="ruling-h">
                        <h2 id="ruling-h" class="card-title">Ruling</h2>
                        <p class="ruling-status">{{ data.status === 'overturned' ? 'Decision overturned: points restored' : 'Decision upheld' }}</p>
                        <p v-if="data.resolution_note" class="resolution-text">“{{ data.resolution_note }}”</p>
                        <div class="muted small" v-if="data.resolved_by_username">
                            {{ data.resolved_by_username }}, {{ fmtDate(data.resolved_at) }}
                        </div>
                    </section>

                    <!-- one round: uphold or overturn, each with a reply the student reads; final -->
                    <section v-else class="card resolve-card" aria-labelledby="rule-h">
                        <h2 id="rule-h" class="card-title">Your ruling</h2>
                        <div class="choice-row">
                            <button type="button" class="choice-btn" :class="{ active: choice === 'uphold' }" :aria-pressed="choice === 'uphold'" @click="choose('uphold')">Uphold</button>
                            <button type="button" class="choice-btn" :class="{ active: choice === 'overturn' }" :aria-pressed="choice === 'overturn'"
                                    :disabled="!data.exam_id" @click="choose('overturn')">Overturn</button>
                        </div>
                        <p v-if="!data.exam_id" class="muted small">This appeal's exam is gone, so it can only be upheld.</p>
                        <template v-if="choice">
                            <p class="choice-explain">{{ CHOICE_EXPLAIN[choice] }}</p>
                            <label for="ruling-reply" class="reply-label">Reply to the student (required)</label>
                            <textarea id="ruling-reply" v-model="reply" class="resolution-input" rows="4"
                                      :aria-invalid="!!saveError" :aria-describedby="saveError ? 'ruling-error' : undefined"
                                      placeholder="They see this with your ruling."></textarea>
                            <div class="resolve-actions">
                                <button type="button" :class="choice === 'overturn' ? 'btn-resolve' : 'btn-uphold'" :disabled="saving" @click="rule">
                                    {{ saving ? 'Saving…' : choice === 'overturn' ? 'Overturn decision' : 'Uphold decision' }}
                                </button>
                                <button type="button" class="btn-cancel" :disabled="saving" @click="choose(null)">Cancel</button>
                            </div>
                        </template>
                        <p v-if="saveError" id="ruling-error" class="save-error" role="alert">{{ saveError }}</p>
                    </section>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { formatDateTime, formatSeconds, formatRisk } from '../utils/format'
import { METRIC_HELP, confidenceClass, confidenceLabel } from '../utils/metrics'
import { caseFileLink } from '../utils/caseFile'
import { TRAINER_APPEAL_STATUS, appealBadgeClass, type AppealStatus } from '../utils/appeals'

type Choice = 'uphold' | 'overturn'
const CHOICE_EXPLAIN: Record<Choice, string> = {
    uphold: 'The decision stands and nothing changes. The student sees your reply.',
    overturn: 'Their behaviour flags on this exam become dismissed; their points are restored. Classmates are not affected.',
}

const route     = useRoute()
const loading   = ref(true)
const error     = ref('')
const data      = ref<any>(null)
const choice    = ref<Choice | null>(null)
const reply     = ref('')
const saving    = ref(false)
const saveError = ref('')

// a legacy per-flag dispute has no exam of its own: its flag names one
const examTitle = computed(() => data.value?.exam_title ?? data.value?.submission?.exam ?? data.value?.flag_context?.exam ?? 'an exam')

onMounted(async () => {
    try {
        const res = await api.get(`/support/disputes/${route.params.id}/`)
        data.value = res.data
    } catch {
        error.value = 'not_found'
    } finally {
        loading.value = false
    }
})

function choose(c: Choice | null) {
    choice.value = c
    saveError.value = ''
    if (c) nextTick(() => document.getElementById('ruling-reply')?.focus())
}

async function rule() {
    if (!choice.value || saving.value) return
    const note = reply.value.trim()
    if (!note) {
        saveError.value = 'Write a reply to the student: they see it with your ruling.'
        return
    }
    saving.value = true
    saveError.value = ''
    try {
        const res = await api.patch(`/support/disputes/${route.params.id}/`, { decision: choice.value, resolution_note: note })
        data.value = res.data
        choice.value = null
    } catch (e: any) {
        saveError.value = e?.response?.data?.error ?? "Couldn't save your ruling. Try again."
    } finally {
        saving.value = false
    }
}

function fmtDate(iso: string): string {
    if (!iso) return ''
    return formatDateTime(iso)
}
function fmtSeconds(s: number): string {
    return formatSeconds(s)
}
function statusClass(s: string): string {
    return s === 'passed' ? 'badge-green' : s === 'failed' ? 'badge-red' : 'badge-dim'
}
function reviewClass(s: string): string {
    return s === 'confirmed' ? 'badge-red' : s === 'dismissed' ? 'badge-green' : 'badge-yellow'
}
function riskClass(r: number): string {
    return r >= 0.7 ? 'red' : r >= 0.4 ? 'warn' : 'green'
}
</script>

<style scoped>
.page { max-width: 1200px; }
.breadcrumb { margin-bottom: 20px; }
.back-btn {
    display: inline-flex;
    padding: 7px 16px;
    background: var(--surface);
    border: 1px solid var(--border2);
    border-radius: var(--radius-pill);
    color: var(--text);
    font-size: 13px;
    font-weight: 600;
    text-decoration: none;
    transition: all 0.15s;
}
.back-btn:hover { background: var(--surface2); }

.loading   { color: var(--text-dim); padding: 40px 0; }
.not-found { text-align: center; padding: 60px 20px; }
.not-found h1 { font-size: 22px; margin: 0 0 8px; }
.not-found p { color: var(--text-muted); margin: 0 0 20px; }
.save-error { margin-top: 10px; color: var(--red-ink); font-size: 14px; }

/* Case header */
.case-header { margin-bottom: 28px; }
.case-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
.case-title { font-size: 22px; font-weight: 700; color: var(--text); margin: 0; }
.case-meta { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.meta-student { font-weight: 600; color: var(--accent-hover); text-decoration: none; }
.meta-student:hover { text-decoration: underline; }
.meta-sep { color: var(--text-dim); }
.meta-type { color: var(--text-dim); text-transform: capitalize; }
.meta-time { color: var(--text-dim); }

/* Layout */
.layout { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; align-items: start; }
.left-col, .right-col { display: flex; flex-direction: column; gap: 16px; }
@media (max-width: 899px) {
    .layout { grid-template-columns: 1fr; }
}

/* Cards */
.card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 22px 24px;
}
.card-title { font-size: 11px; font-weight: 600; color: var(--text-dim); margin: 0 0 14px; }

/* Submission meta */
.sub-meta { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.sub-meta-row { display: flex; align-items: center; gap: 12px; font-size: 13px; }
.sub-label { min-width: 90px; font-size: 11px; font-weight: 600; color: var(--text-dim); }
.sub-val { color: var(--text); }
.sub-val.muted { color: var(--text-dim); }
.lang-chip { font-family: var(--font-mono); font-size: 12px; background: var(--surface2); padding: 2px 8px; border-radius: 4px; color: var(--text-muted); }

/* Behaviour metrics */
.behaviour-metrics {
    display: flex; gap: 20px; flex-wrap: wrap;
    background: var(--surface2); border-radius: var(--radius-sm);
    padding: 12px 16px; margin-bottom: 16px;
}
.metric { flex: 1; }
.metric-label { font-size: 11px; color: var(--text-dim); margin-bottom: 4px; }
.metric-val { font-size: 16px; font-weight: 700; color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.metric-val.red   { color: var(--red-ink); }
.metric-val.green { color: var(--green-ink); }
.metric-sub { font-size: 11px; font-weight: 400; color: var(--text-dim); }

/* Question description */
.question-desc { margin-bottom: 16px; }
.qdesc-label { font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 6px; }
.qdesc-text { font-size: 13px; color: var(--text-muted); line-height: 1.6; margin: 0; }

/* Code */
.code-section { }
.code-label { display: flex; align-items: center; justify-content: space-between; font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 8px; }
.code-block {
    background: var(--code-bg); border: 1px solid var(--border2);
    border-radius: var(--radius-sm); padding: 16px;
    font-family: var(--font-mono);
    font-size: 12px; color: var(--code-text); line-height: 1.6;
    overflow-x: auto; white-space: pre; max-height: 400px; overflow-y: auto;
    margin: 0;
}

/* Flag detail */
.risk-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.risk-label-text { font-size: 13px; color: var(--text-muted); }
.risk-pct { font-size: 24px; font-weight: 700; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.risk-pct.red  { color: var(--red-ink); }
.risk-pct.warn { color: var(--amber-ink); }
.risk-pct.green { color: var(--green-ink); }
.risk-bar-wrap { height: 6px; background: var(--surface2); border-radius: 3px; margin-bottom: 12px; }
.risk-bar { height: 100%; border-radius: 3px; }
.risk-bar.red, .risk-bar.risk-high { background: var(--red); }
.risk-bar.warn { background: var(--yellow); }
.risk-bar.green { background: var(--green); }
.conf-row { margin-bottom: 16px; }
.conf-row.muted { font-size: 12px; color: var(--text-dim); }

.signal-list { margin-bottom: 16px; }
.signal-label { font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 8px; }
.signal-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-muted); padding: 4px 0; }
.signal-item svg { color: var(--yellow); flex-shrink: 0; }

.score-breakdown { border-top: 1px solid var(--border); padding-top: 12px; }
.score-row { display: flex; justify-content: space-between; font-size: 12px; color: var(--text-dim); padding: 3px 0; }
.score-row span:last-child { font-weight: 600; color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

.flag-review-status { border-top: 1px solid var(--border); padding-top: 12px; margin-top: 12px; }
.review-note { font-style: italic; font-size: 13px; color: var(--text-dim); margin: 8px 0 0; }

/* Rebuttal */
.rebuttal-card { border-left: 3px solid var(--border2); }
.rebuttal-text {
    font-style: italic; font-size: 14px; color: var(--text-muted);
    line-height: 1.7; margin: 0;
    border-left: none; padding: 0;
}

/* Decision and ruling */
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.card-head .card-title { margin: 0; }
.card-head .link-btn { display: inline-flex; align-items: center; min-height: 44px; }
.decision-text { margin: 0; font-size: 14px; line-height: 1.6; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
.ruling-status { margin: 0 0 8px; font-size: 15px; font-weight: 600; color: var(--text); }
.choice-row { display: flex; gap: 8px; margin-bottom: 12px; }
.choice-btn {
    flex: 1; min-height: 44px; padding: 0 16px; font-size: 14px; font-weight: 600;
    background: var(--surface); border: 1px solid var(--border2); border-radius: var(--radius-pill);
    color: var(--text); cursor: pointer;
}
.choice-btn.active { background: var(--accent-tint); border-color: var(--accent); color: var(--accent-hover); }
.choice-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.choice-explain { margin: 0 0 12px; font-size: 13px; line-height: 1.5; color: var(--text-muted); }
.reply-label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: var(--text); }
.btn-uphold, .btn-cancel {
    min-height: 44px; padding: 0 20px; font-size: 13px; font-weight: 600;
    border-radius: var(--radius-pill); cursor: pointer;
}
.btn-uphold { flex: 1; background: var(--surface2); border: 1px solid var(--border2); color: var(--text); }
.btn-cancel { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.btn-uphold:disabled, .btn-cancel:disabled { opacity: 0.5; cursor: not-allowed; }

/* Resolution */
.resolution-text { font-size: 14px; color: var(--text-muted); margin: 0 0 8px; line-height: 1.6; }

/* Resolve form */
.resolve-card { border: 1px solid var(--green-dim); }
.decision-caption { font-size: 11px; color: var(--text-dim); margin: -4px 0 12px; }
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
    flex: 1; min-height: 44px; padding: 10px; font-size: 13px; font-weight: 600;
    background: var(--green-dim); border: 1px solid var(--green);
    border-radius: var(--radius-pill); color: var(--green-ink); cursor: pointer;
    transition: all 0.15s;
}
.btn-resolve:hover:not(:disabled) { background: rgba(22,163,74,0.18); }
.btn-resolve:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-escalate {
    padding: 10px 20px; font-size: 13px; font-weight: 600;
    background: var(--red-dim); border: 1px solid var(--red);
    border-radius: var(--radius-pill); color: var(--red-ink); cursor: pointer;
    transition: all 0.15s;
}
.btn-escalate:hover:not(:disabled) { background: rgba(237,3,49,0.18); }
.btn-escalate:disabled { opacity: 0.5; cursor: not-allowed; }

/* Shared */
.badge { display: inline-block; padding: 3px 10px; border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; }
.badge-green  { background: var(--green-dim);  color: var(--green-ink); }
.badge-yellow { background: var(--yellow-dim); color: var(--amber-ink); }
.badge-red    { background: var(--red-dim);    color: var(--red-ink); }
.badge-dim    { background: var(--surface2);   color: var(--text-dim); }
.muted { color: var(--text-dim); }
.small { font-size: 12px; }
.link-btn { font-size: 12px; color: var(--accent-hover); text-decoration: none; font-weight: 600; }
.link-btn:hover { text-decoration: underline; }
</style>
