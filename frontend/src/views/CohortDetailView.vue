<template>
    <div class="page case-file">
        <!-- opened from a student's page or an exam report: the way back comes first -->
        <router-link v-if="from && data" :to="fromLink" class="from-back">← {{ fromLabel }}</router-link>

        <nav class="crumbs" aria-label="Breadcrumb">
            <router-link to="/dashboard/plagiarism/cohorts">Investigation</router-link>
            <template v-if="data">
                <span class="crumb-sep" aria-hidden="true">/</span>
                <router-link v-if="caseKey" :to="allCasesLink">{{ data.exam.title }}</router-link>
                <span v-else aria-current="page" class="crumb-here">{{ data.exam.title }}</span>
                <template v-if="caseKey && openCase">
                    <span class="crumb-sep" aria-hidden="true">/</span>
                    <span aria-current="page" class="crumb-here">Case {{ openCase.number }}</span>
                </template>
            </template>
        </nav>

        <div v-if="loading" class="state-msg">Loading the exam's cases…</div>
        <div v-else-if="error" class="state-msg error-msg" role="alert">{{ error }}</div>

        <!-- ── ALL CASES ──────────────────────────────────────────────────── -->
        <template v-else-if="data && !caseKey">
            <div class="page-header">
                <div class="title-row">
                    <h1>{{ data.exam.title }}</h1>
                    <span :class="['status-chip', data.exam.status]">{{ examStatusLabel(data.exam.status) }}</span>
                </div>
                <p class="meta-line">{{ metaLine }}</p>
            </div>

            <div class="kpi-strip">
                <div class="kpi-cell" :title="METRIC_HELP.took">
                    <span class="kpi-value">{{ data.stats.took }}<span class="kpi-of">/{{ data.stats.enrolled }}</span></span>
                    <span class="kpi-label">Took the exam</span>
                </div>
                <div class="kpi-cell" :title="METRIC_HELP.flagged">
                    <span :class="['kpi-value', { danger: data.stats.flagged_students > 0 }]">{{ formatPct(data.stats.flagged_students_rate) }}</span>
                    <span class="kpi-label">Flagged students</span>
                </div>
                <div class="kpi-cell">
                    <span class="kpi-value">{{ data.stats.similarity_count }}</span>
                    <span class="kpi-label">{{ data.stats.similarity_count === 1 ? 'Similarity pair' : 'Similarity pairs' }}</span>
                </div>
                <div class="kpi-cell">
                    <span :class="['kpi-value', { danger: data.stats.cases_to_decide > 0 }]">{{ data.stats.cases_to_decide }}</span>
                    <span class="kpi-label">{{ data.stats.cases_to_decide === 1 ? 'Case to decide' : 'Cases to decide' }}</span>
                </div>
            </div>

            <div class="columns">
                <section class="main-col" aria-labelledby="cases-h">
                    <div class="section-head">
                        <h2 id="cases-h">Cases to decide</h2>
                        <span class="section-sub">A case groups students whose code matches, with their behaviour</span>
                    </div>

                    <p v-if="data.cases.length === 0" class="card quiet-card">No cases on this exam.</p>

                    <template v-for="c in data.cases" :key="c.key">
                        <!-- a case still waiting: the full card -->
                        <router-link v-if="c.status === 'pending'" :to="caseLink(c.key)" class="card case-card">
                            <div class="case-card-head">
                                <span class="case-chip">Case {{ c.number }}</span>
                                <span v-if="isLargeCase(c)" class="case-names">{{ c.members.length }} students</span>
                                <span v-else class="case-names"><NameList :names="c.members.map(m => m.username)" /></span>
                                <span v-if="labelFor(c)" :class="['label-chip', labelClass(labelFor(c))]">{{ labelFor(c) }}</span>
                                <span v-if="caseAppeals(c).length" class="appeal-chip">Appeal pending</span>
                                <span class="grow"></span>
                                <template v-if="c.pairs.length">
                                    <span class="case-pct">{{ pct(c.max_similarity) }}</span>
                                    <span class="case-pct-label">code match</span>
                                </template>
                                <span v-else-if="c.max_risk !== null" class="case-pct-label">Risk <span class="case-risk">{{ c.max_risk }}</span></span>
                            </div>

                            <template v-if="isLargeCase(c)">
                                <p class="large-summary">
                                    {{ formatPct(shareOfTakers(c.members.length, data.stats.took)) }} of students who took the exam
                                    · {{ plural(flaggedMembers(c), 'member') }} with behaviour flags
                                </p>
                                <ul class="highlights">
                                    <li v-for="h in caseHighlights(c)" :key="h.member.student_id">
                                        <strong>{{ h.member.username }}</strong>
                                        <template v-if="h.partner"> · code matches <strong>{{ h.partner.username }}</strong> {{ pct(h.score ?? 0) }}</template>
                                    </li>
                                </ul>
                            </template>
                            <div v-else-if="topSignals(c).length" class="sig-row">
                                <span v-for="(s, i) in topSignals(c)" :key="i" class="sig"><strong>{{ s.name }}</strong> {{ s.text }}</span>
                            </div>

                            <div class="case-card-foot">
                                <span>{{ waitingLine(c, !isLargeCase(c)) }}</span>
                                <span class="grow"></span>
                                <span class="open-link">Open case →</span>
                            </div>
                        </router-link>

                        <!-- a decided case: one line with its outcome -->
                        <router-link v-else :to="caseLink(c.key)" class="card case-row">
                            <span class="case-chip muted">Case {{ c.number }}</span>
                            <span class="case-row-names">
                                <template v-if="isLargeCase(c)">{{ c.members.length }} students</template>
                                <NameList v-else :names="c.members.map(m => m.username)" />
                            </span>
                            <span :class="['outcome-chip', c.status]">{{ caseStatusLabel(c.status) }}</span>
                            <span v-if="caseAppeals(c).length" class="appeal-chip">Appeal pending</span>
                            <span class="grow"></span>
                            <span class="open-link">Open →</span>
                        </router-link>
                    </template>

                    <p v-if="data.cases.length" class="card quiet-card all-clear">
                        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5L20 7"/></svg>
                        No other students have flags on this exam.
                    </p>

                </section>

                <aside class="side-col" aria-labelledby="clusters-h">
                    <h2 id="clusters-h">Similarity clusters</h2>
                    <div class="card cluster-card">
                        <p class="section-sub">Students connected by matching code. Select a cluster to open its case.</p>
                        <p v-if="data.rings.length === 0" class="cluster-empty">No students share matching code on this exam.</p>
                        <router-link
                            v-for="r in data.rings"
                            :key="r.case ?? r.members[0]?.student_id"
                            :to="r.case ? caseLink(r.case) : allCasesLink"
                            class="cluster-row"
                        >
                            <svg v-if="r.size <= LARGE_CASE_SIZE" class="cluster-drawing" viewBox="0 0 240 110" aria-hidden="true">
                                <line v-for="(e, i) in drawing(r).edges" :key="'e' + i" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2" class="edge" />
                                <g v-for="n in drawing(r).nodes" :key="n.id">
                                    <circle :cx="n.x" :cy="n.y" r="17" :class="['node', { flagged: n.flagged }]" />
                                    <text :x="n.x" :y="n.y + 4" text-anchor="middle" class="node-text">{{ n.initials }}</text>
                                </g>
                            </svg>
                            <span class="cluster-top">
                                <strong>{{ r.size }} students</strong>
                                <span :class="['label-chip', labelClass(clusterLabel(r.size, data.stats.took))]">{{ clusterLabel(r.size, data.stats.took) }}</span>
                            </span>
                            <span v-if="r.size <= LARGE_CASE_SIZE" class="cluster-names">{{ r.members.map(m => m.username).join(', ') }}</span>
                            <span class="share">
                                <span class="share-track"><span class="share-fill" :style="{ width: (shareOfTakers(r.size, data.stats.took) ?? 0) + '%' }"></span></span>
                                <span class="share-val">{{ formatPct(shareOfTakers(r.size, data.stats.took)) }} of takers</span>
                            </span>
                            <span class="cluster-meta">
                                avg similarity {{ pct(r.avg_similarity) }}
                                · {{ plural(flaggedInRing(r), 'member') }} with behaviour flags
                                <template v-if="r.case"> · Case {{ caseNumber(r.case) }}</template>
                            </span>
                        </router-link>
                    </div>
                </aside>
            </div>
        </template>

        <!-- ── ONE CASE ───────────────────────────────────────────────────── -->
        <template v-else-if="data && caseKey">
            <div v-if="!openCase" class="card quiet-card">
                This case isn't on this exam any more: its flags may have been decided separately.
                <router-link :to="allCasesLink">See all cases</router-link>
            </div>

            <div v-else class="case-view">
                <div class="case-head">
                    <router-link :to="allCasesLink" class="back-pill">← All cases</router-link>
                    <h1 class="case-title">
                        <template v-if="isLargeCase(openCase)">Case {{ openCase.number }} · {{ openCase.members.length }} students</template>
                        <NameList v-else :names="openCase.members.map(m => m.username)" />
                    </h1>
                    <span :class="['outcome-chip', openCase.status]">{{ caseStatusLabel(openCase.status) }}</span>
                    <span v-if="labelFor(openCase)" :class="['label-chip', labelClass(labelFor(openCase))]">{{ labelFor(openCase) }}</span>
                </div>

                <!-- a student in this case answered its decision: the trainer rules on the appeal page -->
                <section v-if="caseAppeals(openCase).length" class="card appeal-note" aria-labelledby="appeal-note-h">
                    <h2 id="appeal-note-h" class="appeal-chip">Appeal pending</h2>
                    <p v-for="a in caseAppeals(openCase)" :key="a.id" class="appeal-line">
                        <strong>{{ usernameOf(a.student_id) }}</strong> responded: “{{ a.student_note }}”
                        <router-link :to="`/dashboard/support/disputes/${a.id}`" class="appeal-open">Open appeal →</router-link>
                    </p>
                </section>

                <div class="card verdict-card">
                    <span v-if="openCase.pairs.length" class="verdict-pct">{{ pct(openCase.max_similarity) }}</span>
                    <p class="verdict-text">{{ caseVerdict(openCase) }}</p>
                </div>

                <div class="behaviour-grid">
                    <section
                        v-for="{ member: m, flags, top } in behaviourCards"
                        :key="m.student_id"
                        :class="['card', 'behaviour-card', { focus: isFocus(m.student_id) }]"
                        :aria-label="`${m.username}'s behaviour`"
                    >
                        <div class="behaviour-head">
                            <h2 class="card-title">
                                <router-link :to="`/dashboard/students/${m.student_id}`" class="student-link">{{ m.username }}</router-link>
                            </h2>
                            <span v-if="isFocus(m.student_id)" class="chip focus-chip">Opened from their page</span>
                            <template v-if="top">
                                <span :class="['chip', confidenceClass(top.confidence)]" :title="METRIC_HELP.confidence">{{ confidenceLabel(top.confidence) }}</span>
                                <span :class="['risk-score', riskClass(top.risk_score)]">Risk {{ formatRisk(top.risk_score) }}</span>
                            </template>
                            <span v-if="pastFlags(m.student_id)" class="chip past-chip" title="Behaviour or similarity flags on earlier exams">{{ plural(pastFlags(m.student_id), 'earlier flag') }}</span>
                        </div>
                        <p v-if="flags.length === 0" class="no-flags">No behaviour flags on this exam.</p>
                        <div v-for="f in flags" :key="f.id" class="behaviour-flag">
                            <p class="flag-meta">
                                <template v-if="data.exam.question_count > 1">{{ f.question_title }} · </template>
                                Attempt {{ f.attempt_number }} · {{ submissionStatusLabel(f.submission_status).toLowerCase() }} · {{ formatDateTime(f.submitted_at) }}
                                <span v-if="f.review_status !== 'pending'" :class="['review-badge', f.review_status]">{{ humanize(f.review_status) }}</span>
                            </p>
                            <BehaviourEvidence :flag="f" />
                        </div>
                    </section>
                </div>
                <p v-if="isLargeCase(openCase)" class="others-note">
                    {{ plural(openCase.members.length - behaviourCards.length, 'other student') }} in this group {{ openCase.members.length - behaviourCards.length === 1 ? 'has' : 'have' }} no behaviour flags.
                </p>

                <!-- Matching code: who matches whom, then one comparison at a time -->
                <section v-if="selectedPair" class="card match-card" aria-labelledby="match-h">
                    <div class="match-head">
                        <h2 id="match-h" class="card-title">Matching code</h2>
                        <p class="match-summary">{{ similaritySummary(openCase) }}</p>
                    </div>

                    <div v-if="students.length > 2 && students.length <= GRID_MAX_STUDENTS" class="grid-scroll">
                        <table class="sim-grid">
                            <caption class="sr-only">Similarity between the students in this case. Choose a cell to compare their code below.</caption>
                            <thead>
                                <tr>
                                    <td></td>
                                    <th v-for="s in students" :key="s.student_id" scope="col" :class="{ focus: isFocus(s.student_id) }">
                                        <span class="grid-name" :title="s.username">{{ s.username }}</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                <tr v-for="row in gridRows" :key="row.student.student_id">
                                    <th scope="row" :class="{ focus: isFocus(row.student.student_id) }"><span class="grid-name" :title="row.student.username">{{ row.student.username }}</span></th>
                                    <td v-for="cell in row.cells" :key="cell.student.student_id"
                                        :class="{ focus: isFocus(row.student.student_id) || isFocus(cell.student.student_id) }">
                                        <button
                                            v-if="cell.top"
                                            type="button"
                                            :class="['grid-cell', `step-${shadeStep(cell.top.similarity_score)}`]"
                                            :aria-label="`Compare ${row.student.username} and ${cell.student.username}, ${pct(cell.top.similarity_score)} match`"
                                            :aria-pressed="isSelected(cell.pairs)"
                                            @click="selectPair(cell.top)"
                                        >{{ pct(cell.top.similarity_score) }}</button>
                                        <template v-else>
                                            <span class="grid-empty" aria-hidden="true">—</span>
                                            <span class="sr-only">{{ cell.student.student_id === row.student.student_id ? 'Same student' : 'No flagged match' }}</span>
                                        </template>
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                        <p v-if="focusInGrid" class="focus-note">{{ nameOf(from!.id) }}'s row and column are highlighted.</p>
                    </div>

                    <div v-else-if="students.length > GRID_MAX_STUDENTS" class="pair-list-wrap">
                        <ul class="pair-list" aria-label="Similarity pairs, strongest first">
                            <li v-for="p in listedPairs" :key="p.id">
                                <button
                                    type="button"
                                    class="pair-line"
                                    :aria-pressed="p.id === selectedPair.id"
                                    :aria-label="`Compare ${nameOf(p.student_1_id)} and ${nameOf(p.student_2_id)}, ${pct(p.similarity_score)} match`"
                                    @click="selectPair(p)"
                                >
                                    <span class="pair-line-names">{{ nameOf(p.student_1_id) }} and {{ nameOf(p.student_2_id) }}</span>
                                    <span :class="['pair-line-pct', `step-${shadeStep(p.similarity_score)}`]">{{ pct(p.similarity_score) }}</span>
                                    <span v-if="data.exam.question_count > 1" class="pair-question">{{ p.question_title }}</span>
                                </button>
                            </li>
                        </ul>
                        <button v-if="!showAllPairs && rankedPairs.length > LIST_PAGE" type="button" class="more-btn" @click="showAllPairs = true">
                            Show all {{ rankedPairs.length }} pairs
                        </button>
                    </div>

                    <!-- The one comparison -->
                    <div class="viewer">
                        <div class="viewer-head">
                            <h3 class="viewer-title">
                                {{ nameOf(selectedPair.student_1_id) }} and {{ nameOf(selectedPair.student_2_id) }} · <span class="pair-pct">{{ pct(selectedPair.similarity_score) }}</span> match
                            </h3>
                            <span v-if="data.exam.question_count > 1" class="pair-question">{{ selectedPair.question_title }}</span>
                            <span v-if="selectedPair.review_status !== 'pending'" :class="['review-badge', selectedPair.review_status]">{{ humanize(selectedPair.review_status) }}</span>
                        </div>
                        <div v-if="selectedCell.length > 1" class="also-row" role="group" :aria-label="`Matches between ${nameOf(selectedPair.student_1_id)} and ${nameOf(selectedPair.student_2_id)}`">
                            <button
                                v-for="p in selectedCell"
                                :key="p.id"
                                type="button"
                                class="also-btn"
                                :aria-pressed="p.id === selectedPair.id"
                                @click="selectPair(p)"
                            >{{ data.exam.question_count > 1 ? `${p.question_title} · ` : '' }}attempts {{ p.attempt_1 }} and {{ p.attempt_2 }} · {{ pct(p.similarity_score) }}</button>
                        </div>
                        <p class="legend">Red = same line once names are set aside · underlined = renamed variable</p>
                        <p class="sr-only" role="status">Showing {{ nameOf(selectedPair.student_1_id) }} and {{ nameOf(selectedPair.student_2_id) }}, {{ pct(selectedPair.similarity_score) }} match</p>
                        <!-- One evidence panel per pair, kept once loaded so switching back doesn't reload -->
                        <KeepAlive :max="GRID_MAX_STUDENTS">
                            <SimilarityEvidence
                                :key="selectedPair.id"
                                class="evidence"
                                :pair="selectedPair"
                                :label1="`${nameOf(selectedPair.student_1_id)} · attempt ${selectedPair.attempt_1}`"
                                :label2="`${nameOf(selectedPair.student_2_id)} · attempt ${selectedPair.attempt_2}`"
                                show-code
                                show-explanation
                                :bleed="false"
                                mark-renamed
                            />
                        </KeepAlive>
                    </div>
                </section>

                <!-- Each flag on its own, with its own review controls -->
                <section v-if="perFlag" id="per-flag" class="card per-flag" aria-labelledby="per-flag-h">
                    <h2 id="per-flag-h" class="card-title">Decide each flag</h2>
                    <div v-for="f in caseFlags(openCase)" :key="f.kind + f.id" class="per-flag-row">
                        <div class="per-flag-top">
                            <span class="per-flag-label">{{ f.label }}</span>
                            <span :class="['review-badge', f.status]">{{ humanize(f.status) }}</span>
                        </div>
                        <p v-if="f.note" class="review-note">{{ f.note }}</p>
                        <ReviewControls
                            v-if="f.status === 'pending'"
                            v-model:note="flagNotes[f.kind + f.id]"
                            :busy="saving"
                            :note-label="`Note for the ${f.label.toLowerCase()}`"
                            @decide="d => decideOne(f, d)"
                        />
                    </div>
                </section>

                <p v-if="openCase.status !== 'pending' && caseNotes.length" class="card quiet-card decided-notes">
                    Note to the students: {{ caseNotes.join(' · ') }}
                </p>
            </div>

            <!-- Sticky decision bar: one decision for every flag still waiting in the case -->
            <div v-if="openCase && (openCase.pending > 0 || failed.length)" class="decision-bar">
                <div class="decision-inner">
                    <template v-if="!separateNotes">
                        <label for="case-note" class="sr-only">Note to the students</label>
                        <input
                            id="case-note"
                            v-model="caseNote"
                            :disabled="saving"
                            placeholder="Note to the students, shown on their results (optional)"
                        />
                    </template>
                    <!-- one note per student: each sees only their own on their results -->
                    <div v-else id="student-notes" class="notes-panel" role="group" aria-label="Note to each student">
                        <div v-for="m in openCase.members" :key="m.student_id" class="note-row">
                            <template v-if="matched.has(m.student_id)">
                                <p class="note-who"><strong>{{ m.username }}</strong> <span class="matched-tag">No behaviour signals — matched only</span></p>
                                <span class="send-check">
                                    <input :id="`send-${m.student_id}`" v-model="sendTo[m.student_id]" type="checkbox" :disabled="saving" />
                                    <label :for="`send-${m.student_id}`">Send note to {{ m.username }}</label>
                                </span>
                            </template>
                            <label v-else :for="`note-${m.student_id}`" class="note-label">Note to {{ m.username }}</label>
                            <input
                                v-if="!matched.has(m.student_id) || sendTo[m.student_id]"
                                :id="`note-${m.student_id}`"
                                v-model="studentNotes[m.student_id]"
                                :aria-label="matched.has(m.student_id) ? `Note to ${m.username}` : undefined"
                                :aria-describedby="notePlan.unreached.includes(m.student_id) ? `note-${m.student_id}-warn` : undefined"
                                :disabled="saving"
                                placeholder="Shown on their results (optional)"
                            />
                            <p v-if="notePlan.unreached.includes(m.student_id)" :id="`note-${m.student_id}-warn`" class="note-warn">
                                {{ m.username }} won't see this note: with no behaviour flag of their own, a note reaches them only when it matches the note of a classmate whose code they share.
                            </p>
                        </div>
                    </div>
                    <button type="button" class="bar-confirm" :disabled="saving" @click="decideCase('confirmed')">Confirm case</button>
                    <button type="button" class="bar-dismiss" :disabled="saving" @click="decideCase('dismissed')">Dismiss case</button>
                    <button v-if="openCase.members.length > 1" type="button" class="bar-link" :aria-expanded="separateNotes" aria-controls="student-notes" @click="toggleSeparateNotes">
                        {{ separateNotes ? 'Use one note for everyone' : 'Write separate notes' }}
                    </button>
                    <button type="button" class="bar-link" :aria-expanded="perFlag" aria-controls="per-flag" @click="perFlag = !perFlag">
                        {{ perFlag ? 'Hide separate decisions' : 'Decide each flag separately' }}
                    </button>
                    <p v-if="saving" class="bar-note" role="status">Saving {{ progress.done }} of {{ plural(progress.total, 'flag') }}…</p>
                    <div v-else-if="failed.length" class="bar-error" role="alert">
                        <span>{{ plural(failed.length, 'flag') }} didn't save: {{ failed.map(f => f.label).join('; ') }}.</span>
                        <button type="button" class="bar-retry" @click="decideCase(lastDecision, failed)">Retry</button>
                    </div>
                    <p v-else-if="flagError" class="bar-error" role="alert">{{ flagError }}</p>
                    <p v-else class="bar-note">
                        {{ lastDecision === 'dismissed' ? 'Dismissing' : 'Confirming' }} applies to {{ appliesTo }} in this case. Nothing is decided until you confirm.
                        <template v-if="!separateNotes && leftOut.length"> {{ leftOut.length > 3 ? plural(leftOut.length, 'student') : joinNames(leftOut) }} only matched and won't get the note.</template>
                    </p>
                </div>
            </div>
        </template>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, h, type FunctionalComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'
