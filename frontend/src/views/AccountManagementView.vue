<template>
    <div class="accounts-page">
        <div class="page-header">
            <div>
                <h1>Account Management</h1>
                <p class="page-sub">Create and manage student accounts</p>
            </div>
            <button class="create-btn" @click="showForm = !showForm">
                {{ showForm ? 'Cancel' : '+ New Student' }}
            </button>
        </div>

        <!-- Create form -->
        <div v-if="showForm" class="create-card">
            <h3>Create Student Account</h3>
            <div class="form-grid">
                <div class="field">
                    <label>Username</label>
                    <input v-model="form.username" placeholder="student_username" />
                </div>
                <div class="field">
                    <label>Email</label>
                    <input v-model="form.email" type="email" placeholder="student@example.com" />
                </div>
                <div class="field">
                    <label>Password</label>
                    <input v-model="form.password" type="password" placeholder="••••••••" />
                </div>
                <div class="field">
                    <label>Cohort</label>
                    <input v-model="form.cohort" placeholder="e.g. Batch-A, 2026" />
                </div>
            </div>
            <div v-if="createError" class="form-error">{{ createError }}</div>
            <div class="form-actions">
                <button class="submit-btn" @click="createStudent" :disabled="creating">
                    {{ creating ? 'Creating...' : 'Create Student' }}
                </button>
            </div>
        </div>

        <!-- CSV Bulk Import -->
        <div class="csv-card">
            <div class="csv-header">
                <div>
                    <div class="csv-title">Bulk Import via CSV</div>
                    <div class="csv-sub">CSV format: username,email,password,cohort</div>
                </div>
                <label class="csv-btn">
                    Choose File
                    <input type="file" accept=".csv" @change="handleCSV" style="display:none" />
                </label>
            </div>
            <div v-if="csvResults.length" class="csv-results">
                <div v-for="r in csvResults" :key="r.username" :class="['csv-row', r.ok ? 'ok' : 'fail']">
                    <span class="csv-icon">{{ r.ok ? '✓' : '✗' }}</span>
                    <span>{{ r.username }}</span>
                    <span class="csv-msg">{{ r.msg }}</span>
                </div>
            </div>
        </div>

        <!-- Search + cohort filter -->
        <div class="filter-row">
            <input v-model="search" placeholder="Search students..." class="search-input" />
            <select v-model="cohortFilter">
                <option value="">All Cohorts</option>
                <option v-for="c in cohorts" :key="c" :value="c">{{ c }}</option>
            </select>
        </div>

        <!-- Students table -->
        <div v-if="loading" class="state-msg">Loading students...</div>
        <div v-else-if="filtered.length === 0" class="state-msg">No students found.</div>

        <div v-else class="students-table">
            <div class="table-header">
                <span>Username</span>
                <span>Email</span>
                <span>Cohort</span>
                <span>Actions</span>
            </div>
            <div v-for="s in filtered" :key="s.id" class="table-row">
                <span class="col-username">{{ s.username }}</span>
                <span class="col-email">{{ s.email }}</span>
                <span class="col-cohort">
                    <span v-if="editingId !== s.id" class="cohort-val" @click="startEdit(s)">
                        {{ s.cohort || '—' }}
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
                    </span>
                    <span v-else class="cohort-edit">
                        <input v-model="editCohort" @keydown.enter="saveEdit(s.id)" @keydown.esc="editingId = null" style="width:120px; padding:4px 8px;" />
                        <button class="save-btn" @click="saveEdit(s.id)">Save</button>
                    </span>
                </span>
                <span class="col-actions">
                    <button class="view-btn" @click="$router.push(`/dashboard/students/${s.id}`)">View</button>
                    <button class="delete-btn" @click="confirmDelete(s)">Delete</button>
                </span>
            </div>
        </div>

        <!-- Delete confirm modal -->
        <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
            <div class="modal">
                <h3>Delete student?</h3>
                <p>This will permanently delete <strong>{{ deleteTarget.username }}</strong> and all their submissions.</p>
                <div class="modal-actions">
                    <button class="cancel-btn" @click="deleteTarget = null">Cancel</button>
                    <button class="confirm-delete-btn" @click="doDelete" :disabled="deleting">
                        {{ deleting ? 'Deleting...' : 'Delete' }}
                    </button>
                </div>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import api from '../api'

