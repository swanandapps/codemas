<template>
    <div class="student-dashboard">
        <!-- Welcome -->
        <div class="welcome-row">
            <div>
                <h1>Welcome back, {{ authStore.user?.username }}</h1>
                <p class="sub">Here's where you stand today</p>
            </div>
            <router-link to="/exams" class="browse-btn">Browse exams</router-link>
        </div>

        <!-- the newest trainer decision or appeal ruling since the student last looked -->
        <router-link v-if="banner" :to="banner.to" class="attention-banner">{{ banner.text }}</router-link>

        <div v-if="loading" class="loading-state">Loading...</div>

        <template v-else>
            <!-- KPI strip -->
            <div class="kpi-row">
                <div class="kpi-card">
                    <div class="kpi-label">Score</div>
                    <div class="kpi-value">
                        {{ stats?.score ?? 0 }}
                        <span class="kpi-of" v-if="stats?.score_available">of {{ stats.score_available }} points</span>
                    </div>
                    <div v-if="stats?.points_withheld" class="kpi-note withheld">
                        {{ plural(stats.points_withheld, 'point') }} withheld: plagiarism confirmed by your trainer.
                        <router-link to="/results">See My results</router-link>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Section rank</div>
                    <div class="kpi-value">
                        {{ stats?.rank ? `#${stats.rank}` : '—' }}
                        <span class="kpi-of" v-if="stats?.cohort_size">of {{ stats.cohort_size }}</span>
                    </div>
                    <div v-if="stats && stats.cohort_size > 1" class="kpi-note">
                        Ahead of {{ stats.ahead_of }} of {{ stats.cohort_size - 1 }} classmates
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label" :title="METRIC_HELP.acceptedStudent">Success rate</div>
                    <div class="kpi-value" :class="rateColor(stats?.accepted_rate ?? null)">{{ formatPct(stats?.accepted_rate ?? null) }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Streak</div>
                    <div class="kpi-value">{{ stats?.streak ? plural(stats.streak, 'day') : '—' }}</div>
                </div>
            </div>

            <div class="grid-2">
                <!-- Active exams -->
                <div class="section-card">
                    <div class="section-head">
                        <span class="section-title">Active exams</span>
                        <router-link to="/exams" class="see-all">See all</router-link>
                    </div>
                    <div v-if="activeExams.length === 0" class="empty-msg">No active exams right now.</div>
                    <button
                        v-for="exam in activeExams"
                        :key="exam.id"
                        type="button"
                        class="exam-row"
                        @click="$router.push(`/exams/${exam.id}`)"
                    >
                        <div class="exam-row-left">
            <div class="exam-dot"></div>
                            <div>
                                <div class="exam-row-title">{{ exam.title }}</div>
                                <div class="exam-row-meta">
                                    <span>{{ plural(exam.duration_minutes, 'minute') }}</span>
                                    <span>{{ plural(exam.questions?.length ?? 0, 'question') }}</span>
                                </div>
                            </div>
                        </div>
                    </button>
                </div>

                <!-- Recent submissions -->
                <div class="section-card">
                    <div class="section-head">
                        <span class="section-title">Recent submissions</span>
                        <router-link to="/results" class="see-all">See all</router-link>
                    </div>
                    <div v-if="recentSubs.length === 0" class="empty-msg">No submissions yet.</div>
                    <div v-for="sub in recentSubs" :key="sub.id" class="sub-row">
                        <div class="sub-row-left">
                            <span :class="['sub-dot', sub.status]"></span>
                            <div>
                                <div class="sub-title">{{ sub.question_title }}</div>
                                <div class="sub-meta">
                                    <span>{{ sub.exam_title }}</span>
                                    <span>{{ sub.language }}</span>
                                    <span>{{ formatDateTime(sub.submitted_at) }}</span>
                                </div>
                            </div>
                        </div>
                        <span :class="['status-badge', sub.status]">{{ submissionStatusLabel(sub.status) }}</span>
                    </div>
                </div>
            </div>

            <!-- Mini leaderboard -->
            <div class="section-card">
                <div class="section-head">
                    <span class="section-title">Top 5 on the leaderboard</span>
                    <router-link to="/leaderboard" class="see-all">Full board</router-link>
                </div>
                <div v-if="topLeaderboard.length === 0" class="empty-msg">No data yet.</div>
                <div v-else class="table-scroll">
                <table class="mini-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Student</th>
                            <th>Score</th>
                            <th :title="METRIC_HELP.acceptedStudent">Success rate</th>
                            <th>Streak</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="entry in topLeaderboard"
                            :key="entry.student_id"
                            :class="['lb-row', entry.student_id === authStore.user?.id ? 'mine' : '']"
                        >
                            <td>
                                <span :class="['rank-num', entry.rank <= 3 ? 'top' : '']">{{ entry.rank }}</span>
                            </td>
                            <td>
                                <div class="lb-student">
                                    <div class="mini-avatar">{{ entry.username.slice(0,2).toUpperCase() }}</div>
                                    {{ entry.username }}
                                    <span v-if="entry.student_id === authStore.user?.id" class="you-badge">You</span>
                                </div>
                            </td>
                            <td><strong>{{ entry.score }}</strong></td>
                            <td>
                                <span :class="['rate', rateColor(entry.accepted_rate)]">{{ formatPct(entry.accepted_rate) }}</span>
                            </td>
                            <td>{{ entry.streak > 0 ? plural(entry.streak, 'day') : '—' }}</td>
                        </tr>
                    </tbody>
                </table>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import { formatDateTime, formatPct, plural, submissionStatusLabel } from '../utils/format'
import { canStartExam } from '../utils/exams'
import { METRIC_HELP } from '../utils/metrics'
import { attention, loadAttention } from '../utils/attention'

interface Exam {
    id: number
    title: string
    description: string
    duration_minutes: number
    is_active: boolean
    finished_at?: string | null   // the student submitted this exam
    questions?: unknown[]
}

interface Submission {
    id: number
    exam_title: string
    question_title: string
    status: string
    language: string
    submitted_at: string
}

interface MyStats {
    score: number
    streak: number
    rank: number | null
    cohort_size: number
    accepted_rate: number | null
    score_available: number
    points_withheld?: number   // lost to confirmed plagiarism, already out of the score and rank
    ahead_of: number
}

interface LeaderboardEntry {
    student_id: number
    username: string
    score: number
    streak: number
    rank: number
    accepted_rate: number | null
}

const authStore = useAuthStore()

const loading = ref(true)
const stats = ref<MyStats | null>(null)
const exams = ref<Exam[]>([])
const submissions = ref<Submission[]>([])
const leaderboard = ref<LeaderboardEntry[]>([])

// Live exams the student can still take: one they've submitted shows on the Exams page as "Submitted · see results"
const activeExams = computed(() => exams.value.filter(canStartExam).slice(0, 5))
const recentSubs = computed(() => submissions.value.slice(0, 5))
const topLeaderboard = computed(() => leaderboard.value.slice(0, 5))

const banner = computed(() => {
    const item = attention.data?.latest
    if (!item) return null
    const exam = item.exam_title ?? 'an exam'
    if (item.kind === 'ruling') {
        return { text: `Your appeal for ${exam} was ${item.status} →`, to: `/disputes?appeal=${item.appeal_id}` }
    }
    return { text: `Your trainer reviewed ${exam}. See the decision →`, to: `/results?exam=${item.exam_id}` }
})

onMounted(async () => {
    loadAttention()   // shared with the sidebar's badge request
    try {
        const [examsRes, subsRes, statsRes, lbRes] = await Promise.all([
            api.get('/exams/'),
            api.get('/submissions/'),
            api.get('/leaderboard/me/'),
            api.get('/leaderboard/'),
        ])
        exams.value = examsRes.data
        submissions.value = subsRes.data.results ?? subsRes.data
        stats.value = statsRes.data
        leaderboard.value = lbRes.data.leaderboard ?? []
    } finally {
        loading.value = false
    }
})

function rateColor(rate: number | null): string {
    if (rate === null || rate === undefined) return ''
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'bad'
}
</script>

<style scoped>
.student-dashboard { max-width: 960px; }

.welcome-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 28px;
}
.welcome-row h1 { margin: 0 0 4px; }
.sub { color: var(--text-dim); font-size: 14px; margin: 0; }
.browse-btn {
    padding: 10px 20px;
    background: var(--accent);
    color: var(--accent-ink);
    border-radius: var(--radius-pill);
    text-decoration: none;
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    transition: opacity 0.15s;
}
.browse-btn:hover { opacity: 0.85; }

