import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { requiresAuth: false } },
        { path: '/register', name: 'register', component: () => import('../views/RegisterView.vue'), meta: { requiresAuth: false } },

        // Student routes
        { path: '/home', name: 'student-home', component: () => import('../views/StudentDashboardView.vue'), meta: { requiresAuth: true } },
        { path: '/exams', name: 'exams', component: () => import('../views/ExamsView.vue'), meta: { requiresAuth: true } },
        { path: '/exams/:id', name: 'exam-detail', component: () => import('../views/ExamDetailView.vue'), meta: { requiresAuth: true } },
        { path: '/exams/:id/take', name: 'exam-take', component: () => import('../views/ExamTakeView.vue'), meta: { requiresAuth: true } },
        { path: '/results', name: 'results', component: () => import('../views/MyResultsView.vue'), meta: { requiresAuth: true } },
        { path: '/leaderboard', name: 'leaderboard', component: () => import('../views/LeaderboardView.vue'), meta: { requiresAuth: true } },

        // Trainer routes
        { path: '/dashboard', name: 'dashboard', component: () => import('../views/DashboardView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/students', name: 'students', component: () => import('../views/StudentsView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/students/:id', name: 'student-detail', component: () => import('../views/StudentDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/plagiarism', name: 'plagiarism', component: () => import('../views/PlagiarismView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/plagiarism/queue', name: 'annotation-queue', component: () => import('../views/AnnotationQueueView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/plagiarism/policy', name: 'policy', component: () => import('../views/PolicyView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/plagiarism/cohorts', name: 'cohorts', component: () => import('../views/CohortView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/plagiarism/cohorts/:id', name: 'cohort-detail', component: () => import('../views/CohortDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/accounts', name: 'accounts', component: () => import('../views/AccountManagementView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/submissions', name: 'submissions-search', component: () => import('../views/SubmissionsSearchView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/history', name: 'exam-history', component: () => import('../views/ExamHistoryView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/history/:id', name: 'exam-history-detail', component: () => import('../views/ExamHistoryDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/create', name: 'create-exam', component: () => import('../views/CreateExamView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/costs', name: 'costs', component: () => import('../views/CostView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/code-search', name: 'code-search', component: () => import('../views/CodeSearchView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/submissions/:id', name: 'submission-detail', component: () => import('../views/SubmissionDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/monitoring', name: 'monitoring', component: () => import('../views/MonitoringView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/support/student/:id', name: 'student-case', component: () => import('../views/StudentCaseView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/support/disputes', name: 'dispute-queue', component: () => import('../views/DisputeQueueView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/support/disputes/:id', name: 'dispute-detail', component: () => import('../views/DisputeDetailView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },
        { path: '/dashboard/support/exam/:id', name: 'exam-ops', component: () => import('../views/ExamOpsView.vue'), meta: { requiresAuth: true, requiresTrainer: true } },

        { path: '/', redirect: '/home' },
    ],
})

router.beforeEach((to, _from, next) => {
    const authStore = useAuthStore()
    if (to.meta.requiresAuth && !authStore.isLoggedIn) {
        next('/login')
    } else if (to.meta.requiresTrainer && !authStore.isTrainer) {
        next('/exams')
    } else {
        next()
    }
})

export default router
