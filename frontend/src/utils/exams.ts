// Exam status, one meaning on every page. The server sends `status`
// (exams.models.exam_status): ended once the end time has passed, live while
// open and not past its end time, otherwise draft.

export type ExamStatus = 'draft' | 'live' | 'ended'

const EXAM_STATUS_LABEL: Record<ExamStatus, string> = { draft: 'Draft', live: 'Live', ended: 'Ended' }

/** "Draft", "Live", "Ended". */
export function examStatusLabel(status: string | null | undefined): string {
    return EXAM_STATUS_LABEL[status as ExamStatus] ?? '—'
}

/** A student can start (or go back to) an exam that is open and that they haven't submitted. Same rule as the Exams page. */
export function canStartExam(exam: { is_active: boolean; finished_at?: string | null }): boolean {
    return exam.is_active && !exam.finished_at
}

// Only an ended exam can be (re-)checked: ending a live exam runs the check itself, the same rule
// as the exam report's button
export function canRunPlagiarismCheck(exam: { status: string; total_submissions: number }): boolean {
    return exam.status === 'ended'
}

/** Marks per question by difficulty. Mirrors exams.models.Question.POINTS_MAP on the server. */
export const DIFFICULTY_POINTS = { easy: 10, medium: 20, hard: 30 } as const
export type Difficulty = keyof typeof DIFFICULTY_POINTS

export interface ScheduleProblems { start?: string; end?: string }

/** Problems with a schedule typed into datetime-local inputs. The opening time is required and in the
 *  future; the closing time is optional (as on the exam report) and, when set, after the opening time. */
export function scheduleProblems(start: string, end: string, now: Date = new Date()): ScheduleProblems {
    const out: ScheduleProblems = {}
    const opens = start ? new Date(start) : null
    if (!opens) out.start = 'Pick when the exam opens'
    else if (isNaN(opens.getTime())) out.start = 'Enter a valid opening date and time'
    else if (opens <= now) out.start = 'Pick an opening time in the future'
    if (end) {
        const closes = new Date(end)
        if (isNaN(closes.getTime())) out.end = 'Enter a valid closing date and time'
        else if (opens && !isNaN(opens.getTime()) && closes <= opens) out.end = 'The closing time must be after the opening time'
    }
    return out
}

/** The value a datetime-local input expects, in the browser's time zone. */
export function toLocalInput(d: Date): string {
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
