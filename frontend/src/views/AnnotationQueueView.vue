<template>
    <div class="queue-page" @keydown="handleKey" tabindex="0" ref="pageRef">
        <div class="page-header">
            <div>
                <h1>Annotation Queue</h1>
                <p class="page-sub">J/K to navigate · A to confirm · D to dismiss · keyboard-first review</p>
            </div>
            <div class="header-right">
                <span class="progress-chip">{{ reviewed }} / {{ total }} reviewed</span>
                <div class="progress-bar-wrap">
                    <div class="progress-bar-fill" :style="{ width: progressPct + '%' }" />
                </div>
            </div>
        </div>

        <div class="queue-layout">
            <!-- Left: list of pending flags -->
            <div class="queue-list">
                <div class="list-header">Pending ({{ pendingFlags.length }})</div>
                <div
                    v-for="(flag, i) in pendingFlags"
                    :key="flag.id"
                    :class="['queue-item', currentIndex === i ? 'selected' : '']"
                    @click="currentIndex = i"
                >
                    <div class="qi-top">
                        <span class="qi-student">{{ flag.student }}</span>
                        <span :class="['qi-conf', flag.confidence]">{{ flag.confidence }}</span>
                    </div>
                    <div class="qi-question">{{ flag.question_title }}</div>
                    <div class="qi-risk">{{ (flag.risk_score * 100).toFixed(0) }}% risk</div>
                </div>
                <div v-if="pendingFlags.length === 0" class="empty-list">
                    All flags reviewed
                </div>
            </div>

            <!-- Right: detail panel for selected flag -->
            <div class="detail-panel" v-if="currentFlag">
                <!-- ML Confidence Explainer -->
                <div class="explainer-card">
                    <div class="explainer-header">
                        <div>
                            <div class="explainer-student">{{ currentFlag.student }}</div>
                            <div class="explainer-question">{{ currentFlag.question_title }} · {{ currentFlag.exam_title }}</div>
                        </div>
                        <div class="explainer-badges">
                            <span :class="['conf-badge', currentFlag.confidence]">{{ currentFlag.confidence }} confidence</span>
                            <span :class="['risk-badge', riskClass(currentFlag.risk_score)]">
                                {{ (currentFlag.risk_score * 100).toFixed(0) }}% risk
                            </span>
                        </div>
                    </div>

                    <div class="why-label">Why was this flagged?</div>

                    <div class="signal-grid">
                        <div v-for="s in signalBreakdown" :key="s.label" class="signal-block">
                            <div class="signal-top">
                                <span class="signal-name">{{ s.label }}</span>
                                <span class="signal-weight">{{ s.weight * 100 }}% weight</span>
                            </div>
                            <div class="signal-bar-track">
                                <div
                                    class="signal-bar-fill"
                                    :style="{ width: (s.score * 100) + '%' }"
                                    :class="barClass(s.score)"
                                />
                            </div>
                            <div class="signal-bottom">
                                <span class="signal-score-val">{{ (s.score * 100).toFixed(0) }}%</span>
                                <span class="signal-contribution">
                                    contributes {{ (s.score * s.weight * 100).toFixed(1) }}% to total
                                </span>
                            </div>
                        </div>
                    </div>

                    <div class="triggered-signals" v-if="currentFlag.signals_triggered.length">
                        <div class="why-label" style="margin-top:16px">Triggered signals</div>
                        <div class="chips-row">
                            <span v-for="s in currentFlag.signals_triggered" :key="s" class="signal-chip">{{ s }}</span>
                        </div>
                    </div>
                </div>

                <!-- Review actions -->
                <div class="action-card">
                    <input
                        v-model="currentNote"
                        placeholder="Add review note (optional) — press A to confirm, D to dismiss"
                        class="note-input"
                    />
                    <div class="action-row">
                        <button class="btn-confirm" @click="doReview('confirmed')" :disabled="reviewing">
                            <span class="kbd">A</span> Confirm
                        </button>
                        <button class="btn-dismiss" @click="doReview('dismissed')" :disabled="reviewing">
                            <span class="kbd">D</span> Dismiss
                        </button>
                    </div>
                </div>
            </div>

            <div v-else class="detail-panel empty-detail">
                <p>Select a flag from the list or start pressing J/K to navigate</p>
            </div>
        </div>

        <!-- Completed section -->
        <div v-if="completedFlags.length > 0" class="completed-section">
            <div class="completed-header" @click="showCompleted = !showCompleted">
                Reviewed ({{ completedFlags.length }})
                <svg :style="{ transform: showCompleted ? 'rotate(180deg)' : '' }" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
            </div>
            <div v-if="showCompleted" class="completed-list">
                <div v-for="flag in completedFlags" :key="flag.id" class="completed-row">
                    <span class="cr-student">{{ flag.student }}</span>
                    <span class="cr-question">{{ flag.question_title }}</span>
                    <span :class="['cr-status', flag.review_status]">{{ flag.review_status }}</span>
                    <span class="cr-note" v-if="flag.review_note">{{ flag.review_note }}</span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import api from '../api'

