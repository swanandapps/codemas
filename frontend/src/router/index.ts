import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { requiresAuth: false, title: 'Sign in' } },
        { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue'), meta: { requiresAuth: false, title: 'Create account' } },

        // Student routes
        { path: '/home', name: 'student-home', component: () => import('../views/StudentDashboardView.vue'), meta: { requiresAuth: true, title: 'Home' } },
        { path: '/exams', name: 'exams', component: () => import('../views/ExamsView.vue'), meta: { requiresAuth: true, title: 'Exams' } },
        {
            path: '/exams/:id', name: 'exam-detail', component: () => import('../views/ExamDetailView.vue'), meta: { requiresAuth: true, title: 'Exam' },
            // the student's exam start page; a trainer's one exam page is the exam report
            beforeEnter: (to) => useAuthStore().isTrainer ? `/dashboard/history/${to.params.id}` : true,
        },
        { path: '/exams/:id/take', name: 'exam-take', component: () => import('../views/ExamTakeView.vue'), meta: { requiresAuth: true, hideNav: true, title: 'Exam in progress' } },
        { path: '/results', name: 'results', component: () => import('../views/MyResultsView.vue'), meta: { requiresAuth: true, title: 'My results' } },
        // the student's own appeals; a trainer's Disputes page is /dashboard/support/disputes
        { path: '/disputes', name: 'my-disputes', component: () => import('../views/StudentDisputesView.vue'), meta: { requiresAuth: true, requiresStudent: true, title: 'Disputes' } },
        { path: '/leaderboard', name: 'leaderboard', component: () => import('../views/LeaderboardView.vue'), meta: { requiresAuth: true, title: 'Leaderboard' } },

        // Trainer routes
        { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Overview' } },
        { path: '/dashboard/students', name: 'students', component: () => import('../views/StudentsView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Students' } },
        { path: '/dashboard/students/:id', name: 'student-detail', component: () => import('../views/StudentDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Student' } },
        // The old Flags page was folded into Investigation; keep the URL working for bookmarks and old emails.
        { path: '/dashboard/plagiarism', redirect: '/dashboard/plagiarism/cohorts' },
        // Flags are reviewed on each exam's case file, reached from Investigation
        { path: '/dashboard/plagiarism/queue', redirect: '/dashboard/plagiarism/cohorts' },
        { path: '/dashboard/plagiarism/policy', name: 'policy', component: () => import('../views/PolicyView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Policy' } },
        { path: '/dashboard/plagiarism/cohorts', name: 'cohorts', component: () => import('../views/CohortView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Investigation' } },
        { path: '/dashboard/plagiarism/cohorts/:id', name: 'cohort-detail', component: () => import('../views/CohortDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Cohort investigation' } },
        { path: '/dashboard/accounts', name: 'accounts', component: () => import('../views/AccountManagementView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Accounts' } },
        { path: '/dashboard/submissions', name: 'submissions-search', component: () => import('../views/SubmissionsSearchView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Submissions' } },
        { path: '/dashboard/history', name: 'exam-history', component: () => import('../views/ExamHistoryView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Exams' } },
        { path: '/dashboard/history/:id', name: 'exam-history-detail', component: () => import('../views/ExamHistoryDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Exam report' } },
        { path: '/dashboard/create', name: 'create-exam', component: () => import('../views/CreateExamView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Create exam' } },
        { path: '/dashboard/code-search', name: 'code-search', component: () => import('../views/CodeSearchView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Code search' } },
        { path: '/dashboard/submissions/:id', name: 'submission-detail', component: () => import('../views/SubmissionDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Submission' } },
        { path: '/dashboard/monitoring', name: 'monitoring', component: () => import('../views/MonitoringView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Monitoring' } },
        // The student case page was folded into the student page (same user id)
        { path: '/dashboard/support/student/:id', redirect: to => `/dashboard/students/${to.params.id}` },
        { path: '/dashboard/support/disputes', name: 'dispute-queue', component: () => import('../views/DisputeQueueView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Disputes' } },
        { path: '/dashboard/support/disputes/:id', name: 'dispute-detail', component: () => import('../views/DisputeDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true, title: 'Dispute' } },
        // Exam operations was folded into the exam report
        { path: '/dashboard/support/exam/:id', redirect: to => `/dashboard/history/${to.params.id}` },

        // Send each role to its own home page
        {
            path: '/',
            redirect: () => {
                const authStore = useAuthStore()
                if (!authStore.isLoggedIn) return '/login'
                return authStore.isTrainer ? '/dashboard' : '/home'
            },
        },
        { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('../views/NotFoundView.vue'), meta: { requiresAuth: false, title: 'Page not found' } },
    ],
})

router.beforeEach((to) => {
    const authStore = useAuthStore()
    if (to.meta.requiresAuth && !authStore.isLoggedIn) return '/login'
    if (to.meta.requiresTrainer && !authStore.isTrainer) return '/exams'
    if (to.meta.requiresStudent && !authStore.isStudent) return authStore.isTrainer ? '/dashboard/support/disputes' : '/'
    return true
})

// Give every tab a specific title, led by who is signed in so tabs for several
// accounts stay apart, e.g. "Aarav · Home | CodeMas" (aarav_sharma0 → Aarav)
router.afterEach((to) => {
    const title = to.meta.title as string | undefined
    const first = useAuthStore().user?.username.split('_')[0]?.replace(/\d+$/, '')
    const who = first ? `${first.charAt(0).toUpperCase()}${first.slice(1)} · ` : ''
    document.title = `${who}${title ? `${title} | CodeMas` : 'CodeMas'}`
})

// After a deploy, an open tab can still be running the previous build, whose page files are
// gone: the import fails and the click silently does nothing (e.g. Sign in). Reload once into
// the new build at the page that was being opened.
const RELOAD_KEY = 'codemas:reloaded-for'
router.onError((error, to) => {
    const msg = String((error as Error)?.message ?? error)
    if (!/dynamically imported module|Importing a module script failed|MIME type|error loading/i.test(msg)) return
    try {
        if (sessionStorage.getItem(RELOAD_KEY) === to.fullPath) return  // already tried once: don't loop
        sessionStorage.setItem(RELOAD_KEY, to.fullPath)
    } catch { /* storage unavailable: still reload once */ }
    window.location.assign(to.fullPath)
})
router.afterEach(() => {
    try { sessionStorage.removeItem(RELOAD_KEY) } catch { /* ignore */ }
})

export default router
