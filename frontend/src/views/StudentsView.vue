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
                <option value="">All sections</option>
                <option v-for="c in cohorts" :key="c" :value="c">{{ c }}</option>
            </select>
        </div>

        <div v-if="loading" class="state-msg">Loading students...</div>

        <div v-else class="table-scroll">
        <table class="table">
            <thead>
                <tr>
                    <th class="sortable" @click="toggleSort('username')">
                        Username <span class="sort-ind">{{ sortIcon('username') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('cohort')">
                        Section <span class="sort-ind">{{ sortIcon('cohort') }}</span>
                    </th>
                    <th class="sortable" @click="toggleSort('total_submissions')">
                        Submissions <span class="sort-ind">{{ sortIcon('total_submissions') }}</span>
                    </th>
                    <th class="sortable" :title="METRIC_HELP.acceptedStudent" @click="toggleSort('accepted_rate')">
                        Success rate <span class="sort-ind">{{ sortIcon('accepted_rate') }}</span>
                    </th>
                    <th class="sortable" :title="METRIC_HELP.confidence" @click="toggleSort('confidence_rank')">
                        {{ METRIC_LABEL.confidence }} <span class="sort-ind">{{ sortIcon('confidence_rank') }}</span>
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
                        <span :class="['rate-badge', passRateClass(s.accepted_rate)]">
                            {{ formatPct(s.accepted_rate) }}
                        </span>
                    </td>
                    <td>
                        <span v-if="s.max_confidence" :class="['conf-badge', confidenceClass(s.max_confidence)]" :title="METRIC_HELP.confidence">
                            {{ humanize(s.max_confidence) }}
                            <span class="risk-pct" :title="METRIC_HELP.risk">Risk {{ s.max_risk ?? '—' }}</span>
                        </span>
                        <span v-else class="clean-badge">Clean</span>
                    </td>
                    <td>
                        <button type="button" class="view-btn" @click="router.push(`/dashboard/students/${s.student_id}`)">
                            View
                        </button>
                    </td>
                </tr>
            </tbody>
        </table>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { formatPct, humanize } from '../utils/format'
import { METRIC_HELP, METRIC_LABEL, confidenceClass, type FlagConfidence } from '../utils/metrics'

interface StudentSummary {
    student_id: number
    username: string
    cohort: string
    total_submissions: number
    accepted_rate: number | null
    max_confidence: FlagConfidence | null
    max_risk: number | null
    confidence_rank: number
}

const router = useRouter()
const students = ref<StudentSummary[]>([])
const loading = ref<boolean>(true)
const search = ref<string>('')
const route = useRoute()
const cohortFilter = ref<string>(typeof route.query.section === 'string' ? route.query.section : '')  // set by the Overview section cards
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
    else { sortBy.value = col; sortDir.value = col === 'confidence_rank' || col === 'accepted_rate' ? -1 : 1 }
}

function sortIcon(col: string): string {
    if (sortBy.value !== col) return ''
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

function passRateClass(rate: number | null): string {
    if (rate === null || rate === undefined) return ''
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
.table-scroll { overflow-x: auto; }
.table {
    width: 100%;
    min-width: 620px;
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
.rate-badge { padding: 3px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.rate-good { background: var(--green-dim); color: var(--green-ink); }
.rate-mid { background: var(--yellow-dim); color: var(--amber-ink); }
.rate-low { background: var(--red-dim); color: var(--red-ink); }

.conf-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
}
.risk-pct { font-size: 10px; font-weight: 400; opacity: 0.8; }

.clean-badge {
    padding: 3px 10px;
    background: var(--green-dim);
    color: var(--green-ink);
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
.view-btn:hover { border-color: var(--accent); color: var(--accent); }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .filters { flex-wrap: wrap; }
    .filters input { width: 100%; }
}
</style>
