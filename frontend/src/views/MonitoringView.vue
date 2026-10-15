<template>
    <div class="page">
        <div class="page-header">
            <div>
                <h1>Integrity monitoring</h1>
                <p class="page-subtitle">Model accuracy, signal effectiveness, and coverage gaps</p>
            </div>
        </div>

        <div v-if="loading" class="loading">Loading monitoring data…</div>
        <div v-else-if="error" class="error-msg">{{ error }}</div>

        <template v-else>
            <!-- KPI strip -->
            <div class="kpi-strip">
                <div class="kpi-card">
                    <div class="kpi-label" :title="METRIC_HELP.toReview">Flags to review</div>
                    <div class="kpi-value warn">
                        {{ data.summary.behavioural.flags_to_review }}
                    </div>
                    <div class="kpi-sub">{{ plural(data.summary.similarity.pending, 'similarity pair') }} also pending</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Behavioural precision</div>
                    <div class="kpi-value" :class="precisionClass(data.summary.behavioural.precision)">
                        {{ fmtPct(data.summary.behavioural.precision) }}
                    </div>
                    <div class="kpi-sub">of reviewed flags confirmed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Similarity precision</div>
                    <div class="kpi-value" :class="precisionClass(data.summary.similarity.precision)">
                        {{ fmtPct(data.summary.similarity.precision) }}
                    </div>
                    <div class="kpi-sub">of reviewed flags confirmed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Behavioural coverage</div>
                    <div class="kpi-value" :class="coverageClass(data.coverage.behavioural_pct)">
                        {{ data.coverage.behavioural_pct }}%
                    </div>
                    <div class="kpi-sub">{{ data.coverage.behavioural_done }} / {{ data.coverage.total_submissions }} submissions</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Similarity coverage</div>
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
                    <h2 class="card-title">Signal effectiveness</h2>
                    <p class="card-sub">Which signals best predict cases trainers confirmed</p>
                <div class="table-scroll">
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
                </div>

                <!-- Flag confidence breakdown (high = 3+ signals = most suspicious) -->
                <div class="card">
                    <h2 class="card-title">{{ METRIC_LABEL.confidence }} breakdown</h2>
                    <p class="card-sub">{{ METRIC_HELP.confidence }} Precision is how many reviewed flags were confirmed.</p>
                <div class="table-scroll">
                    <table class="data-table">
                        <thead>
                            <tr><th :title="METRIC_HELP.confidence">{{ METRIC_LABEL.confidence }}</th><th>Total</th><th>Confirmed</th><th>Precision</th></tr>
                        </thead>
                        <tbody>
                            <tr v-for="{ level, row } in confidenceRows" :key="level">
                                <td>
                                    <span class="badge" :class="confidenceClass(level)">{{ humanize(level) }}</span>
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
                </div>

                    <h2 class="card-title" style="margin-top:24px">Similarity by score range</h2>
                    <p class="card-sub">Where the threshold is set matters</p>
                <div class="table-scroll">
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
            </div>

            <!-- Drift -->
            <div class="card">
                <h2 class="card-title">Activity drift — last 7 days vs previous 7 days</h2>
                <div class="drift-grid">
                    <div class="drift-item">
                        <div class="drift-label">Behavioural flags</div>
                        <div class="drift-nums">
                            <span class="drift-big">{{ data.drift.behavioural_last7d }}</span>
                            <span class="drift-arrow" :class="trendClass(data.drift.behavioural_last7d, data.drift.behavioural_prev7d)">
                                {{ trendArrow(data.drift.behavioural_last7d, data.drift.behavioural_prev7d) }}
                            </span>
                            <span class="drift-prev">was {{ data.drift.behavioural_prev7d }}</span>
                        </div>
                    </div>
                    <div class="drift-item">
                        <div class="drift-label">Similarity flags</div>
                        <div class="drift-nums">
                            <span class="drift-big">{{ data.drift.similarity_last7d }}</span>
                            <span class="drift-arrow" :class="trendClass(data.drift.similarity_last7d, data.drift.similarity_prev7d)">
                                {{ trendArrow(data.drift.similarity_last7d, data.drift.similarity_prev7d) }}
                            </span>
                            <span class="drift-prev">was {{ data.drift.similarity_prev7d }}</span>
                        </div>
                    </div>
                    <div class="drift-item">
                        <div class="drift-label">Avg risk score (last 7d)</div>
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
                <h2 class="card-title">Coverage gaps by exam</h2>
                <p class="card-sub">Exams below 100% may have unchecked submissions</p>
                <div class="table-scroll">
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
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'
import { humanize, plural } from '../utils/format'
import { METRIC_HELP, METRIC_LABEL, CONFIDENCE_LEVELS, confidenceClass } from '../utils/metrics'

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

