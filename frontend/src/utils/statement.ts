// Splits a question description into a problem statement and headed sections
// (Input format, Output format, Constraints, Note) so the exam page can show
// them under their own headings. Works on labels at the start of a line
// ("Input (line 1): ...") and on labels run into one paragraph ("... target. Input format: ...").

export interface StatementSection {
    heading: string
    items: string[]
}

export interface Statement {
    statement: string[]            // paragraphs before the first label
    sections: StatementSection[]
}

const LABEL = /(^|\n|[.!?][ \t]+)(input format|input \(line (\d+)\)|input|output format|output|constraints?|notes?)[ \t]*:/gi

function headingFor(label: string): string {
    const l = label.toLowerCase()
    if (l.startsWith('input')) return 'Input format'
    if (l.startsWith('output')) return 'Output format'
    if (l.startsWith('constraint')) return 'Constraints'
    return 'Note'
}

/** One item per line; a single line of several sentences becomes one item per sentence. */
function splitItems(body: string): string[] {
    const lines = body.split('\n').map(l => l.trim()).filter(Boolean)
    if (lines.length !== 1) return lines
    return lines[0]!.split(/(?<=[.!?])\s+(?=[A-Z])/).map(s => s.trim()).filter(Boolean)
}

export function parseStatement(description: string | null | undefined): Statement {
    const text = (description || '').replace(/\r\n/g, '\n')
    const matches = [...text.matchAll(LABEL)]
    // The text before a label ends at the label, keeping a sentence's closing punctuation.
    const chunkEnd = (m: RegExpMatchArray) => m.index! + (/^[.!?]/.test(m[1]!) ? 1 : 0)

    const head = text.slice(0, matches.length ? chunkEnd(matches[0]!) : text.length)
    const statement = head.split(/\n\s*\n/).map(p => p.trim()).filter(Boolean)

    const sections: StatementSection[] = []
    matches.forEach((m, i) => {
        const next = matches[i + 1]
        const body = text.slice(m.index! + m[0].length, next ? chunkEnd(next) : text.length)
        const line = m[3]
        const items = splitItems(body).map(item => (line ? `Line ${line}: ${item}` : item))
        const heading = headingFor(m[2]!)
        const existing = sections.find(s => s.heading === heading)
        if (existing) existing.items.push(...items)
        else if (items.length) sections.push({ heading, items })
    })
    return { statement, sections }
}
