/**
 * Where the login lives. Each tab keeps its own (sessionStorage), so a trainer and two
 * students can be signed in side by side in one browser and a refresh keeps each tab's
 * account. A new tab starts from the most recent login (localStorage), so a link opened
 * in a new tab stays signed in.
 */

export interface Auth {
    access: string
    refresh: string
    user: { id: number; username: string; email: string; role: 'student' | 'trainer' | 'admin'; cohort: string }
}

const TAB = 'codemas:auth'
const LAST = 'codemas:last-auth'

function read(store: Storage, key: string): Auth | null {
    try { return JSON.parse(store.getItem(key) || 'null') } catch { return null }
}

function write(store: Storage, key: string, auth: Auth | null): void {
    try {
        if (auth) store.setItem(key, JSON.stringify(auth))
        else store.removeItem(key)
    } catch { /* storage unavailable: the login lasts until the tab closes */ }
}

// Logins saved before per-tab sessions (flat keys) carry over once.
function legacy(): Auth | null {
    try {
        const access = localStorage.getItem('access_token')
        const user = JSON.parse(localStorage.getItem('user') || 'null')
        if (!access || !user) return null
        return { access, refresh: localStorage.getItem('refresh_token') || '', user }
    } catch { return null }
}

/** This tab's login, adopting the most recent one if the tab has none yet. */
export function getAuth(): Auth | null {
    const own = read(sessionStorage, TAB)
    if (own) return own
    const last = read(localStorage, LAST) ?? legacy()
    if (last) write(sessionStorage, TAB, last)
    return last
}

function isLast(auth: Auth | null): boolean {
    const last = read(localStorage, LAST)
    return !!auth && !!last && last.user.id === auth.user.id
}

/** A fresh login: this tab's account, and the one new tabs start with. */
export function saveLogin(auth: Auth): void {
    write(sessionStorage, TAB, auth)
    write(localStorage, LAST, auth)
}

/** A refreshed access token for this tab's account. */
export function updateAccess(access: string): void {
    const auth = getAuth()
    if (!auth) return
    const next = { ...auth, access }
    if (isLast(auth)) write(localStorage, LAST, next)
    write(sessionStorage, TAB, next)
}

/** Sign this tab out; other tabs keep their own accounts. */
export function clearLogin(): void {
    const auth = read(sessionStorage, TAB)
    if (isLast(auth)) write(localStorage, LAST, null)
    write(sessionStorage, TAB, null)
    try { ['access_token', 'refresh_token', 'user'].forEach(k => localStorage.removeItem(k)) } catch { /* ignore */ }
}