import { formatDate, formatDateTime, formatPct, formatRisk, humanize, plural, submissionStatusLabel } from '../utils/format'
import { METRIC_HELP, confidenceClass, confidenceLabel, type FlagConfidence } from '../utils/metrics'
import { examStatusLabel } from '../utils/exams'
import {
    LARGE_CASE_SIZE, caseFlags, caseHighlights, caseStatusLabel, caseVerdict, clusterLabel, decisionMessage, isLargeCase,
    joinNames, matchedOnly, parseCaseFrom, pendingFlags, planNotes, reviewAll, reviewPath, shareOfTakers, topSignals,
    waitingLine, type CaseFlag, type CasePair, type ExamCase, type NotePlan,
} from '../utils/caseFile'
import {
    GRID_MAX_STUDENTS, LIST_PAGE, cellLookup, gridStudents, rankPairs, scorePct, shadeStep, similaritySummary,
} from '../utils/similarityGrid'
import BehaviourEvidence from '../components/BehaviourEvidence.vue'
import SimilarityEvidence from '../components/SimilarityEvidence.vue'
import ReviewControls from '../components/ReviewControls.vue'

interface RingMember { student_id: number; username: string }
interface Ring {
    size: number
    members: RingMember[]
    avg_similarity: number
    max_similarity: number
    confirmed: number
    case: string | null
}
interface Student {
    student_id: number
    username: string
    submission_id: number
    behavioural_risk: number | null
    risk: number | null
    behavioural_confidence: FlagConfidence | null
    similarity_pairs: number
    max_similarity: number
    past_flags: number
    combined_risk: number
    case: string | null
}
interface CohortDetail {
    exam: {
        id: number
        title: string
        status: string
        question_count: number
        duration_minutes: number
        start_time: string | null
        end_time: string | null
        last_checked_at: string | null
    }
    stats: {
        total_submissions: number
        took: number
        enrolled: number
        took_rate: number | null
        flagged_students: number
        flagged_students_rate: number | null
        similarity_count: number
        cases_to_decide: number
        health: 'green' | 'amber' | 'red'
    }
    students: Student[]
    rings: Ring[]
    cases: ExamCase[]
    appeals?: { id: number; student_id: number; student_note: string; created_at: string }[]   // open ones
}