// most suspicious first, whatever order the API returns the keys in
const confidenceRows = computed(() =>
    CONFIDENCE_LEVELS
        .filter(level => data.value?.confidence_breakdown?.[level])
        .map(level => ({ level, row: data.value.confidence_breakdown[level] }))
)

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

function driftMessage(label: string, prev: number, curr: number, followUp: string): string {
    if (prev === 0) {
        return `${label} went from 0 to ${curr} this week. ${followUp}`
    }
    return `${label} more than doubled this week, from ${prev} to ${curr}. ${followUp}`
}

const driftAlert = computed(() => {
    if (!data.value) return null
    const d = data.value.drift
    if (d.behavioural_last7d > d.behavioural_prev7d * 2 && d.behavioural_last7d > 5) {
        return driftMessage('Behavioural flags', d.behavioural_prev7d, d.behavioural_last7d, 'Review recent flags for a new pattern.')
    }
    if (d.similarity_last7d > d.similarity_prev7d * 2 && d.similarity_last7d > 3) {
        return driftMessage('Similarity flags', d.similarity_prev7d, d.similarity_last7d, 'Check whether code is being shared between students.')
    }
    return null
})
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-subtitle { font-size: 15px; color: var(--text-muted); margin: 4px 0 0; }

.loading   { color: var(--text-dim); padding: 40px 0; font-size: 14px; }
.error-msg { color: var(--red-ink); padding: 20px 0; font-size: 14px; }

/* KPI strip */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(5, 1fr);
    gap: 12px;
    margin-bottom: 24px;
}
@media (max-width: 899px) {
    .kpi-strip { grid-template-columns: repeat(2, 1fr); }
    .two-col { grid-template-columns: 1fr; }
}
@media (max-width: 600px) {
    .kpi-strip { grid-template-columns: 1fr; }
    .drift-grid { grid-template-columns: 1fr; }
}
.kpi-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 18px 20px;
}
.kpi-label { font-size: 11px; font-weight: 600; color: var(--text-dim); margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; color: var(--text); line-height: 1; margin-bottom: 4px; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.kpi-value.warn       { color: var(--amber-ink); }
.kpi-value.badge-green { color: var(--green-ink); }
.kpi-value.badge-yellow { color: var(--amber-ink); }
.kpi-value.badge-red   { color: var(--red-ink); }
.kpi-sub { font-size: 11px; color: var(--text-dim); }

/* Drift alert */
.drift-alert {
    display: flex;
    align-items: center;
    gap: 8px;
    background: var(--yellow-dim);
    border: 1px solid var(--yellow);
    border-radius: var(--radius-sm);
    padding: 10px 16px;
    font-size: 13px;
    color: var(--amber-ink);
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
.table-scroll { overflow-x: auto; }
.data-table { width: 100%; min-width: 480px; border-collapse: collapse; font-size: 13px; }
.data-table th {
    text-align: left;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-dim);
    padding: 0 8px 8px;
    border-bottom: 1px solid var(--border);
}
.data-table td {
    padding: 10px 8px;
    border-bottom: 1px solid var(--border);
    color: var(--text);
    vertical-align: middle;
    font-variant-numeric: tabular-nums;
}
.data-table tr:last-child td { border-bottom: none; }
.signal-name { font-weight: 600; text-transform: capitalize; }
.reviewed-cell { color: var(--text-muted); }
.mono { font-family: var(--font-mono); font-size: 12px; }

/* Badges */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
    font-weight: 600;
}
.badge-green  { background: var(--green-dim);  color: var(--green-ink); }
.badge-yellow { background: var(--yellow-dim); color: var(--amber-ink); }
.badge-red    { background: var(--red-dim);    color: var(--red-ink); }
.badge-dim    { background: var(--surface2);   color: var(--text-dim); }

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
.mini-bar.badge-green  { background: var(--green); }
.mini-bar.badge-yellow { background: var(--yellow); }
.mini-bar.badge-red    { background: var(--red); }

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
.drift-big   { font-size: 28px; font-weight: 700; color: var(--text); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.drift-prev  { font-size: 12px; color: var(--text-dim); font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.drift-arrow { font-size: 18px; font-weight: 700; }
.trend-up    { color: var(--red-ink); }
.trend-down  { color: var(--green-ink); }

/* Phone fixes. These must come after the base rules above, otherwise the
   two-column defaults win on source order. */
.two-col > *, .card { min-width: 0; }
@media (max-width: 899px) {
    .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .two-col { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 600px) {
    .kpi-strip { grid-template-columns: minmax(0, 1fr); }
    .drift-grid { grid-template-columns: minmax(0, 1fr); }
}
</style>
