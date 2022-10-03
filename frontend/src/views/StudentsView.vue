<template>
    <div class="students-page">
        <div class="page-header">
            <div>
                <h1>Students</h1>
                <p class="page-sub">Monitor performance and activity</p>
            </div>
        </div>

        <div class="filters">
            <input v-model="search" placeholder="Search by username..." />
            <select v-model="cohortFilter">
                <option value="">All Cohorts</option>
                <option v-for="c in cohorts" :key="c" :value="c">{{ c }}</option>
            </select>
        </div>

        <div v-if="loading" class="state-msg">Loading students...</div>

        <table v-else class="table">
            <thead>
                <tr>
                    <th class="sortable" @click="toggleSort('username')">
                        Username <span class="sort-ind">{{ sortIcon('username') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('cohort')">
                        Cohort <span class="sort-ind">{{ sortIcon('cohort') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('total_submissions')">
                        Submissions <span class="sort-ind">{{ sortIcon('total_submissions') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('pass_rate')">
                        Pass Rate <span class="sort-ind">{{ sortIcon('pass_rate') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('confidence_rank')">
                        Confidence <span class="sort-ind">{{ sortIcon('confidence_rank') }}</span>
                    </th>
                    <th></th>
                </tr>
            </thead>
            <tbody>
                <tr v-for="s in sorted" :key="s.student_id">
                    <td class="name-cell">{{ s.username }}</td>
                    <td>{{ s.cohort || '—' }}</td>
                    <td>{{ s.total_submissions }}</td>
                    <td>
                        <span :class="['rate-badge', passRateClass(s.pass_rate)]">
                            {{ s.pass_rate?.toFixed(1) }}%
                        </span>
                    </td>
                    <td>
                        <span v-if="s.max_confidence" :class="['conf-badge', s.max_confidence]">
                            {{ s.max_confidence.toUpperCase() }}
                            <span class="risk-pct">{{ s.max_risk_score }}%</span>
                        </span>
                        <span v-else class="clean-badge">Clean</span>
                    </td>
                    <td>
                        <button class="view-btn" @click="router.push(`/dashboard/students/${s.student_id}`)">
                            View
                        </button>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

interface StudentSummary {
    student_id: number
    username: string
    cohort: string
    total_submissions: number
    pass_rate: number
    max_confidence: 'high' | 'medium' | 'low' | null
    max_risk_score: number | null
    confidence_rank: number
}

const router = useRouter()
const students = ref<StudentSummary[]>([])
const loading = ref<boolean>(true)
const search = ref<string>('')
const cohortFilter = ref<string>('')
const sortBy = ref<string>('username')
const sortDir = ref<1 | -1>(1)

const cohorts = computed<string[]>(() => {
    const all = students.value.map(s => s.cohort).filter(Boolean)
    return [...new Set(all)].sort()
})

const filtered = computed<StudentSummary[]>(() =>
    students.value.filter(s => {
        const matchSearch = s.username.toLowerCase().includes(search.value.toLowerCase())
        const matchCohort = !cohortFilter.value || s.cohort === cohortFilter.value
        return matchSearch && matchCohort
    })
)

const sorted = computed<StudentSummary[]>(() =>
    [...filtered.value].sort((a, b) => {
        const av = (a as any)[sortBy.value]
        const bv = (b as any)[sortBy.value]
        if (av == null && bv == null) return 0
        if (av == null) return sortDir.value
        if (bv == null) return -sortDir.value
        if (typeof av === 'string') return av.localeCompare(bv) * sortDir.value
        return (av - bv) * sortDir.value
    })
)

function toggleSort(col: string) {
    if (sortBy.value === col) sortDir.value = sortDir.value === 1 ? -1 : 1
    else { sortBy.value = col; sortDir.value = col === 'confidence_rank' || col === 'pass_rate' ? -1 : 1 }
}

function sortIcon(col: string): string {
    if (sortBy.value !== col) return '⇅'
    return sortDir.value === 1 ? '▲' : '▼'
}

onMounted(async () => {
    try {
        const res = await api.get('/dashboard/students/')
        students.value = res.data
    } finally {
        loading.value = false
    }
})

function passRateClass(rate: number): string {
    if (rate >= 70) return 'rate-good'
    if (rate >= 40) return 'rate-mid'
    return 'rate-low'
}
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
.filters { display: flex; gap: 12px; margin-bottom: 20px; }
.filters input { width: 260px; }
.filters select { width: auto; }
.state-msg { color: var(--text-muted); padding: 40px 0; }
.table {
    width: 100%;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    border-collapse: collapse;
    overflow: hidden;
}
.table th {
    padding: 12px 16px;
    background: var(--surface2);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    text-align: left;
    border-bottom: 1px solid var(--border);
    white-space: nowrap;
}
.table th.sortable {
    cursor: pointer;
    user-select: none;
}
.table th.sortable:hover { color: var(--text); }
.sort-ind { font-size: 10px; margin-left: 4px; opacity: 0.6; }
.table td {
    padding: 14px 16px;
    font-size: 14px;
    color: var(--text-muted);
    border-bottom: 1px solid var(--border);
}
.table tbody tr:last-child td { border-bottom: none; }
.table tbody tr:hover td { background: var(--surface2); }
.name-cell { color: var(--text); font-weight: 600; }
.rate-badge { padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; }
.rate-good { background: rgba(16,185,129,0.12); color: var(--green); }
.rate-mid { background: var(--yellow-dim); color: var(--yellow); }
.rate-low { background: var(--red-dim); color: var(--red); }

.conf-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
}
.conf-badge.low { background: rgba(230,57,70,0.15); color: #e63946; }
.conf-badge.medium { background: rgba(245,158,11,0.15); color: #f59e0b; }
.conf-badge.high { background: rgba(59,130,246,0.15); color: #3b82f6; }
.risk-pct { font-size: 10px; font-weight: 400; opacity: 0.8; }

.clean-badge {
    padding: 3px 10px;
    background: rgba(16,185,129,0.1);
    color: var(--green);
    border-radius: 20px;
    font-size: 12px;
    font-weight: 600;
}
.view-btn {
    padding: 5px 14px;
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    font-size: 12px;
    cursor: pointer;
    transition: all 0.15s;
}
.view-btn:hover { border-color: var(--green); color: var(--green); }
</style>