// "a and b" with the joining words muted, as in the case file design
const NameList: FunctionalComponent<{ names: string[] }> = ({ names }) => {
    const out: (string | ReturnType<typeof h>)[] = []
    names.forEach((n, i) => {
        if (i > 0) out.push(h('span', { class: 'name-join' }, i === names.length - 1 ? ' and ' : ', '))
        out.push(n)
    })
    return h('span', { 'aria-label': joinNames(names) }, out)
}

const route = useRoute()
const router = useRouter()
const data = ref<CohortDetail | null>(null)
const loading = ref(true)
const error = ref('')

const caseKey = computed(() => (typeof route.query.case === 'string' ? route.query.case : ''))
const openCase = computed(() => data.value?.cases.find(c => c.key === caseKey.value) ?? null)
const allCasesLink = computed(() => ({ name: 'cohort-detail', params: { id: route.params.id } }))
function caseLink(key: string) {
    return { name: 'cohort-detail', params: { id: route.params.id }, query: { case: key } }
}
function caseNumber(key: string): number | undefined {
    return data.value?.cases.find(c => c.key === key)?.number
}

// Opened from a student's page or an exam report (?from=student:<id> | report:<examId>): a way
// back at the top, the student highlighted, and the trainer returned there once it's decided.
const from = computed(() => parseCaseFrom(route.query.from))
const fromLink = computed(() => {
    if (from.value?.kind === 'student') return { path: `/dashboard/students/${from.value.id}`, query: { tab: 'integrity' } }
    if (from.value?.kind === 'dispute') return { path: `/dashboard/support/disputes/${from.value.id}` }
    return { path: `/dashboard/history/${from.value?.id}` }
})
const fromLabel = computed(() => {
    if (from.value?.kind === 'report') return `Back to ${data.value?.exam.title} report`
    if (from.value?.kind === 'dispute') return 'Back to the appeal'
    const sid = from.value?.id
    const name = data.value?.cases.flatMap(c => c.members).find(m => m.student_id === sid)?.username
        ?? data.value?.students.find(s => s.student_id === sid)?.username
    return name ? `Back to ${name}` : 'Back to the student'
})
// Open appeals by students in a case (the appeal is per exam; it shows on the student's case)
function caseAppeals(c: ExamCase) {
    const members = new Set(c.members.map(m => m.student_id))
    return (data.value?.appeals ?? []).filter(a => members.has(a.student_id))
}
function usernameOf(studentId: number): string {
    return data.value?.cases.flatMap(c => c.members).find(m => m.student_id === studentId)?.username ?? 'A student'
}

