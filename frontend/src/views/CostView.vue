<template>
    <div class="cost-page">
        <div class="page-header">
            <div>
                <h1>Cost Analysis</h1>
                <p class="page-sub">AWS Fargate pricing · 0.5 vCPU · 128 MB · per-submission compute cost</p>
            </div>
        </div>

        <div v-if="loading" class="state-msg">Calculating costs...</div>

        <template v-else>
            <!-- ── Summary KPI strip ─────────────────────────────────────── -->
            <div class="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-label">Total Compute Spend</div>
                    <div class="kpi-value">${{ data.summary.total_compute_cost.toFixed(4) }}</div>
                    <div class="kpi-sub">all time · {{ data.summary.total_submissions }} submissions</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Cost per Submission</div>
                    <div class="kpi-value">${{ data.summary.avg_cost_per_submission.toFixed(5) }}</div>
                    <div class="kpi-sub">avg exec {{ data.summary.avg_exec_ms }}ms + 2s cold start</div>
                </div>
                <div class="kpi-card warn-card">
                    <div class="kpi-label">Wasted on Failures</div>
                    <div class="kpi-value text-red">${{ data.summary.wasted_cost.toFixed(4) }}</div>
                    <div class="kpi-sub">{{ data.summary.waste_pct }}% of compute spend</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Monthly Projection</div>
                    <div class="kpi-value">${{ data.summary.monthly_total_projection.toFixed(2) }}</div>
                    <div class="kpi-sub">${{ data.summary.monthly_compute_projection.toFixed(2) }} compute + ${{ data.summary.monthly_fixed_cost.toFixed(0) }} fixed</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Weekly Compute</div>
                    <div class="kpi-value">${{ data.summary.weekly_compute_cost.toFixed(4) }}</div>
                    <div class="kpi-sub">last 7 days actual</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-label">Retry Waste</div>
                    <div class="kpi-value text-yellow">${{ data.summary.retry_cost.toFixed(4) }}</div>
                    <div class="kpi-sub">cost of attempt 2 & 3</div>
                </div>
            </div>

            <!-- ── Infrastructure breakdown ─────────────────────────────── -->
            <div class="section-row">
                <div class="infra-card">
                    <div class="card-title">Infrastructure Breakdown</div>
                    <div class="infra-row">
                        <span class="infra-label">Compute (Docker containers)</span>
                        <div class="infra-bar-wrap">
                            <div class="infra-bar compute-bar" :style="{ width: computePct + '%' }" />
                        </div>
                        <span class="infra-cost">${{ data.summary.monthly_compute_projection.toFixed(2) }}/mo</span>
                    </div>
                    <div class="infra-row">
                        <span class="infra-label">Redis (ElastiCache t3.micro)</span>
                        <div class="infra-bar-wrap">
                            <div class="infra-bar redis-bar" :style="{ width: redisPct + '%' }" />
                        </div>
                        <span class="infra-cost">${{ data.infrastructure.redis_monthly.toFixed(2) }}/mo</span>
                    </div>
                    <div class="infra-row">
                        <span class="infra-label">PostgreSQL (RDS t3.micro)</span>
                        <div class="infra-bar-wrap">
                            <div class="infra-bar db-bar" :style="{ width: dbPct + '%' }" />
                        </div>
                        <span class="infra-cost">${{ data.infrastructure.database_monthly.toFixed(2) }}/mo</span>
                    </div>
                    <div class="infra-row">
                        <span class="infra-label">Celery Worker (EC2 t3.small)</span>
                        <div class="infra-bar-wrap">
                            <div class="infra-bar celery-bar" :style="{ width: celeryPct + '%' }" />
                        </div>
                        <span class="infra-cost">${{ data.infrastructure.celery_worker_monthly.toFixed(2) }}/mo</span>
                    </div>
                    <div class="infra-total">
                        <span>Total estimated monthly</span>
                        <span class="infra-total-val">${{ data.summary.monthly_total_projection.toFixed(2) }}</span>
                    </div>
                    <div class="pricing-note">Based on {{ data.infrastructure.pricing_basis }}</div>
                </div>

                <div class="container-card">
                    <div class="card-title">Container Config</div>
                    <div class="config-row">
                        <span class="config-key">CPU</span>
                        <span class="config-val">{{ data.infrastructure.container_vcpu }} vCPU</span>
                    </div>
                    <div class="config-row">
                        <span class="config-key">Memory</span>
                        <span class="config-val">{{ data.infrastructure.container_memory_gb * 1024 }}MB</span>
                    </div>
                    <div class="config-row">
                        <span class="config-key">Cold start</span>
                        <span class="config-val">~{{ data.infrastructure.cold_start_ms }}ms</span>
                    </div>
                    <div class="config-row">
                        <span class="config-key">Avg exec</span>
                        <span class="config-val">{{ data.summary.avg_exec_ms }}ms</span>
                    </div>
                    <div class="config-row">
                        <span class="config-key">vCPU rate</span>
                        <span class="config-val">$0.04048/hr</span>
                    </div>
                    <div class="config-row">
                        <span class="config-key">Memory rate</span>
                        <span class="config-val">$0.004445/GB-hr</span>
                    </div>
                    <div class="config-divider" />
                    <div class="config-row highlight">
                        <span class="config-key">Cost per sub</span>
                        <span class="config-val">${{ data.summary.avg_cost_per_submission.toFixed(5) }}</span>
                    </div>
                    <div class="config-row highlight">
                        <span class="config-key">1000 subs cost</span>
                        <span class="config-val">${{ (data.summary.avg_cost_per_submission * 1000).toFixed(3) }}</span>
                    </div>
                </div>
            </div>

            <!-- ── Language cost breakdown ───────────────────────────────── -->
            <div class="card">
                <div class="card-title">Cost by Language</div>
                <div class="lang-table">
                    <div class="lang-header">
                        <span>Language</span>
                        <span>Submissions</span>
                        <span>Avg Exec Time</span>
                        <span>Avg Cost / Sub</span>
                        <span>Total Spend</span>
                        <span>Relative Cost</span>
                    </div>
                    <div v-for="(d, lang) in data.by_language" :key="lang" class="lang-row">
                        <span class="lang-name">
                            <span :class="['lang-dot', lang]" />
                            {{ lang }}
                        </span>
                        <span class="lang-val">{{ d.count }}</span>
                        <span class="lang-val" :class="d.avg_exec_ms > 2000 ? 'text-red' : d.avg_exec_ms > 1000 ? 'text-yellow' : 'text-green'">
                            {{ d.avg_exec_ms }}ms
                        </span>
                        <span class="lang-val">${{ d.avg_cost_per_sub.toFixed(6) }}</span>
                        <span class="lang-val">${{ d.total_cost.toFixed(4) }}</span>
                        <span class="lang-bar-cell">
                            <div class="lang-bar-wrap">
                                <div class="lang-bar"
                                    :style="{ width: (d.total_cost / maxLangCost * 100) + '%' }"
                                    :class="d.avg_exec_ms > 2000 ? 'bar-red' : d.avg_exec_ms > 1000 ? 'bar-yellow' : 'bar-green'" />
                            </div>
                        </span>
                    </div>
                </div>
            </div>

            <!-- ── Per-exam cost breakdown ───────────────────────────────── -->
            <div class="card">
                <div class="card-title">Cost by Exam</div>
                <div class="exam-table">
                    <div class="exam-header">
                        <span>Exam</span>
                        <span>Submissions</span>
                        <span>Total Cost</span>
                        <span>Wasted (failed)</span>
                        <span>Retry Cost</span>
                        <span>Cost / Student</span>
                        <span>Waste %</span>
                    </div>
                    <div v-for="exam in data.by_exam" :key="exam.exam_id" class="exam-row">
                        <span class="exam-name">{{ exam.title }}</span>
                        <span class="exam-val">{{ exam.total_submissions }}</span>
                        <span class="exam-val bold">${{ exam.total_cost_usd.toFixed(4) }}</span>
                        <span class="exam-val text-red">${{ exam.wasted_cost_usd.toFixed(4) }}</span>
                        <span class="exam-val text-yellow">${{ exam.retry_cost_usd.toFixed(4) }}</span>
                        <span class="exam-val">${{ exam.cost_per_student.toFixed(5) }}</span>
                        <span class="exam-val">
                            <span :class="['waste-badge', exam.waste_pct > 40 ? 'high' : exam.waste_pct > 20 ? 'mid' : 'low']">
                                {{ exam.waste_pct }}%
                            </span>
                        </span>
                    </div>
                </div>
            </div>

            <!-- ── Optimisation suggestions ──────────────────────────────── -->
            <div class="card">
                <div class="card-title">Optimisation Recommendations</div>
                <div class="suggestions-list">
                    <div v-for="(s, i) in data.optimizations" :key="i" :class="['suggestion', s.type]">
                        <div class="sug-left">
                            <span :class="['sug-badge', s.type]">{{ s.type }}</span>
                        </div>
                        <div class="sug-body">
                            <div class="sug-title">{{ s.title }}</div>
                            <div class="sug-detail">{{ s.detail }}</div>
                            <div class="sug-action">
                                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>
                                {{ s.action }}
                            </div>
                        </div>
                        <div class="sug-savings">
                            <div class="savings-label">Potential saving</div>
                            <div class="savings-val">{{ s.savings }}</div>
                        </div>
                    </div>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const loading = ref(true)
