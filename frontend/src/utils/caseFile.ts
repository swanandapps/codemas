// The exam case file (Investigation → one exam). The server groups flags into cases
// (plagiarism.views._cases): students linked by similarity pairs, plus each student with
// behaviour flags who is in no such group. This file turns a case into the words and
// numbers the page shows, and decides a whole case through the per-flag review endpoints.
// A case opened from a student's page or an exam report says so (`from`), so the page can
// lead back there once the case is decided.

import type { FlagConfidence } from './metrics'
import { plural } from './format'

export interface CaseMember { student_id: number; username: string; first_name: string }

export interface CasePair {
    id: number
    submission_1: number
    submission_2: number
    student_1_id: number
    student_2_id: number
    attempt_1: number
    attempt_2: number
    question_title: string
    similarity_score: number
    review_status: string
    review_note: string
}

/** A behavioural flag as the flags API serialises it. */
export interface BehaviouralFlag {
    id: number
    submission_id: number
    student: string
    student_id: number
    question_title: string
    question_difficulty: string
    exam_title: string
    exam_id: number
    attempt_number: number
    submission_status: string
    language: string
    submitted_at: string
    risk_score: number
    confidence: FlagConfidence
    paste_score: number
    time_score: number
    snapshot_score: number
    submission_score: number
    signals_triggered: string[]
    review_status: string
    review_note: string
}

export type CaseStatus = 'pending' | 'confirmed' | 'dismissed' | 'mixed'

export interface ExamCase {
    key: string
    number: number
    members: CaseMember[]
    pairs: CasePair[]
    behavioural: BehaviouralFlag[]
    pending: number
    status: CaseStatus
    max_similarity: number
    max_risk: number | null
}

// A case card lists every student up to this size; above it the card summarises the
// group and names only the flagged members and the students their code matches most.
export const LARGE_CASE_SIZE = 6

// When one group of matching code covers this share of the students who took the exam,
// it is most likely the expected solution, not copying. A group needs at least
// COMMON_SOLUTION_MIN_STUDENTS for that: two students in a three-student exam are 67%.
export const COMMON_SOLUTION_SHARE_PCT = 30
export const COMMON_SOLUTION_MIN_STUDENTS = 5

const STATUS_LABEL: Record<CaseStatus, string> = {
    pending: 'Pending decision',
    confirmed: 'Confirmed',
    dismissed: 'Dismissed',
    mixed: 'Partly confirmed',
}

export function caseStatusLabel(status: CaseStatus): string {
    return STATUS_LABEL[status] ?? status
}

export function isLargeCase(c: ExamCase): boolean {
    return c.members.length > LARGE_CASE_SIZE
}

/** Students in a group as a share of the students who took the exam (1 decimal), or null. */
export function shareOfTakers(size: number, took: number): number | null {
    if (!took) return null
    return Math.round(size / took * 1000) / 10
}

/** "Common solution" or "Likely copying" for a group of two or more; null for one student. */
export function clusterLabel(size: number, took: number): 'Common solution' | 'Likely copying' | null {
    if (size < 2) return null
    const share = shareOfTakers(size, took) ?? 0
    return size >= COMMON_SOLUTION_MIN_STUDENTS && share >= COMMON_SOLUTION_SHARE_PCT
        ? 'Common solution' : 'Likely copying'
}

export function displayName(m: CaseMember | undefined): string {
    return m ? (m.first_name || m.username) : ''
}

