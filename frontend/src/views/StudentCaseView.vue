<template>
    <div class="page">
        <div class="page-header">
            <h1 class="page-title">Student Case</h1>
            <p class="page-subtitle">Full 360 view — submissions, flags, and disputes</p>
        </div>

        <div v-if="loading" class="loading">Loading…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else-if="data">
            <!-- Student profile card -->
            <div class="profile-card">
                <div class="avatar">{{ initials }}</div>
                <div class="profile-info">
                    <div class="profile-name">{{ data.student.username }}</div>
                    <div class="profile-email">{{ data.student.email }}</div>
                </div>
                <div class="profile-stats">
                    <div class="pstat">
                        <div class="pstat-val">{{ data.student.total_submissions }}</div>
                        <div class="pstat-label">Submissions</div>
                    </div>
                    <div class="pstat">
                        <div class="pstat-val" :class="data.behavioural.length ? 'red' : 'green'">
                            {{ data.behavioural.length }}
                        </div>
                        <div class="pstat-label">Behav. Flags</div>
                    </div>
                    <div class="pstat">
                        <div class="pstat-val" :class="data.similarity.length ? 'red' : 'green'">
                            {{ data.similarity.length }}
                        </div>
                        <div class="pstat-label">Sim. Flags</div>
                    </div>
                    <div class="pstat">
                        <div class="pstat-val warn">{{ data.student.open_disputes }}</div>
                        <div class="pstat-label">Open Disputes</div>
                    </div>
                </div>
            </div>

            <!-- Tabs -->
            <div class="tabs">
                <button v-for="t in tabs" :key="t.key" class="tab" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">
                    {{ t.label }}
                    <span class="tab-count">{{ t.count }}</span>
                </button>
            </div>

            <!-- Submissions tab -->
            <div v-if="activeTab === 'submissions'">
                <table class="data-table">
                    <thead>
                        <tr><th>Exam</th><th>Question</th><th>Lang</th><th>Attempt</th><th>Status</th><th>Checks</th><th>Submitted</th><th></th></tr>
                    </thead>
                    <tbody>
                        <tr v-for="s in data.submissions" :key="s.id">
                            <td>{{ s.exam }}</td>
                            <td class="muted">{{ s.question }}</td>
                            <td><span class="lang-badge">{{ s.language }}</span></td>
                            <td>#{{ s.attempt }}</td>
                            <td><span class="badge" :class="statusClass(s.status)">{{ s.status }}</span></td>
                            <td>
                                <span class="check-dot" :class="s.behavioural_done ? 'done' : 'pending'" title="Behavioural">B</span>
                                <span class="check-dot" :class="s.similarity_done  ? 'done' : 'pending'" title="Similarity">S</span>
                            </td>
                            <td class="muted small">{{ fmtDate(s.submitted_at) }}</td>
                            <td>
                                <router-link :to="`/dashboard/submissions/${s.id}`" class="link-btn">View →</router-link>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>

            <!-- Behavioural flags tab -->
            <div v-if="activeTab === 'behavioural'">
                <div v-if="!data.behavioural.length" class="empty">No behavioural flags for this student.</div>
                <div v-for="f in data.behavioural" :key="f.flag_id" class="flag-card">
                    <div class="flag-header">
                        <div>
                            <span class="flag-exam">{{ f.exam }}</span>
                            <span class="muted"> — {{ f.question }}</span>
                        </div>
                        <span class="badge" :class="confidenceClass(f.confidence)">{{ f.confidence }} confidence</span>
                    </div>
                    <div class="risk-bar-wrap">
                        <div class="risk-bar" :style="{ width: (f.risk_score * 100) + '%' }" :class="riskClass(f.risk_score)"></div>
                        <span class="risk-label">Risk {{ (f.risk_score * 100).toFixed(0) }}%</span>
                    </div>
                    <div class="signals">
                        <span v-for="sig in f.signals" :key="sig" class="signal-chip">{{ sig }}</span>
                    </div>
                    <div class="flag-footer">
                        <span class="badge" :class="reviewClass(f.review_status)">{{ f.review_status }}</span>
                        <span v-if="f.review_note" class="review-note">"{{ f.review_note }}"</span>
                        <span v-if="f.reviewed_by" class="muted small"> by {{ f.reviewed_by }}</span>
                        <router-link :to="`/dashboard/submissions/${f.submission_id}`" class="link-btn" style="margin-left:auto">View →</router-link>
                    </div>
                </div>
            </div>

            <!-- Similarity flags tab -->
            <div v-if="activeTab === 'similarity'">
                <div v-if="!data.similarity.length" class="empty">No similarity flags for this student.</div>
                <div v-for="f in data.similarity" :key="f.flag_id" class="flag-card">
                    <div class="flag-header">
                        <div>
                            <span class="flag-exam">{{ f.exam }}</span>
                        </div>
                        <span class="sim-score" :class="simClass(f.similarity_score)">
                            {{ (f.similarity_score * 100).toFixed(1) }}% match
                        </span>
                    </div>
                    <div class="flag-footer">
                        <span class="muted">Matched with </span>
                        <router-link :to="`/dashboard/support/student/${f.other_student_id}`" class="link-btn">
                            {{ f.other_student }}
                        </router-link>
                        <span class="badge" :class="reviewClass(f.review_status)" style="margin-left:12px">{{ f.review_status }}</span>
                        <span v-if="f.review_note" class="review-note">"{{ f.review_note }}"</span>
                    </div>
                </div>
            </div>

            <!-- Disputes tab -->
            <div v-if="activeTab === 'disputes'">
                <div v-if="!data.disputes.length" class="empty">No disputes filed by this student.</div>
                <div v-for="d in data.disputes" :key="d.id" class="flag-card">
                    <div class="flag-header">
                        <span class="flag-exam">{{ d.flag_type }} flag #{{ d.flag_id }}</span>
                        <span class="badge" :class="disputeClass(d.status)">{{ d.status }}</span>
                    </div>
                    <p class="dispute-note">"{{ d.student_note }}"</p>
                    <div v-if="d.resolution_note" class="resolution">
                        <strong>Resolution:</strong> {{ d.resolution_note }}
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route   = useRoute()
const loading = ref(true)
const error   = ref('')
const data    = ref<any>(null)
const activeTab = ref('submissions')

