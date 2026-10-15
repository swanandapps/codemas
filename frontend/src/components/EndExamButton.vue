<template>
    <div class="end-exam">
        <button type="button" class="end-btn" :disabled="ending" @click="confirming = true">
            {{ ending ? 'Ending…' : 'End exam' }}
        </button>
        <p v-if="error" class="end-error" role="alert">{{ error }}</p>

        <div v-if="confirming" class="dialog-backdrop" @click.self="confirming = false" @keydown.esc="confirming = false">
            <div class="dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
                <h2 :id="titleId">End this exam?</h2>
                <p>Students can't submit after this, and the plagiarism check starts. You can't undo it.</p>
                <div class="dialog-actions">
                    <button type="button" class="dialog-cancel" @click="confirming = false" autofocus>Keep it running</button>
                    <button type="button" class="dialog-confirm" @click="endExam">End exam</button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
// The one "End exam", on the trainer's exam report: a confirmation, then the call that
// closes the exam.
import { ref } from 'vue'
import api from '../api'

const props = defineProps<{ examId: number | string }>()
const emit = defineEmits<{ ended: [] }>()

const confirming = ref(false)
const ending = ref(false)
const error = ref('')
const titleId = `end-exam-title-${props.examId}`

async function endExam(): Promise<void> {
    confirming.value = false
    ending.value = true
    error.value = ''
    try {
        await api.patch(`/exams/${props.examId}/`, { is_active: false })  // closing starts the plagiarism checks
        emit('ended')
    } catch {
        error.value = "Couldn't end the exam. Try again."
    } finally {
        ending.value = false
    }
}
</script>

<style scoped>
.end-btn {
    min-height: 40px;
    padding: 0 20px; font-size: 14px; font-weight: 600;
    font-family: var(--font-display);
    background: var(--red); border: none;
    border-radius: var(--radius-pill); color: #fff; cursor: pointer;
    transition: opacity 0.15s;
}
.end-btn:hover { opacity: 0.85; }
.end-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.end-error { margin: 8px 0 0; color: var(--red-ink); font-size: 14px; }
.dialog-backdrop {
    position: fixed; inset: 0; z-index: 200;
    background: rgba(33, 25, 27, 0.4);
    display: flex; align-items: center; justify-content: center; padding: 16px;
}
.dialog {
    width: 100%; max-width: 420px;
    background: var(--surface); border-radius: var(--radius-lg); padding: 28px;
    box-shadow: var(--shadow-lg);
    display: flex; flex-direction: column; gap: 12px;
    text-align: left;
}
.dialog h2 { margin: 0; font-size: 20px; }
.dialog p { margin: 0; color: var(--text-muted); line-height: 1.6; font-size: 14px; }
.dialog-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; flex-wrap: wrap; }
.dialog-cancel {
    min-height: 44px; padding: 0 20px; border-radius: var(--radius-pill);
    background: var(--surface); border: 1px solid var(--border2); color: var(--text);
    font-family: var(--font-display); font-weight: 500; font-size: 14px; cursor: pointer;
}
.dialog-confirm {
    min-height: 44px; padding: 0 20px; border-radius: var(--radius-pill); border: none;
    background: var(--accent); color: var(--accent-ink);
    font-family: var(--font-display); font-weight: 600; font-size: 14px; cursor: pointer;
}
.dialog-confirm:hover { background: var(--accent-hover); }
</style>
