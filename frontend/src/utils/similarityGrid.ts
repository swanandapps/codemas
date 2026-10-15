// The similarity part of an opened case: which students' code matches whose, as a grid
// (small case) or a ranked list of pairs (big case), and the one line that sums it up.
// The page shows one comparison at a time; this file decides the order and what each
// cell points at.

import type { CasePair, ExamCase } from './caseFile'
import { formatPct, plural } from './format'

/** Up to this many students in pairs, the case shows a grid; above it, a ranked list of pairs. */
export const GRID_MAX_STUDENTS = 10
/** The ranked list shows this many pairs before "Show all N pairs". */
export const LIST_PAGE = 10
/** A score at or above this is the same code once variable names are set aside. */
export const SAME_CODE_SCORE = 0.995

/** 0.927 → "92.7%", 1 → "100%". */
export function scorePct(score: number): string {
    return formatPct(Math.round(score * 1000) / 10)
}

/** Strongest first; equal scores keep the server's order. */
export function rankPairs(pairs: CasePair[]): CasePair[] {
    return [...pairs].sort((a, b) => b.similarity_score - a.similarity_score)
}

export interface GridStudent { student_id: number; username: string }

/** Students who are in at least one pair: strongest match first, then most matches, then name. */
export function gridStudents(c: ExamCase): GridStudent[] {
    const stats = new Map<number, { best: number; count: number; total: number }>()
    for (const p of c.pairs) {
        for (const id of [p.student_1_id, p.student_2_id]) {
            const s = stats.get(id) ?? { best: 0, count: 0, total: 0 }
            s.best = Math.max(s.best, p.similarity_score)
            s.count += 1
            s.total += p.similarity_score
            stats.set(id, s)
        }
    }
    const name = (id: number) => c.members.find(m => m.student_id === id)?.username ?? `Student ${id}`
    return [...stats.entries()]
        .sort(([ia, a], [ib, b]) => b.best - a.best || b.count - a.count || b.total - a.total || name(ia).localeCompare(name(ib)))
        .map(([student_id]) => ({ student_id, username: name(student_id) }))
}

/** Grid when the students in pairs fit, list above that. */
export function useGrid(c: ExamCase): boolean {
    return gridStudents(c).length <= GRID_MAX_STUDENTS
}

function cellKey(a: number, b: number): string {
    return a < b ? `${a}-${b}` : `${b}-${a}`
}

/** Pairs between each two students, strongest first. The same for (a, b) and (b, a): two
 *  students can match on more than one question or attempt, so a cell can hold several. */
export function cellLookup(pairs: CasePair[]): (a: number, b: number) => CasePair[] {
    const cells = new Map<string, CasePair[]>()
    for (const p of rankPairs(pairs)) {
        const k = cellKey(p.student_1_id, p.student_2_id)
        cells.set(k, [...(cells.get(k) ?? []), p])
    }
    return (a, b) => (a === b ? [] : cells.get(cellKey(a, b)) ?? [])
}

/** Shade step for a cell, 3 = strongest. */
export function shadeStep(score: number): 0 | 1 | 2 | 3 {
    if (score >= SAME_CODE_SCORE) return 3
    if (score >= 0.9) return 2
    if (score >= 0.8) return 1
    return 0
}

/** The line above the grid or list. */
export function similaritySummary(c: ExamCase): string {
    if (!c.pairs.length) return ''
    const students = gridStudents(c).length
    if (c.pairs.every(p => p.similarity_score >= SAME_CODE_SCORE)) {
        return students === 2
            ? 'Both students submitted the same code once variable names are set aside.'
            : `All ${students} students submitted the same code once variable names are set aside.`
    }
    const top = scorePct(Math.max(...c.pairs.map(p => p.similarity_score)))
    if (c.pairs.length === 1) return `1 similarity pair between 2 students, ${top}.`
    return `${plural(c.pairs.length, 'similarity pair')} among ${students} students, strongest ${top}.`
}
