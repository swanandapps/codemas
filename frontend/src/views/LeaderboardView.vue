<template>
    <div class="leaderboard-page">
        <h1>Leaderboard</h1>

        <!-- Cohort filter -->
        <div class="filters">
            <button
                :class="['cohort-btn', !activeCohort ? 'active' : '']"
                @click="activeCohort = ''; load()"
            >Whole cohort</button>
            <button
                v-for="c in sortedCohorts"
                :key="c"
                :class="['cohort-btn', activeCohort === c ? 'active' : '']"
                @click="activeCohort = c; load()"
            >{{ c }}</button>
        </div>

        <div v-if="loading" class="loading">Loading...</div>

        <div v-else class="board-wrap">
            <!-- Top 3 podium -->
            <div class="podium" v-if="leaderboard.length >= 3">
                <div class="podium-item second">
                    <div class="avatar">{{ leaderboard[1].username.slice(0,2).toUpperCase() }}</div>
                    <div class="podium-name">{{ leaderboard[1].username }}</div>
                    <div class="podium-score">{{ leaderboard[1].score }} pts</div>
                    <div class="podium-block p2">2</div>
                </div>
                <div class="podium-item first">
                    <div class="avatar gold">{{ leaderboard[0].username.slice(0,2).toUpperCase() }}</div>
                    <div class="podium-name">{{ leaderboard[0].username }}</div>
                    <div class="podium-score">{{ leaderboard[0].score }} pts</div>
                    <div class="podium-block p1">1</div>
                </div>
                <div class="podium-item third">
                    <div class="avatar">{{ leaderboard[2].username.slice(0,2).toUpperCase() }}</div>
                    <div class="podium-name">{{ leaderboard[2].username }}</div>
                    <div class="podium-score">{{ leaderboard[2].score }} pts</div>
                    <div class="podium-block p3">3</div>
                </div>
            </div>

            <!-- Full table -->
            <div class="board-card">
                <table class="board-table">
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Student</th>
                            <th>Section</th>
                            <th>Score</th>
                            <th :title="METRIC_HELP.acceptedStudent">Success rate</th>
                            <th>Submissions</th>
                            <th v-if="hasStreak">Streak</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="entry in leaderboard"
                            :key="entry.student_id"
                            :class="['board-row', entry.student_id === myId ? 'mine' : '']"
                        >
                            <td>
                                <span :class="['rank-num', entry.rank <= 3 ? 'top' : '']">{{ entry.rank }}</span>
                            </td>
                            <td>
                                <div class="student-cell">
                                    <div class="mini-avatar">{{ entry.username.slice(0,2).toUpperCase() }}</div>
                                    <span>{{ entry.username }}</span>
                                    <span v-if="entry.student_id === myId" class="you-badge">You</span>
                                </div>
                            </td>
                            <td>{{ entry.cohort || '—' }}</td>
                            <td><strong class="score">{{ entry.score }}</strong></td>
                            <td>
                                <span :class="['rate', rateClass(entry.accepted_rate)]">
                                    {{ formatPct(entry.accepted_rate) }}
                                </span>
                            </td>
                            <td>{{ entry.total_submissions }}</td>
                            <td v-if="hasStreak">
                                <span v-if="entry.streak > 0" class="streak">
                                    {{ plural(entry.streak, 'day') }}
                                </span>
                                <span v-else class="no-streak">—</span>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'
import { formatPct, plural } from '../utils/format'
import { METRIC_HELP } from '../utils/metrics'

interface LeaderboardEntry {
    student_id: number
    username: string
    cohort: string
    score: number
    streak: number
    rank: number
    total_submissions: number
    accepted_rate: number | null
}

const authStore = useAuthStore()
const myId = authStore.user?.id

const leaderboard = ref<LeaderboardEntry[]>([])
const cohorts = ref<string[]>([])
const activeCohort = ref<string>('')
const loading = ref<boolean>(true)

const sortedCohorts = computed(() => [...cohorts.value].sort((a, b) => a.localeCompare(b)))
const hasStreak = computed(() => leaderboard.value.some(e => e.streak > 0))

