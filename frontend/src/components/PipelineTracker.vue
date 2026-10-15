<template>
    <div class="pipeline-tracker">
        <div v-if="showBanner" class="pt-banner" aria-live="polite">
            <span class="pt-banner-chip" :style="{ background: bannerFill }"></span>
            <span class="pt-banner-label" :style="{ color: bannerInk }">{{ bannerLabel }}</span>
            <span class="pt-banner-text">{{ bannerText }}</span>
            <div class="pt-banner-spacer"></div>
            <span v-if="elapsedLabel" class="pt-banner-elapsed">{{ elapsedLabel }}</span>
        </div>

        <div class="pt-groups">
            <div v-for="g in groups" :key="g.key" class="pt-group">
                <span class="pt-group-label" :style="{ color: g.reached ? g.ink : 'var(--text-dim)' }">{{ g.label }}</span>
                <div class="pt-dots">
                    <span
                        v-for="d in g.dots"
                        :key="d.key"
                        class="pt-dot"
                        :class="d.state"
                        :title="d.title"
                        :aria-label="d.aria"
                        :style="d.styleVars"
                    ></span>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Stage = 'idle' | 'submit' | 'queue' | 'execute' | 'grade' | 'feedback' | 'done'

interface TestEntry {
    passed: boolean
}

const props = withDefaults(defineProps<{
    stage: Stage
    tests: TestEntry[] | null
    testCount: number
    rubricReady: boolean
    hintExpected: boolean
    hintReady: boolean
    elapsedMs: number | null
    showBanner?: boolean
    outOfAttempts?: boolean   // idle with no attempts left: say so instead of "Ready"
}>(), {
    showBanner: true,
    outOfAttempts: false,
})

// Ordering of stages, used to decide what's "reached" / "current" / "done".
const STAGE_ORDER: Stage[] = ['idle', 'submit', 'queue', 'execute', 'grade', 'feedback', 'done']

function stageIndex(s: Stage): number {
    return STAGE_ORDER.indexOf(s)
}

const currentIndex = computed(() => stageIndex(props.stage))

const elapsedLabel = computed(() => {
    if (props.elapsedMs === null || props.stage === 'idle') return ''
    return (props.elapsedMs / 1000).toFixed(1) + ' s'
})

interface GroupDef {
    key: string
    label: string
    fill: string
    ink: string
    stage: Stage
    dotDefs: Array<{ key: string; label: string; isTest?: boolean; testIndex?: number }>
}

const groupDefs = computed<GroupDef[]>(() => {
    const execDots = []
    const n = props.testCount || 0
    for (let i = 0; i < n; i++) {
        execDots.push({ key: 'test-' + i, label: 'Test ' + (i + 1), isTest: true, testIndex: i })
    }

    const feedbackDots: Array<{ key: string; label: string }> = [
        { key: 'rubric', label: 'Rubric scored' },
    ]
    if (props.hintExpected) {
        feedbackDots.push({ key: 'hint', label: 'Hint ready' })
    }

    return [
        {
            key: 'submit',
            label: 'Submit',
            fill: 'var(--accent)',
            ink: 'var(--text)',
            stage: 'submit',
            dotDefs: [
                { key: 'code-sent', label: 'Code sent' },
                { key: 'saved', label: 'Saved' },
            ],
        },
        {
            key: 'queue',
            label: 'Queue',
            fill: 'var(--accent)',
            ink: 'var(--text)',
            stage: 'queue',
            dotDefs: [
                { key: 'queued', label: 'Queued' },
                { key: 'picked-up', label: 'Picked up' },
            ],
        },
        {
            key: 'execute',
            label: 'Execute',
            fill: 'var(--accent)',
            ink: 'var(--text)',
            stage: 'execute',
            dotDefs: execDots,
        },
        {
            key: 'grade',
            label: 'Grade',
            fill: 'var(--accent)',
            ink: 'var(--text)',
            stage: 'grade',
            dotDefs: [
                { key: 'results-stored', label: 'Results stored' },
                { key: 'verdict', label: 'Verdict' },
            ],
        },
        {
            key: 'feedback',
            label: 'Feedback',
            fill: 'var(--accent)',
            ink: 'var(--text)',
            stage: 'feedback',
            dotDefs: feedbackDots,
        },
    ]
})

// Decide the state of a single dot within a group, given where the overall
// pipeline currently is and (for Execute) the real test results.
function dotState(groupStage: Stage, dotKey: string, dotIndex: number, totalDots: number, testIdx?: number): 'waiting' | 'in-progress' | 'done' | 'passed' | 'failed' {
    const gi = stageIndex(groupStage)
    if (props.stage === 'idle') return 'waiting'

    // Test dots: once results are known for that index, reflect pass/fail —
    // independent of overall stage, since results can resolve before 'grade'.
    if (testIdx !== undefined && props.tests && props.tests[testIdx]) {
        return props.tests[testIdx].passed ? 'passed' : 'failed'
    }

    if (currentIndex.value > gi) return 'done'
    if (currentIndex.value === gi) {
        // Within the current group, light dots progressively based on index
        // for groups with no finer-grained real signal (we only know "we are
        // in this phase", not sub-steps) — treat the first dot as in-progress.
        if (testIdx !== undefined) return 'in-progress'
        return dotIndex === 0 ? 'in-progress' : 'waiting'
    }
    return 'waiting'
}

