// Canonical metric labels and one-line explanations. The numbers themselves
// come from the API (backend/analytics/metrics.py); see docs/metrics.md.

import { humanize, plural } from './format'

export const METRIC_LABEL = {
    accepted: 'Success rate',
    flagged: 'Flagged students',
    toReview: 'Flags to review',
    took: 'Took the exam',
    risk: 'Risk',
    confidence: 'Flag confidence',
} as const

export const METRIC_HELP = {
    accepted: 'Students who passed (solved at least half the questions), out of students who took the exam.',
    acceptedStudent: 'Exams passed (at least half the questions solved), out of exams taken.',
    acceptedQuestion: 'Students who solved this question, out of students who attempted it.',
    passed: 'Passed means at least half of the exam\'s questions solved: what the success rate counts.',
    flagged: 'Students with at least one behavioural flag a trainer has not dismissed, out of those who took the exam.',
    toReview: 'Behavioural flags still waiting for a trainer decision.',
    took: 'Students who submitted at least once, out of those enrolled.',
    risk: 'Behavioural risk score for one flag, from 0 to 100.',
    confidence: 'How strongly the signals point to misconduct: high means 3 or more signals.',
} as const

// A question voided for confirmed plagiarism is not solved: its tests passed, but it neither
// scores nor counts toward the pass, so it can fail the exam (analytics.metrics.exam_results).
export const NOT_COUNTED_HELP =
    'Plagiarism was confirmed on this question: its tests passed, but it does not count as solved, so it can fail the exam.'

/** "1 not counted: plagiarism confirmed": solved questions a confirmed plagiarism case voided. */
export function notCountedNote(n: number): string {
    return `${n} not counted: plagiarism confirmed`
}

/** "1 question not counted": the same, where the noun is needed. */
export function questionsNotCounted(n: number): string {
    return `${plural(n, 'question')} not counted`
}

/** "3 of 5 students solved it": the counts behind a question's success rate. */
export function solvedCaption(q: { solved_students?: number; attempted_students?: number }): string {
    return `${q.solved_students ?? 0} of ${plural(q.attempted_students ?? 0, 'student')} solved it`
}

/** Text colour for a flagged-students rate, from the server's integrity health band. */
export function integrityClass(health: string | null | undefined): string {
    return health === 'red' ? 'text-red' : health === 'amber' ? 'text-amber' : 'text-muted'
}

// Flagged-students thresholds for watch / at risk. Mirrors HEALTH_RULES in
// backend/dashboard/health.py; pages that load /dashboard/health/ read the
// live values from `rules` instead.
export const FLAGGED_WATCH_PCT = 30
export const FLAGGED_AT_RISK_PCT = 50

// ── Flag confidence ─────────────────────────────────────────────────────────
// Confidence that a behavioural flag indicates misconduct, one meaning
// everywhere (set by compute_behavioural_risk in backend/plagiarism/tasks.py):
//   high = 3+ signals (most suspicious), medium = 2 signals, low = 1 signal.
// Colours: high = red, medium = amber, low = neutral. Classes live in
// assets/theme.css so every page renders the same badge colours.

export type FlagConfidence = 'high' | 'medium' | 'low'

/** Most suspicious first. */
export const CONFIDENCE_LEVELS: readonly FlagConfidence[] = ['high', 'medium', 'low']

/** Sort key: higher = more suspicious; 0 for no flag. Matches the API's confidence_rank. */
export function confidenceRank(c: string | null | undefined): number {
    return c === 'high' ? 3 : c === 'medium' ? 2 : c === 'low' ? 1 : 0
}

/** Badge class (background + text): high = red, medium = amber, low = neutral. */
export function confidenceClass(c: string | null | undefined): string {
    return c === 'high' ? 'conf-high' : c === 'medium' ? 'conf-medium' : c === 'low' ? 'conf-low' : ''
}

/** Text-only colour for a confidence value shown without a badge (KPI numbers, inline text). */
export function confidenceTextClass(c: string | null | undefined): string {
    return c === 'high' ? 'conf-text-high' : c === 'medium' ? 'conf-text-medium' : 'conf-text-low'
}

/** "High confidence", "Low confidence"; "—" when there is no flag. */
export function confidenceLabel(c: string | null | undefined): string {
    return c ? `${humanize(c)} confidence` : '—'
}

/** A flag a trainer dismissed no longer counts as flagged (backend: analytics.metrics.FLAGGED). */
export function countsAsFlagged(flag: { review_status?: string | null }): boolean {
    return flag.review_status !== 'dismissed'
}

/** The most suspicious level among several flags, or null when there are none. */
export function maxConfidence(levels: Iterable<string | null | undefined>): FlagConfidence | null {
    let best: FlagConfidence | null = null
    for (const c of levels) {
        if (confidenceRank(c) > confidenceRank(best)) best = c as FlagConfidence
    }
    return best
}