/** "a", "a and b", "a, b and c". */
export function joinNames(names: string[]): string {
    if (names.length <= 1) return names[0] ?? ''
    return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`
}

const lowerFirst = (s: string) => s.charAt(0).toLowerCase() + s.slice(1)

function memberOf(c: ExamCase, studentId: number): CaseMember | undefined {
    return c.members.find(m => m.student_id === studentId)
}

/** Each student's strongest behaviour signals for the case card, riskiest flag first. */
export function topSignals(c: ExamCase, perStudent = 2): { name: string; text: string }[] {
    const out: { name: string; text: string }[] = []
    const seen = new Set<number>()
    for (const f of [...c.behavioural].sort((a, b) => b.risk_score - a.risk_score)) {
        if (seen.has(f.student_id)) continue
        seen.add(f.student_id)
        const name = displayName(memberOf(c, f.student_id))
        f.signals_triggered.slice(0, perStudent).forEach(s => out.push({ name, text: lowerFirst(s) }))
    }
    return out
}

/** "Waiting: 1 similarity pair, 2 behaviour flags on Aarav" — per student, or in total for a large case. */
export function waitingLine(c: ExamCase, perStudent = true): string {
    const parts: string[] = []
    const pairs = c.pairs.filter(p => p.review_status === 'pending').length
    if (pairs) parts.push(plural(pairs, 'similarity pair'))
    const flags = c.behavioural.filter(f => f.review_status === 'pending')
    if (perStudent) {
        const byStudent = new Map<number, number>()
        flags.forEach(f => byStudent.set(f.student_id, (byStudent.get(f.student_id) ?? 0) + 1))
        byStudent.forEach((n, sid) => parts.push(`${plural(n, 'behaviour flag')} on ${displayName(memberOf(c, sid))}`))
    } else if (flags.length) {
        parts.push(plural(flags.length, 'behaviour flag'))
    }
    return parts.length ? `Waiting: ${parts.join(', ')}` : 'Nothing waiting'
}

export interface CaseHighlight { member: CaseMember; partner: CaseMember | undefined; score: number | null }

/** For a large case: each member with a behaviour flag and the student whose code matches theirs most.
 *  With no behaviour flags in the group, the strongest pair stands in. */
export function caseHighlights(c: ExamCase): CaseHighlight[] {
    const flagged = [...new Set(c.behavioural.map(f => f.student_id))]
    const out: CaseHighlight[] = []
    for (const sid of flagged) {
        const member = memberOf(c, sid)
        if (!member) continue
        let best: CasePair | undefined
        for (const p of c.pairs) {
            if ((p.student_1_id === sid || p.student_2_id === sid) && (!best || p.similarity_score > best.similarity_score)) best = p
        }
        const other = best ? (best.student_1_id === sid ? best.student_2_id : best.student_1_id) : null
        out.push({ member, partner: other === null ? undefined : memberOf(c, other), score: best ? best.similarity_score : null })
    }
    if (!out.length && c.pairs.length) {
        const top = c.pairs.reduce((a, b) => (b.similarity_score > a.similarity_score ? b : a))
        const member = memberOf(c, top.student_1_id)
        if (member) out.push({ member, partner: memberOf(c, top.student_2_id), score: top.similarity_score })
    }
    return out
}

// ── the one-line verdict ─────────────────────────────────────────────────────
// Built only from the pair score and the behaviour signal texts the detector wrote
// (plagiarism/tasks.py); anything it can't read is quoted, never paraphrased into a claim.

/** "39s" → "39 seconds", "1m 5s" → "1 min 5 s", "4m 0s" → "4 min". */
function spokenElapsed(raw: string): string {
    const m = /^(?:(\d+)m )?(\d+)s$/.exec(raw)
    if (!m) return raw
    const min = Number(m[1] ?? 0)
    const sec = Number(m[2])
    if (!min) return plural(sec, 'second')
    return sec ? `${min} min ${sec} s` : `${min} min`
}

function behaviourClause(f: BehaviouralFlag, name: string): string {
    const signals = f.signals_triggered
    const paste = signals.map(s => /^Pasted (\d+)% of final code/.exec(s)).find(Boolean)
    const time = signals.map(s => /((?:\d+m )?\d+s) after starting/.exec(s)).find(Boolean)
    const tab = signals.map(s => /^Left exam tab (\d+) times/.exec(s)).find(Boolean)
    const pasted = paste ? `pasted ${paste[1] === '100' ? 'all of' : `${paste[1]}% of`} the final code` : ''
    if (paste && time) return `${name} ${pasted} ${spokenElapsed(time[1]!)} after starting`
    if (paste) return `${name} ${pasted}`
    if (time) return `${name} submitted ${spokenElapsed(time[1]!)} after starting`
    if (tab) return `${name} left the exam tab ${tab[1]} times`
    if (signals.length) return `${name}'s behaviour was flagged: ${lowerFirst(signals[0]!)}`
    return `${name}'s behaviour was flagged with risk ${Math.round(f.risk_score * 100)}`
}

function pairClause(c: ExamCase): string {
    if (!c.pairs.length) return ''
    const top = Math.max(...c.pairs.map(p => p.similarity_score))
    const pct = Math.round(top * 100)
    if (c.members.length > 2) return `${c.members.length} students' code matches, up to ${pct}% once variable names are set aside`
    return pct >= 100
        ? 'Their code is identical once variable names are set aside'
        : `Their code is ${pct}% the same once variable names are set aside`
}

/** One sentence: what the code match and the strongest behaviour signal say. */
export function caseVerdict(c: ExamCase): string {
    const counted = c.behavioural.filter(f => f.review_status !== 'dismissed')
    const pool = counted.length ? counted : c.behavioural
    const strongest = [...pool].sort((a, b) => b.risk_score - a.risk_score)[0]
    const behaviour = strongest ? behaviourClause(strongest, displayName(memberOf(c, strongest.student_id)) || strongest.student) : ''
    const code = pairClause(c)
    if (code && behaviour) return `${code}, and ${behaviour}.`
    return `${code || behaviour}.`
}

// ── deciding a case ──────────────────────────────────────────────────────────

export interface CaseFlag { kind: 'similarity' | 'behavioural'; id: number; label: string }

function usernameOf(c: ExamCase, sid: number): string {
    return memberOf(c, sid)?.username ?? ''
}

