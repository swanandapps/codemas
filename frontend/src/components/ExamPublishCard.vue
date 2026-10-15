<template>
    <!-- Publish controls for a draft (or scheduled) exam, on the exam report -->
    <div class="publish-card">
        <div class="publish-row">
            <div>
                <div class="publish-title">This exam is a draft</div>
                <div class="publish-sub">Activate it and every student in {{ audienceLabel }} sees it right away.</div>
            </div>
            <button class="publish-btn activate" :disabled="publishing || !loaded" @click="activate">
                {{ publishing ? '…' : 'Activate now' }}
            </button>
        </div>

        <div v-if="sections.length" class="audience-row">
            <span class="field-label" id="audience-label">Who takes it</span>
            <div class="chips" role="group" aria-labelledby="audience-label">
                <button type="button" :class="['chip', { on: !picked.length }]" :aria-pressed="!picked.length" @click="picked = []">
                    Whole cohort · {{ totalStudents }}
                </button>
                <button
                    v-for="sec in sections" :key="sec.name" type="button"
                    :class="['chip', { on: picked.includes(sec.name) }]" :aria-pressed="picked.includes(sec.name)"
                    @click="toggleSection(sec.name)"
                >{{ sec.name }} · {{ sec.students }}</button>
            </div>
        </div>

        <div class="schedule-row">
            <div class="sched-field">
                <label for="sched-start">Opens at (optional)</label>
                <input id="sched-start" type="datetime-local" v-model="schedule.start" />
            </div>
            <div class="sched-field">
                <label for="sched-end">Closes at (optional)</label>
                <input id="sched-end" type="datetime-local" v-model="schedule.end" />
            </div>
            <button class="sched-btn" :disabled="publishing || !loaded" @click="saveSchedule">Save schedule</button>
        </div>
        <p class="sched-hint">With a schedule set, the exam auto-opens and auto-closes at those times.</p>
        <p v-if="publishError" class="publish-error" role="alert">{{ publishError }}</p>
    </div>
</template>

<script setup lang="ts">
// Same requests and rules as the exam page's publish card had: going live enrolls the
// audience; the server decides the status, so the parent reloads after each change.
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { toLocalInput } from '../utils/exams'

const props = defineProps<{ examId: number | string; notice?: string }>()
const emit = defineEmits<{ changed: [] }>()

interface Section { name: string; students: number }

const loaded = ref(false)
const isActive = ref(false)
const publishing = ref(false)
// Create exam's "saved, but couldn't go live / schedule" message shows here first
const publishError = ref(props.notice ?? '')
const schedule = ref<{ start: string; end: string }>({ start: '', end: '' })

// Audience: no sections picked = the whole cohort
const sections = ref<Section[]>([])
const picked = ref<string[]>([])
const totalStudents = computed(() => sections.value.reduce((n, s) => n + s.students, 0))
const audienceLabel = computed(() => picked.value.length ? picked.value.join(', ') : 'the whole cohort')

function toggleSection(name: string): void {
    picked.value = picked.value.includes(name) ? picked.value.filter(n => n !== name) : [...picked.value, name].sort()
}

const localInput = (iso: string | null) => iso ? toLocalInput(new Date(iso)) : ''

onMounted(async () => {
    try {
        const [res, secRes] = await Promise.all([
            api.get(`/exams/${props.examId}/`),
            api.get('/exams/sections/').catch(() => null),
        ])
        isActive.value = !!res.data.is_active
        schedule.value = { start: localInput(res.data.start_time), end: localInput(res.data.end_time) }
        picked.value = res.data.sections ?? []
        sections.value = Array.isArray(secRes?.data) ? secRes.data : []
        loaded.value = true
    } catch (e: any) {
        publishError.value = e.response?.data?.error || 'Failed to load exam'
    }
})

async function activate(): Promise<void> {
    publishing.value = true
    publishError.value = ''
    try {
        await api.patch(`/exams/${props.examId}/`, { is_active: true, sections: picked.value })
        emit('changed')
    } catch (e: any) {
        publishError.value = e.response?.data?.error || 'Failed to update exam'
    } finally {
        publishing.value = false
    }
}

async function saveSchedule(): Promise<void> {
    publishing.value = true
    publishError.value = ''
    try {
        await api.patch(`/exams/${props.examId}/`, {
            start_time: schedule.value.start ? new Date(schedule.value.start).toISOString() : null,
            end_time: schedule.value.end ? new Date(schedule.value.end).toISOString() : null,
            ...(isActive.value ? {} : { sections: picked.value }),
        })
        emit('changed')
    } catch (e: any) {
        publishError.value = e.response?.data?.error || 'Failed to save schedule'
    } finally {
        publishing.value = false
    }
}
</script>

<style scoped>
.publish-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
    margin-bottom: 16px;
}
.publish-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.publish-title { font-size: 14px; font-weight: 700; color: var(--text); }
.publish-sub { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.publish-btn {
    padding: 9px 20px; min-height: 40px; border: none; border-radius: var(--radius-pill);
    font-family: var(--font-display);
    font-size: 13px; font-weight: 700; cursor: pointer; white-space: nowrap;
}
.publish-btn.activate { background: var(--accent); color: var(--accent-ink); }
.publish-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.schedule-row { display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end; margin-top: 16px; padding-top: 16px; border-top: 1px solid var(--border); }
.sched-field { display: flex; flex-direction: column; gap: 4px; }
.sched-field label, .field-label { font-size: 11px; font-weight: 600; color: var(--text-dim); }
.sched-field input {
    background: var(--surface2); border: 1px solid var(--border); color: var(--text);
    padding: 7px 10px; min-height: 40px; border-radius: var(--radius-sm); font-size: 13px;
}
.sched-btn {
    padding: 8px 16px; min-height: 40px; background: var(--surface2); border: 1px solid var(--border);
    color: var(--text-muted); border-radius: var(--radius-pill); font-size: 13px; cursor: pointer;
}
.sched-btn:hover { border-color: var(--border2); color: var(--text); }
.sched-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.audience-row { display: grid; gap: 6px; margin-top: 14px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { font: inherit; font-size: 12px; font-weight: 600; padding: 5px 12px; min-height: 32px; border-radius: var(--radius-pill); border: 1px solid var(--border); background: var(--surface); color: var(--text-muted); cursor: pointer; }
.chip.on { border-color: var(--red); background: var(--red-dim); color: var(--red-ink); }
.sched-hint { font-size: 11px; color: var(--text-dim); margin-top: 8px; }
.publish-error { font-size: 13px; color: var(--red-ink); margin-top: 8px; }

@media (max-width: 600px) {
    .publish-row { flex-wrap: wrap; }
    .publish-btn { width: 100%; }
    .schedule-row { flex-direction: column; align-items: stretch; }
    .sched-btn { width: 100%; }
}
</style>
