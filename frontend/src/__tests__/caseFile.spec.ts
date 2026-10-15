import { describe, it, expect } from 'vitest'

import {
    caseVerdict, clusterLabel, shareOfTakers, waitingLine, caseHighlights, pendingFlags,
    reviewPath, reviewAll, joinNames, topSignals, caseStatusLabel, isLargeCase,
    matchedOnly, planNotes, parseCaseFrom, caseFileLink, decisionMessage,
    type ExamCase, type CaseFlag,
} from '../utils/caseFile'
import { findRenamedNames, splitRenamed } from '../utils/codeCompare'

const aarav = { student_id: 1, username: 'aarav_sharma0', first_name: 'Aarav' }
const tara = { student_id: 2, username: 'tara_shah96', first_name: '' }

function bFlag(id: number, student_id: number, signals: string[], risk = 0.7, review_status = 'pending') {
    return {
        id, submission: id, submission_id: id, student: '', student_id,
        question_title: 'Q', question_difficulty: 'medium', exam_title: 'E', exam_id: 9,
        attempt_number: 1, submission_status: 'passed', language: 'javascript', submitted_at: '',
        risk_score: risk, confidence: 'medium' as const,
        paste_score: 1, time_score: 1, snapshot_score: 0, submission_score: 0,
        signals_triggered: signals, review_status, review_note: '',
    }
}

function pair(id: number, s1: number, s2: number, score: number, review_status = 'pending') {
    return {
        id, submission_1: 100 + s1, submission_2: 100 + s2, student_1_id: s1, student_2_id: s2,
        attempt_1: 1, attempt_2: 3, question_title: 'Palindrome', similarity_score: score,
        review_status, review_note: '',
    }
}

function makeCase(over: Partial<ExamCase> = {}): ExamCase {
    return {
        key: '1', number: 1, members: [aarav, tara],
        pairs: [pair(10, 1, 2, 1.0)],
        behavioural: [bFlag(20, 1, [
            'Pasted 100% of final code (485 chars)',
            'Submitted 39s after starting, on a medium problem (typical: 4m 0s)',
        ])],
        pending: 2, status: 'pending', max_similarity: 1.0, max_risk: 70,
        ...over,
    }
}

describe('caseVerdict', () => {
    it('templates the pair score and the strongest behaviour signal', () => {
        expect(caseVerdict(makeCase())).toBe(
            'Their code is identical once variable names are set aside, and Aarav pasted all of the final code 39 seconds after starting.')
    })

    it('gives the percentage when the code is not identical', () => {
        const c = makeCase({ pairs: [pair(10, 1, 2, 0.874)], behavioural: [] })
        expect(caseVerdict(c)).toBe('Their code is 87% the same once variable names are set aside.')
    })

    it('uses the username when there is no first name, and the time signal alone', () => {
        const c = makeCase({ behavioural: [bFlag(21, 2, ['Submitted 1m 5s after starting, on an easy problem (typical: 1m 30s)'])] })
        expect(caseVerdict(c)).toBe(
            'Their code is identical once variable names are set aside, and tara_shah96 submitted 1 min 5 s after starting.')
    })

    it('describes a single-student case from behaviour only', () => {
        const c = makeCase({ members: [aarav], pairs: [], behavioural: [bFlag(20, 1, ['Pasted 85% of final code (300 chars)'])] })
        expect(caseVerdict(c)).toBe('Aarav pasted 85% of the final code.')
    })

    it('handles tab switching and unknown signals without inventing detail', () => {
        const tab = makeCase({ members: [aarav], pairs: [], behavioural: [bFlag(20, 1, ['Left exam tab 6 times during this question'])] })
        expect(caseVerdict(tab)).toBe('Aarav left the exam tab 6 times.')
        const other = makeCase({ members: [aarav], pairs: [], behavioural: [bFlag(20, 1, ['Attempt 2 code is completely different from attempt 1 (10% similar) but suddenly passes'])] })
        expect(caseVerdict(other)).toBe("Aarav's behaviour was flagged: attempt 2 code is completely different from attempt 1 (10% similar) but suddenly passes.")
        const none = makeCase({ members: [aarav], pairs: [], behavioural: [bFlag(20, 1, [], 0.42)] })
        expect(caseVerdict(none)).toBe("Aarav's behaviour was flagged with risk 42.")
    })

    it('summarises a group of more than two students', () => {
        const carol = { student_id: 3, username: 'carol', first_name: '' }
        const c = makeCase({ members: [aarav, tara, carol], pairs: [pair(10, 1, 2, 0.95), pair(11, 2, 3, 0.9)], behavioural: [] })
        expect(caseVerdict(c)).toBe("3 students' code matches, up to 95% once variable names are set aside.")
    })

    it('prefers a flag that still counts over a dismissed one', () => {
        const c = makeCase({ behavioural: [
            bFlag(20, 1, ['Pasted 100% of final code (485 chars)'], 0.9, 'dismissed'),
            bFlag(21, 2, ['Left exam tab 5 times during this question'], 0.3),
        ] })
        expect(caseVerdict(c)).toBe('Their code is identical once variable names are set aside, and tara_shah96 left the exam tab 5 times.')
    })
})