function isFocus(studentId: number): boolean {
    return from.value?.kind === 'student' && from.value.id === studentId
}

const metaLine = computed(() => {
    const e = data.value!.exam
    const parts = [plural(e.question_count, 'question'), `${e.duration_minutes} min`]
    if (e.start_time) parts.push(`started ${formatDate(e.start_time)}`)
    if (e.last_checked_at) parts.push(`last checked ${checkedAt(e.last_checked_at)}`)
    return parts.join(' · ')
})

/** "19:12" today, otherwise the date too. */
function checkedAt(iso: string): string {
    const d = new Date(iso)
    const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    return d.toDateString() === new Date().toDateString() ? time : formatDateTime(iso)
}

const pct = scorePct
// Flags this student had on earlier exams, shown on their card in an opened case
function pastFlags(studentId: number): number {
    return data.value?.students.find(s => s.student_id === studentId)?.past_flags ?? 0
}
function riskClass(score: number): string {
    if (score >= 0.7) return 'high'
    if (score >= 0.4) return 'medium'
    return 'low'
}

function labelFor(c: ExamCase) {
    return clusterLabel(c.members.length, data.value?.stats.took ?? 0)
}
function labelClass(label: string | null): string {
    return label === 'Common solution' ? 'common' : 'copying'
}