.loading-state { color: var(--text-muted); padding: 40px 0; }

.attention-banner {
    display: flex;
    align-items: center;
    min-height: 44px;
    margin: -12px 0 24px;
    padding: 10px 16px;
    border: 1px solid var(--border);
    border-left: 3px solid var(--red);
    border-radius: var(--radius-sm);
    background: var(--surface);
    color: var(--text);
    font-size: 14px;
    font-weight: 600;
    text-decoration: none;
    overflow-wrap: anywhere;
}
.attention-banner:hover { background: var(--surface2); text-decoration: none; }
.attention-banner:focus-visible { outline: 2px solid var(--red); outline-offset: 2px; }

.kpi-row {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 12px;
    margin-bottom: 20px;
}
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 16px;
}
.kpi-label {
    font-size: 11px;
    color: var(--text-dim);
    font-weight: 600;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 26px;
    font-weight: 700;
    color: var(--text);
    font-variant-numeric: tabular-nums;
}
.kpi-value.good { color: var(--green-ink); }
.kpi-value.mid { color: var(--amber-ink); }
.kpi-value.bad { color: var(--red-ink); }
.kpi-of { font-size: 12px; font-weight: 400; color: var(--text-dim); margin-left: 4px; }
.kpi-note { margin-top: 6px; font-size: 13px; line-height: 1.4; color: var(--text-muted); }
.kpi-note.withheld { color: var(--red-ink); font-weight: 600; }
.kpi-note.withheld a { color: inherit; text-decoration: underline; }

.grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
}

.section-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 16px;
}
.section-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 16px;
}
.section-title {
    font-size: 13px;
    font-weight: 700;
    color: var(--text-muted);
}
.see-all {
    font-size: 12px;
    color: var(--accent);
    text-decoration: none;
    font-weight: 500;
}
.see-all:hover { opacity: 0.75; }
.empty-msg { font-size: 13px; color: var(--text-dim); padding: 8px 0; }

/* Active exams */
.exam-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    width: 100%;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    border-left: none;
    border-right: none;
    border-top: none;
    background: none;
    cursor: pointer;
    font: inherit;
    text-align: left;
    min-height: 40px;
    transition: opacity 0.15s;
}
.exam-row:last-child { border-bottom: none; }
.exam-row:hover { opacity: 0.75; }
.exam-row-left { display: flex; align-items: center; gap: 10px; }
.exam-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--green);
    flex-shrink: 0;
}
.exam-row-title { font-size: 14px; font-weight: 600; color: var(--text); }
.exam-row-meta { display: flex; gap: 8px; font-size: 12px; color: var(--text-dim); margin-top: 2px; }

/* Recent submissions */
.sub-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
}
.sub-row:last-child { border-bottom: none; }
.sub-row-left { display: flex; align-items: center; gap: 10px; }
.sub-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}
.sub-dot.passed { background: var(--green); }
.sub-dot.failed { background: var(--red); }
.sub-dot.running { background: var(--yellow); }
.sub-title { font-size: 14px; font-weight: 500; color: var(--text); }
.sub-meta { display: flex; gap: 8px; font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.status-badge {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    white-space: nowrap;
    flex-shrink: 0;
}
.status-badge.passed { background: var(--green-dim); color: var(--green-ink); }
.status-badge.failed { background: var(--red-dim); color: var(--red-ink); }
.status-badge.running { background: var(--yellow-dim); color: var(--amber-ink); }

/* Mini leaderboard */
.mini-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.mini-table th {
    padding: 8px 12px;
    text-align: left;
    font-size: 10px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    font-weight: 600;
}
.mini-table td { padding: 12px 12px; border-bottom: 1px solid var(--border); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.lb-row:last-child td { border-bottom: none; }
.lb-row:hover td { background: var(--surface2); }
.lb-row.mine { background: var(--green-dim); }
.lb-row.mine td { color: var(--text); }

.lb-student { display: flex; align-items: center; gap: 8px; }
.mini-avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--surface3);
    border: 1px solid var(--border2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
    color: var(--text-muted);
    flex-shrink: 0;
}
.you-badge {
    padding: 2px 7px;
    background: var(--green-dim);
    color: var(--green-ink);
    border: 1px solid var(--green);
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
}
.rank-num { color: var(--text-muted); font-size: 13px; font-family: var(--font-mono); }
.rank-num.top { color: var(--text); font-weight: 600; }
.rate { padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.rate.good { background: var(--green-dim); color: var(--green-ink); }
.rate.mid { background: var(--yellow-dim); color: var(--amber-ink); }
.rate.bad { background: var(--red-dim); color: var(--red-ink); }

.table-scroll { overflow-x: auto; }

@media (max-width: 899px) {
    .kpi-row { grid-template-columns: repeat(2, 1fr); }
    .grid-2 { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
    .kpi-row { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
    .browse-btn { width: 100%; text-align: center; }
    .mini-table { min-width: 480px; }
}

/* Phone: stack each submission's details instead of squeezing them into columns */
.sub-row-left { min-width: 0; }
@media (max-width: 600px) {
    .sub-meta { flex-direction: column; gap: 2px; }
}
</style>