const data = ref<any>({
    summary: {},
    infrastructure: {},
    by_exam: [],
    by_language: {},
    optimizations: [],
})

onMounted(async () => {
    const res = await api.get('/dashboard/costs/')
    data.value = res.data
    loading.value = false
})

const totalMonthly = computed(() => data.value.summary.monthly_total_projection || 1)
const computePct  = computed(() => Math.round(data.value.summary.monthly_compute_projection / totalMonthly.value * 100))
const redisPct    = computed(() => Math.round(data.value.infrastructure.redis_monthly / totalMonthly.value * 100))
const dbPct       = computed(() => Math.round(data.value.infrastructure.database_monthly / totalMonthly.value * 100))
const celeryPct   = computed(() => Math.round(data.value.infrastructure.celery_worker_monthly / totalMonthly.value * 100))

const maxLangCost = computed(() =>
    Math.max(...Object.values(data.value.by_language).map((d: any) => d.total_cost), 0.0001)
)
</script>

<style scoped>
.page-header { margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 13px; margin-top: 4px; font-family: monospace; }
.state-msg { color: var(--text-muted); padding: 40px 0; }

/* KPI strip */
.kpi-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin-bottom: 20px; }
.kpi-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 20px; }
.warn-card { border-color: rgba(230,57,70,0.3); background: rgba(230,57,70,0.04); }
.kpi-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 6px; }
.kpi-value { font-size: 26px; font-weight: 700; color: var(--text); font-variant-numeric: tabular-nums; }
.kpi-sub { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.text-red    { color: var(--red) !important; }
.text-yellow { color: var(--yellow) !important; }
.text-green  { color: var(--green) !important; }

/* Section row */
.section-row { display: flex; gap: 16px; margin-bottom: 16px; }
.infra-card { flex: 2; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; }
.container-card { flex: 1; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 22px; margin-bottom: 16px; }
.card-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-muted); margin-bottom: 18px; }