/** Members with a behavioural flag that still counts (not dismissed). */
function flaggedMembers(c: ExamCase): number {
    return new Set(c.behavioural.filter(f => f.review_status !== 'dismissed').map(f => f.student_id)).size
}
function flaggedInRing(r: Ring): number {
    const c = r.case ? data.value?.cases.find(x => x.key === r.case) : undefined
    return c ? flaggedMembers(c) : 0
}

/** Node drawing for a small cluster: members on a circle, a line for each pair that counts. */
function drawing(r: Ring) {
    const c = r.case ? data.value?.cases.find(x => x.key === r.case) : undefined
    const flagged = new Set(c?.behavioural.filter(f => f.review_status !== 'dismissed').map(f => f.student_id))
    const n = r.members.length
    const pos = new Map<number, { x: number; y: number }>()
    const nodes = r.members.map((m, i) => {
        const angle = n === 2 ? Math.PI * i : (2 * Math.PI * i) / n - Math.PI / 2
        const p = { x: Math.round(120 + Math.cos(angle) * (n === 2 ? 70 : 80)), y: Math.round(55 + Math.sin(angle) * 34) }
        pos.set(m.student_id, p)
        const initials = m.username.replace(/[^A-Za-z]/g, '').slice(0, 2).toUpperCase() || '?'
        return { id: m.student_id, ...p, initials, flagged: flagged.has(m.student_id) }
    })
    const edges = (c?.pairs ?? [])
        .filter(p => p.review_status !== 'dismissed' && pos.has(p.student_1_id) && pos.has(p.student_2_id))
        .map(p => {
            const a = pos.get(p.student_1_id)!, b = pos.get(p.student_2_id)!
            return { x1: a.x, y1: a.y, x2: b.x, y2: b.y }
        })
    return { nodes, edges }
}

// ── one case ─────────────────────────────────────────────────────────────────

function nameOf(studentId: number): string {
    return openCase.value?.members.find(m => m.student_id === studentId)?.username ?? ''
}
/** One behaviour card per student, riskiest flag first: everyone in a small case, only the
 *  flagged students in a large one. */
const behaviourCards = computed(() => {
    const c = openCase.value
    if (!c) return []
    return c.members
        .map(member => {
            const flags = c.behavioural.filter(f => f.student_id === member.student_id)   // server sends riskiest first
            return { member, flags, top: flags[0] }
        })
        .filter(card => !isLargeCase(c) || card.flags.length > 0)
})

// Matching code: a grid of who matches whom (or a ranked list in a big case) and one
// comparison below it, the strongest pair until another is chosen.
const rankedPairs = computed(() => rankPairs(openCase.value?.pairs ?? []))
const students = computed(() => (openCase.value ? gridStudents(openCase.value) : []))
const cellOf = computed(() => cellLookup(openCase.value?.pairs ?? []))
const gridRows = computed(() => students.value.map(student => ({
    student,
    cells: students.value.map(s => {
        const pairs = cellOf.value(student.student_id, s.student_id)
        return { student: s, pairs, top: pairs[0] }
    }),
})))
const showAllPairs = ref(false)
const listedPairs = computed(() => (showAllPairs.value ? rankedPairs.value : rankedPairs.value.slice(0, LIST_PAGE)))
const selectedId = ref<number | null>(null)
const selectedPair = computed(() => rankedPairs.value.find(p => p.id === selectedId.value) ?? rankedPairs.value[0])
const selectedCell = computed(() => (selectedPair.value
    ? cellOf.value(selectedPair.value.student_1_id, selectedPair.value.student_2_id)
    : []))
function selectPair(p: CasePair): void {
    selectedId.value = p.id
}
function isSelected(pairs: CasePair[]): boolean {
    return pairs.some(p => p.id === selectedPair.value?.id)
}
const focusInGrid = computed(() => students.value.some(s => isFocus(s.student_id)))

const caseNotes = computed(() => [...new Set(caseFlags(openCase.value!).map(f => f.note).filter(Boolean))])

/** "the similarity pair and 2 behaviour flags" — what the case decision will touch. */
const appliesTo = computed(() => {
    const flags = openCase.value ? pendingFlags(openCase.value) : []
    const pairs = flags.filter(f => f.kind === 'similarity').length
    const behaviour = flags.length - pairs
    const parts = []
    if (pairs) parts.push(pairs === 1 ? 'the similarity pair' : `${pairs} similarity pairs`)
    if (behaviour) parts.push(behaviour === 1 ? 'the behaviour flag' : `${behaviour} behaviour flags`)
    return joinNames(parts)
})

const caseNote = ref('')
// Notes per student: one group note by default; "Write separate notes" gives each student a box.
// A student who is only in the case through matching code gets no note unless ticked.
const separateNotes = ref(false)
const studentNotes = ref<Record<number, string>>({})
const sendTo = ref<Record<number, boolean>>({})
const matched = computed(() => (openCase.value ? matchedOnly(openCase.value) : new Set<number>()))
const leftOut = computed(() => (openCase.value?.members ?? [])
    .filter(m => matched.value.has(m.student_id) && !sendTo.value[m.student_id]).map(m => m.username))
function noteFor(studentId: number): string {
    if (matched.value.has(studentId) && !sendTo.value[studentId]) return ''
    return (separateNotes.value ? studentNotes.value[studentId] : caseNote.value) ?? ''
}
const notePlan = computed<NotePlan>(() => (openCase.value
    ? planNotes(openCase.value, pendingFlags(openCase.value), noteFor)
    : { notes: {}, reached: [], unreached: [] }))
function toggleSeparateNotes(): void {
    if (!separateNotes.value) {   // each box starts from the group note
        studentNotes.value = Object.fromEntries((openCase.value?.members ?? []).map(m => [m.student_id, caseNote.value]))
    }
    separateNotes.value = !separateNotes.value
}

const perFlag = ref(false)
const flagNotes = ref<Record<string, string>>({})
const saving = ref(false)
const progress = ref({ done: 0, total: 0 })
const failed = ref<CaseFlag[]>([])
const lastDecision = ref<'confirmed' | 'dismissed'>('confirmed')
const flagError = ref('')

