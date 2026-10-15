<template>
    <!-- What happens on save: go live, schedule or keep as a draft, and who takes it.
         Same fields and meaning as the exam report's publish card (ExamPublishCard). -->
    <div class="publish" :class="{ compact }">
        <fieldset class="pub-field">
            <legend class="pub-label">When</legend>
            <div class="when-options">
                <label v-for="o in OPTIONS" :key="o.value" class="when-opt">
                    <input v-model="when" type="radio" :name="`${idPrefix}-when`" :value="o.value" />
                    <span>{{ o.label }}</span>
                </label>
            </div>
        </fieldset>

        <div v-if="when === 'schedule'" class="sched">
            <div class="pub-field">
                <label :for="`${idPrefix}-start`" class="pub-label">Opens at</label>
                <input
                    :id="`${idPrefix}-start`" v-model="start" type="datetime-local"
                    :aria-invalid="!!problems.start" :aria-describedby="problems.start ? `${idPrefix}-start-err` : undefined"
                />
                <p v-if="problems.start" :id="`${idPrefix}-start-err`" class="field-error">{{ problems.start }}</p>
            </div>
            <div class="pub-field">
                <label :for="`${idPrefix}-end`" class="pub-label">Closes at (optional)</label>
                <input
                    :id="`${idPrefix}-end`" v-model="end" type="datetime-local"
                    :aria-invalid="!!problems.end" :aria-describedby="problems.end ? `${idPrefix}-end-err` : undefined"
                />
                <p v-if="problems.end" :id="`${idPrefix}-end-err`" class="field-error">{{ problems.end }}</p>
            </div>
        </div>

        <!-- No sections picked = the whole cohort -->
        <div v-if="sections.length" class="pub-field">
            <span :id="`${idPrefix}-who`" class="pub-label">Who takes it</span>
            <div class="chips" role="group" :aria-labelledby="`${idPrefix}-who`">
                <button type="button" :class="['pick', { on: !picked.length }]" :aria-pressed="!picked.length" @click="picked = []">
                    Whole cohort · {{ totalStudents }}
                </button>
                <button
                    v-for="sec in sections" :key="sec.name" type="button"
                    :class="['pick', { on: picked.includes(sec.name) }]" :aria-pressed="picked.includes(sec.name)"
                    @click="toggleSection(sec.name)"
                >{{ sec.name }} · {{ sec.students }}</button>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScheduleProblems } from '../utils/exams'

export type PublishWhen = 'live' | 'schedule' | 'draft'

const props = defineProps<{
    idPrefix: string
    sections: { name: string; students: number }[]
    problems: ScheduleProblems
    compact?: boolean
}>()
const when = defineModel<PublishWhen>('when', { required: true })
const start = defineModel<string>('start', { required: true })
const end = defineModel<string>('end', { required: true })
const picked = defineModel<string[]>('picked', { required: true })

const OPTIONS: { value: PublishWhen; label: string }[] = [
    { value: 'live', label: 'Go live now' },
    { value: 'schedule', label: 'Schedule' },
    { value: 'draft', label: 'Save as draft' },
]

const totalStudents = computed(() => props.sections.reduce((n, s) => n + s.students, 0))

function toggleSection(name: string): void {
    picked.value = picked.value.includes(name) ? picked.value.filter(n => n !== name) : [...picked.value, name].sort()
}

</script>

<style scoped>
.publish { display: flex; flex-direction: column; gap: 14px; }
.pub-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; border: 0; padding: 0; margin: 0; }
.pub-label { font-family: var(--font-display); font-size: var(--fs-sm); font-weight: 600; color: var(--text); padding: 0; }

.when-options { display: flex; flex-direction: column; gap: 6px; }
.when-opt {
    display: flex; align-items: center; gap: 10px; min-height: 44px; padding: 0 12px;
    border: 1px solid var(--border2); border-radius: var(--radius-sm); background: var(--surface);
    font-family: var(--font-display); font-size: 14px; font-weight: 500; color: var(--text-muted); cursor: pointer;
}
.when-opt:hover { border-color: var(--text-dim); color: var(--text); }
.when-opt:has(input:checked) { border-color: var(--accent); background: var(--accent-tint); color: var(--red-ink); font-weight: 600; }
.when-opt input { width: 18px; height: 18px; padding: 0; margin: 0; accent-color: var(--accent); flex-shrink: 0; cursor: pointer; }
.when-opt:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }

.sched { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; }
.field-error { margin: 0; font-size: var(--fs-sm); color: var(--red-ink); }
input[aria-invalid="true"] { border-color: var(--red); }

.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.pick {
    min-height: 44px; padding: 0 14px; border-radius: var(--radius-pill);
    border: 1px solid var(--border2); background: var(--surface);
    font-size: var(--fs-sm); font-weight: 600; color: var(--text-muted);
}
.pick:hover { color: var(--text); border-color: var(--text-dim); }
.pick.on { border-color: var(--red); background: var(--red-dim); color: var(--red-ink); }

/* Compact: one row in the editor's top bar */
.compact { flex-direction: row; flex-wrap: wrap; align-items: flex-start; gap: 12px 20px; }
.compact .when-options { flex-direction: row; flex-wrap: wrap; }
.compact .sched { grid-template-columns: repeat(2, minmax(0, 220px)); }

@media (max-width: 600px) {
    .compact > * { width: 100%; }
    .compact .when-options { flex-direction: column; }
    .compact .sched { grid-template-columns: minmax(0, 1fr); }
}
</style>