/* Infrastructure bars */
.infra-row { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }
.infra-label { font-size: 13px; color: var(--text-muted); width: 220px; flex-shrink: 0; }
.infra-bar-wrap { flex: 1; height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.infra-bar { height: 100%; border-radius: 3px; transition: width 0.5s; }
.compute-bar { background: var(--red); }
.redis-bar   { background: #e67e22; }
.db-bar      { background: #3498db; }
.celery-bar  { background: #9b59b6; }
.infra-cost { font-size: 13px; font-weight: 600; color: var(--text); width: 80px; text-align: right; font-variant-numeric: tabular-nums; }
.infra-total { display: flex; justify-content: space-between; align-items: center; padding-top: 14px; border-top: 1px solid var(--border); margin-top: 6px; font-size: 14px; color: var(--text-muted); }
.infra-total-val { font-size: 20px; font-weight: 700; color: var(--text); }
.pricing-note { font-size: 11px; color: var(--text-dim); margin-top: 10px; font-family: monospace; }

/* Container config */
.config-row { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 13px; }
.config-row:last-child { border-bottom: none; }
.config-key { color: var(--text-dim); }
.config-val { font-weight: 600; color: var(--text); font-family: monospace; }
.config-divider { height: 1px; background: var(--border2); margin: 8px 0; }
.config-row.highlight .config-key { color: var(--text-muted); }
.config-row.highlight .config-val { color: var(--red); }

/* Language table */
.lang-table, .exam-table { width: 100%; }
.lang-header, .lang-row,
.exam-header, .exam-row {
    display: grid;
    gap: 12px;
    padding: 10px 0;
    align-items: center;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}
.lang-header, .exam-header {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
}
.lang-header { grid-template-columns: 120px 90px 110px 120px 100px 1fr; }
.lang-row    { grid-template-columns: 120px 90px 110px 120px 100px 1fr; }
.lang-row:last-child, .exam-row:last-child { border-bottom: none; }

.exam-header { grid-template-columns: 1fr 90px 90px 110px 90px 100px 80px; }
.exam-row    { grid-template-columns: 1fr 90px 90px 110px 90px 100px 80px; }

.lang-name { display: flex; align-items: center; gap: 8px; font-weight: 600; color: var(--text); }
.lang-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.lang-dot.python     { background: #3498db; }
.lang-dot.javascript { background: #f1c40f; }
.lang-dot.java       { background: #e67e22; }
.lang-dot.cpp        { background: #9b59b6; }
.lang-val { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.lang-bar-wrap { height: 6px; background: var(--surface3); border-radius: 3px; overflow: hidden; }
.lang-bar { height: 100%; border-radius: 3px; transition: width 0.5s; }
.bar-green  { background: var(--green); }
.bar-yellow { background: var(--yellow); }
.bar-red    { background: var(--red); }
.lang-bar-cell { display: flex; align-items: center; }

.exam-name { color: var(--text); font-weight: 500; }
.exam-val { color: var(--text-muted); font-variant-numeric: tabular-nums; }
.exam-val.bold { font-weight: 700; color: var(--text); }
.waste-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 10px; }
.waste-badge.high { background: var(--red-dim); color: var(--red); }
.waste-badge.mid  { background: rgba(241,196,15,0.1); color: var(--yellow); }
.waste-badge.low  { background: rgba(46,204,113,0.1); color: var(--green); }

/* Suggestions */
.suggestions-list { display: flex; flex-direction: column; gap: 12px; }
.suggestion {
    display: flex;
    gap: 16px;
    padding: 16px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
    background: var(--surface2);
    align-items: flex-start;
}
.suggestion.high   { border-color: rgba(230,57,70,0.3); background: rgba(230,57,70,0.04); }
.suggestion.medium { border-color: rgba(241,196,15,0.3); background: rgba(241,196,15,0.04); }
.suggestion.low    { border-color: var(--border); }

.sug-left { flex-shrink: 0; }
.sug-badge {
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 3px 8px;
    border-radius: 10px;
}
.sug-badge.high   { background: var(--red-dim); color: var(--red); }
.sug-badge.medium { background: rgba(241,196,15,0.12); color: var(--yellow); }
.sug-badge.low    { background: var(--surface3); color: var(--text-dim); }

.sug-body { flex: 1; }
.sug-title { font-size: 14px; font-weight: 600; color: var(--text); margin-bottom: 5px; }
.sug-detail { font-size: 13px; color: var(--text-muted); line-height: 1.6; margin-bottom: 8px; }
.sug-action { font-size: 12px; color: var(--text-dim); display: flex; align-items: center; gap: 5px; font-style: italic; }

.sug-savings { flex-shrink: 0; text-align: right; min-width: 120px; }
.savings-label { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; color: var(--text-dim); margin-bottom: 4px; }
.savings-val { font-size: 15px; font-weight: 700; color: var(--green); }
</style>
