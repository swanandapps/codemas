// The Create exam page's unsaved work, kept in this browser so a reload doesn't lose a generated
// draft (and cost another generation). Keyed by trainer, so someone else on the same computer
// never sees it; cleared when the exam is saved or the trainer starts over; a week-old draft is
// dropped. Storage can be missing or full (private windows, blocked site data): every call is
// best effort and never throws.

export const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000

const keyFor = (username: string) => `codemas:create-exam-draft:${username}`

export function saveDraft(username: string | undefined, state: Record<string, unknown>): void {
    if (!username) return
    try {
        localStorage.setItem(keyFor(username), JSON.stringify({ v: 1, savedAt: Date.now(), state }))
    } catch { /* storage unavailable or full: the page still works, just without restore */ }
}

export function loadDraft(username: string | undefined): Record<string, any> | null {
    if (!username) return null
    try {
        const raw = localStorage.getItem(keyFor(username))
        if (!raw) return null
        const saved = JSON.parse(raw)
        if (saved?.v !== 1 || typeof saved.savedAt !== 'number' || Date.now() - saved.savedAt > DRAFT_MAX_AGE_MS) {
            localStorage.removeItem(keyFor(username))
            return null
        }
        return { ...saved.state, savedAt: saved.savedAt }
    } catch {
        return null
    }
}

export function clearDraft(username: string | undefined): void {
    if (!username) return
    try { localStorage.removeItem(keyFor(username)) } catch { /* nothing to clear */ }
}
