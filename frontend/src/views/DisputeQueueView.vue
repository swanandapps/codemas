<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1 class="page-title">Dispute Queue</h1>
                <p class="page-subtitle">Students who contested a plagiarism flag</p>
            </div>
            <div class="filter-row">
                <button v-for="f in filters" :key="f.val" class="filter-btn" :class="{ active: activeFilter === f.val }" @click="setFilter(f.val)">
                    {{ f.label }}
                </button>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <div v-else-if="!disputes.length" class="empty">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="40" height="40"><path d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
            <p>No {{ activeFilter === 'all' ? '' : activeFilter }} disputes.</p>
        </div>

        <div v-else>
            <div v-for="d in disputes" :key="d.id" class="dispute-card" @click="openDispute(d.id)">
                <div class="dispute-header">
                    <div class="dispute-meta">
                        <router-link :to="`/dashboard/support/student/${d.student}`" class="student-link" @click.stop>
                            {{ d.student_username }}
                        </router-link>
                        <span class="flag-ref">{{ d.flag_type }} flag</span>
                        <span class="time-ago">{{ fmtDate(d.created_at) }}</span>
                    </div>
                    <div style="display:flex;align-items:center;gap:8px">
                        <span class="badge" :class="statusClass(d.status)">{{ d.status }}</span>
                        <span class="open-arrow">→</span>
                    </div>
                </div>

                <!-- Exam + question -->
                <div v-if="d.flag_context?.exam" class="submission-context">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="12" height="12"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
                    <span>{{ d.flag_context.exam }}</span>
                    <span class="ctx-sep">·</span>
                    <span class="ctx-question">{{ d.flag_context.question }}</span>
                    <span v-if="d.flag_context.language" class="lang-chip">{{ d.flag_context.language }}</span>
                </div>

                <!-- Flag context -->
                <div v-if="d.flag_context && Object.keys(d.flag_context).length" class="flag-context">
                    <template v-if="d.flag_type === 'behavioural'">
                        <span class="ctx-item">Risk: <strong>{{ (d.flag_context.risk_score * 100).toFixed(0) }}%</strong></span>
                        <span class="ctx-item">Confidence: <strong :class="confClass(d.flag_context.confidence)">{{ d.flag_context.confidence }}</strong></span>
                        <span v-for="sig in d.flag_context.signals" :key="sig" class="signal-chip">{{ sig }}</span>
                    </template>
                    <template v-else>
                        <span class="ctx-item">Similarity: <strong>{{ (d.flag_context.similarity_score * 100).toFixed(1) }}%</strong></span>
                    </template>
                </div>

                <blockquote class="student-note">"{{ d.student_note }}"</blockquote>

                <div v-if="d.resolution_note" class="resolution">
                    <strong>Resolution:</strong> {{ d.resolution_note }}
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router       = useRouter()
const loading      = ref(true)
const error        = ref('')
const disputes     = ref<any[]>([])
const activeFilter = ref('open')

const filters = [
    { val: 'open',      label: 'Open' },
    { val: 'resolved',  label: 'Resolved' },
    { val: 'escalated', label: 'Escalated' },
    { val: 'all',       label: 'All' },
]

async function load() {
    loading.value = true
    error.value   = ''
    try {
        const res = await api.get(`/support/disputes/?status=${activeFilter.value}`)
        disputes.value = res.data
    } catch {
        error.value = 'Failed to load disputes.'
    } finally {
        loading.value = false
    }
}

async function setFilter(f: string) {
    activeFilter.value = f
    await load()
}

function openDispute(id: number) {
    router.push(`/dashboard/support/disputes/${id}`)
}

onMounted(load)

function fmtDate(iso: string) {
    return new Date(iso).toLocaleString()
}
function statusClass(s: string) {
    return s === 'open' ? 'badge-yellow' : s === 'escalated' ? 'badge-red' : 'badge-green'
}
function confClass(c: string) {
    return c === 'high' ? 'text-red' : c === 'medium' ? 'text-warn' : ''
}
</script>

<style scoped>
.page { padding: 32px 40px; max-width: 900px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; }
.page-title  { font-size: 22px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--text-dim); margin: 0; }
.loading   { color: var(--text-dim); padding: 40px 0; }
.error-msg { color: var(--red); padding: 20px 0; }

.filter-row { display: flex; gap: 4px; }
.filter-btn {
    padding: 6px 14px; font-size: 12px; font-weight: 500;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-sm); color: var(--text-muted); cursor: pointer;
    transition: all 0.15s;
}
.filter-btn:hover { color: var(--text); }
.filter-btn.active { background: var(--red-dim); border-color: rgba(230,57,70,0.3); color: var(--red); }

.empty { text-align: center; padding: 60px 0; color: var(--text-dim); }
.empty svg { margin: 0 auto 12px; display: block; opacity: 0.4; }
.empty p { font-size: 14px; }

.dispute-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 20px 24px; margin-bottom: 12px;
    cursor: pointer; transition: border-color 0.15s, box-shadow 0.15s;
}
.dispute-card:hover {
    border-color: rgba(230,57,70,0.4);
    box-shadow: 0 2px 12px rgba(0,0,0,0.15);
}
.open-arrow { color: var(--text-dim); font-size: 14px; }
.dispute-card:hover .open-arrow { color: var(--red); }

.submission-context {
    display: flex; align-items: center; gap: 6px;
    font-size: 12px; color: var(--text-dim);
    margin-bottom: 10px;
}
.ctx-sep { opacity: 0.5; }
.ctx-question { color: var(--text-muted); font-weight: 500; }
.lang-chip { font-family: monospace; font-size: 10px; background: var(--surface2); padding: 1px 6px; border-radius: 4px; color: var(--text-dim); }
.dispute-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.dispute-meta { display: flex; align-items: center; gap: 12px; }
.student-link { font-weight: 700; color: var(--red); text-decoration: none; font-size: 15px; }
.student-link:hover { text-decoration: underline; }
.flag-ref { font-size: 12px; background: var(--surface2); padding: 2px 8px; border-radius: 4px; color: var(--text-dim); font-family: monospace; }
.time-ago { font-size: 12px; color: var(--text-dim); }

.flag-context { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 10px; }
.ctx-item { font-size: 12px; color: var(--text-dim); }
.ctx-item strong { color: var(--text); }
.text-red  { color: var(--red) !important; }
.text-warn { color: #f59e0b !important; }
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
    background: rgba(34,197,94,0.1); border: 1px solid rgba(34,197,94,0.3);
    border-radius: var(--radius-sm); color: #22c55e; cursor: pointer;
    transition: all 0.15s;
}
.btn-dismiss:hover { background: rgba(34,197,94,0.2); }
.btn-escalate {
    padding: 8px 20px; font-size: 13px; font-weight: 600;
    background: var(--red-dim); border: 1px solid rgba(230,57,70,0.3);
    border-radius: var(--radius-sm); color: var(--red); cursor: pointer;
    transition: all 0.15s;
}
.btn-escalate:hover { background: rgba(230,57,70,0.2); }

.badge { display: inline-block; padding: 3px 10px; border-radius: 4px; font-size: 12px; font-weight: 600; }
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-yellow { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-red    { background: rgba(230,57,70,0.12);  color: var(--red); }
</style>
