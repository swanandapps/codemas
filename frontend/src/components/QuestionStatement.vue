<template>
    <!-- What a student reads for a question: the exam page and the Create exam previews both
         render through here, so the two can never drift -->
    <div class="q-body">
        <div class="q-section">
            <h2 class="q-heading">Problem</h2>
            <p v-for="(para, i) in statement.statement" :key="i" class="q-text">{{ para }}</p>
        </div>
        <div v-for="section in statement.sections" :key="section.heading" class="q-section">
            <h2 class="q-heading">{{ section.heading }}</h2>
            <ul v-if="section.items.length > 1" class="q-list">
                <li v-for="(item, i) in section.items" :key="i">{{ item }}</li>
            </ul>
            <p v-else class="q-text">{{ section.items[0] }}</p>
        </div>
        <div v-for="(ex, i) in examples" :key="ex.id ?? i" class="q-section">
            <h2 class="q-heading">Example {{ i + 1 }}</h2>
            <div class="q-example">
                <span class="q-example-label">Input</span>
                <pre class="q-example-io">{{ ex.input_data }}</pre>
                <span class="q-example-label">Output</span>
                <pre class="q-example-io">{{ ex.expected_output }}</pre>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { parseStatement } from '../utils/statement'

interface StatementTestCase {
    id?: number
    is_hidden?: boolean
    input_data?: string        // a student only receives it for visible (sample) tests
    expected_output?: string
}

const props = defineProps<{ description: string | null | undefined; testCases?: StatementTestCase[] }>()

// Description split into Problem / Input format / Output format / Constraints sections
const statement = computed(() => parseStatement(props.description))
// Visible test cases double as worked examples; hidden ones never reach the student
const examples = computed(() =>
    (props.testCases || []).filter(tc => !tc.is_hidden && tc.input_data != null))
</script>

<style scoped>
.q-body { display: flex; flex-direction: column; gap: 20px; max-width: 58ch; }
.q-section { display: flex; flex-direction: column; gap: 8px; }
.q-heading {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text);
}
.q-text {
    margin: 0;
    font-size: 15px;
    line-height: 1.65;
    color: #3B3435;
    white-space: pre-line;
}
.q-list {
    margin: 0;
    padding-left: 20px;
    font-size: 15px;
    line-height: 1.65;
    color: #3B3435;
}
.q-example {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: 8px 12px;
    align-items: start;
    padding: 12px 14px;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--bg);
}
.q-example-label { font-size: 13px; font-weight: 600; color: var(--text-muted); padding-top: 2px; }
.q-example-io {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 14px;
    white-space: pre-wrap;
    word-break: break-word;
    color: var(--text);
}
</style>
