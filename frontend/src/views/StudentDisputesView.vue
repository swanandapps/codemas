<template>
    <div class="disputes-page">
        <h1>Disputes</h1>
        <p class="sub">Your responses to plagiarism decisions, and how your trainer ruled. Each decision can be appealed once.</p>

        <div v-if="loading" class="loading">Loading...</div>
        <p v-else-if="error" class="error" role="alert">{{ error }}</p>

        <div v-else-if="appeals.length === 0" class="empty">
            <p class="empty-title">You haven't disputed any decisions.</p>
            <p class="empty-hint">If your trainer confirms plagiarism on an exam, you can respond to the decision from My results.</p>
        </div>

        <!-- newest first: one card per appeal, the ruling visible, the rest behind the toggle -->
        <template v-else>
            <article v-for="a in appeals" :id="`appeal-${a.id}`" :key="a.id" class="appeal-row" :class="{ open: open[a.id] }">
                <button
                    type="button"
                    class="appeal-toggle"
                    :aria-expanded="!!open[a.id]"
                    :aria-controls="`appeal-body-${a.id}`"
                    @click="open[a.id] = !open[a.id]"
                >
                    <span class="appeal-title">
                        <span class="appeal-exam">{{ a.exam_title ?? 'An earlier exam' }}</span>
                        <small>Filed {{ formatDateTime(a.created_at) }}</small>
                    </span>
                    <span v-if="a.is_new" class="pill new">New</span>
                    <span :class="['pill', a.status]">{{ STUDENT_APPEAL_STATUS[a.status] }}</span>
                    <svg class="chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="9 18 15 12 9 6" /></svg>
                </button>
                <p v-if="a.status !== 'open' && a.resolution_note" class="reply">
                    <span class="label">Your trainer replied</span> “{{ a.resolution_note }}”
                </p>

                <div v-if="open[a.id]" :id="`appeal-body-${a.id}`" class="appeal-body">
                    <div class="part">
                        <span class="label">Your trainer's decision</span>
                        <p class="quote">{{ a.decision_note ? `“${a.decision_note}”` : 'Plagiarism confirmed. No note was left.' }}</p>
                    </div>
                    <div class="part">
                        <span class="label">Your response · {{ formatDate(a.created_at) }}</span>
                        <p class="quote">“{{ a.student_note }}”</p>
                    </div>
                    <div class="part">
                        <span class="label">Ruling<template v-if="a.resolved_at"> · {{ formatDate(a.resolved_at) }}</template></span>
                        <p v-if="a.status === 'open'" class="quote muted">Your trainer hasn't ruled yet.</p>
                        <p v-else class="quote">{{ STUDENT_APPEAL_STATUS[a.status] }}<template v-if="a.resolution_note">: “{{ a.resolution_note }}”</template></p>
                    </div>
                    <router-link v-if="a.exam_id" :to="`/results?exam=${a.exam_id}`" class="to-results">View in My results →</router-link>
                </div>
            </article>
        </template>
    </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'
import { formatDate, formatDateTime } from '../utils/format'
import { STUDENT_APPEAL_STATUS, type MyAppeal } from '../utils/appeals'
import { markIntegritySeen } from '../utils/attention'

const route = useRoute()
const loading = ref(true)
const error = ref('')
const appeals = ref<MyAppeal[]>([])
const open = ref<Record<number, boolean>>({})

onMounted(async () => {
    try {
        const res = await api.get('/support/disputes/mine/')
        appeals.value = Array.isArray(res.data) ? res.data : []
    } catch {
        error.value = "Couldn't load your disputes. Try again."
    } finally {
        loading.value = false
    }
    // after the list arrived (its "New" marks are relative to the last visit): this visit sees them
    markIntegritySeen()

    // ?appeal=<id> (the Home banner): open that one and bring it into view
    const id = Number(route.query.appeal)
    if (id && appeals.value.some(a => a.id === id)) {
        open.value[id] = true
        await nextTick()
        document.getElementById(`appeal-${id}`)?.scrollIntoView({ block: 'start' })
    }
})
</script>

<style scoped>
.disputes-page { max-width: 760px; }
h1 { margin-bottom: 6px; }
.sub { margin: 0 0 24px; font-size: 14px; color: var(--text-muted); max-width: 64ch; }
.loading { color: var(--text-muted); }
.error { color: var(--red-ink); }

.empty { padding: 32px 24px; border: 1px dashed var(--border2); border-radius: var(--radius); text-align: center; }
.empty-title { margin: 0 0 6px; font-family: var(--font-display); font-size: 16px; font-weight: 600; color: var(--text); }
.empty-hint { margin: 0; font-size: 13px; color: var(--text-muted); }

.appeal-row { border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface); margin-bottom: 12px; overflow: hidden; }
.appeal-toggle {
    display: flex; flex-wrap: wrap; align-items: center; gap: 8px 12px;
    width: 100%; min-height: 56px; padding: 12px 18px;
    border: 0; background: var(--surface2); font: inherit; color: inherit; text-align: left; cursor: pointer;
}
.appeal-toggle:hover { background: var(--surface3); }
.appeal-toggle:focus-visible { outline: 2px solid var(--red); outline-offset: -2px; }
.appeal-title { display: grid; flex: 1; min-width: 160px; }
.appeal-exam { font-family: var(--font-display); font-size: 16px; font-weight: 600; color: var(--text); overflow-wrap: anywhere; }
.appeal-title small { font-size: 12px; color: var(--text-dim); }
.pill { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: var(--radius-pill); white-space: nowrap; }
.pill.open { background: var(--yellow-dim); color: var(--amber-ink); }
.pill.upheld { background: var(--surface); border: 1px solid var(--border); color: var(--text-muted); }
.pill.overturned { background: var(--green-dim); color: var(--green-ink); }
.pill.new { background: var(--red); color: #fff; }
.chev { width: 16px; height: 16px; flex: none; color: var(--text-dim); transition: transform 0.2s; }
.appeal-row.open .chev { transform: rotate(90deg); }
@media (prefers-reduced-motion: reduce) { .chev { transition: none; } }

.reply { margin: 0; padding: 10px 18px; font-size: 14px; color: var(--text); border-top: 1px solid var(--border); overflow-wrap: anywhere; }
.label { display: block; font-size: 12px; font-weight: 600; letter-spacing: 0.04em; color: var(--text-muted); margin-bottom: 2px; }
.reply .label { display: inline; margin-right: 4px; }

.appeal-body { display: grid; gap: 12px; padding: 14px 18px 16px; border-top: 1px solid var(--border); }
.part { display: grid; }
.quote { margin: 0; font-size: 14px; line-height: 1.55; color: var(--text); white-space: pre-wrap; overflow-wrap: anywhere; }
.quote.muted { color: var(--text-muted); font-style: italic; }
.to-results { justify-self: start; display: inline-flex; align-items: center; min-height: 44px; font-weight: 600; }
</style>
