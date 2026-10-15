<template>
    <div class="dashboard">
        <div class="dash-header">
            <h1>Overview</h1>
        </div>

        <div v-if="loading" class="loading">Loading dashboard...</div>

        <!-- ── OVERVIEW TAB ──────────────────────────────────────────────── -->
        <template v-else>
            <div v-if="loadingHealth" class="loading">Loading overview...</div>

            <template v-else>
                <div class="overview-head">
                    <p class="overview-summary">{{ summarySentence }}</p>
                </div>
                <!-- live counts of what waits on a trainer (the same as the sidebar badges) -->
                <p v-if="waiting.appeals || waiting.cases" class="waiting-line">
                    <template v-if="waiting.appeals"><RouterLink to="/dashboard/support/disputes">{{ plural(waiting.appeals, 'appeal') }}</RouterLink></template>
                    <template v-if="waiting.appeals && waiting.cases"> and </template>
                    <template v-if="waiting.cases"><RouterLink to="/dashboard/plagiarism/cohorts">{{ plural(waiting.cases, 'case') }}</RouterLink></template>
                    waiting for you
                </p>

                <section class="ch-section" aria-labelledby="ch-heading">
                    <div class="ch-heading-row">
                        <h2 id="ch-heading">Section health</h2>
                        <span class="ch-caption">Based on each section's latest graded exam and the three before it</span>
                    </div>

                    <div v-if="health.cohorts.length === 0" class="empty-box">No section data yet.</div>

                    <div v-else class="cohort-grid">
                        <article v-for="c in health.cohorts" :key="c.cohort" class="cohort-card" @click="router.push(sectionLink(c.cohort))">
                            <div class="cc-top">
                                <h3 class="cc-name"><RouterLink :to="sectionLink(c.cohort)" class="cc-name-link" @click.stop>{{ c.cohort }}</RouterLink></h3>
                                <span :class="['state-pill', c.state]">{{ stateLabel(c.state) }}</span>
                                <div class="cc-spacer"></div>
                                <span class="cc-count">{{ plural(c.students, 'student') }}</span>
                            </div>

                            <div v-if="c.latest" class="cc-stat-row">
                                <div class="cc-latest">
                                    <div class="cc-latest-top">
                                        <span class="cc-latest-num">{{ formatPct(c.latest.accepted_rate) }}</span>
                                        <span v-if="c.delta !== null && c.delta !== undefined" :class="['delta-chip', deltaClass(c.delta)]">{{ deltaLabel(c) }}</span>
                                    </div>
                                    <span class="cc-latest-caption" :title="METRIC_HELP.accepted">Success rate, latest graded exam</span>
                                </div>
                                <div class="cc-spark">
                                    <svg :width="SPARK_W" :height="SPARK_H" :viewBox="`0 0 ${SPARK_W} ${SPARK_H}`" role="img" :aria-label="sparkline(c.series).label">
                                        <line x1="0" :y1="sparkline(c.series).y55" :x2="SPARK_W" :y2="sparkline(c.series).y55" stroke="var(--surface3)" stroke-width="1" stroke-dasharray="3 3" />
                                        <polyline :points="sparkline(c.series).points" fill="none" stroke="var(--text)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
                                        <circle :cx="sparkline(c.series).lastX" :cy="sparkline(c.series).lastY" r="4" fill="var(--accent)" />
                                    </svg>
                                    <span class="cc-spark-caption">Success rate, last {{ c.series.length }} exams</span>
                                </div>
                            </div>

                            <div class="cc-bands">
                                <div class="band-bar" role="img" :aria-label="bandLabel(c.bands)">
                                    <span class="band-seg thriving" :style="{ flex: bandFlex(c.bands, 'thriving') }"></span>
                                    <span class="band-seg steady" :style="{ flex: bandFlex(c.bands, 'steady') }"></span>
                                    <span class="band-seg struggling" :style="{ flex: bandFlex(c.bands, 'struggling') }"></span>
                                </div>
                                <div class="band-legend">
                                    <span><span class="dot thriving"></span>{{ c.bands.thriving }} thriving</span>
                                    <span><span class="dot steady"></span>{{ c.bands.steady }} steady</span>
                                    <span><span class="dot struggling"></span>{{ c.bands.struggling }} struggling</span>
                                </div>
                            </div>

                            <div v-if="c.latest" class="cc-footer">
                                <div class="cc-foot-stat">
                                    <span class="cc-foot-label" :title="METRIC_HELP.took">Took the exam</span>
                                    <span class="cc-foot-val mono">{{ c.latest.took }} of {{ c.latest.enrolled }}</span>
                                </div>
                                <div class="cc-foot-stat">
                                    <span class="cc-foot-label" :title="METRIC_HELP.flagged">Flagged students</span>
                                    <span class="cc-foot-val mono" :class="flagClass(c.latest.flagged_students_rate)">{{ formatPct(c.latest.flagged_students_rate) }}</span>
                                </div>
                                <div class="cc-foot-stat">
                                    <span class="cc-foot-label" :title="METRIC_HELP.toReview">Flags to review</span>
                                    <button type="button" class="cc-foot-link mono" @click.stop="router.push('/dashboard/plagiarism/cohorts')">{{ c.flags_to_review }}</button>
                                </div>
                            </div>

                            <p v-if="c.state !== 'on_track'" class="cc-reason">{{ reasonSentence(c) }}</p>
                        </article>
                    </div>
                </section>

                <section class="help-section" aria-labelledby="help-heading">
                    <div class="section-head help-head">
                        <h2 id="help-heading">Students who need help</h2>
                        <span class="ch-caption" :title="METRIC_HELP.acceptedStudent">Success rate below 40% across all exams</span>
                    </div>
                    <div v-if="health.students_needing_help.length === 0" class="empty-box">No students with a success rate below 40%.</div>
                    <div v-else>
                        <div v-for="s in health.students_needing_help" :key="s.student_id" class="help-row">
                            <span class="help-name">{{ s.username }}</span>
                            <span class="mono help-rate">{{ formatPct(s.accepted_rate) }}</span>
                            <span class="help-meta">{{ s.cohort || '—' }}{{ s.flags > 0 ? ', ' + plural(s.flags, 'flag') : '' }}</span>
                            <button type="button" class="help-link" @click="router.push(`/dashboard/students/${s.student_id}`)">View student</button>
                        </div>
                    </div>
                </section>


                <p class="rules-note">{{ rulesSentence }}</p>
            </template>
        </template>

    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'
