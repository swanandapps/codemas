import { reactive } from 'vue'
import api from '../api'

/** The newest new item for a student's Home banner (GET /support/attention/). */
export interface AttentionItem {
    kind: 'decision' | 'ruling'
    exam_id: number | null
    exam_title: string | null
    appeal_id?: number
    status?: 'upheld' | 'overturned'
    at: string
}

/** Badge counts. A student gets new decisions and rulings since they last opened My results
 *  or Disputes; a trainer gets live counts of open appeals and cases to decide. */
export interface Attention {
    new_decisions?: number
    new_rulings?: number
    latest?: AttentionItem | null
    open_appeals?: number
    cases_to_decide?: number
}

// One copy shared by the sidebar and the pages that show the same counts
export const attention = reactive<{ data: Attention | null }>({ data: null })

let inflight: Promise<Attention | null> | null = null
let seenMarks = 0   // bumped each time the student marks things seen

function seen(data: Attention): Attention {
    return { ...data, new_decisions: 0, new_rulings: 0, latest: null }
}

/** Fetch the counts; calls made while one is in flight share it, so a navigation that mounts
 *  the sidebar and a page together asks once. No polling: callers load on navigation. */
export function loadAttention(): Promise<Attention | null> {
    if (inflight) return inflight
    const marks = seenMarks
    inflight = api.get('/support/attention/')
        .then(res => {
            const data = res.data as Attention
            // asked before this visit marked everything seen: its "new" counts are already stale
            attention.data = marks === seenMarks ? data : seen(data)
            return attention.data
        })
        .catch(() => null)
        .finally(() => { inflight = null })
    return inflight
}

/** The student opened My results or Disputes: what's there is seen, the badges and banner clear. */
export async function markIntegritySeen(): Promise<void> {
    try {
        await api.post('/support/attention/seen/')
    } catch {
        return   // the badge just stays until the next visit
    }
    seenMarks++
    if (attention.data) attention.data = seen(attention.data)
}

/** Tests only: forget the shared counts. */
export function resetAttention(): void {
    attention.data = null
    inflight = null
}
