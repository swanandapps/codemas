<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1>Disputes</h1>
                <p class="page-subtitle">Students who appealed a plagiarism decision. Each exam's decision can be appealed once, and your ruling is final.</p>
            </div>
            <div class="filter-row" role="group" aria-label="Show appeals">
                <button v-for="f in filters" :key="f.val" type="button" class="filter-btn" :class="{ active: activeFilter === f.val }"
                        :aria-pressed="activeFilter === f.val" @click="setFilter(f.val)">
                    {{ f.label }}
                </button>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading…</div>
        <div v-else-if="error" class="error-msg" role="alert">{{ error }}</div>

        <div v-else-if="!disputes.length" class="empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40" aria-hidden="true"><path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
            <p>{{ activeFilter === 'all' ? 'No appeals yet.' : `No ${activeFilter} appeals.` }}</p>
        </div>

        <div v-else>
            <article v-for="d in disputes" :key="d.id" class="dispute-card">
                <div class="dispute-header">
                    <div class="dispute-meta">
                        <router-link :to="`/dashboard/students/${d.student}`" class="student-link">{{ d.student_username }}</router-link>
                        <span class="exam-name">{{ examTitle(d) }}</span>
                        <span v-if="d.flag_id" class="flag-ref" title="Filed on one flag, before appeals were per exam">{{ d.flag_type }} flag</span>
                        <span class="time-ago">Filed {{ formatDateTime(d.created_at) }}</span>
                    </div>
                    <span class="badge" :class="appealBadgeClass(d.status)">{{ TRAINER_APPEAL_STATUS[d.status as AppealStatus] ?? d.status }}</span>
                </div>

                <p class="quote-label">The student's response</p>
                <blockquote class="student-note">“{{ d.student_note }}”</blockquote>

                <div v-if="d.resolution_note" class="resolution">
                    <strong>Your reply:</strong> {{ d.resolution_note }}
                </div>

                <div class="card-links">
                    <router-link v-if="d.exam_id" :to="caseFileLink(d.exam_id, d.case_key, `dispute:${d.id}`)" class="card-link">View case</router-link>
                    <router-link :to="`/dashboard/support/disputes/${d.id}`" class="card-link primary">
                        {{ d.status === 'open' ? 'Rule on this appeal →' : 'Open appeal →' }}
                    </router-link>
                </div>
            </article>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'
import { formatDateTime } from '../utils/format'
import { caseFileLink } from '../utils/caseFile'
import { TRAINER_APPEAL_STATUS, appealBadgeClass, type AppealStatus } from '../utils/appeals'

const loading      = ref(true)
const error        = ref('')
const disputes     = ref<any[]>([])
const activeFilter = ref('open')

const filters = [
    { val: 'open',       label: 'Open' },
    { val: 'upheld',     label: 'Upheld' },
    { val: 'overturned', label: 'Overturned' },
    { val: 'all',        label: 'All' },
]

async function load() {
    loading.value = true
    error.value   = ''
    try {
        const res = await api.get(`/support/disputes/?status=${activeFilter.value}`)
        disputes.value = res.data
    } catch {
        error.value = 'Failed to load appeals.'
    } finally {
        loading.value = false
    }
}

async function setFilter(f: string) {
    activeFilter.value = f
    await load()
}

// a legacy per-flag dispute has no exam of its own: its flag names one
function examTitle(d: any): string {
    return d.exam_title ?? d.flag_context?.exam ?? 'Exam no longer available'
}

onMounted(load)
</script>

<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
.page-subtitle { font-size: 15px; color: var(--text-muted); margin: 4px 0 0; }
.loading   { color: var(--text-dim); padding: 40px 0; }
.error-msg { color: var(--red-ink); padding: 20px 0; }

.filter-row { display: flex; gap: 4px; flex-wrap: wrap; }
.filter-btn {
    min-height: 44px; padding: 6px 16px; font-size: 13px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-pill); color: var(--text-muted); cursor: pointer;
    transition: all 0.15s;
}
.filter-btn:hover { color: var(--text); }
.filter-btn.active { background: var(--accent-tint); border-color: var(--accent); color: var(--accent-hover); }