// What the first try of a case decision planned: the retry sends the same notes, and the
// message after it counts the students it was for.
let planned: { plan: NotePlan; students: number } | null = null

/** Confirm / dismiss the case: every pending flag through its own review endpoint, each with the
 *  note for the student(s) it concerns, so each flag keeps its own audit entry. `only` retries
 *  the flags that failed last time. Opened from a student or report, a full success goes back there. */
async function decideCase(decision: 'confirmed' | 'dismissed', only?: CaseFlag[]): Promise<void> {
    if (!openCase.value || saving.value) return
    const flags = only ?? pendingFlags(openCase.value)
    if (!only) planned = { plan: notePlan.value, students: openCase.value.members.length }
    const notes = planned!.plan.notes
    lastDecision.value = decision
    failed.value = []
    flagError.value = ''
    saving.value = true
    progress.value = { done: 0, total: flags.length }
    failed.value = await reviewAll(
        flags,
        f => api.patch(reviewPath(f), { review_status: decision, review_note: notes[f.kind + f.id] ?? '' }),
        done => { progress.value = { done, total: flags.length } },
    )
    saving.value = false
    if (!failed.value.length && from.value) {
        const caseNotice = decisionMessage(decision, planned!.students, planned!.plan.reached.length)
        await router.push({ ...fromLink.value, state: { caseNotice } })
        return
    }
    if (!failed.value.length) resetNotes()
    await load(true)
}

function resetNotes(): void {
    caseNote.value = ''
    separateNotes.value = false
    studentNotes.value = {}
    sendTo.value = {}
}

async function decideOne(f: CaseFlag, decision: 'confirmed' | 'dismissed'): Promise<void> {
    flagError.value = ''
    saving.value = true
    try {
        await api.patch(reviewPath(f), { review_status: decision, review_note: flagNotes.value[f.kind + f.id] || '' })
    } catch {
        flagError.value = `${f.label} didn't save. Try again.`
    } finally {
        saving.value = false
    }
    await load(true)
}

async function load(quiet = false): Promise<void> {
    if (!quiet) loading.value = true
    error.value = ''
    try {
        const res = await api.get(`/plagiarism/cohorts/${route.params.id}/`)
        data.value = res.data
    } catch (e: any) {
        if (!quiet || !data.value) error.value = e.response?.data?.error || e.message
    } finally {
        loading.value = false
    }
}

watch(() => route.params.id, () => load(), { immediate: true })

// Opening or leaving a case starts at the top, with nothing half-decided carried over
watch(caseKey, () => {
    selectedId.value = null
    showAllPairs.value = false
    perFlag.value = false
    resetNotes()
    failed.value = []
    flagError.value = ''
    window.scrollTo(0, 0)
})
</script>

<style scoped>
.sr-only {
    position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
    overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0;
}
.grow { flex-grow: 1; }
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
}