import { formatDate, formatPct, plural } from '../utils/format'
import { METRIC_HELP } from '../utils/metrics'
import { attention, loadAttention } from '../utils/attention'

const router = useRouter()
// A section card opens the Students page filtered to that section
const sectionLink = (section: string) => ({ name: 'students', query: { section } })
const loading = ref(true)
const loadingHealth = ref(true)

const health = ref<any>({
    summary: { students: 0, cohorts: 0, unassigned_students: 0, latest_exam: null },
    cohorts: [],
    students_needing_help: [],
    rules: { at_risk: {}, watch: {} },
})

const waiting = computed(() => ({
    appeals: attention.data?.open_appeals ?? 0,
    cases: attention.data?.cases_to_decide ?? 0,
}))

onMounted(async () => {
    loadAttention()   // shared with the sidebar's badge request
    try {
        const res = await api.get('/dashboard/health/')
        health.value = res.data
    } finally {
        loading.value = false
        loadingHealth.value = false
    }
})

// ── Overview: summary sentence ──────────────────────────────────────────────

const summarySentence = computed(() => {
    const s = health.value.summary
    const cohortPart = s.cohorts > 0 ? ` in ${plural(s.cohorts, 'section')}` : ''
    const examPart = s.latest_exam ? ` Latest graded exam: ${s.latest_exam.title}, ${formatDate(s.latest_exam.start_time)}.` : ''
    return `${plural(s.students, 'student')}${cohortPart}.${examPart}`
})

// ── Overview: cohort health cards ───────────────────────────────────────────

const STATE_LABELS: Record<string, string> = { on_track: 'On track', watch: 'Watch', at_risk: 'At risk' }
function stateLabel(state: string) {
    return STATE_LABELS[state] || state
}

// Change against the average of up to three exams before the latest one.
function deltaLabel(c: { delta: number | null; series: unknown[] }) {
    if (c.delta === null || c.delta === undefined) return ''
    const prev = Math.min(3, Math.max(0, c.series.length - 1))
    const sign = c.delta >= 0 ? '+' : ''
    return `${sign}${c.delta.toFixed(1)} vs last ${plural(prev, 'exam')}`
}

function deltaClass(delta: number | null) {
    return delta !== null && delta <= -8 ? 'bad' : 'neutral'
}

// Same thresholds the server uses for health (echoed back as `rules`).
function flagClass(rate: number | null) {
    const r = health.value.rules
    if (rate === null || rate === undefined) return 'text-muted'
    if (rate >= (r?.at_risk?.flagged_students_pct ?? 50)) return 'text-red'
    if (rate >= (r?.watch?.flagged_students_pct ?? 30)) return 'text-amber'
    return 'text-muted'
}

interface Bands { thriving: number; steady: number; struggling: number; no_submissions: number }

function bandFlex(bands: Bands, key: 'thriving' | 'steady' | 'struggling') {
    const total = bands.thriving + bands.steady + bands.struggling
    if (!total) return '0 0 0%'
    return `0 0 ${(100 * bands[key] / total).toFixed(1)}%`
}