describe('cluster labels and share', () => {
    it('labels a group covering a large share of takers a common solution', () => {
        expect(clusterLabel(40, 100)).toBe('Common solution')
        expect(clusterLabel(8, 100)).toBe('Likely copying')
        expect(clusterLabel(2, 100)).toBe('Likely copying')
    })
    it('never calls a tiny group a common solution, even in a tiny exam', () => {
        expect(clusterLabel(2, 2)).toBe('Likely copying')
    })
    it('has no label for a single student', () => {
        expect(clusterLabel(1, 100)).toBeNull()
    })
    it('computes the share of takers', () => {
        expect(shareOfTakers(1, 3)).toBe(33.3)
        expect(shareOfTakers(2, 0)).toBeNull()
    })
    it('treats more than six students as a large case', () => {
        expect(isLargeCase(makeCase({ members: Array.from({ length: 7 }, (_, i) => ({ ...aarav, student_id: i })) }))).toBe(true)
        expect(isLargeCase(makeCase())).toBe(false)
    })
})

describe('case card text', () => {
    it('joins names', () => {
        expect(joinNames(['a'])).toBe('a')
        expect(joinNames(['a', 'b'])).toBe('a and b')
        expect(joinNames(['a', 'b', 'c'])).toBe('a, b and c')
    })
    it('lists what is waiting, per student', () => {
        const c = makeCase({ behavioural: [bFlag(20, 1, []), bFlag(22, 1, []), bFlag(21, 2, [])] })
        expect(waitingLine(c)).toBe('Waiting: 1 similarity pair, 2 behaviour flags on Aarav, 1 behaviour flag on tara_shah96')
        expect(waitingLine(c, false)).toBe('Waiting: 1 similarity pair, 3 behaviour flags')
        expect(waitingLine(makeCase({ pairs: [pair(10, 1, 2, 1, 'confirmed')], behavioural: [] }))).toBe('Nothing waiting')
    })
    it('gives the top behaviour signals per student, lower-cased', () => {
        expect(topSignals(makeCase())).toEqual([
            { name: 'Aarav', text: 'pasted 100% of final code (485 chars)' },
            { name: 'Aarav', text: 'submitted 39s after starting, on a medium problem (typical: 4m 0s)' },
        ])
    })
    it('labels a case status', () => {
        expect(caseStatusLabel('pending')).toBe('Pending decision')
        expect(caseStatusLabel('mixed')).toBe('Partly confirmed')
        expect(caseStatusLabel('dismissed')).toBe('Dismissed')
    })
})

describe('caseHighlights', () => {
    it('lists flagged members with the student their code matches most', () => {
        const members = Array.from({ length: 8 }, (_, i) => ({ student_id: i + 1, username: `s${i + 1}`, first_name: '' }))
        const c = makeCase({
            members,
            pairs: [pair(1, 1, 2, 0.85), pair(2, 3, 1, 0.97), pair(3, 4, 5, 0.99)],
            behavioural: [bFlag(20, 1, [])],
        })
        expect(caseHighlights(c)).toEqual([{ member: members[0], partner: members[2], score: 0.97 }])
    })
    it('falls back to the strongest pair when nobody has a behaviour flag', () => {
        const members = Array.from({ length: 8 }, (_, i) => ({ student_id: i + 1, username: `s${i + 1}`, first_name: '' }))
        const c = makeCase({ members, pairs: [pair(1, 1, 2, 0.85), pair(3, 4, 5, 0.99)], behavioural: [] })
        expect(caseHighlights(c)).toEqual([{ member: members[3], partner: members[4], score: 0.99 }])
    })
})

describe('deciding a whole case', () => {
    it('collects every pending flag in the case', () => {
        const c = makeCase({ behavioural: [bFlag(20, 1, []), bFlag(21, 2, [], 0.5, 'confirmed')] })
        expect(pendingFlags(c)).toEqual([
            { kind: 'similarity', id: 10, label: 'Similarity pair: aarav_sharma0 and tara_shah96' },
            { kind: 'behavioural', id: 20, label: 'Behaviour flag on aarav_sharma0' },
        ])
    })

    it('uses the existing per-flag review endpoints', () => {
        expect(reviewPath({ kind: 'similarity', id: 5, label: '' })).toBe('/plagiarism/5/review/')
        expect(reviewPath({ kind: 'behavioural', id: 6, label: '' })).toBe('/plagiarism/behavioural/6/review/')
    })

    it('saves every flag, reports progress and returns the ones that failed', async () => {
        const flags: CaseFlag[] = [1, 2, 3, 4, 5].map(id => ({ kind: 'behavioural', id, label: `f${id}` }))
        const seen: number[] = []
        const progress: number[] = []
        const failed = await reviewAll(flags, async f => {
            seen.push(f.id)
            if (f.id === 3) throw new Error('nope')
        }, done => progress.push(done), 2)
        expect(seen.sort()).toEqual([1, 2, 3, 4, 5])
        expect(failed.map(f => f.id)).toEqual([3])
        expect(progress[progress.length - 1]).toBe(5)
    })
})

