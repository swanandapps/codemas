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
                        <span :class="['status-badge', exam.is_active ? 'active' : 'inactive']">
                            {{ exam.is_active ? 'Active' : 'Closed' }}
                        </span>
                    </div>
                    <p class="exam-desc">{{ exam.description }}</p>
                    <div class="exam-meta">
                        <span class="meta-chip">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
                            {{ exam.duration_minutes }} minutes
                        </span>
                        <span class="meta-chip">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="13" height="13"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
                            {{ exam.questions.length }} questions
                        </span>
                    </div>
                </div>
                <div>
                    <button v-if="exam.is_active" class="start-btn" @click="startExam">
                        Start Exam →
                    </button>
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
                                <span :class="['diff-badge', question.difficulty]">{{ question.difficulty }}</span>
                                <span class="pts-badge">{{ question.points }} pts</span>
                            </div>
                            <p class="q-desc">{{ question.description }}</p>
                            <div class="q-meta">
                                <span>{{ question.max_attempts }} attempts max</span>
                                <span v-if="question.tags" class="tags">{{ question.tags }}</span>
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
    questions: Question[]
}

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
    padding: 7px 14px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 13px;
    cursor: pointer;
    transition: all 0.15s;
    margin-bottom: 28px;
}
.back-btn:hover { border-color: var(--border2); color: var(--text); }
.state-msg { color: var(--text-muted); padding: 40px 0; }
.state-msg.error { color: var(--red); }
.exam-hero {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 28px;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 24px;
    margin-bottom: 32px;
}
.exam-title-row {
    display: flex;
    align-items: center;
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
.status-badge.active { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.inactive { background: var(--red-dim); color: var(--red); }
.exam-desc { color: var(--text-muted); font-size: 14px; margin-bottom: 16px; }
.exam-meta { display: flex; gap: 12px; }
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
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 15px;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
}
.start-btn:hover { background: var(--red-hover); }
.closed-msg { color: var(--text-dim); font-size: 14px; }
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
.q-title-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.q-title-row h3 { font-size: 15px; color: var(--text); }
.diff-badge { padding: 2px 10px; border-radius: 10px; font-size: 11px; font-weight: 700; text-transform: capitalize; }
.diff-badge.easy { background: rgba(46,204,113,0.12); color: var(--green); }
.diff-badge.medium { background: var(--yellow-dim); color: var(--yellow); }
.diff-badge.hard { background: var(--red-dim); color: var(--red); }
.pts-badge { padding: 2px 8px; background: var(--blue-dim); color: var(--blue); border-radius: 10px; font-size: 11px; font-weight: 700; }
.q-desc { font-size: 13px; color: var(--text-muted); margin-bottom: 10px; }
.q-meta { display: flex; gap: 16px; font-size: 12px; color: var(--text-dim); }
.tags { color: var(--text-dim); }
</style>