function bandLabel(bands: Bands) {
    return `${bands.thriving} thriving, ${bands.steady} steady, ${bands.struggling} struggling`
}

const SPARK_W = 180
const SPARK_H = 48
const SPARK_PAD = 6

// Scales a cohort's accepted-% series into the sparkline viewbox, always
// keeping the 55% reference line inside the visible range.
function sparkline(series: Array<{ accepted_rate: number | null }>) {
    const values = series.map((s) => s.accepted_rate).filter((v): v is number => v !== null && v !== undefined)
    if (values.length === 0) {
        return { points: '', lastX: 0, lastY: 0, y55: SPARK_H / 2, label: 'No exam data yet' }
    }
    const lo = Math.min(...values, 55) - 5
    const hi = Math.max(...values, 55) + 5
    const y = (v: number) => (SPARK_H - SPARK_PAD - ((v - lo) / (hi - lo)) * (SPARK_H - 2 * SPARK_PAD)).toFixed(1)
    const step = values.length > 1 ? (SPARK_W - 2 * SPARK_PAD) / (values.length - 1) : 0
    const pts = values.map((v, i) => `${(SPARK_PAD + i * step).toFixed(1)},${y(v)}`)
    const lastPoint = pts[pts.length - 1] ?? '0,0'
    const [lastX, lastY] = lastPoint.split(',')
    return {
        points: pts.join(' '),
        lastX: lastX ?? '0',
        lastY: lastY ?? '0',
        y55: y(55),
        label: `Success rate over the last ${values.length} exams: ${values.join(', ')} percent`,
    }
}

function reasonSentence(c: any) {
    const prefix = c.state === 'at_risk' ? 'At risk' : 'Watch'
    const reasons = c.reasons as string[]
    if (reasons.length === 0) return ''
    if (reasons.length === 1) return `${prefix}: ${reasons[0]}.`
    const head = reasons.slice(0, -1).join(', ')
    const tail = reasons[reasons.length - 1]
    return `${prefix}: ${head}, and ${tail}.`
}

// ── Overview: "how health is decided" ───────────────────────────────────────

const rulesSentence = computed(() => {
    const r = health.value.rules
    if (!r?.at_risk || !r?.watch) return ''
    const a = r.at_risk
    const w = r.watch
    return (
        `How health is decided. At risk: latest graded exam success rate under ${a.latest_accepted_pct}%, ` +
        `at least ${a.struggling_share_pct}% of students struggling, at least ${a.flagged_students_pct}% of students ` +
        `who took the latest graded exam flagged, or fewer than ${a.participation_pct}% of enrolled students taking it. ` +
        `Watch: success rate under ${w.latest_accepted_pct}%, a drop of ${Math.abs(w.delta_pts)} points or more against ` +
        `the previous three exams, at least ${w.struggling_share_pct}% of students struggling, at least ` +
        `${w.flagged_students_pct}% of students flagged, or fewer than ${w.participation_pct}% taking it. Otherwise on track.`
    )
})
</script>

<style scoped>
.dashboard { max-width: 1100px; }
.dash-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
h1 { margin: 0; font-size: 32px; font-weight: 600; }
h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--text); }
h3 { margin: 0 0 16px; font-size: 18px; font-weight: 600; color: var(--text); }


.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.loading { color: var(--text-muted); padding: 40px 0; }

/* ── Overview: header ────────────────────────────────────────────────────── */
.overview-head { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; margin-bottom: 32px; }
.overview-summary { margin: 0; font-size: 15px; color: var(--text-muted); }
.waiting-line { margin: -20px 0 28px; font-size: 15px; font-weight: 500; color: var(--text); }
.waiting-line a { display: inline-flex; align-items: center; min-height: 44px; font-weight: 600; }

.ch-section { display: flex; flex-direction: column; gap: 16px; margin-bottom: 28px; }
.ch-heading-row { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; }
.ch-caption { font-size: 13px; color: var(--text-muted); }

.empty-box { border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 20px; color: var(--text-muted); font-size: 14px; }

/* ── Overview: cohort health cards ───────────────────────────────────────── */
.cohort-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }
.cohort-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 22px 24px;
    display: flex;
    flex-direction: column;
    gap: 18px;
    cursor: pointer;
    transition: border-color 0.15s, box-shadow 0.15s;
}
.cohort-card:hover { border-color: var(--accent); box-shadow: var(--shadow-lg); }
.cc-name-link { color: inherit; text-decoration: none; }
.cohort-card:hover .cc-name-link, .cc-name-link:focus-visible { color: var(--accent); }
.cc-top { display: flex; align-items: center; gap: 10px 12px; flex-wrap: wrap; }
.cc-top h3 { margin: 0; font-size: 18px; }
.cc-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; flex-shrink: 0; }
.cc-spacer { flex-grow: 1; min-width: 0; }
.cc-count { font-size: 13px; color: var(--text-muted); white-space: nowrap; }