interface BehaviouralFlag {
    id: number
    student: string
    question_title: string
    exam_title: string
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

const flags = ref<BehaviouralFlag[]>([])
const currentIndex = ref<number>(0)
const currentNote = ref<string>('')
const reviewing = ref<boolean>(false)
const showCompleted = ref<boolean>(false)
const pageRef = ref<HTMLElement | null>(null)

const pendingFlags = computed(() => flags.value.filter(f => f.review_status === 'pending'))
const completedFlags = computed(() => flags.value.filter(f => f.review_status !== 'pending'))
const currentFlag = computed<BehaviouralFlag | null>(() => pendingFlags.value[currentIndex.value] ?? null)

const total = computed(() => flags.value.length)
const reviewed = computed(() => completedFlags.value.length)
const progressPct = computed(() => total.value ? Math.round(reviewed.value / total.value * 100) : 0)

const signalBreakdown = computed(() => {
    if (!currentFlag.value) return []
    return [
        { label: 'Paste', score: currentFlag.value.paste_score, weight: 0.40 },
        { label: 'Time', score: currentFlag.value.time_score, weight: 0.30 },
        { label: 'Tab Switches', score: currentFlag.value.snapshot_score, weight: 0.15 },
        { label: 'Submission Surprise', score: currentFlag.value.submission_score, weight: 0.15 },
    ]
})

function riskClass(score: number) {
    return score >= 0.7 ? 'high' : score >= 0.4 ? 'medium' : 'low'
}
function barClass(score: number) {
    return score >= 0.7 ? 'bar-high' : score >= 0.4 ? 'bar-medium' : 'bar-low'
}

onMounted(async () => {
    const res = await api.get('/plagiarism/behavioural/')
    flags.value = res.data
    await nextTick()
    pageRef.value?.focus()
})

function handleKey(e: KeyboardEvent) {
    if (e.target instanceof HTMLInputElement) return
    if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault()
        if (currentIndex.value < pendingFlags.value.length - 1) currentIndex.value++
    } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault()
        if (currentIndex.value > 0) currentIndex.value--
    } else if (e.key === 'a') {
        doReview('confirmed')
    } else if (e.key === 'd') {
        doReview('dismissed')
    }
}

async function doReview(decision: string) {
    if (!currentFlag.value || reviewing.value) return
    reviewing.value = true
    try {
        const res = await api.patch(`/plagiarism/behavioural/${currentFlag.value.id}/review/`, {
            review_status: decision,
            review_note: currentNote.value,
        })
        const idx = flags.value.findIndex(f => f.id === currentFlag.value!.id)
        if (idx !== -1) flags.value[idx] = res.data
        currentNote.value = ''
        // keep index in range
        if (currentIndex.value >= pendingFlags.value.length) {
            currentIndex.value = Math.max(0, pendingFlags.value.length - 1)
        }
    } finally {
        reviewing.value = false
    }
}
</script>

<style scoped>
.queue-page {
    outline: none;
}
.page-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 28px;
}
.page-sub { color: var(--text-dim); font-size: 13px; margin-top: 4px; font-family: monospace; }
.header-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
.progress-chip {
    font-size: 13px;
    color: var(--text-muted);
    background: var(--surface2);
    padding: 4px 12px;
    border-radius: 12px;
    border: 1px solid var(--border);
}
.progress-bar-wrap {
    width: 160px;
    height: 4px;
    background: var(--surface3);
    border-radius: 2px;
    overflow: hidden;
}
.progress-bar-fill { height: 100%; background: var(--green); border-radius: 2px; transition: width 0.3s; }

.queue-layout { display: flex; gap: 20px; min-height: 500px; }

