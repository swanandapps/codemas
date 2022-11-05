<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1 class="page-title">Integrity Monitoring</h1>
                <p class="page-subtitle">Model accuracy, signal effectiveness, and coverage gaps</p>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading monitoring data…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else>
            <!-- KPI strip -->
            <div class="kpi-strip">
                <div class="kpi-card">
                    <div class="kpi-label">Pending Review</div>
                    <div class="kpi-value warn">
                        {{ data.summary.behavioural.pending + data.summary.similarity.pending }}
                    </div>
                    <div class="kpi-sub">flags awaiting trainer</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Behavioural Precision</div>
                    <div class="kpi-value" :class="precisionClass(data.summary.behavioural.precision)">
                        {{ fmtPct(data.summary.behavioural.precision) }}
                    </div>
                    <div class="kpi-sub">of reviewed flags confirmed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Similarity Precision</div>
                    <div class="kpi-value" :class="precisionClass(data.summary.similarity.precision)">
                        {{ fmtPct(data.summary.similarity.precision) }}
                    </div>
                    <div class="kpi-sub">of reviewed flags confirmed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Behavioural Coverage</div>
                    <div class="kpi-value" :class="coverageClass(data.coverage.behavioural_pct)">
                        {{ data.coverage.behavioural_pct }}%
                    </div>
                    <div class="kpi-sub">{{ data.coverage.behavioural_done }} / {{ data.coverage.total_submissions }} submissions</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Similarity Coverage</div>
                    <div class="kpi-value" :class="coverageClass(data.coverage.similarity_pct)">
                        {{ data.coverage.similarity_pct }}%
                    </div>
                    <div class="kpi-sub">{{ data.coverage.similarity_done }} / {{ data.coverage.total_submissions }} submissions</div>
                </div>
            </div>

            <!-- Drift alert -->
            <div v-if="driftAlert" class="drift-alert">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" width="16" height="16"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                Drift detected: {{ driftAlert }}
            </div>

            <div class="two-col">
                <!-- Signal effectiveness -->
                <div class="card">
                    <h2 class="card-title">Signal Effectiveness</h2>
                    <p class="card-sub">Which signals actually predict confirmed cheating</p>
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Signal</th>
                                <th>Fired</th>
                                <th>Reviewed</th>
                                <th>Confirmed</th>
                                <th>Precision</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            <tr v-for="row in data.signal_effectiveness" :key="row.signal">
                                <td class="signal-name">{{ row.signal }}</td>
                                <td>{{ row.total }}</td>
                                <td class="reviewed-cell">{{ row.confirmed + row.dismissed }}</td>
                                <td>{{ row.confirmed }}</td>
                                <td>
                                    <span class="badge" :class="precisionClass(row.precision)">
                                        {{ fmtPct(row.precision) }}
                                    </span>
                                </td>
                                <td>
                                    <div class="mini-bar-wrap">
                                        <div class="mini-bar" :style="{ width: barWidth(row.precision) }" :class="precisionClass(row.precision)"></div>
                                    </div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>

                <!-- Confidence breakdown -->
                <div class="card">
                    <h2 class="card-title">Confidence Breakdown</h2>
                    <p class="card-sub">Model confidence vs actual confirmed rate</p>
                    <table class="data-table">
                        <thead>
                            <tr><th>Confidence</th><th>Total</th><th>Confirmed</th><th>Precision</th></tr>
                        </thead>
                        <tbody>
                            <tr v-for="(row, level) in data.confidence_breakdown" :key="level">
                                <td>
                                    <span class="badge" :class="levelClass(level)">{{ level }}</span>
                                </td>
                                <td>{{ row.total }}</td>
                                <td>{{ row.confirmed }}</td>
                                <td>
                                    <span class="badge" :class="precisionClass(row.precision)">
                                        {{ fmtPct(row.precision) }}
                                    </span>
                                </td>
                            </tr>
                        </tbody>
                    </table>

                    <h2 class="card-title" style="margin-top:24px">Similarity by Score Range</h2>
                    <p class="card-sub">Where the threshold is set matters</p>
                    <table class="data-table">
                        <thead>
                            <tr><th>Range</th><th>Total</th><th>Confirmed</th><th>Precision</th></tr>
                        </thead>
                        <tbody>
                            <tr v-for="row in data.similarity_by_range" :key="row.range">
                                <td class="mono">{{ row.range }}</td>
                                <td>{{ row.total }}</td>
                                <td>{{ row.confirmed }}</td>
                                <td>
                                    <span class="badge" :class="precisionClass(row.precision)">
                                        {{ fmtPct(row.precision) }}
                                    </span>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- Drift -->
            <div class="card">
                <h2 class="card-title">Activity Drift — Last 7 Days vs Previous 7 Days</h2>
                <div class="drift-grid">
                    <div class="drift-item">
                        <div class="drift-label">Behavioural Flags</div>
                        <div class="drift-nums">
                            <span class="drift-big">{{ data.drift.behavioural_last7d }}</span>
                            <span class="drift-arrow" :class="trendClass(data.drift.behavioural_last7d, data.drift.behavioural_prev7d)">
                                {{ trendArrow(data.drift.behavioural_last7d, data.drift.behavioural_prev7d) }}
                            </span>
                            <span class="drift-prev">was {{ data.drift.behavioural_prev7d }}</span>
                        </div>
                    </div>
                    <div class="drift-item">
                        <div class="drift-label">Similarity Flags</div>
                        <div class="drift-nums">
                            <span class="drift-big">{{ data.drift.similarity_last7d }}</span>
                            <span class="drift-arrow" :class="trendClass(data.drift.similarity_last7d, data.drift.similarity_prev7d)">
                                {{ trendArrow(data.drift.similarity_last7d, data.drift.similarity_prev7d) }}
                            </span>
                            <span class="drift-prev">was {{ data.drift.similarity_prev7d }}</span>
                        </div>
                    </div>
                    <div class="drift-item">
                        <div class="drift-label">Avg Risk Score (last 7d)</div>
                        <div class="drift-nums">
                            <span class="drift-big">{{ data.drift.avg_risk_last7d ?? '—' }}</span>
                            <span class="drift-arrow" :class="trendClass(data.drift.avg_risk_last7d, data.drift.avg_risk_prev7d)">
                                {{ trendArrow(data.drift.avg_risk_last7d, data.drift.avg_risk_prev7d) }}
                            </span>
                            <span class="drift-prev">was {{ data.drift.avg_risk_prev7d ?? '—' }}</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Exam coverage -->
            <div class="card">
                <h2 class="card-title">Coverage Gaps by Exam</h2>
                <p class="card-sub">Exams below 100% may have unchecked submissions</p>
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>Exam</th>
                            <th>Submissions</th>
                            <th>Behavioural</th>
                            <th></th>
                            <th>Similarity</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr v-for="row in data.exam_coverage" :key="row.exam_id">
                            <td>{{ row.exam_title }}</td>
                            <td>{{ row.total }}</td>
                            <td>
                                <span class="badge" :class="coverageClass(row.behavioural_pct)">
                                    {{ row.behavioural_pct }}%
                                </span>
                            </td>
                            <td>
                                <div class="mini-bar-wrap">
                                    <div class="mini-bar coverage-bar" :style="{ width: row.behavioural_pct + '%' }" :class="coverageClass(row.behavioural_pct)"></div>
                                </div>
                            </td>
                            <td>
                                <span class="badge" :class="coverageClass(row.similarity_pct)">
                                    {{ row.similarity_pct }}%
                                </span>
                            </td>
                            <td>
                                <div class="mini-bar-wrap">
                                    <div class="mini-bar coverage-bar" :style="{ width: row.similarity_pct + '%' }" :class="coverageClass(row.similarity_pct)"></div>
                                </div>
                            </td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const loading = ref(true)