interface Student { id: number; username: string; email: string; cohort: string }

const students = ref<Student[]>([])
const loading = ref(true)
const showForm = ref(false)
const creating = ref(false)
const createError = ref('')
const search = ref('')
const cohortFilter = ref('')
const editingId = ref<number | null>(null)
const editCohort = ref('')
const deleteTarget = ref<Student | null>(null)
const deleting = ref(false)
const csvResults = ref<{ username: string; ok: boolean; msg: string }[]>([])

const form = ref({ username: '', email: '', password: '', cohort: '' })

const cohorts = computed(() => [...new Set(students.value.map(s => s.cohort).filter(Boolean))])

const filtered = computed(() => {
    let list = students.value
    if (search.value) {
        const q = search.value.toLowerCase()
        list = list.filter(s => s.username.toLowerCase().includes(q) || s.email.toLowerCase().includes(q))
    }
    if (cohortFilter.value) list = list.filter(s => s.cohort === cohortFilter.value)
    return list
})

onMounted(async () => {
    await loadStudents()
})

async function loadStudents() {
    loading.value = true
    const res = await api.get('/auth/students/')
    students.value = res.data
    loading.value = false
}

async function createStudent() {
    createError.value = ''
    creating.value = true
    try {
        const res = await api.post('/auth/students/', form.value)
        students.value.push(res.data)
        form.value = { username: '', email: '', password: '', cohort: '' }
        showForm.value = false
    } catch (e: any) {
        const errs = e.response?.data
        createError.value = errs ? Object.values(errs).flat().join(' ') : 'Create failed'
    } finally {
        creating.value = false
    }
}

function startEdit(s: Student) {
    editingId.value = s.id
    editCohort.value = s.cohort || ''
}

async function saveEdit(id: number) {
    await api.patch(`/auth/students/${id}/`, { cohort: editCohort.value })
    const idx = students.value.findIndex(s => s.id === id)
    if (idx !== -1) students.value[idx].cohort = editCohort.value
    editingId.value = null
}

function confirmDelete(s: Student) {
    deleteTarget.value = s
}

async function doDelete() {
    if (!deleteTarget.value) return
    deleting.value = true
    try {
        await api.delete(`/auth/students/${deleteTarget.value.id}/`)
        students.value = students.value.filter(s => s.id !== deleteTarget.value!.id)
        deleteTarget.value = null
    } finally {
        deleting.value = false
    }
}

async function handleCSV(e: Event) {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const text = await file.text()
    const lines = text.trim().split('\n').filter(l => l.trim() && !l.startsWith('username'))
    csvResults.value = []
    for (const line of lines) {
        const [username, email, password, cohort] = line.split(',').map(s => s.trim())
        try {
            const res = await api.post('/auth/students/', { username, email, password, cohort: cohort || '', role: 'student' })
            students.value.push(res.data)
            csvResults.value.push({ username, ok: true, msg: 'Created' })
        } catch (err: any) {
            const msg = err.response?.data ? Object.values(err.response.data).flat().join(' ') : 'Failed'
            csvResults.value.push({ username, ok: false, msg })
        }
    }
}
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
.page-sub { color: var(--text-dim); font-size: 14px; margin-top: 4px; }
.create-btn {
    padding: 9px 18px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
}
.create-btn:hover { opacity: 0.85; }

