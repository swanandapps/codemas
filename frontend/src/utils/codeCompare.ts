// Which lines of two submissions match, for the side-by-side view on the exam case file.
// Lines are compared the way the detector compares code: comments dropped and every
// variable renamed by order of first appearance (VAR_0, VAR_1…), so `left` in one file and
// `leftpointer` in the other match when they play the same part. Keywords and property /
// method names (anything after a dot) are kept, so `x.push(y)` never matches `x.pop(y)`.

const KEYWORDS = new Set([
    // JavaScript
    'const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'do', 'break', 'continue',
    'new', 'typeof', 'instanceof', 'in', 'of', 'true', 'false', 'null', 'undefined', 'this', 'class',
    'extends', 'super', 'import', 'export', 'default', 'try', 'catch', 'finally', 'throw', 'switch',
    'case', 'async', 'await', 'yield', 'delete', 'void',
    // Python
    'def', 'elif', 'not', 'and', 'or', 'is', 'None', 'True', 'False', 'from', 'as', 'with', 'except',
    'raise', 'lambda', 'pass', 'global', 'nonlocal',
])

const IDENTIFIER = /(\.\s*)?\b([A-Za-z_$][\w$]*)\b/g

/** Each line with comments removed and variables renamed consistently across the whole file.
 *  `names` collects each original name's placeholder (VAR_0, VAR_1…). */
function normalizeLines(lines: string[], names = new Map<string, string>()): string[] {
    return lines.map(raw => raw
        .replace(/\/\/.*$/, '')          // JS line comment
        .replace(/(^|\s)#.*$/, '')       // Python comment
        .trim()
        .replace(IDENTIFIER, (whole, dot: string | undefined, id: string) => {
            if (dot || KEYWORDS.has(id)) return whole
            if (!names.has(id)) names.set(id, `VAR_${names.size}`)
            return names.get(id)!
        }))
}

// A line with no letters or digits (`}`, `});`) matches everywhere and proves nothing
const meaningful = (line: string) => /[A-Za-z0-9]/.test(line)

export function findMatchedLines(lines1: string[], lines2: string[]): { matched1: Set<number>, matched2: Set<number> } {
    const norm1 = normalizeLines(lines1)
    const norm2 = normalizeLines(lines2)
    const where2 = new Map<string, number[]>()
    norm2.forEach((line, j) => {
        if (!meaningful(line)) return
        if (!where2.has(line)) where2.set(line, [])
        where2.get(line)!.push(j)
    })
    const matched1 = new Set<number>()
    const matched2 = new Set<number>()
    norm1.forEach((line, i) => {
        const hits = meaningful(line) ? where2.get(line) : undefined
        if (!hits) return
        matched1.add(i)
        hits.forEach(j => matched2.add(j))
    })
    return { matched1, matched2 }
}

/** Names that play the same part in both files under a different spelling (`left` / `leftpointer`),
 *  for underlining on the case file. */
export function findRenamedNames(lines1: string[], lines2: string[]): { renamed1: Set<string>, renamed2: Set<string> } {
    const names1 = new Map<string, string>()
    const names2 = new Map<string, string>()
    normalizeLines(lines1, names1)
    normalizeLines(lines2, names2)
    const byVar2 = new Map([...names2].map(([name, v]) => [v, name]))
    const renamed1 = new Set<string>()
    const renamed2 = new Set<string>()
    names1.forEach((v, name) => {
        const other = byVar2.get(v)
        if (other !== undefined && other !== name) {
            renamed1.add(name)
            renamed2.add(other)
        }
    })
    return { renamed1, renamed2 }
}

/** A line cut into pieces, with each renamed name (not a property after a dot) as its own piece. */
export function splitRenamed(line: string, renamed: Set<string>): { text: string, renamed: boolean }[] {
    const out: { text: string, renamed: boolean }[] = []
    let last = 0
    for (const m of line.matchAll(IDENTIFIER)) {
        if (m[1] || !renamed.has(m[2]!)) continue
        if (m.index! > last) out.push({ text: line.slice(last, m.index), renamed: false })
        out.push({ text: m[2]!, renamed: true })
        last = m.index! + m[0].length
    }
    if (last < line.length) out.push({ text: line.slice(last), renamed: false })
    return out
}