const error   = ref('')
const data    = ref<any>(null)

onMounted(async () => {
    try {
        const res = await api.get('/plagiarism/monitoring/')
        data.value = res.data
    } catch {
        error.value = 'Failed to load monitoring data.'
    } finally {
        loading.value = false
    }
})

function fmtPct(v: number | null): string {
    if (v === null || v === undefined) return '—'
    return (v * 100).toFixed(1) + '%'
}

function precisionClass(v: number | null): string {
    if (v === null || v === undefined) return 'badge-dim'
    if (v >= 0.7) return 'badge-green'
    if (v >= 0.4) return 'badge-yellow'
    return 'badge-red'
}

function coverageClass(v: number): string {
    if (v >= 90) return 'badge-green'
    if (v >= 50) return 'badge-yellow'
    return 'badge-red'
}

function levelClass(level: string): string {
    return level === 'high' ? 'badge-red' : level === 'medium' ? 'badge-yellow' : 'badge-dim'
}

function barWidth(v: number | null): string {
    if (v === null || v === undefined) return '0%'
    return (v * 100) + '%'
}

function trendArrow(curr: number | null, prev: number | null): string {
    if (curr === null || prev === null) return '–'
    return curr > prev ? '↑' : curr < prev ? '↓' : '='
}

function trendClass(curr: number | null, prev: number | null): string {
    if (curr === null || prev === null) return ''
    return curr > prev ? 'trend-up' : curr < prev ? 'trend-down' : ''
}