describe('renamed identifiers', () => {
    const a = ['let left = 0;', 'while (left < n) left++;']
    const b = ['let leftpointer = 0;', 'while (leftpointer < n) leftpointer++;']
    it('finds names that play the same part under a different name', () => {
        const { renamed1, renamed2 } = findRenamedNames(a, b)
        expect([...renamed1]).toEqual(['left'])
        expect([...renamed2]).toEqual(['leftpointer'])
    })
    it('splits a line so renamed names can be marked', () => {
        expect(splitRenamed('let left = left;', new Set(['left']))).toEqual([
            { text: 'let ', renamed: false },
            { text: 'left', renamed: true },
            { text: ' = ', renamed: false },
            { text: 'left', renamed: true },
            { text: ';', renamed: false },
        ])
    })
})


// ── acting on a student: notes per student, where the case was opened from ───────

describe('matched-only students', () => {
    it('are members with no behaviour flag that still counts', () => {
        const carol = { student_id: 3, username: 'carol', first_name: '' }
        const c = makeCase({
            members: [aarav, tara, carol],
            behavioural: [bFlag(20, 1, []), bFlag(21, 3, [], 0.5, 'dismissed')],
        })
        expect([...matchedOnly(c)].sort()).toEqual([2, 3])
    })
})

describe('planNotes: the note each flag carries', () => {
    const carol = { student_id: 3, username: 'carol', first_name: '' }
    // aarav and tara both have behaviour flags; carol only matched aarav's code
    const c = makeCase({
        members: [aarav, tara, carol],
        pairs: [pair(10, 1, 2, 1), pair(11, 1, 3, 0.9)],
        behavioural: [bFlag(20, 1, []), bFlag(21, 2, [])],
    })
    const flags = pendingFlags(c)

    it('puts one group note on every flag of students who get it', () => {
        const plan = planNotes(c, flags, sid => (sid === 3 ? '' : 'Same code'))
        expect(plan.notes).toEqual({ similarity10: 'Same code', similarity11: '', behavioural20: 'Same code', behavioural21: 'Same code' })
        expect(plan.reached).toEqual([1, 2])
        expect(plan.unreached).toEqual([])
    })

    it('gives a pair a note only when both of its students get the same one', () => {
        const notes: Record<number, string> = { 1: 'You shared it', 2: 'You copied it', 3: '' }
        const plan = planNotes(c, flags, sid => notes[sid]!)
        expect(plan.notes).toEqual({ similarity10: '', similarity11: '', behavioural20: 'You shared it', behavioural21: 'You copied it' })
        expect(plan.reached).toEqual([1, 2])
    })

    it('reaches a matched-only student only through a pair with the same note', () => {
        const same = planNotes(c, flags, () => 'Same code')
        expect(same.notes.similarity11).toBe('Same code')
        expect(same.reached).toEqual([1, 2, 3])
        // carol's own words can't travel: she has no behaviour flag and aarav's note differs
        const own = planNotes(c, flags, sid => (sid === 3 ? 'Please see me' : 'Same code'))
        expect(own.notes.similarity11).toBe('')
        expect(own.reached).toEqual([1, 2])
        expect(own.unreached).toEqual([3])
    })

    it('leaves out the flags it was not asked about (a retry)', () => {
        const plan = planNotes(c, flags.filter(f => f.kind === 'behavioural'), () => 'x')
        expect(Object.keys(plan.notes)).toEqual(['behavioural20', 'behavioural21'])
    })
})

describe('where the case file was opened from', () => {
    it('reads student and report origins and ignores anything else', () => {
        expect(parseCaseFrom('student:4')).toEqual({ kind: 'student', id: 4 })
        expect(parseCaseFrom('report:9')).toEqual({ kind: 'report', id: 9 })
        expect(parseCaseFrom('student:')).toBeNull()
        expect(parseCaseFrom('admin:3')).toBeNull()
        expect(parseCaseFrom(undefined)).toBeNull()
        expect(parseCaseFrom(['student:4'])).toBeNull()
    })

    it('links to one case and says where it was opened from', () => {
        expect(caseFileLink(9, '4', 'student:4')).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=student:4')
        expect(caseFileLink(9, '4', 'report:9')).toBe('/dashboard/plagiarism/cohorts/9?case=4&from=report:9')
        expect(caseFileLink(9, null, 'student:4')).toBe('/dashboard/plagiarism/cohorts/9?from=student:4')
    })
})

describe('decisionMessage', () => {
    it('says what was decided and who has the note', () => {
        expect(decisionMessage('confirmed', 4, 4)).toBe('Case confirmed for 4 students. Your note is on their results.')
        expect(decisionMessage('dismissed', 1, 1)).toBe('Case dismissed for 1 student. Your note is on their results.')
        expect(decisionMessage('confirmed', 4, 3)).toBe('Case confirmed for 4 students. Your note is on the results of 3 of them.')
        expect(decisionMessage('dismissed', 2, 0)).toBe('Case dismissed for 2 students.')
    })
})