onMounted(() => load())

async function load(): Promise<void> {
    loading.value = true
    try {
        const params = activeCohort.value ? `?cohort=${activeCohort.value}` : ''
        const res = await api.get(`/leaderboard/${params}`)
        leaderboard.value = res.data.leaderboard
        cohorts.value = res.data.cohorts
    } finally {
        loading.value = false
    }
}

function rateClass(rate: number | null): string {
    if (rate === null || rate === undefined) return ''
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'low'
}
</script>

<style scoped>
.leaderboard-page { max-width: 900px; width: 100%; margin: 0 auto; }
h1 { margin-bottom: 20px; }

.filters { display: flex; gap: 8px; margin-bottom: 28px; flex-wrap: wrap; }
.cohort-btn {
    padding: 6px 16px;
    border: 1px solid var(--border);
    border-radius: var(--radius-pill);
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
}
.cohort-btn:hover { border-color: var(--border2); color: var(--text); }
.cohort-btn.active { background: var(--accent-tint); border-color: var(--accent); color: var(--accent); }

.podium {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    gap: 16px;
    margin-bottom: 32px;
}
.podium-item { display: flex; flex-direction: column; align-items: center; }
.avatar {
    width: 48px;
    height: 48px;
    border-radius: 50%;
    background: var(--surface3);
    border: 1px solid var(--border2);
    color: var(--text);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
    margin-bottom: 8px;
}
.avatar.gold { background: var(--yellow-dim); border-color: var(--yellow); color: var(--amber-ink); }
.podium-name { font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 2px; }
.podium-score { font-size: 12px; color: var(--text-dim); margin-bottom: 8px; }
.podium-block {
    width: 80px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 20px;
    font-weight: 700;
    border-radius: 6px 6px 0 0;
}
.p1 { height: 80px; background: var(--yellow-dim); border: 1px solid var(--yellow); color: var(--amber-ink); }
.p2 { height: 60px; background: var(--surface2); border: 1px solid var(--border); color: var(--text-muted); }
.p3 { height: 44px; background: rgba(205,127,50,0.15); border: 1px solid rgba(205,127,50,0.3); color: #cd7f32; }

.board-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow-x: auto; }
.board-table { width: 100%; min-width: 640px; border-collapse: collapse; font-size: 14px; }
.board-table th {
    padding: 12px 16px;
    text-align: left;
    font-size: 11px;
    color: var(--text-dim);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
}
.board-table td { padding: 14px 16px; border-bottom: 1px solid var(--border); color: var(--text-muted); font-variant-numeric: tabular-nums; }
.board-row:last-child td { border-bottom: none; }
.board-row:hover td { background: var(--surface2); }
.board-row.mine { background: var(--green-dim); }
.board-row.mine td { color: var(--text); }

.rank-num { color: var(--text-muted); font-size: 13px; font-family: var(--font-mono); }
.rank-num.top { color: var(--text); font-weight: 600; }

.student-cell { display: flex; align-items: center; gap: 8px; }
.mini-avatar {
    width: 30px;
    height: 30px;
    border-radius: 50%;
    background: var(--surface3);
    border: 1px solid var(--border2);
    color: var(--text-muted);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    font-weight: 700;
    flex-shrink: 0;
}
.you-badge {
    padding: 2px 8px;
    background: var(--green-dim);
    color: var(--green-ink);
    border: 1px solid var(--green);
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
}
.score { font-size: 15px; font-weight: 600; color: var(--text); font-variant-numeric: tabular-nums; }
.rate { padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.rate.good { background: var(--green-dim); color: var(--green-ink); }
.rate.mid { background: var(--yellow-dim); color: var(--amber-ink); }
.rate.low { background: var(--red-dim); color: var(--red-ink); }
.streak { color: var(--amber-ink); font-weight: 600; }
.no-streak { color: var(--text-dim); }
.loading { color: var(--text-muted); }

@media (max-width: 600px) {
    .podium { gap: 8px; }
    .podium-block { width: 60px; }
}
</style>
