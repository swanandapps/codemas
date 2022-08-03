<template>
    <div class="leaderboard-page">
        <h1>Leaderboard</h1>

        <!-- Cohort filter -->
        <div class="filters">
            <button
                :class="['cohort-btn', !activeCohort ? 'active' : '']"
                @click="activeCohort = ''; load()"
            >All</button>
            <button
                v-for="c in cohorts"
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
                    <div class="crown">👑</div>
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
                            <th>Cohort</th>
                            <th>Score</th>
                            <th>Pass Rate</th>
                            <th>Submissions</th>
                            <th>Streak</th>
                            <th>Avg Speed</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr
                            v-for="entry in leaderboard"
                            :key="entry.student_id"
                            :class="['board-row', entry.student_id === myId ? 'mine' : '']"
                        >
                            <td>
                                <span v-if="entry.rank === 1" class="medal">🥇</span>
                                <span v-else-if="entry.rank === 2" class="medal">🥈</span>
                                <span v-else-if="entry.rank === 3" class="medal">🥉</span>
                                <span v-else class="rank-num">#{{ entry.rank }}</span>
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
                                <span :class="['rate', rateClass(entry.pass_rate)]">
                                    {{ entry.pass_rate }}%
                                </span>
                            </td>
                            <td>{{ entry.total_submissions }}</td>
                            <td>
                                <span v-if="entry.streak > 0" class="streak">
                                    🔥 {{ entry.streak }}
                                </span>
                                <span v-else class="no-streak">—</span>
                            </td>
                            <td>{{ entry.avg_execution_time ? entry.avg_execution_time + 'ms' : '—' }}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth'
import api from '../api'

interface LeaderboardEntry {
    student_id: number
    username: string
    cohort: string
    score: number
    streak: number
    rank: number
    total_submissions: number
    pass_rate: number
    avg_execution_time: number | null
}

const authStore = useAuthStore()
const myId = authStore.user?.id

const leaderboard = ref<LeaderboardEntry[]>([])
const cohorts = ref<string[]>([])
const activeCohort = ref<string>('')
const loading = ref<boolean>(true)

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

function rateClass(rate: number): string {
    if (rate >= 70) return 'good'
    if (rate >= 40) return 'mid'
    return 'low'
}
</script>

<style scoped>
.leaderboard-page { max-width: 900px; }
h1 { margin-bottom: 20px; }

.filters { display: flex; gap: 8px; margin-bottom: 28px; flex-wrap: wrap; }
.cohort-btn {
    padding: 6px 16px;
    border: 1px solid var(--border);
    border-radius: 20px;
    background: transparent;
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
    transition: all 0.15s;
}
.cohort-btn:hover { border-color: var(--border2); color: var(--text); }
.cohort-btn.active { background: var(--red-dim); border-color: var(--red); color: var(--red); }

.podium {
    display: flex;
    justify-content: center;
    align-items: flex-end;
    gap: 16px;
    margin-bottom: 32px;
}
.podium-item { display: flex; flex-direction: column; align-items: center; }
.crown { font-size: 24px; margin-bottom: 4px; }
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
.avatar.gold { background: rgba(241,196,15,0.15); border-color: var(--yellow); color: var(--yellow); }
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
.p1 { height: 80px; background: rgba(241,196,15,0.2); border: 1px solid rgba(241,196,15,0.4); color: var(--yellow); }
.p2 { height: 60px; background: var(--surface2); border: 1px solid var(--border); color: var(--text-muted); }
.p3 { height: 44px; background: rgba(205,127,50,0.15); border: 1px solid rgba(205,127,50,0.3); color: #cd7f32; }

.board-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.board-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.board-table th {
    padding: 12px 16px;
    text-align: left;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    background: var(--surface2);
    border-bottom: 1px solid var(--border);
}
.board-table td { padding: 14px 16px; border-bottom: 1px solid var(--border); color: var(--text-muted); }
.board-row:last-child td { border-bottom: none; }
.board-row:hover td { background: var(--surface2); }
.board-row.mine { background: rgba(46,204,113,0.04); }
.board-row.mine td { color: var(--text); }

.medal { font-size: 20px; }
.rank-num { color: var(--text-dim); font-size: 13px; }

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
    background: rgba(46,204,113,0.15);
    color: var(--green);
    border: 1px solid rgba(46,204,113,0.3);
    border-radius: 10px;
    font-size: 10px;
    font-weight: 700;
}
.score { font-size: 15px; font-weight: 600; color: var(--text); }
.rate { padding: 3px 8px; border-radius: 10px; font-size: 12px; font-weight: 600; }
.rate.good { background: rgba(46,204,113,0.12); color: var(--green); }
.rate.mid { background: var(--yellow-dim); color: var(--yellow); }
.rate.low { background: var(--red-dim); color: var(--red); }
.streak { color: var(--yellow); font-weight: 600; }
.no-streak { color: var(--text-dim); }
.loading { color: var(--text-muted); }
</style>
