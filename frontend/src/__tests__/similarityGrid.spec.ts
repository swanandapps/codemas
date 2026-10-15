import { describe, it, expect } from 'vitest'

import type { CasePair, ExamCase } from '../utils/caseFile'
import {
    GRID_MAX_STUDENTS, cellLookup, gridStudents, rankPairs, scorePct, shadeStep, similaritySummary, useGrid,
} from '../utils/similarityGrid'

function pair(id: number, s1: number, s2: number, score: number): CasePair {
    return {
        id, submission_1: id * 10, submission_2: id * 10 + 1, student_1_id: s1, student_2_id: s2,
        attempt_1: 1, attempt_2: 1, question_title: 'Q', similarity_score: score, review_status: 'pending', review_note: '',
    }
}

function caseOf(pairs: CasePair[], ids?: number[]): ExamCase {
    const all = ids ?? [...new Set(pairs.flatMap(p => [p.student_1_id, p.student_2_id]))]
    return {
        key: '1', number: 1, pairs, behavioural: [], pending: pairs.length, status: 'pending',
        max_similarity: Math.max(0, ...pairs.map(p => p.similarity_score)), max_risk: null,
        members: all.map(id => ({ student_id: id, username: `s${id}`, first_name: '' })),
    }
}

describe('similarity grid', () => {
    it('ranks pairs strongest first', () => {
        const ranked = rankPairs([pair(1, 1, 2, 0.8), pair(2, 1, 3, 0.95), pair(3, 2, 3, 0.9)])
        expect(ranked.map(p => p.id)).toEqual([2, 3, 1])
    })

    it('orders students by strongest match, then number of matches, and leaves out members with no pair', () => {
        const c = caseOf([pair(1, 1, 2, 0.85), pair(2, 3, 4, 0.97), pair(3, 1, 4, 0.85)], [1, 2, 3, 4, 5])
        expect(gridStudents(c).map(s => s.username)).toEqual(['s4', 's3', 's1', 's2'])
    })

    it('looks a cell up the same way round both ways, empty on the diagonal and with no pair', () => {
        const cell = cellLookup([pair(1, 1, 2, 0.85), pair(2, 2, 1, 0.99), pair(3, 2, 3, 0.9)])
        expect(cell(1, 2).map(p => p.id)).toEqual([2, 1])
        expect(cell(2, 1)).toEqual(cell(1, 2))
        expect(cell(1, 1)).toEqual([])
        expect(cell(1, 3)).toEqual([])
    })

    it('shades by strength in four steps', () => {
        expect([1, 0.995, 0.97, 0.9, 0.85, 0.8, 0.6].map(shadeStep)).toEqual([3, 3, 2, 2, 1, 1, 0])
    })

    it('uses the grid up to GRID_MAX_STUDENTS students, a list above', () => {
        const chain = (n: number) => caseOf(Array.from({ length: n - 1 }, (_, i) => pair(i + 1, i + 1, i + 2, 0.9)))
        expect(GRID_MAX_STUDENTS).toBe(10)
        expect(useGrid(chain(10))).toBe(true)
        expect(useGrid(chain(11))).toBe(false)
    })

    it('says when everyone handed in the same code', () => {
        const all = caseOf([pair(1, 1, 2, 1), pair(2, 1, 3, 0.996), pair(3, 2, 3, 1)])
        expect(similaritySummary(all)).toBe('All 3 students submitted the same code once variable names are set aside.')
        expect(similaritySummary(caseOf([pair(1, 1, 2, 1)]))).toBe('Both students submitted the same code once variable names are set aside.')
    })

    it('otherwise counts pairs and students and gives the strongest match', () => {
        const mixed = caseOf([pair(1, 1, 2, 1), pair(2, 1, 3, 0.9), pair(3, 2, 3, 0.874), pair(4, 3, 4, 0.8)])
        expect(similaritySummary(mixed)).toBe('4 similarity pairs among 4 students, strongest 100%.')
        expect(similaritySummary(caseOf([pair(1, 1, 2, 0.874)]))).toBe('1 similarity pair between 2 students, 87.4%.')
        expect(similaritySummary(caseOf([]))).toBe('')
    })

    it('formats scores like the rest of the case file', () => {
        expect(scorePct(1)).toBe('100%')
        expect(scorePct(0.9274)).toBe('92.7%')
    })
})