const tabs = computed(() => [
    { key: 'submissions', label: 'Submissions', count: data.value?.submissions?.length ?? 0 },
    { key: 'behavioural', label: 'Behavioural Flags', count: data.value?.behavioural?.length ?? 0 },
    { key: 'similarity',  label: 'Similarity Flags',  count: data.value?.similarity?.length ?? 0 },
    { key: 'disputes',    label: 'Disputes',           count: data.value?.disputes?.length ?? 0 },
])

const initials = computed(() =>
    (data.value?.student?.username || '').slice(0, 2).toUpperCase()
)

onMounted(async () => {
    try {
        const res = await api.get(`/support/student/${route.params.id}/`)
        data.value = res.data
    } catch {
        error.value = 'Failed to load student case.'
    } finally {
        loading.value = false
    }
})

function fmtDate(iso: string): string {
    return new Date(iso).toLocaleString()
}
function statusClass(s: string) {
    return s === 'passed' ? 'badge-green' : s === 'failed' ? 'badge-red' : 'badge-dim'
}
function confidenceClass(c: string) {
    return c === 'high' ? 'badge-red' : c === 'medium' ? 'badge-yellow' : 'badge-dim'
}
function riskClass(r: number) {
    return r >= 0.7 ? 'risk-high' : r >= 0.4 ? 'risk-mid' : 'risk-low'
}
function reviewClass(s: string) {
    return s === 'confirmed' ? 'badge-red' : s === 'dismissed' ? 'badge-green' : 'badge-yellow'
}
function simClass(s: number) {
    return s >= 0.9 ? 'red' : s >= 0.7 ? 'warn' : ''
}
function disputeClass(s: string) {
    return s === 'open' ? 'badge-yellow' : s === 'escalated' ? 'badge-red' : 'badge-green'
}
</script>

<style scoped>
.page { padding: 32px 40px; max-width: 1100px; }
.page-header { margin-bottom: 24px; }
.page-title  { font-size: 22px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--text-dim); margin: 0; }
.loading  { color: var(--text-dim); padding: 40px 0; }
.error-msg { color: var(--red); padding: 20px 0; }