.from-back {
    display: inline-flex; align-items: center; min-height: 44px; padding: 0 18px; margin-bottom: 14px;
    border-radius: var(--radius-pill); background: var(--accent); color: var(--accent-ink);
    font-size: 14px; font-weight: 600; overflow-wrap: anywhere;
}
.from-back:hover { background: var(--accent-hover); color: var(--accent-ink); text-decoration: none; }
.crumbs { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 14px; color: var(--text-dim); margin-bottom: 20px; }
.crumbs a { color: var(--text-dim); }
.crumbs a:hover { color: var(--accent-hover); }
.crumb-sep { color: #C9BDBE; }
.crumb-here { color: var(--text); font-weight: 500; overflow-wrap: anywhere; }

.state-msg { text-align: center; padding: 48px; color: var(--text-dim); font-size: 14px; }
.error-msg { color: var(--red-ink); }

/* Header */
.page-header { display: flex; flex-direction: column; gap: 8px; margin-bottom: 24px; }
.title-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.title-row h1 { margin: 0; font-size: 32px; overflow-wrap: anywhere; }
.meta-line { margin: 0; font-size: 14px; color: var(--text-muted); }
.status-chip {
    display: inline-flex; align-items: center; height: 26px; padding: 0 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
}
.status-chip.live  { background: var(--green-dim); color: var(--green-ink); }
.status-chip.ended { background: var(--surface3); color: var(--text-muted); }
.status-chip.draft { background: var(--yellow-dim); color: var(--amber-ink); }

/* KPI strip: one card, four cells */
.kpi-strip {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 18px;
    overflow: hidden;
    margin-bottom: 24px;
}
.kpi-cell {
    display: flex; flex-direction: column; gap: 6px;
    padding: 20px 22px;
    border-right: 1px solid #F1E9E9;
    border-bottom: 1px solid #F1E9E9;
    margin: 0 -1px -1px 0;   /* cells on the last column / row lose their divider under the card edge */
}
.kpi-value { font-family: var(--font-mono); font-size: 30px; font-weight: 500; color: var(--text); line-height: 1.1; font-variant-numeric: tabular-nums; }
.kpi-value.danger { color: var(--red-ink); }
.kpi-of { font-size: 16px; color: var(--text-dim); }
.kpi-label { font-size: 13px; color: var(--text-muted); }

/* Two columns: cases + table, clusters aside */
.columns { display: flex; gap: 24px; flex-wrap: wrap; align-items: flex-start; }
.main-col { flex: 999 1 600px; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.side-col { flex: 1 1 320px; max-width: 420px; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
.main-col h2, .side-col h2 { margin: 0; font-size: 19px; }
.section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.section-sub { font-size: 13px; color: var(--text-dim); margin: 0; }

.quiet-card { margin: 0; padding: 18px 22px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; color: var(--text-muted); font-size: 14px; }
.all-clear svg { color: var(--green-ink); flex-shrink: 0; }

/* Case cards */
.case-card {
    display: flex; flex-direction: column; gap: 14px;
    padding: 20px 22px;
    color: var(--text);
    border-color: #E3D8D8;
    box-shadow: 0 12px 32px rgba(33, 25, 27, 0.06);
    transition: border-color 0.15s;
}
.case-card:hover { border-color: var(--accent); text-decoration: none; color: var(--text); }
.case-card-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.case-chip {
    display: inline-flex; align-items: center; height: 26px; padding: 0 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
    background: var(--accent-tint); color: var(--red-ink);
}
.case-chip.muted { background: var(--surface2); color: var(--text-muted); }
.case-names { font-family: var(--font-display); font-size: 18px; font-weight: 600; overflow-wrap: anywhere; min-width: 0; }
.case-pct { font-family: var(--font-mono); font-size: 20px; color: var(--red-ink); }
.case-pct-label { font-size: 13px; color: var(--text-muted); }
.case-risk { font-family: var(--font-mono); font-size: 20px; color: var(--red-ink); }
.sig-row { display: flex; gap: 8px; flex-wrap: wrap; }
.sig {
    display: inline-flex; align-items: center; gap: 6px; min-height: 28px; padding: 4px 10px;
    border-radius: var(--radius-pill); background: #F7F1EE; font-size: 12px; color: #3B3435;
    max-width: 100%;
}
.large-summary { margin: 0; font-size: 14px; color: var(--text-muted); }
.highlights { margin: 0; padding-left: 18px; font-size: 14px; color: var(--text-muted); line-height: 1.7; }
.highlights strong { color: var(--text); font-weight: 600; }
.case-card-foot { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 14px; color: var(--text-muted); }
.open-link { font-weight: 600; color: var(--red-ink); white-space: nowrap; }

.label-chip {
    display: inline-flex; align-items: center; height: 24px; padding: 0 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
}
.label-chip.copying { background: var(--red-dim); color: var(--red-ink); }
.label-chip.common  { background: var(--surface2); color: var(--text-muted); }

.case-row {
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    min-height: 56px; padding: 10px 22px;
    color: var(--text); font-size: 14px;
}
.case-row:hover { border-color: var(--border2); text-decoration: none; color: var(--text); }
.case-row-names { font-weight: 600; overflow-wrap: anywhere; min-width: 0; }
.appeal-chip {
    display: inline-flex; align-items: center; height: 26px; padding: 0 10px; margin: 0;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
    background: var(--yellow-dim); color: #92400E;
}
.appeal-note { padding: 14px 22px; display: grid; gap: 8px; justify-items: start; border-left: 3px solid var(--yellow); }
.appeal-line { margin: 0; font-size: 14px; color: var(--text); overflow-wrap: anywhere; }
.appeal-open { display: inline-flex; align-items: center; min-height: 44px; margin-left: 6px; font-weight: 600; }
.outcome-chip {
    display: inline-flex; align-items: center; height: 26px; padding: 0 10px;
    border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; white-space: nowrap;
}
.outcome-chip.pending   { background: var(--yellow-dim); color: #92400E; }
.outcome-chip.confirmed { background: var(--red-dim);    color: var(--red-ink); }
.outcome-chip.dismissed { background: var(--green-dim);  color: var(--green-ink); }
.outcome-chip.mixed     { background: var(--surface2);   color: var(--text-muted); }

/* Student table */
.student-link { font-weight: 600; color: var(--text); }
.student-link:hover { color: var(--accent); }

/* Similarity clusters */
.cluster-card { padding: 22px; display: flex; flex-direction: column; gap: 14px; }
.cluster-empty { margin: 0; font-size: 14px; color: var(--text-muted); }
.cluster-row {
    display: flex; flex-direction: column; gap: 8px;
    padding: 14px 16px; border-radius: 14px;
    background: var(--bg); border: 1px solid #F1E9E9;
    color: var(--text);
}
.cluster-row:hover { border-color: var(--border2); text-decoration: none; color: var(--text); }
.cluster-drawing { width: 100%; max-width: 280px; height: auto; align-self: center; }
.edge { stroke: var(--red); stroke-width: 2; }
.node { fill: var(--surface2); stroke: var(--border2); }
.node.flagged { fill: var(--accent-tint); stroke: var(--red); }
.node-text { font-family: var(--font-display); font-size: 11px; font-weight: 600; fill: var(--text); }
.cluster-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 14px; }
.cluster-names { font-size: 13px; color: var(--text-muted); overflow-wrap: anywhere; }
.share { display: flex; align-items: center; gap: 10px; }
.share-track { flex: 1; height: 6px; border-radius: 3px; background: var(--surface3); overflow: hidden; }
.share-fill { display: block; height: 100%; background: var(--red); }
.share-val { font-size: 12px; color: var(--text-muted); white-space: nowrap; font-family: var(--font-mono); }
.cluster-meta { font-size: 12px; color: var(--text-dim); }

/* ── One case ── */
.case-view { display: flex; flex-direction: column; gap: 22px; padding-bottom: 24px; }
.case-head { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.back-pill {
    display: inline-flex; align-items: center; min-height: 44px; padding: 0 16px;
    border: 1px solid var(--border); border-radius: var(--radius-pill);
    background: var(--surface); color: var(--text); font-size: 14px;
}
.back-pill:hover { border-color: var(--border2); color: var(--text); text-decoration: none; }
.case-title { margin: 0; font-size: 28px; overflow-wrap: anywhere; min-width: 0; }

.verdict-card { padding: 18px 22px; display: flex; gap: 14px; align-items: center; flex-wrap: wrap; background: #FFF6F7; border-color: #F6CBD4; }
.verdict-pct { font-family: var(--font-mono); font-size: 32px; color: var(--red-ink); }
.verdict-text { flex: 1 1 260px; margin: 0; font-size: 15px; line-height: 1.55; color: #3B3435; }

.behaviour-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(300px, 100%), 1fr)); gap: 16px; }
.behaviour-card { padding: 20px 22px; display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.behaviour-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.card-title { margin: 0; font-size: 18px; overflow-wrap: anywhere; }
.chip { display: inline-flex; align-items: center; height: 26px; padding: 0 10px; border-radius: var(--radius-pill); font-size: 12px; font-weight: 600; }
:deep(.name-join) { color: var(--text-dim); font-weight: 500; }   /* the "and" between names, built in script */
.past-chip { background: var(--yellow-dim); color: var(--amber-ink); }
.risk-score { font-size: 14px; font-weight: 600; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.risk-score.high { color: var(--red-ink); }
.risk-score.medium { color: var(--amber-ink); }
.risk-score.low { color: var(--text-muted); }
.no-flags { margin: 0; font-size: 14px; color: var(--text-muted); }
/* the student the case was opened from */
.behaviour-card.focus { border: 2px solid var(--accent); }
.focus-chip { background: var(--accent-tint); color: var(--red-ink); }
.flag-meta { margin: 0 0 10px; font-size: 13px; color: var(--text-dim); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.behaviour-flag + .behaviour-flag { border-top: 1px solid #F1E9E9; padding-top: 12px; }
.others-note { margin: -8px 0 0; font-size: 13px; color: var(--text-dim); }

.review-badge { padding: 3px 10px; border-radius: var(--radius-pill); font-size: 11px; font-weight: 600; white-space: nowrap; }
.review-badge.pending   { background: var(--yellow-dim); color: var(--amber-ink); }
.review-badge.confirmed { background: var(--red-dim);    color: var(--red-ink); }
.review-badge.dismissed { background: var(--green-dim);  color: var(--green-ink); }
.review-note {
    font-size: 13px; color: var(--text-dim); font-style: italic; margin: 8px 0 0;
    padding: 8px 12px; background: var(--surface2); border-radius: var(--radius-sm);
}

.match-card { overflow: hidden; min-width: 0; }
.match-head { display: flex; flex-direction: column; gap: 4px; padding: 20px 22px 16px; }
.match-summary { margin: 0; font-size: 14px; color: var(--text-muted); }
.pair-pct { font-family: var(--font-mono); color: var(--red-ink); }
.pair-question { font-size: 13px; color: var(--text-muted); }
.legend { margin: 0; padding: 0 22px 12px; font-size: 13px; color: var(--text-dim); }

/* Who matches whom: shade steps from the theme's red scale, the % always written */
.grid-scroll { overflow-x: auto; padding: 0 22px 20px; }
.sim-grid { border-collapse: separate; border-spacing: 4px; font-size: 13px; }
.sim-grid th { font-weight: 600; color: var(--text-muted); padding: 0 6px; }
.sim-grid thead th { text-align: center; vertical-align: bottom; }
.sim-grid tbody th { text-align: right; }
.sim-grid td { padding: 0; text-align: center; }
.grid-name { display: inline-block; max-width: 11ch; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; vertical-align: bottom; }
.grid-cell, .grid-empty {
    display: inline-flex; align-items: center; justify-content: center;
    min-width: 64px; min-height: 44px; padding: 0 8px; border-radius: var(--radius-sm);
    font-family: var(--font-mono); font-size: 13px; font-variant-numeric: tabular-nums;
}
.grid-empty { color: var(--text-dim); background: var(--bg); }
.sim-grid th.focus { color: var(--red-ink); }
.sim-grid th.focus .grid-name { text-decoration: underline; text-underline-offset: 3px; }
.sim-grid td.focus { background: var(--accent-tint); border-radius: var(--radius-sm); }
.focus-note { margin: 8px 0 0; font-size: 13px; color: var(--text-dim); }
.grid-cell { border: 2px solid transparent; }
.grid-cell:hover { border-color: var(--border2); }
.grid-cell[aria-pressed="true"] { border-color: var(--text); box-shadow: 0 0 0 1px var(--surface) inset; font-weight: 700; }
.step-3 { background: var(--red-ink);     color: var(--accent-ink); }
.step-2 { background: var(--accent-tint); color: var(--red-ink); }
.step-1 { background: var(--red-dim);     color: var(--red-ink); }
.step-0 { background: var(--surface2);    color: var(--text-muted); }

/* Big case: the pairs, strongest first */
.pair-list-wrap { padding: 0 22px 20px; display: flex; flex-direction: column; align-items: flex-start; gap: 10px; }
.pair-list { list-style: none; margin: 0; padding: 0; width: 100%; display: flex; flex-direction: column; gap: 6px; }
.pair-line {
    display: flex; align-items: center; gap: 10px; flex-wrap: wrap; width: 100%;
    min-height: 44px; padding: 6px 12px; text-align: left;
    border: 1px solid var(--border); border-radius: var(--radius-sm);
    background: var(--surface); color: var(--text); font-size: 14px;
}
.pair-line:hover { border-color: var(--border2); }
.pair-line[aria-pressed="true"] { border-color: var(--accent); background: var(--red-dim); }
.pair-line-names { font-weight: 600; overflow-wrap: anywhere; min-width: 0; }
.pair-line-pct { padding: 2px 8px; border-radius: var(--radius-pill); font-family: var(--font-mono); font-size: 13px; }
.more-btn {
    min-height: 44px; padding: 0 18px;
    border: 1px solid var(--border2); border-radius: var(--radius-pill);
    background: var(--surface); color: var(--text); font-size: 14px; font-weight: 600;
}
.more-btn:hover { background: var(--surface2); }

/* The one comparison */
.viewer { border-top: 1px solid var(--border); }
.viewer-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 16px 22px 6px; }
.viewer-title { margin: 0; font-size: 16px; overflow-wrap: anywhere; min-width: 0; }
.also-row { display: flex; gap: 8px; flex-wrap: wrap; padding: 4px 22px 10px; }
.also-btn {
    min-height: 36px; padding: 0 14px; border-radius: var(--radius-pill);
    border: 1px solid var(--border2); background: var(--surface); color: var(--text); font-size: 13px;
}
.also-btn[aria-pressed="true"] { border-color: var(--accent); background: var(--accent-tint); color: var(--red-ink); font-weight: 600; }
.evidence :deep(.ai-expl-panel) { margin: 16px 22px 20px; }

.per-flag { padding: 20px 22px; display: flex; flex-direction: column; gap: 16px; }
.per-flag-row + .per-flag-row { border-top: 1px solid #F1E9E9; padding-top: 16px; }
.per-flag-top { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.per-flag-label { font-size: 14px; font-weight: 600; overflow-wrap: anywhere; }
.decided-notes { font-style: italic; }

/* Sticky decision bar */
.decision-bar {
    position: sticky;
    bottom: 0;
    margin: 0 -56px -40px;   /* runs to the edges of the main content area */
    border-top: 1px solid var(--border);
    background: var(--surface);
    box-shadow: 0 -8px 24px rgba(33, 25, 27, 0.06);
    z-index: 20;
}
.decision-inner {
    max-width: 1280px; margin: 0 auto; padding: 16px 56px;
    display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
}
.decision-inner input { flex: 1 1 320px; min-height: 48px; font-size: 15px; }
.bar-confirm, .bar-dismiss {
    min-height: 48px; padding: 0 24px; border-radius: var(--radius-pill);
    font-size: 15px; font-weight: 600; white-space: nowrap;
}
.bar-confirm { background: var(--accent); color: var(--accent-ink); }
.bar-confirm:hover { background: var(--accent-hover); }
.bar-dismiss { background: var(--surface); color: var(--text); border: 1px solid #E3D8D8; }
.bar-dismiss:hover { background: var(--surface2); }
.bar-confirm:disabled, .bar-dismiss:disabled { opacity: 0.6; cursor: default; }
.bar-link {
    min-height: 44px; padding: 0 4px; background: none;
    color: var(--red-ink); font-size: 14px; font-weight: 500; font-family: var(--font-sans);
}
.bar-link:hover { text-decoration: underline; }
.notes-panel {
    flex: 1 1 100%; max-height: 40vh; overflow-y: auto;
    display: flex; flex-direction: column; gap: 12px; padding: 2px 2px 4px;
}
.note-row { display: flex; flex-direction: column; gap: 6px; }
.note-row input:not([type="checkbox"]) { min-height: 44px; font-size: 15px; }
.note-label, .note-who { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); overflow-wrap: anywhere; }
.matched-tag { margin-left: 6px; font-weight: 500; color: var(--text-dim); }
.send-check { display: inline-flex; align-items: center; gap: 8px; min-height: 44px; font-size: 14px; }
.send-check input { width: 20px; height: 20px; accent-color: var(--accent); }
.note-warn { margin: 0; font-size: 13px; color: var(--amber-ink); }
.bar-note { flex-basis: 100%; margin: 0; font-size: 13px; color: var(--text-dim); }
.bar-error { flex-basis: 100%; margin: 0; font-size: 13px; color: var(--red-ink); display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.bar-retry {
    min-height: 44px; padding: 0 18px; border-radius: var(--radius-pill);
    border: 1px solid var(--red); background: var(--surface); color: var(--red-ink); font-weight: 600;
}

@media (max-width: 899px) {
    .title-row h1 { font-size: 26px; }
    .case-title { font-size: 22px; }
    .decision-bar { margin: 0 -16px -32px; }
    .decision-inner { padding: 12px 16px; }
    .bar-confirm, .bar-dismiss { flex: 1 1 140px; }
}
</style>
