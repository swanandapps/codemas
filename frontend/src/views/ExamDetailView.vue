<template>
    <div class="detail-page">
        <button class="back-btn" @click="router.back()">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="14" height="14"><polyline points="15 18 9 12 15 6"/></svg>
            Back
        </button>

        <div v-if="loading" class="state-msg">Loading exam...</div>
        <div v-else-if="error" class="state-msg error">{{ error }}</div>

        <template v-else-if="exam">
            <div class="exam-hero">
                <div class="hero-left">
                    <div class="exam-title-row">
                        <h1>{{ exam.title }}</h1>
                        <span v-if="exam.finished_at" class="status-badge inactive">Submitted</span>
                        <span v-else :class="['status-badge', exam.status === 'live' ? 'active' : 'inactive']">
                            {{ examStatusLabel(exam.status) }}
                        </span>
                    </div>
                    <p class="exam-desc">{{ exam.description }}</p>
                    <div class="exam-meta">
                        <span class="meta-chip">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            {{ plural(exam.duration_minutes, 'minute') }}
                        </span>
                        <span class="meta-chip">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
                            {{ plural(exam.questions.length, 'question') }}
                        </span>
                    </div>
                </div>
                <div class="hero-actions">
                    <button v-if="canStartExam(exam)" class="start-btn" @click="startExam">
                        Start exam
                    </button>
                    <p v-else-if="exam.finished_at" class="closed-msg">
                        You've submitted this exam. <router-link to="/results">See results</router-link>
                    </p>
                    <p v-else class="closed-msg">This exam is closed</p>
                </div>
            </div>

            <div class="section-header">
                <h2>Questions</h2>
                <span class="count-badge">{{ exam.questions.length }}</span>
            </div>

            <div class="question-list">
                <div
                    v-for="(question, index) in exam.questions"
                    :key="question.id"
                    class="question-card"
                >
                    <div class="q-top">
                        <div class="q-index">Q{{ index + 1 }}</div>
                        <div class="q-info">
                            <div class="q-title-row">
                                <h3>{{ question.title }}</h3>
                                <span :class="['diff-badge', question.difficulty]">
                                    <span class="diff-dot" :class="question.difficulty"></span>
                                    {{ humanize(question.difficulty) }}
                                </span>
                                <span class="pts-badge">{{ plural(question.points, 'point') }}</span>
                            </div>
                            <p class="q-desc">{{ question.description }}</p>
                            <div class="q-meta">
                                <span>{{ plural(question.max_attempts, 'attempt') }} max</span>
                                <span v-if="questionTags(question.tags).length" class="tags">
                                    <span v-for="tag in questionTags(question.tags)" :key="tag" class="tag-chip">{{ tag }}</span>
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import api from '../api'
import { plural, humanize } from '../utils/format'
import { canStartExam, examStatusLabel, type ExamStatus } from '../utils/exams'

interface Question {
    id: number
    title: string
    description: string
    difficulty: string
    tags: string
    points: number
    max_attempts: number
}

interface Exam {
    id: number
    title: string
    description: string
    duration_minutes: number
    is_active: boolean
    start_time: string | null
    end_time: string | null
    status: ExamStatus
    finished_at?: string | null   // students only: when they submitted the exam
    sections: string[]
    questions: Question[]
}

// The student's exam start page; trainers are sent to the exam report by the router.
const router = useRouter()
const route = useRoute()

const exam = ref<Exam | null>(null)
const loading = ref<boolean>(true)
const error = ref<string>('')

onMounted(async () => {
    try {
        const res = await api.get(`/exams/${route.params.id}/`)
        exam.value = res.data
    } catch (e: any) {
        error.value = e.response?.data?.error || 'Failed to load exam'
    } finally {
        loading.value = false
    }
})

function questionTags(tags: string | null | undefined): string[] {
    if (!tags) return []
    return tags.split(',').map(t => t.trim()).filter(Boolean)
}

function startExam(): void {
    router.push(`/exams/${route.params.id}/take`)
}
</script>

<style scoped>
.detail-page { max-width: 860px; margin: 0 auto; }
.back-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 9px 18px;
    min-height: 40px;
    background: var(--surface);
    border: 1px solid var(--border2);
    border-radius: var(--radius-pill);
    color: var(--text);
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.15s;
    margin-bottom: 28px;
}
.back-btn:hover { border-color: var(--border2); background: var(--surface2); }
.state-msg { color: var(--text-muted); padding: 40px 0; }
.state-msg.error { color: var(--red-ink); }
.exam-hero {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 28px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 24px;
    margin-bottom: 32px;
}
.exam-title-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 8px;
}
.exam-title-row h1 { font-size: 22px; }
.status-badge {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
}
.status-badge.active { background: var(--green-dim); color: var(--green-ink); }
.status-badge.inactive { background: var(--surface2); color: var(--text-muted); }
.exam-desc { color: var(--text-muted); font-size: 14px; margin-bottom: 16px; white-space: pre-line; }
.exam-meta { display: flex; flex-wrap: wrap; gap: 12px; }
.meta-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 13px;
    color: var(--text-dim);
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 4px 12px;
    border-radius: 20px;
}
.start-btn {
    padding: 12px 28px;
    background: var(--accent);
    color: var(--accent-ink);
    border: none;
    border-radius: var(--radius-pill);
    font-family: var(--font-display);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
}
.start-btn:hover { background: var(--accent-hover); }
.closed-msg { color: var(--text-dim); font-size: 14px; }
.hero-actions { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }

.section-header {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
}
.count-badge {
    background: var(--surface2);
    border: 1px solid var(--border);
    color: var(--text-muted);
    font-size: 12px;
    font-weight: 600;
    padding: 2px 10px;
    border-radius: 20px;
}
.question-list { display: flex; flex-direction: column; gap: 12px; }
.question-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px;
    transition: border-color 0.15s;
}
.question-card:hover { border-color: var(--border2); }
.q-top { display: flex; gap: 16px; }
.q-index {
    width: 32px;
    height: 32px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    color: var(--text-muted);
    flex-shrink: 0;
}
.q-info { flex: 1; }
.q-title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; }
.q-title-row h3 { font-size: 15px; color: var(--text); }
.diff-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 2px 10px;
    border-radius: 10px;
    background: var(--surface2);
    color: var(--text-muted);
    font-size: 11px;
    font-weight: 700;
}
.diff-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; background: var(--text-dim); }
.diff-dot.easy { background: var(--green); }
.diff-dot.medium { background: var(--yellow); }
.diff-dot.hard { background: var(--red); }
.pts-badge { padding: 2px 8px; background: var(--surface2); color: var(--text-muted); border-radius: 10px; font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums; }
.q-desc { font-size: 13px; color: var(--text-muted); margin-bottom: 10px; white-space: pre-line; }
.q-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; font-size: 12px; color: var(--text-dim); }
.tags { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.tag-chip {
    background: var(--surface2);
    color: var(--text-muted);
    padding: 2px 9px;
    border-radius: 10px;
    font-size: 11px;
}

@media (max-width: 600px) {
    .exam-hero { flex-direction: column; }
    .hero-actions { align-items: stretch; width: 100%; }
    .start-btn { width: 100%; }
}
</style>