.create-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px;
    margin-bottom: 20px;
}
.create-card h3 { font-size: 14px; font-weight: 600; color: var(--text-muted); margin-bottom: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 6px; }
.field label { font-size: 12px; color: var(--text-dim); font-weight: 600; }
.form-error { color: var(--red); font-size: 13px; margin-top: 8px; }
.form-actions { margin-top: 16px; display: flex; justify-content: flex-end; }
.submit-btn {
    padding: 9px 22px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-weight: 600;
    font-size: 13px;
    cursor: pointer;
}
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.csv-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 20px;
    margin-bottom: 20px;
}
.csv-header { display: flex; justify-content: space-between; align-items: center; }
.csv-title { font-size: 14px; font-weight: 600; color: var(--text); }
.csv-sub { font-size: 12px; color: var(--text-dim); margin-top: 2px; font-family: monospace; }
.csv-btn {
    padding: 8px 16px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    font-size: 13px;
    color: var(--text-muted);
    cursor: pointer;
    font-family: inherit;
}
.csv-btn:hover { border-color: var(--border2); color: var(--text); }
.csv-results { margin-top: 12px; display: flex; flex-direction: column; gap: 4px; }
.csv-row { display: flex; align-items: center; gap: 10px; font-size: 13px; padding: 6px 10px; border-radius: var(--radius-sm); }
.csv-row.ok { background: rgba(46,204,113,0.08); }
.csv-row.fail { background: var(--red-dim); }
.csv-icon { font-weight: 700; }
.csv-row.ok .csv-icon { color: var(--green); }
.csv-row.fail .csv-icon { color: var(--red); }
.csv-msg { color: var(--text-dim); font-size: 12px; margin-left: auto; }

.filter-row { display: flex; gap: 12px; margin-bottom: 20px; }
.search-input { flex: 1; }
.filter-row select { width: 160px; }

.state-msg { color: var(--text-muted); padding: 40px 0; }

.students-table { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.table-header, .table-row {
    display: grid;
    grid-template-columns: 1fr 1fr 160px 140px;
    gap: 16px;
    padding: 12px 20px;
    align-items: center;
}
.table-header {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-dim);
    border-bottom: 1px solid var(--border);
    background: var(--surface2);
}
.table-row { border-bottom: 1px solid var(--border); font-size: 14px; }
.table-row:last-child { border-bottom: none; }
.table-row:hover { background: var(--surface2); }
.col-username { font-weight: 600; color: var(--text); }
.col-email { color: var(--text-muted); }
.cohort-val {
    display: flex;
    align-items: center;
    gap: 6px;
    cursor: pointer;
    color: var(--text-muted);
    font-size: 13px;
}
.cohort-val:hover { color: var(--text); }
.cohort-edit { display: flex; align-items: center; gap: 6px; }
.save-btn {
    padding: 4px 10px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    font-size: 12px;
    cursor: pointer;
}
.col-actions { display: flex; gap: 8px; }
.view-btn, .delete-btn {
    padding: 5px 12px;
    border-radius: var(--radius-sm);
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
}
.view-btn { background: var(--surface3); border: 1px solid var(--border); color: var(--text-muted); }
.view-btn:hover { color: var(--text); }
.delete-btn { background: var(--red-dim); border: 1px solid rgba(230,57,70,0.2); color: var(--red); }
.delete-btn:hover { background: var(--red); color: white; }

.modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}
.modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px;
    width: 400px;
}
.modal h3 { font-size: 16px; font-weight: 700; margin-bottom: 10px; }
.modal p { font-size: 14px; color: var(--text-muted); margin-bottom: 20px; }
.modal-actions { display: flex; gap: 10px; justify-content: flex-end; }
.cancel-btn {
    padding: 8px 18px;
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    color: var(--text-muted);
    cursor: pointer;
    font-size: 13px;
}
.confirm-delete-btn {
    padding: 8px 18px;
    background: var(--red);
    color: white;
    border: none;
    border-radius: var(--radius-sm);
    cursor: pointer;
    font-size: 13px;
    font-weight: 600;
}
.confirm-delete-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