/** Every flag in the case, pairs first, with a label for the decision list and error messages. */
export function caseFlags(c: ExamCase): (CaseFlag & { status: string; note: string })[] {
    return [
        ...c.pairs.map(p => ({
            kind: 'similarity' as const, id: p.id, status: p.review_status, note: p.review_note,
            label: `Similarity pair: ${usernameOf(c, p.student_1_id)} and ${usernameOf(c, p.student_2_id)}`,
        })),
        ...c.behavioural.map(f => ({
            kind: 'behavioural' as const, id: f.id, status: f.review_status, note: f.review_note,
            label: `Behaviour flag on ${usernameOf(c, f.student_id) || f.student}`,
        })),
    ]
}

export function pendingFlags(c: ExamCase): CaseFlag[] {
    return caseFlags(c).filter(f => f.status === 'pending').map(({ kind, id, label }) => ({ kind, id, label }))
}

/** The existing per-flag review endpoint, so every flag keeps its own audit entry. */
export function reviewPath(f: CaseFlag): string {
    return f.kind === 'similarity' ? `/plagiarism/${f.id}/review/` : `/plagiarism/behavioural/${f.id}/review/`
}

/** Saves each flag with `save`, a few at a time; returns the flags that didn't save. */
export async function reviewAll(
    flags: CaseFlag[],
    save: (f: CaseFlag) => Promise<unknown>,
    onProgress?: (done: number, total: number) => void,
    concurrency = 4,
): Promise<CaseFlag[]> {
    const failed: CaseFlag[] = []
    let next = 0
    let done = 0
    async function worker(): Promise<void> {
        while (next < flags.length) {
            const f = flags[next++]!
            try { await save(f) } catch { failed.push(f) }
            onProgress?.(++done, flags.length)
        }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, flags.length) }, worker))
    return flags.filter(f => failed.includes(f))   // in the order they were asked for
}

// ── notes per student ────────────────────────────────────────────────────────
// A note is shown to the student on their results with each flag it sits on, and a
// similarity pair is shown to both of its students. So a student's note rides on their own
// behaviour flags, and a pair carries a note only when both of its students get the same
// one; otherwise it carries none, and nobody sees a classmate's note.

/** Students in the case only through matching code: no behaviour flag of their own that
 *  still counts. Their points are never withheld for a match alone (analytics.metrics),
 *  so by default they aren't sent the note either. */
export function matchedOnly(c: ExamCase): Set<number> {
    const flagged = new Set(c.behavioural.filter(f => f.review_status !== 'dismissed').map(f => f.student_id))
    return new Set(c.members.map(m => m.student_id).filter(sid => !flagged.has(sid)))
}

export interface NotePlan {
    /** The note for each flag, by kind + id (as the per-flag note boxes are keyed). */
    notes: Record<string, string>
    /** Students who will see their note, in member order. */
    reached: number[]
    /** Students given a note that no flag can carry to them (no behaviour flag of their own
     *  being decided, and no pair with a classmate getting the same words). */
    unreached: number[]
}

/** The note each of `flags` is saved with, from the note meant for each student. */
export function planNotes(c: ExamCase, flags: CaseFlag[], noteFor: (studentId: number) => string): NotePlan {
    const notes: Record<string, string> = {}
    const reached = new Set<number>()
    for (const f of flags) {
        let ids: number[] = []
        let note = ''
        if (f.kind === 'similarity') {
            const p = c.pairs.find(x => x.id === f.id)
            if (p && noteFor(p.student_1_id) === noteFor(p.student_2_id)) {
                ids = [p.student_1_id, p.student_2_id]
                note = noteFor(p.student_1_id)
            }
        } else {
            const b = c.behavioural.find(x => x.id === f.id)
            if (b) {
                ids = [b.student_id]
                note = noteFor(b.student_id)
            }
        }
        notes[f.kind + f.id] = note
        if (note) ids.forEach(id => reached.add(id))
    }
    const members = c.members.map(m => m.student_id)
    return {
        notes,
        reached: members.filter(sid => reached.has(sid)),
        unreached: members.filter(sid => noteFor(sid) && !reached.has(sid)),
    }
}

/** "Case confirmed for 4 students. Your note is on their results." — shown where the trainer lands. */
export function decisionMessage(decision: 'confirmed' | 'dismissed', students: number, noted: number): string {
    const done = `Case ${decision} for ${plural(students, 'student')}.`
    if (!noted) return done
    return noted >= students
        ? `${done} Your note is on their results.`
        : `${done} Your note is on the results of ${noted} of them.`
}

// ── where the case was opened from ───────────────────────────────────────────

export interface CaseFrom { kind: 'student' | 'report' | 'dispute'; id: number }

/** `from=student:<studentId>`, `from=report:<examId>` or `from=dispute:<appealId>`; anything else is ignored. */
export function parseCaseFrom(raw: unknown): CaseFrom | null {
    if (typeof raw !== 'string') return null
    const m = /^(student|report|dispute):(\d+)$/.exec(raw)
    return m ? { kind: m[1] as CaseFrom['kind'], id: Number(m[2]) } : null
}

/** The exam's case file, opened at one case when the key is known. */
export function caseFileLink(examId: number, key: string | null, from: string): string {
    const query = [key ? `case=${key}` : '', `from=${from}`].filter(Boolean).join('&')
    return `/dashboard/plagiarism/cohorts/${examId}?${query}`
}