.queue-list {
    width: 280px;
    flex-shrink: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
}
.list-header {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    padding: 0 8px;
    margin-bottom: 6px;
}
.queue-item {
    padding: 12px 14px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--surface);
    cursor: pointer;
    transition: all 0.15s;
}
.queue-item:hover { border-color: var(--border2); }
.queue-item.selected { border-color: var(--red); background: var(--red-dim); }
.qi-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.qi-student { font-weight: 600; font-size: 13px; color: var(--text); }
.qi-conf { font-size: 10px; font-weight: 700; text-transform: uppercase; padding: 2px 7px; border-radius: 10px; }
.qi-conf.high { background: var(--red-dim); color: var(--red); }
.qi-conf.medium { background: rgba(241,196,15,0.12); color: var(--yellow); }
.qi-conf.low { background: rgba(52,152,219,0.12); color: var(--blue); }
.qi-question { font-size: 12px; color: var(--text-muted); margin-bottom: 2px; }
.qi-risk { font-size: 11px; color: var(--text-dim); }
.empty-list { padding: 20px 8px; color: var(--text-dim); font-size: 13px; }

.detail-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 16px;
}
.detail-panel.empty-detail {
    justify-content: center;
    align-items: center;
    color: var(--text-dim);
    font-size: 14px;
    background: var(--surface);
    border-radius: var(--radius);
    border: 1px solid var(--border);
}

.explainer-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
}
.explainer-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.explainer-student { font-size: 18px; font-weight: 700; color: var(--text); }
.explainer-question { font-size: 13px; color: var(--text-muted); margin-top: 4px; }
.explainer-badges { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }
.conf-badge, .risk-badge {
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
}
.conf-badge.high, .risk-badge.high { background: var(--red-dim); color: var(--red); }
.conf-badge.medium, .risk-badge.medium { background: rgba(241,196,15,0.12); color: var(--yellow); }
.conf-badge.low, .risk-badge.low { background: rgba(52,152,219,0.12); color: var(--blue); }

.why-label { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--text-dim); margin-bottom: 12px; }

.signal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.signal-block {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    padding: 14px;
}
.signal-top { display: flex; justify-content: space-between; margin-bottom: 10px; }
.signal-name { font-size: 13px; font-weight: 600; color: var(--text); }
.signal-weight { font-size: 11px; color: var(--text-dim); }
.signal-bar-track { height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; margin-bottom: 8px; }
.signal-bar-fill { height: 100%; border-radius: 3px; transition: width 0.4s; }
.signal-bar-fill.bar-high { background: var(--red); }
.signal-bar-fill.bar-medium { background: var(--yellow); }
.signal-bar-fill.bar-low { background: var(--green); }
.signal-bottom { display: flex; justify-content: space-between; }
.signal-score-val { font-size: 14px; font-weight: 700; color: var(--text); }
.signal-contribution { font-size: 11px; color: var(--text-dim); }

.chips-row { display: flex; flex-wrap: wrap; gap: 6px; }
.signal-chip {
    padding: 5px 12px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 12px;
    color: var(--text-muted);
}

.action-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 12px;
}
.note-input { width: 100%; }
.action-row { display: flex; gap: 12px; }
.btn-confirm, .btn-dismiss {
    flex: 1;
    padding: 11px;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: opacity 0.15s;
}
.btn-confirm { background: var(--red); color: white; }
.btn-confirm:hover:not(:disabled) { opacity: 0.85; }
.btn-dismiss { background: rgba(46,204,113,0.15); color: var(--green); border: 1px solid rgba(46,204,113,0.3); }
.btn-dismiss:hover:not(:disabled) { background: rgba(46,204,113,0.25); }
.btn-confirm:disabled, .btn-dismiss:disabled { opacity: 0.5; cursor: not-allowed; }
.kbd {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    background: rgba(255,255,255,0.15);
    border-radius: 4px;
    font-size: 11px;
    font-weight: 800;
    font-family: monospace;
}

.completed-section { margin-top: 32px; }
.completed-header {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--text-muted);
    cursor: pointer;
    padding: 10px 0;
    border-top: 1px solid var(--border);
}
.completed-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.completed-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 14px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 13px;
}
.cr-student { font-weight: 600; color: var(--text); }
.cr-question { color: var(--text-muted); flex: 1; }
.cr-status {
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
}
.cr-status.confirmed { background: var(--red-dim); color: var(--red); }
.cr-status.dismissed { background: rgba(46,204,113,0.12); color: var(--green); }
.cr-note { font-size: 12px; color: var(--text-dim); font-style: italic; }
</style>