.empty { text-align: center; padding: 60px 0; color: var(--text-dim); }
.empty svg { margin: 0 auto 12px; display: block; opacity: 0.4; }
.empty p { font-size: 14px; }

.dispute-card {
    display: block;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px; margin-bottom: 12px;
}
.exam-name { font-size: 14px; font-weight: 600; color: var(--text); overflow-wrap: anywhere; }
.quote-label { margin: 0; font-size: 12px; font-weight: 600; color: var(--text-dim); }
.card-links { display: flex; flex-wrap: wrap; gap: 4px 16px; margin-top: 8px; }
.card-link { display: inline-flex; align-items: center; min-height: 44px; font-size: 14px; font-weight: 600; color: var(--text-muted); }
.card-link.primary { color: var(--accent-hover); }

.submission-context {
    display: flex; align-items: center; flex-wrap: wrap; gap: 6px;
    font-size: 12px; color: var(--text-dim);
    margin-bottom: 10px;
}
.ctx-sep { opacity: 0.5; }
.ctx-question { color: var(--text-muted); font-weight: 500; }
.lang-chip { font-family: var(--font-mono); font-size: 10px; background: var(--surface2); padding: 1px 6px; border-radius: 4px; color: var(--text-dim); }
.dispute-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.dispute-meta { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.student-link { font-weight: 700; color: var(--accent-hover); text-decoration: none; font-size: 15px; }
.student-link:hover { text-decoration: underline; }
.flag-ref { font-size: 12px; background: var(--surface2); padding: 2px 8px; border-radius: 4px; color: var(--text-dim); font-family: var(--font-mono); }
.time-ago { font-size: 12px; color: var(--text-dim); }

.flag-context { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.ctx-item { font-size: 12px; color: var(--text-dim); }
.ctx-item strong { color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.text-red  { color: var(--red-ink) !important; }
.signal-chip { font-size: 11px; padding: 2px 8px; background: var(--surface2); border-radius: 4px; color: var(--text-dim); }

.student-note {
    font-style: italic; color: var(--text-muted);
    border-left: 3px solid var(--border2); margin: 10px 0; padding-left: 12px;
    font-size: 14px;
}
.resolution { font-size: 12px; color: var(--text-dim); background: var(--surface2); padding: 8px 12px; border-radius: 4px; margin-top: 8px; }

.resolve-form { margin-top: 16px; border-top: 1px solid var(--border); padding-top: 16px; }
.resolution-input {
    width: 100%; padding: 10px 12px; font-size: 13px;
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text);
    resize: vertical; min-height: 60px; margin-bottom: 10px;
    box-sizing: border-box;
}
.resolution-input::placeholder { color: var(--text-dim); }
.resolve-actions { display: flex; gap: 8px; }
.btn-dismiss {
    padding: 8px 20px; font-size: 13px; font-weight: 600;
    background: var(--green-dim); border: 1px solid var(--green);
    border-radius: var(--radius-sm); color: var(--green-ink); cursor: pointer;
    transition: all 0.15s;
}
.btn-dismiss:hover { background: var(--green); color: #fff; }
.btn-escalate {
    padding: 8px 20px; font-size: 13px; font-weight: 600;
    background: var(--red-dim); border: 1px solid var(--red);
    border-radius: var(--radius-sm); color: var(--red-ink); cursor: pointer;
    transition: all 0.15s;
}
.btn-escalate:hover { background: var(--red); color: #fff; }

.badge { display: inline-block; padding: 3px 10px; border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; }
.badge-green  { background: var(--green-dim);  color: var(--green-ink); }
.badge-yellow { background: var(--yellow-dim); color: var(--amber-ink); }
.badge-red    { background: var(--red-dim);    color: var(--red-ink); }
.badge-dim    { background: var(--surface2);   color: var(--text-muted); }
@media (max-width: 560px) {
    .dispute-card { padding: 16px; }
}
</style>
