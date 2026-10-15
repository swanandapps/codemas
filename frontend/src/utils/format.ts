// Shared display formatting so every page shows dates, percentages and durations the same way.

type DateInput = string | number | Date | null | undefined

function toDate(value: DateInput): Date | null {
    if (value === null || value === undefined || value === '') return null
    const d = value instanceof Date ? value : new Date(value)
    return Number.isNaN(d.getTime()) ? null : d
}

/** "26 Jun 2026", or an em dash when there's no date. */
export function formatDate(value: DateInput): string {
    const d = toDate(value)
    if (!d) return '—'
    return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

/** "26 Jun 2026, 11:58" */
export function formatDateTime(value: DateInput): string {
    const d = toDate(value)
    if (!d) return '—'
    const time = d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
    return `${formatDate(d)}, ${time}`
}

/**
 * Percentages with one decimal ("61.8%"), but whole numbers at the ends ("0%", "100%").
 * Pass `null` when there is nothing to measure (e.g. no submissions) to get an em dash.
 */
export function formatPct(value: number | null | undefined, digits = 1): string {
    if (value === null || value === undefined || Number.isNaN(value)) return '—'
    if (value === 0 || value === 100) return `${value}%`
    return `${value.toFixed(digits)}%`
}

/** Milliseconds as "850 ms" under a second, otherwise "1.9 s". */
export function formatMs(ms: number | null | undefined): string {
    if (ms === null || ms === undefined || Number.isNaN(ms)) return '—'
    if (ms < 1000) return `${Math.round(ms)} ms`
    return `${(ms / 1000).toFixed(1)} s`
}

/** Seconds as "45 s", "8 min" or "1 min 30 s". */
export function formatSeconds(seconds: number | null | undefined): string {
    if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return '—'
    const s = Math.round(seconds)
    if (s < 60) return `${s} s`
    const m = Math.floor(s / 60)
    const rest = s % 60
    return rest ? `${m} min ${rest} s` : `${m} min`
}

/** "1 question", "3 questions". Pass the plural when it isn't just +s. */
export function plural(n: number, singular: string, pluralForm?: string): string {
    return `${n} ${n === 1 ? singular : (pluralForm ?? `${singular}s`)}`
}

/**
 * A submission's status as students see it, the same on every page. 'error' means it
 * couldn't be graded (it doesn't use up an attempt), so it isn't called a failure.
 */
export function submissionStatusLabel(status: string | null | undefined): string {
    return status === 'error' ? "Couldn't run" : humanize(status)
}

/** Turns raw enum values like "pending_review" into "Pending review". */
export function humanize(value: string | null | undefined): string {
    if (!value) return '—'
    const s = value.replace(/[_-]+/g, ' ').trim().toLowerCase()
    return s.charAt(0).toUpperCase() + s.slice(1)
}

/** Risk for one behavioural flag: risk_score × 100 as a whole number ("73"). Pass the raw 0–1 score. */
export function formatRisk(score: number | null | undefined): string {
    if (score === null || score === undefined || Number.isNaN(score)) return '—'
    return `${Math.round(score * 100)}`
}