const groups = computed(() => {
    return groupDefs.value.map((g) => {
        const reached = currentIndex.value >= stageIndex(g.stage)
        const total = g.dotDefs.length
        const dots = g.dotDefs.map((d, i) => {
            let state = dotState(g.stage, d.key, i, total, d.testIndex)

            // Feedback group special-casing using real readiness signals.
            if (g.key === 'feedback') {
                if (d.key === 'rubric') {
                    if (props.rubricReady) state = 'done'
                    else if (props.stage === 'feedback') state = 'in-progress'
                    else state = currentIndex.value > stageIndex('feedback') ? 'done' : 'waiting'
                } else if (d.key === 'hint') {
                    if (props.hintReady) state = 'done'
                    else if (props.stage === 'feedback' && props.rubricReady) state = 'in-progress'
                    else state = 'waiting'
                }
                if (props.stage === 'done') {
                    if (d.key === 'rubric') state = 'done'
                    if (d.key === 'hint') state = props.hintReady ? 'done' : 'waiting'
                }
            }

            const styleVars: Record<string, string> = {}
            if (state === 'done') {
                // Completed stages are near-black; red is reserved for the stage in progress,
                // so a finished run never looks like a row of failures.
                styleVars['background'] = 'var(--text)'
            } else if (state === 'passed') {
                styleVars['background'] = 'var(--green)'
            } else if (state === 'failed') {
                styleVars['border'] = '2px solid var(--red-ink)'
            } else if (state === 'in-progress') {
                styleVars['border'] = `2px solid ${g.fill}`
            }

            return {
                key: d.key,
                title: d.label,
                aria: `${d.label}: ${state === 'in-progress' ? 'in progress' : state}`,
                state: state === 'in-progress' ? 'in-progress' : state,
                styleVars,
            }
        })

        return {
            key: g.key,
            label: g.label,
            ink: g.ink,
            reached,
            dots,
        }
    })
})

const bannerFill = computed(() => {
    switch (props.stage) {
        case 'submit':
        case 'queue':
        case 'execute':
        case 'grade':
        case 'feedback': return 'var(--accent)'
        case 'done': return 'var(--green)'
        default: return 'var(--text-dim)'
    }
})

const bannerInk = computed(() => {
    switch (props.stage) {
        case 'submit':
        case 'queue':
        case 'execute':
        case 'grade':
        case 'feedback': return 'var(--red-ink)'
        case 'done': return 'var(--green-ink)'
        default: return 'var(--text-muted)'
    }
})

const bannerLabel = computed(() => {
    switch (props.stage) {
        case 'submit': return 'Submit'
        case 'queue': return 'Queue'
        case 'execute': return 'Execute'
        case 'grade': return 'Grade'
        case 'feedback': return 'Feedback'
        case 'done': return 'Done'
        default: return props.outOfAttempts ? 'No attempts left' : 'Ready'
    }
})

const bannerText = computed(() => {
    const n = props.testCount || 0
    switch (props.stage) {
        case 'submit': return 'Saving your submission'
        case 'queue': return 'Waiting in line'
        case 'execute': return `Running ${n} test cases`
        case 'grade': return 'Storing results'
        case 'feedback': return 'Result ready. Scoring rubric review.'
        case 'done': {
            let text = 'Graded. Rubric review is ready.'
            if (props.hintExpected && props.hintReady) text = 'Graded. Rubric review and a hint are ready.'
            return text
        }
        default: return props.outOfAttempts
            ? 'You have used every attempt on this question.'
            : `Submit to run your code against ${n} test cases.`
    }
})
</script>

<style scoped>
.pipeline-tracker {
    display: flex;
    flex-direction: column;
    gap: 16px;
}

.pt-banner {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 18px;
    border-radius: var(--radius-pill);
    background: var(--surface2);
}
.pt-banner-chip {
    width: 9px;
    height: 9px;
    border-radius: 50%;
    flex-shrink: 0;
}
.pt-banner-label {
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 600;
}
.pt-banner-text {
    font-size: 14px;
    color: var(--text);
}
.pt-banner-spacer {
    flex-grow: 1;
}
.pt-banner-elapsed {
    font-family: var(--font-mono);
    font-size: 13px;
    color: var(--text-muted);
    font-variant-numeric: tabular-nums;
}

.pt-groups {
    display: flex;
    gap: 36px;
    padding: 0 2px;
    flex-wrap: wrap;
}
.pt-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.pt-group-label {
    font-family: var(--font-display);
    font-size: 13px;
    font-weight: 600;
}
.pt-dots {
    display: flex;
    gap: 7px;
    margin-top: 4px;
    flex-wrap: wrap;
}

.pt-dot {
    display: block;
    width: 11px;
    height: 11px;
    border-radius: 50%;
    box-sizing: border-box;
    border: 1.5px solid #A8A0A1; /* visible on white; waiting stages */
}
.pt-dot.done,
.pt-dot.passed {
    border: none;
}
.pt-dot.failed {
    border-radius: 2px;
}
.pt-dot.in-progress {
    animation: pt-pulse 1s ease-in-out infinite;
}

@keyframes pt-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.4; transform: scale(0.75); }
}

@media (prefers-reduced-motion: reduce) {
    .pt-dot.in-progress {
        animation: none !important;
    }
}
</style>