/* Profile card */
.profile-card {
    display: flex;
    align-items: center;
    gap: 20px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 24px;
}
.avatar {
    width: 52px; height: 52px; border-radius: 50%;
    background: var(--red-dim);
    border: 2px solid rgba(230,57,70,0.3);
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; font-weight: 700; color: var(--red); flex-shrink: 0;
}
.profile-info { flex: 1; }
.profile-name { font-size: 18px; font-weight: 700; color: var(--text); }
.profile-email { font-size: 13px; color: var(--text-dim); margin-top: 2px; }
.profile-stats { display: flex; gap: 32px; }
.pstat { text-align: center; }
.pstat-val { font-size: 22px; font-weight: 700; color: var(--text); }
.pstat-val.red { color: var(--red); }
.pstat-val.green { color: #22c55e; }
.pstat-val.warn { color: #f59e0b; }
.pstat-label { font-size: 11px; color: var(--text-dim); margin-top: 2px; }

/* Tabs */
.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
.tab {
    padding: 8px 16px; font-size: 13px; font-weight: 500;
    color: var(--text-muted); background: none; border: none;
    border-bottom: 2px solid transparent; cursor: pointer;
    display: flex; align-items: center; gap: 6px;
    transition: all 0.15s;
}
.tab:hover { color: var(--text); }
.tab.active { color: var(--red); border-bottom-color: var(--red); }
.tab-count {
    background: var(--surface2); border-radius: 10px;
    padding: 1px 6px; font-size: 11px; font-weight: 600;
}
.tab.active .tab-count { background: var(--red-dim); color: var(--red); }

/* Table */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
    text-align: left; font-size: 11px; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.5px;
    color: var(--text-dim); padding: 0 8px 8px;
    border-bottom: 1px solid var(--border);
}
.data-table td { padding: 10px 8px; border-bottom: 1px solid var(--border); color: var(--text); vertical-align: middle; }
.data-table tr:last-child td { border-bottom: none; }
.muted { color: var(--text-dim); }
.small { font-size: 12px; }

/* Check dots */
.check-dot {
    display: inline-flex; width: 18px; height: 18px; border-radius: 50%;
    align-items: center; justify-content: center;
    font-size: 9px; font-weight: 700; margin-right: 2px;
}
.check-dot.done    { background: rgba(34,197,94,0.15); color: #22c55e; }
.check-dot.pending { background: var(--surface2);       color: var(--text-dim); }

/* Badges */
.badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-yellow { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-red    { background: rgba(230,57,70,0.12);  color: var(--red); }
.badge-dim    { background: var(--surface2);        color: var(--text-dim); }

.lang-badge { font-size: 11px; font-family: monospace; background: var(--surface2); padding: 2px 6px; border-radius: 4px; color: var(--text-dim); }

/* Flag cards */
.flag-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 18px 20px; margin-bottom: 10px;
}
.flag-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; font-size: 14px; }
.flag-exam { font-weight: 600; color: var(--text); }
.flag-footer { display: flex; align-items: center; gap: 10px; margin-top: 12px; font-size: 13px; }

.risk-bar-wrap { height: 6px; background: var(--surface2); border-radius: 3px; margin: 8px 0; position: relative; }
.risk-bar { height: 100%; border-radius: 3px; }
.risk-bar.risk-high { background: var(--red); }
.risk-bar.risk-mid  { background: #f59e0b; }
.risk-bar.risk-low  { background: #22c55e; }
.risk-label { font-size: 11px; color: var(--text-dim); margin-top: 2px; display: block; }

.signals { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.signal-chip {
    font-size: 11px; padding: 3px 8px;
    background: var(--surface2); border-radius: 4px; color: var(--text-dim);
}

.sim-score { font-weight: 700; font-size: 15px; }
.sim-score.red { color: var(--red); }
.sim-score.warn { color: #f59e0b; }

.review-note { font-style: italic; color: var(--text-dim); font-size: 12px; }

.dispute-note { font-style: italic; color: var(--text-muted); margin: 8px 0; font-size: 13px; }
.resolution { font-size: 12px; color: var(--text-dim); background: var(--surface2); padding: 8px 12px; border-radius: 4px; }

.link-btn { font-size: 12px; color: var(--red); text-decoration: none; font-weight: 600; }
.link-btn:hover { text-decoration: underline; }

.empty { padding: 32px 0; color: var(--text-dim); font-size: 14px; text-align: center; }
</style>
