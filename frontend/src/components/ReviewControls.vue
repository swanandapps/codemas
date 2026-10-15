<template>
    <div class="review-controls">
        <div class="actions">
            <input
                v-model="note"
                :aria-label="noteLabel"
                :disabled="busy"
                placeholder="Note to the student, shown on their results (optional)"
            />
            <button type="button" class="confirm-btn" :disabled="busy" @click="emit('decide', 'confirmed')">Confirm</button>
            <button type="button" class="dismiss-btn" :disabled="busy" @click="emit('decide', 'dismissed')">Dismiss</button>
        </div>
        <p class="decision-caption">Nothing is decided until you confirm.</p>
    </div>
</template>

<script setup lang="ts">
// Note + Confirm / Dismiss for one flag, used per flag on the exam case file;
// the parent sends the decision to the flag's review endpoint.
withDefaults(defineProps<{ busy?: boolean; noteLabel?: string }>(), {
    busy: false,
    noteLabel: 'Note to the student',
})
const note = defineModel<string>('note', { default: '' })
const emit = defineEmits<{ decide: [decision: 'confirmed' | 'dismissed'] }>()
</script>

<style scoped>
.actions { display: flex; gap: 8px; align-items: center; margin-top: 12px; flex-wrap: wrap; }
.actions input { flex: 1 1 220px; min-height: 44px; }
.decision-caption { font-size: 11px; color: var(--text-dim); margin-top: 6px; }
.confirm-btn, .dismiss-btn {
    min-height: 44px;
    padding: 7px 16px;
    border-radius: var(--radius-pill);
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
    white-space: nowrap;
    transition: all 0.15s;
}
.confirm-btn { background: var(--surface); border: 1px solid var(--red); color: var(--red-ink); }
.confirm-btn:hover { background: var(--red-dim); }
.dismiss-btn { background: var(--surface); border: 1px solid var(--border2); color: var(--text); }
.dismiss-btn:hover { background: var(--surface2); }
.confirm-btn:disabled, .dismiss-btn:disabled { opacity: 0.6; cursor: default; }
</style>
