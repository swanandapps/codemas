<template>
    <div class="student-dashboard">
        <!-- Welcome -->
        <div class="welcome-row">
            <div>
                <h1>Welcome back, {{ authStore.user?.username }}</h1>
                <p class="sub">Here's where you stand today</p>
            </div>
            <router-link to="/exams" class="browse-btn">Browse Exams →</router-link>
        </div>

        <div v-if="loading" class="loading-state">Loading...</div>

        <template v-else>
            <!-- KPI strip -->
            <div class="kpi-row">
                <div class="kpi-card">
                    <div class="kpi-label">Score</div>
                    <div class="kpi-value blue">{{ stats?.score ?? 0 }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cohort Rank</div>
                    <div class="kpi-value">
                        {{ stats?.rank ? `#${stats.rank}` : '—' }}
                        <span class="kpi-of" v-if="stats?.cohort_size">of {{ stats.cohort_size }}</span>
                    </div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Pass Rate</div>
                    <div class="kpi-value" :class="rateColor(stats?.pass_rate ?? 0)">{{ stats?.pass_rate ?? 0 }}%</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Streak</div>
                    <div class="kpi-value">{{ stats?.streak ? `🔥 ${stats.streak}` : '—' }}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Beats Cohort</div>
                    <div class="kpi-value" :class="rateColor(stats?.beats_pct ?? 0)">
                        {{ stats?.beats_pct != null ? stats.beats_pct + '%' : '—' }}
                    </div>
                </div>
            </div>

            <div class="grid-2">
                <!-- Active exams -->
                <div class="section-card">
                    <div class="section-head">
                        <span class="section-title">Active Exams</span>
                        <router-link to="/exams" class="see-all">See all</router-link>
                    </div>
                    <div v-if="activeExams.length === 0" class="empty-msg">No active exams right now.</div>
                    <div
                        v-for="exam in activeExams"
                        :key="exam.id"
                        class="exam-row"
                        @click="$router.push(`/exams/${exam.id}`)"
                    >
                        <div class="exam-row-left">
                            <div class="exam-dot"></div>
                            <div>
                                <div class="exam-row-title">{{ exam.title }}</div>
                                <div class="exam-row-meta">{{ exam.duration_minutes }}m · {{ exam.questions?.length ?? 0 }} questions</div>
                            </div>
                        </div>
                        <span class="go-arrow">→</span>
                    </div>
                </div>

                <!-- Recent submissions -->
                <div class="section-card">
                    <div class="section-head">
                        <span class="section-title">Recent Submissions</span>
                        <router-link to="/results" class="see-all">See all</router-link>
                    </div>
                    <div v-if="recentSubs.length === 0" class="empty-msg">No submissions yet.</div>
                    <div v-for="sub in recentSubs" :key="sub.id" class="sub-row">
                        <div class="sub-row-left">
                            <span :class="['sub-dot', sub.status]"></span>
                            <div>
                                <div class="sub-title">{{ sub.question_title }}</div>
                                <div class="sub-meta">{{ sub.exam_title }} · {{ sub.language }} · {{ formatDate(sub.submitted_at) }}</div>
                            </div>
                        </div>
                        <span :class="['status-badge', sub.status]">{{ sub.status }}</span>
                    </div>
                </div>
            </div>

            <!-- Mini leaderboard -->
            <div class="section-card">
                <div class="section-head">
                    <span class="section-title">Leaderboard — Top 5</span>
                    <router-link to="/leaderboard" class="see-all">Full board</router-link>
                </div>
                <div v-if="topLeaderboard.length === 0" class="empty-msg">No data yet.</div>
                <table v-else class="mini-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Student</th>
                            <th>Score</th>
                            <th>Pass Rate</th>
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
                                <span v-if="entry.rank === 1">🥇</span>
                                <span v-else-if="entry.rank === 2">🥈</span>
                                <span v-else-if="entry.rank === 3">🥉</span>
                                <span v-else class="rank-num">#{{ entry.rank }}</span>
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
                                <span :class="['rate', rateColor(entry.pass_rate)]">{{ entry.pass_rate }}%</span>
                            </td>
                            <td>{{ entry.streak > 0 ? `🔥 ${entry.streak}` : '—' }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

interface Exam {
    id: number
    title: string
    description: string
    duration_minutes: number
    is_active: boolean
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
    pass_rate: number
    beats_pct: number | null
}

interface LeaderboardEntry {
    student_id: number
    username: string
    score: number
    streak: number
    rank: number
    pass_rate: number
}

const authStore = useAuthStore()

const loading = ref(true)
const stats = ref<MyStats | null>(null)
const exams = ref<Exam[]>([])
const submissions = ref<Submission[]>([])
const leaderboard = ref<LeaderboardEntry[]>([])

const activeExams = computed(() => exams.value.filter(e => e.is_active).slice(0, 5))
const recentSubs = computed(() => submissions.value.slice(0, 5))
const topLeaderboard = computed(() => leaderboard.value.slice(0, 5))

onMounted(async () => {
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

function rateColor(rate: number): string {
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'bad'
}

function formatDate(iso: string): string {
    return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.student-dashboard { max-width: 960px; }

.welcome-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 28px;
}
.welcome-row h1 { margin: 0 0 4px; }
.sub { color: var(--text-dim); font-size: 14px; margin: 0; }
.browse-btn {
    padding: 10px 20px;
    background: var(--red);
    color: white;
    border-radius: var(--radius-sm);
    text-decoration: none;
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    transition: opacity 0.15s;
}
.browse-btn:hover { opacity: 0.85; }

.loading-state { color: var(--text-muted); padding: 40px 0; }

.kpi-row {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
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
    text-transform: uppercase;
    color: var(--text-dim);
    font-weight: 600;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}
.kpi-value {
    font-size: 26px;
    font-weight: 700;
    color: var(--text);
}
.kpi-value.blue { color: var(--blue); }
.kpi-value.good { color: var(--green); }
.kpi-value.mid { color: var(--yellow); }
.kpi-value.bad { color: var(--red); }
.kpi-of { font-size: 12px; font-weight: 400; color: var(--text-dim); margin-left: 4px; }

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
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
}
.see-all {
    font-size: 12px;
    color: var(--red);
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
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    cursor: pointer;
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
.exam-row-meta { font-size: 12px; color: var(--text-dim); margin-top: 2px; }
.go-arrow { color: var(--text-dim); font-size: 14px; }

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
.sub-meta { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.status-badge {
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    white-space: nowrap;
    flex-shrink: 0;
}
.status-badge.passed { background: rgba(46,204,113,0.12); color: var(--green); }
.status-badge.failed { background: var(--red-dim); color: var(--red); }
.status-badge.running { background: var(--yellow-dim); color: var(--yellow); }

/* Mini leaderboard */
.mini-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.mini-table th {
    padding: 8px 12px;
    text-align: left;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    font-weight: 600;
}
.mini-table td { padding: 12px 12px; border-bottom: 1px solid var(--border); color: var(--text-muted); }
.lb-row:last-child td { border-bottom: none; }
.lb-row:hover td { background: var(--surface2); }
.lb-row.mine { background: rgba(46,204,113,0.04); }
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
    background: rgba(46,204,113,0.15);
    color: var(--green);
    border: 1px solid rgba(46,204,113,0.3);
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
}
.rank-num { color: var(--text-dim); font-size: 13px; }
.rate { padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.rate.good { background: rgba(46,204,113,0.12); color: var(--green); }
.rate.mid { background: var(--yellow-dim); color: var(--yellow); }
.rate.bad { background: var(--red-dim); color: var(--red); }
</style>
