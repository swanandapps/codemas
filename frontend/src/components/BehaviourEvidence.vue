<template>
    <div class="behaviour-evidence">
        <!-- Signal chips -->
        <div class="signals-row">
            <div v-for="signal in flag.signals_triggered" :key="signal" class="signal-chip">{{ signal }}</div>
            <div v-if="flag.signals_triggered.length === 0" class="signal-chip muted">No strong signals</div>
        </div>

        <!-- Score bars -->
        <div class="score-bars">
            <div v-for="bar in bars" :key="bar.label" class="score-bar-row">
                <span class="score-label">{{ bar.label }}</span>
                <div class="score-track"><div class="score-fill" :style="{ width: (bar.value * 100) + '%' }"/></div>
                <span class="score-val">{{ (bar.value * 100).toFixed(0) }}%</span>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
// The evidence of one behavioural flag — what fired and the four signal scores. Used on
// the exam case file.
import { computed } from 'vue'

const props = defineProps<{
    flag: {
        signals_triggered: string[]
        paste_score: number
        time_score: number
        snapshot_score: number
        submission_score: number
    }
}>()

const bars = computed(() => [
    { label: 'Paste', value: props.flag.paste_score },
    { label: 'Time', value: props.flag.time_score },
    { label: 'Tab switches', value: props.flag.snapshot_score },
    { label: 'Resubmission', value: props.flag.submission_score },
])
</script>

<style scoped>
/* Triggered signal pills */
.signals-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.signal-chip {
    padding: 4px 10px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 12px;
    font-size: 11px;
    color: var(--text-muted);
}
.signal-chip.muted { color: var(--text-dim); border-style: dashed; }

/* Four-signal breakdown bars */
.score-bars { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.score-bar-row { display: flex; align-items: center; gap: 8px; }
.score-label { font-size: 11px; color: var(--text-dim); width: 72px; flex-shrink: 0; }
.score-track { flex: 1; height: 4px; background: var(--surface3); border-radius: 2px; overflow: hidden; }
.score-fill { height: 100%; background: var(--red); border-radius: 2px; }
.score-val { font-size: 11px; color: var(--text-muted); width: 32px; text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
</style>
