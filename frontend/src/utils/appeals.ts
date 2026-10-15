// Appeals: one round per exam. A student responds once to a confirmed plagiarism decision;
// a trainer upholds or overturns it, and the ruling is final.

export type AppealStatus = 'open' | 'upheld' | 'overturned'
export type IntegrityOutcome = 'withheld' | 'overturned' | 'confirmed' | 'dismissed'

/** The student's integrity outcome on one exam (leaderboard/me/exams/ `integrity`). */
export interface ExamIntegrity {
    outcome: IntegrityOutcome
    points_withheld: number
    appeal: AppealStatus | null
    can_appeal: boolean
}

/** A student's own appeal (GET /support/disputes/mine/). */
export interface MyAppeal {
    id: number
    exam_id: number | null
    exam_title: string | null
    status: AppealStatus
    student_note: string
    decision_note: string
    resolution_note: string
    created_at: string
    resolved_at: string | null
    is_new?: boolean
}

export const APPEAL_NOTE_MAX = 1000

/** The review box's headline on My results. */
export function outcomeHeadline(i: ExamIntegrity): string {
    switch (i.outcome) {
        case 'withheld': return `Points withheld: plagiarism confirmed (−${i.points_withheld})`
        case 'overturned': return 'Decision overturned: points restored'
        case 'confirmed': return 'Plagiarism confirmed: no points withheld'
        default: return 'Reviewed — no action taken'
    }
}

/** How the student sees their appeal's status. */
export const STUDENT_APPEAL_STATUS: Record<AppealStatus, string> = {
    open: 'Waiting for your trainer',
    upheld: 'Decision upheld',
    overturned: 'Decision overturned — points restored',
}

/** How a trainer sees an appeal's status. */
export const TRAINER_APPEAL_STATUS: Record<AppealStatus, string> = {
    open: 'Open',
    upheld: 'Upheld',
    overturned: 'Overturned',
}

export function appealBadgeClass(status: string): string {
    return status === 'open' ? 'badge-yellow' : status === 'overturned' ? 'badge-green' : 'badge-dim'
}
