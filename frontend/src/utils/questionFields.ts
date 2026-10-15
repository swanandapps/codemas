// A question's description is one text field on the server. The Create exam page edits it
// as separate fields (Problem, Input format, Output format, Constraints, Note) and joins them
// back in the layout parseStatement reads, so the exam page shows the same headed sections.

import { parseStatement } from './statement'

export interface QuestionFields {
    problem: string        // paragraphs separated by a blank line
    inputFormat: string    // one item per line
    outputFormat: string
    constraints: string
    note: string
}

// Written in this order; parseStatement gives each its own heading
const SECTIONS: [keyof QuestionFields, string][] = [
    ['inputFormat', 'Input format'],
    ['outputFormat', 'Output format'],
    ['constraints', 'Constraints'],
    ['note', 'Note'],
]

export function emptyFields(): QuestionFields {
    return { problem: '', inputFormat: '', outputFormat: '', constraints: '', note: '' }
}

/** Split a stored description into the editor's fields. */
export function decomposeDescription(description: string | null | undefined): QuestionFields {
    const parsed = parseStatement(description)
    const fields = emptyFields()
    fields.problem = parsed.statement.join('\n\n')
    for (const [key, heading] of SECTIONS) {
        fields[key] = parsed.sections.find(s => s.heading === heading)?.items.join('\n') ?? ''
    }
    return fields
}

/** Join the fields into one description: problem, then "Heading:" + lines per non-empty section. */
export function composeDescription(fields: QuestionFields): string {
    const parts = [fields.problem.trim()]
    for (const [key, heading] of SECTIONS) {
        const body = fields[key].trim()
        if (body) parts.push(`${heading}:\n${body}`)
    }
    return parts.filter(Boolean).join('\n\n')
}

// Small words a cut-off title shouldn't end on ("Given an array of integers and" → "… integers")
const TRAILING_SMALL = new Set(['a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'with', 'from', 'by', 'at', 'is', 'are'])

/** A short title from free text: its first sentence, cut to about six words, first letter capitalised. '' for empty text. */
export function shortTitle(text: string | null | undefined, maxWords = 6): string {
    const firstLine = (text || '').trim().split('\n')[0]!.trim()
    const sentence = firstLine.split(/(?<=[.!?:;])\s/)[0]!.replace(/[.!?:;,]+$/, '').trim()
    const words = sentence.split(/\s+/).filter(Boolean).slice(0, maxWords)
    if (words.length === maxWords) {
        while (words.length > 1 && TRAILING_SMALL.has(words[words.length - 1]!.toLowerCase())) words.pop()
    }
    const title = words.join(' ').replace(/[,;:]+$/, '')
    return title ? title.charAt(0).toUpperCase() + title.slice(1) : ''
}