const driftAlert = computed(() => {
    if (!data.value) return null
    const d = data.value.drift
    if (d.behavioural_last7d > d.behavioural_prev7d * 2 && d.behavioural_last7d > 5) {
        return `Behavioural flags doubled this week (${d.behavioural_prev7d} → ${d.behavioural_last7d}). New cheating vector possible.`
    }
    if (d.similarity_last7d > d.similarity_prev7d * 2 && d.similarity_last7d > 3) {
        return `Similarity flags doubled this week (${d.similarity_prev7d} → ${d.similarity_last7d}). Coordinated sharing suspected.`
    }
    return null
})
</script>

<style scoped>
.page { padding: 32px 40px; max-width: 1200px; }
.page-header { margin-bottom: 28px; }
.page-title  { font-size: 22px; font-weight: 700; color: var(--text); margin: 0 0 4px; }
.page-subtitle { font-size: 13px; color: var(--text-dim); margin: 0; }

.loading   { color: var(--text-dim); padding: 40px 0; font-size: 14px; }
.error-msg { color: var(--red); padding: 20px 0; font-size: 14px; }

/* KPI strip */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 24px;
}
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
}
.kpi-label { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; color: var(--text); line-height: 1; margin-bottom: 4px; }
.kpi-value.warn       { color: #f59e0b; }
.kpi-value.badge-green { color: #22c55e; }
.kpi-value.badge-yellow { color: #f59e0b; }
.kpi-value.badge-red   { color: var(--red); }
.kpi-sub { font-size: 11px; color: var(--text-dim); }

/* Drift alert */
.drift-alert {
    display: flex;
    align-items: center;
    gap: 8px;
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.3);
    border-radius: var(--radius-sm);
    padding: 10px 16px;
    font-size: 13px;
    color: #f59e0b;
    margin-bottom: 24px;
}

/* Two-col layout */
.two-col {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    margin-bottom: 16px;
}

/* Cards */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 16px;
}
.card-title { font-size: 15px; font-weight: 600; color: var(--text); margin: 0 0 4px; }
.card-sub   { font-size: 12px; color: var(--text-dim); margin: 0 0 16px; }

/* Table */
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.data-table th {
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    padding: 0 8px 8px;
    border-bottom: 1px solid var(--border);
}
.data-table td {
    padding: 10px 8px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: middle;
}
.data-table tr:last-child td { border-bottom: none; }
.signal-name { font-weight: 600; text-transform: capitalize; }
.reviewed-cell { color: var(--text-muted); }
.mono { font-family: monospace; font-size: 12px; }

/* Badges */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}
.badge-green  { background: rgba(34,197,94,0.12);  color: #22c55e; }
.badge-yellow { background: rgba(245,158,11,0.12); color: #f59e0b; }
.badge-red    { background: rgba(230,57,70,0.12);  color: var(--red); }
.badge-dim    { background: var(--surface2);        color: var(--text-dim); }

/* Mini bar */
.mini-bar-wrap {
    width: 80px;
    height: 6px;
    background: var(--surface2);
    border-radius: 3px;
    overflow: hidden;
}
.mini-bar {
    height: 100%;
    border-radius: 3px;
    transition: width 0.4s ease;
}
.mini-bar.badge-green  { background: #22c55e; }
.mini-bar.badge-yellow { background: #f59e0b; }
.mini-bar.badge-red    { background: var(--red); }
.mini-bar.coverage-bar { background: #3b82f6; }

/* Drift grid */
.drift-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 24px;
    margin-top: 8px;
}
.drift-item { }
.drift-label { font-size: 12px; color: var(--text-dim); margin-bottom: 6px; }
.drift-nums  { display: flex; align-items: baseline; gap: 8px; }
.drift-big   { font-size: 28px; font-weight: 700; color: var(--text); }
.drift-prev  { font-size: 12px; color: var(--text-dim); }
.drift-arrow { font-size: 18px; font-weight: 700; }
.trend-up    { color: var(--red); }
.trend-down  { color: #22c55e; }
</style>