.state-pill { padding: 4px 12px; border-radius: var(--radius-pill); font-family: var(--font-display); font-size: 13px; font-weight: 600; }
.state-pill.on_track { background: var(--green-dim); color: var(--green-ink); }
.state-pill.watch { background: var(--yellow-dim); color: var(--amber-ink); }
.state-pill.at_risk { background: var(--red-dim); color: var(--red-ink); }

.cc-stat-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 20px; }
.cc-latest { display: flex; flex-direction: column; gap: 4px; }
.cc-latest-top { display: flex; align-items: baseline; gap: 10px; }
.cc-latest-num { font-family: var(--font-display); font-size: 40px; font-weight: 600; letter-spacing: -0.02em; line-height: 1; color: var(--text); }
.cc-latest-caption { font-size: 13px; color: var(--text-muted); max-width: 220px; }

.delta-chip { font-family: var(--font-mono); font-size: 13px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--surface2); color: var(--text); white-space: nowrap; }
.delta-chip.bad { background: var(--red-dim); color: var(--red-ink); }

.cc-spark { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }
.cc-spark-caption { font-size: 12px; color: var(--text-dim); }

.cc-bands { display: flex; flex-direction: column; gap: 8px; }
.band-bar { display: flex; height: 12px; border-radius: var(--radius-pill); overflow: hidden; gap: 2px; background: var(--surface2); }
.band-seg.thriving { background: var(--green); }
.band-seg.steady { background: var(--border2); }
.band-seg.struggling { background: var(--red); }
.band-legend { display: flex; gap: 16px; font-size: 13px; color: var(--text); }
.band-legend span { display: flex; align-items: center; gap: 6px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.dot.thriving { background: var(--green); }
.dot.steady { background: var(--border2); }
.dot.struggling { background: var(--red); }

.cc-footer { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding-top: 14px; border-top: 1px solid var(--border); }
.cc-foot-stat { display: flex; flex-direction: column; gap: 2px; }
.cc-foot-label { font-size: 12px; color: var(--text-dim); }
.cc-foot-val { font-size: 15px; color: var(--text); }
.cc-foot-link { background: none; border: none; padding: 0; text-align: left; font-size: 15px; font-weight: 500; color: var(--red-ink); cursor: pointer; }
.cc-foot-link:hover { text-decoration: underline; }

.cc-reason { margin: 0; padding: 10px 14px; border-radius: var(--radius-sm); background: var(--yellow-dim); font-size: 13px; line-height: 1.5; color: var(--amber-ink); }

/* ── Overview: students who need help ───────────────────────────────────── */
.help-section { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); overflow: hidden; margin-bottom: 24px; }
.section-head { padding: 20px 24px 14px; display: flex; align-items: baseline; justify-content: space-between; }
.help-head { flex-direction: column; align-items: flex-start; gap: 4px; }

.help-row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 4px 12px;
    padding: 13px 24px;
    border-top: 1px solid var(--border);
}
.help-name { font-weight: 500; font-size: 14px; color: var(--text); }
.help-rate { font-size: 14px; color: var(--red-ink); }
.help-meta { font-size: 13px; color: var(--text-muted); }
.help-link { justify-self: end; background: none; border: none; padding: 0; font-family: var(--font-display); font-size: 13px; font-weight: 600; color: var(--red-ink); cursor: pointer; }
.help-link:hover { text-decoration: underline; }

.rules-note { margin: 0; font-size: 13px; line-height: 1.6; color: var(--text-muted); max-width: 100ch; }

.text-red    { color: var(--red-ink) !important; }
.text-amber  { color: var(--amber-ink) !important; }
.text-muted  { color: var(--text-muted) !important; }

/* ── Responsive ──────────────────────────────────────────────────────────── */
@media (max-width: 899px) {
    .cohort-grid { grid-template-columns: 1fr; }
    .dash-header { flex-wrap: wrap; gap: 12px; }
    .overview-head { flex-wrap: wrap; }
}

@media (max-width: 600px) {
    .cc-footer { grid-template-columns: 1fr 1fr; }
    .ch-heading-row { flex-direction: column; align-items: flex-start; gap: 4px; }
}

/* Phone fixes: grid tracks may shrink below their content, and the card's number and chart stack */
@media (max-width: 899px) {
    .cohort-grid { grid-template-columns: minmax(0, 1fr); }
    .cohort-card { min-width: 0; }
}
@media (max-width: 600px) {
    .cc-stat-row { flex-direction: column; align-items: flex-start; }
    .cc-spark { align-items: flex-start; }
}
</style>
