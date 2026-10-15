from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from dashboard.views import _COLD_START_MS


class StudentsListViewTest(TestCase):

    def setUp(self):
        self.api = APIClient()
        self.trainer = User.objects.create_user(username='trainer', password='pass', role='trainer')
        self.student = User.objects.create_user(username='alice', password='pass', role='student')
        # Superuser whose role defaults to 'student' (pre-existing data / old createsuperuser runs)
        self.admin = User.objects.create_superuser(username='admin', email='admin@codemas.dev', password='pass')
        User.objects.filter(pk=self.admin.pk).update(role='student')

    def test_excludes_superusers_even_if_role_is_student(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/dashboard/students/')
        self.assertEqual(resp.status_code, 200)
        usernames = [s['username'] for s in resp.data]
        self.assertIn('alice', usernames)
        self.assertNotIn('admin', usernames)


class StudentsListConfidenceTest(TestCase):
    """max_confidence = most suspicious flag; high (3+ signals) ranks first."""

    def setUp(self):
        from exams.models import Exam, Question
        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag
        self.api = APIClient()
        self.trainer = User.objects.create_user(username='trainer', password='pass', role='trainer')
        exam = Exam.objects.create(title='E', created_by=self.trainer, duration_minutes=60)
        q1 = Question.objects.create(exam=exam, title='Q1', description='d', difficulty='easy', language='python')
        q2 = Question.objects.create(exam=exam, title='Q2', description='d', difficulty='easy', language='python')

        def flag(name, *levels):
            student = User.objects.create_user(username=name, password='pass', role='student')
            for q, level in zip((q1, q2), levels):
                sub = Submission.objects.create(student=student, exam=exam, question=q, code='x',
                                                language='python', attempt_number=1, status='passed')
                BehaviouralFlag.objects.create(submission=sub, risk_score=0.5, confidence=level)

        flag('one_signal', 'low')
        flag('mixed', 'low', 'high')
        flag('two_signals', 'medium')
        User.objects.create_user(username='clean', password='pass', role='student')

    def _rows(self):
        self.api.force_authenticate(user=self.trainer)
        return {s['username']: s for s in self.api.get('/api/dashboard/students/').data}

    def test_max_confidence_is_the_most_suspicious_flag(self):
        rows = self._rows()
        self.assertEqual(rows['mixed']['max_confidence'], 'high')
        self.assertEqual(rows['two_signals']['max_confidence'], 'medium')
        self.assertEqual(rows['one_signal']['max_confidence'], 'low')
        self.assertIsNone(rows['clean']['max_confidence'])

    def test_confidence_rank_orders_most_suspicious_first(self):
        rows = self._rows()
        ranked = sorted(rows.values(), key=lambda s: -s['confidence_rank'])
        self.assertEqual([s['username'] for s in ranked],
                         ['mixed', 'two_signals', 'one_signal', 'clean'])


class CostAnalysisViewTest(TestCase):

    def setUp(self):
        self.api = APIClient()
        self.trainer = User.objects.create_user(username='trainer', password='pass', role='trainer')

    def test_response_includes_cold_start_ms_in_infrastructure_config(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/dashboard/costs/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['infrastructure']['cold_start_ms'], _COLD_START_MS)

    def test_cache_docker_images_insight_derives_text_from_cold_start_ms(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/dashboard/costs/')
        suggestion = next(
            s for s in resp.data['optimizations'] if s['title'] == 'Cache Docker images on worker nodes'
        )
        expected_seconds = round(_COLD_START_MS / 1000)
        self.assertIn(f'~{expected_seconds}s', suggestion['detail'])
        self.assertNotIn('~2s', suggestion['detail'])


class StudentDetailOrderTest(TestCase):
    """The newest exam's questions come first, so today's attempt isn't buried under past exams."""

    def test_newest_exam_questions_first(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, Question
        from submissions.models import Submission
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        student = User.objects.create_user(username='s', password='pw', role='student')
        now = timezone.now()
        old = Exam.objects.create(title='June', created_by=trainer, start_time=now - timedelta(days=120))
        new = Exam.objects.create(title='Today', created_by=trainer, start_time=now)
        old_q = Question.objects.create(exam=old, title='Old Q', description='d')  # seeded first: lower id
        new_q = Question.objects.create(exam=new, title='New Q', description='d')
        for exam, q in ((old, old_q), (new, new_q)):
            Submission.objects.create(student=student, exam=exam, question=q, code='x', language='javascript',
                                      attempt_number=1)
        api = APIClient()
        api.force_authenticate(trainer)
        r = api.get(f'/api/dashboard/students/{student.id}/')
        self.assertEqual([q['question_title'] for q in r.data['questions']], ['New Q', 'Old Q'])


class NewestFirstOrderTest(TestCase):
    """Every list puts the exam that ran most recently first, even when it was created earlier."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, Question
        from submissions.models import Submission
        from plagiarism.models import PlagiarismFlag
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        a = User.objects.create_user(username='a', password='pw', role='student')
        b = User.objects.create_user(username='b', password='pw', role='student')
        now = timezone.now()
        # created first, opened today: must still lead every list
        self.today = Exam.objects.create(title='Zeta today', created_by=self.trainer)
        self.june = Exam.objects.create(title='Alpha June', created_by=self.trainer,
                                        start_time=now - timedelta(days=120), end_time=now - timedelta(days=119))
        self.mid = Exam.objects.create(title='Mid September', created_by=self.trainer,  # made last
                                       start_time=now - timedelta(days=30), end_time=now - timedelta(days=29))
        self.today.is_active = True
        self.today.save()
        for exam, score in ((self.june, 0.99), (self.mid, 0.95), (self.today, 0.9)):  # old pairs score higher
            q = Question.objects.create(exam=exam, title=f'{exam.title} Q', description='d')
            s1, s2 = (Submission.objects.create(student=u, exam=exam, question=q, code='x', language='javascript',
                                                attempt_number=1) for u in (a, b))
            PlagiarismFlag.objects.create(submission_1=s1, submission_2=s2, similarity_score=score, flagged=True)
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)

    def titles(self, url, key='title'):
        data = self.api.get(url).data
        rows = data.get('results', data) if isinstance(data, dict) else data
        return [r[key] for r in rows]

    def test_exam_lists(self):
        expected = ['Zeta today', 'Mid September', 'Alpha June']
        self.assertEqual(self.titles('/api/exams/'), expected)
        self.assertEqual(self.titles('/api/dashboard/exams/'), expected)

    def test_similarity_pairs(self):
        self.assertEqual(self.titles('/api/plagiarism/', 'exam_title'), ['Zeta today', 'Mid September', 'Alpha June'])


class StudentPageConsistencyTest(TestCase):
    """The trainer's student page and exam report use the same definitions as the student's own pages.

    Section C, one exam with easy E and medium M:
        s1: E failed, E failed, E passed, M passed  -> 30 points, success rate 50%
        s2: E passed                                -> 10 points, 100%
        s3: E passed                                -> 10 points, 100% (tied with s2)
    """

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, ExamEnrollment, Question
        from submissions.models import Submission
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.s1, self.s2, self.s3 = (
            User.objects.create_user(username=n, password='pw', role='student', cohort='C') for n in ('s1', 's2', 's3'))
        now = timezone.now()
        self.exam = Exam.objects.create(title='Exam', created_by=self.trainer, duration_minutes=60,
                                        start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1))
        self.E = Question.objects.create(exam=self.exam, title='E', description='d', difficulty='easy')
        self.M = Question.objects.create(exam=self.exam, title='M', description='d', difficulty='medium')
        self.subs = {}
        for s in (self.s1, self.s2, self.s3):
            ExamEnrollment.objects.create(exam=self.exam, student=s)

        def sub(stu, q, status, **extra):
            n = Submission.objects.filter(student=stu, question=q).count() + 1
            self.subs[(stu.username, q.title, n)] = Submission.objects.create(
                student=stu, exam=self.exam, question=q, code='x', language='python',
                attempt_number=n, status=status, **extra)

        sub(self.s1, self.E, 'failed')
        sub(self.s1, self.E, 'failed')
        sub(self.s1, self.E, 'passed', time_to_complete_seconds=120, time_remaining_seconds=3000)
        sub(self.s1, self.M, 'passed')
        sub(self.s2, self.E, 'passed')
        sub(self.s3, self.E, 'passed')
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)

    def detail(self, student):
        return self.api.get(f'/api/dashboard/students/{student.id}/').data

    def report(self):
        return {s['username']: s for s in self.api.get(f'/api/dashboard/exams/{self.exam.id}/').data['students']}

    def test_section_rank_is_by_points_with_shared_ties(self):
        self.assertEqual((self.detail(self.s1)['student']['cohort_rank'], self.detail(self.s1)['student']['cohort_size']), (1, 3))
        self.assertEqual(self.detail(self.s2)['student']['cohort_rank'], 2)
        self.assertEqual(self.detail(self.s3)['student']['cohort_rank'], 2)

    def test_section_rank_matches_the_students_own_home_page(self):
        for s in (self.s1, self.s2, self.s3):
            me = APIClient()
            me.force_authenticate(s)
            self.assertEqual(self.detail(s)['student']['cohort_rank'], me.get('/api/leaderboard/me/').data['rank'])

    def test_exam_report_rank_is_by_points_with_shared_ties(self):
        rows = self.report()
        self.assertEqual({n: r['rank'] for n, r in rows.items()}, {'s1': 1, 's2': 2, 's3': 2})
        self.assertEqual(rows['s1']['points'], 30)

    def test_exam_report_rank_matches_my_results_within_one_section(self):
        rows = self.report()
        for s in (self.s1, self.s2, self.s3):
            me = APIClient()
            me.force_authenticate(s)
            mine = next(e for e in me.get('/api/leaderboard/me/exams/').data if e['exam_id'] == self.exam.id)
            self.assertEqual(rows[s.username]['rank'], mine['rank'])

    def test_solve_time_is_time_to_complete(self):
        attempt = next(a for q in self.detail(self.s1)['questions'] if q['question_title'] == 'E'
                       for a in q['attempts'] if a['status'] == 'passed')
        self.assertEqual(attempt['solve_time_seconds'], 120)   # not duration - time remaining (600)

    def test_attempts_used_leave_out_refunded_errors_and_limit_is_the_policy(self):
        from plagiarism.models import PlagiarismPolicy
        from submissions.models import Submission
        Submission.objects.create(student=self.s2, exam=self.exam, question=self.M, code='x', language='python',
                                  attempt_number=1, status='error')
        policy = PlagiarismPolicy.get()
        policy.max_attempts = 4
        policy.save()
        q = next(q for q in self.detail(self.s2)['questions'] if q['question_title'] == 'M')
        self.assertEqual((len(q['attempts']), q['attempts_used'], q['max_attempts']), (1, 0, 4))

    def test_dismissed_flags_do_not_count_on_trainer_pages(self):
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag
        s1_e = self.subs[('s1', 'E', 3)]
        BehaviouralFlag.objects.create(submission=s1_e, risk_score=0.9, confidence='high', review_status='dismissed')
        BehaviouralFlag.objects.create(submission=self.subs[('s1', 'M', 1)], risk_score=0.3, confidence='low')
        PlagiarismFlag.objects.create(submission_1=s1_e, submission_2=self.subs[('s2', 'E', 1)],
                                      similarity_score=0.95, flagged=True, review_status='dismissed')

        students = {s['username']: s for s in self.api.get('/api/dashboard/students/').data}
        self.assertEqual((students['s1']['max_confidence'], students['s1']['max_risk']), ('low', 30))
        self.assertIsNone(students['s2']['max_confidence'])

        e_attempts = next(q for q in self.detail(self.s1)['questions'] if q['question_title'] == 'E')['attempts']
        self.assertIsNone(next(a for a in e_attempts if a['status'] == 'passed')['plagiarism'])

        rows = self.report()
        self.assertEqual((rows['s1']['behavioural_flags'], rows['s1']['similarity_flags']), (1, 0))
        self.assertEqual(rows['s2']['similarity_flags'], 0)
        history = next(r for r in self.api.get('/api/dashboard/exams/').data if r['exam_id'] == self.exam.id)
        self.assertEqual((history['behavioural_flags'], history['similarity_pairs']), (1, 0))
        self.assertEqual({q['title']: q['flag_count'] for q in history['questions']}, {'E': 0, 'M': 1})

    def test_hardest_question_tie_goes_to_the_lowest_question_id(self):
        from analytics import metrics
        from dashboard.health import build_dashboard_health
        from submissions.models import Submission
        # both questions at 0%: E (lower id) is the hardest on every page
        Submission.objects.filter(exam=self.exam).update(status='failed')
        history = next(r for r in self.api.get('/api/dashboard/exams/').data if r['exam_id'] == self.exam.id)
        overview = next(r for r in build_dashboard_health()['exams'] if r['exam_id'] == self.exam.id)
        self.assertEqual(history['hardest_question'], 'E')
        self.assertEqual(overview['hardest_question'], 'E')
        rows = {9: {'accepted_rate': 0.0}, 3: {'accepted_rate': 0.0}, 5: {'accepted_rate': None}}
        self.assertEqual(metrics.hardest_question(rows)[0], 3)


class StudentPageHasTheCaseDetailsTest(TestCase):
    """The one student page carries what the old student case page showed: who reviewed each flag and
    their note, the matched student's id, each question's exam, and the student's disputes."""

    def setUp(self):
        from exams.models import Exam, Question
        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag
        from support.models import DisputeRequest
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.a, self.b = (User.objects.create_user(username=n, password='pw', role='student') for n in ('a', 'b'))
        exam = Exam.objects.create(title='Week 1', created_by=self.trainer)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        self.sa, self.sb = (Submission.objects.create(student=u, exam=exam, question=q, code='x', language='python',
                                                      attempt_number=1) for u in (self.a, self.b))
        self.bf = BehaviouralFlag.objects.create(submission=self.sa, risk_score=0.8, confidence='high',
                                                 review_status='confirmed', review_note='pasted', reviewed_by=self.trainer)
        self.pf = PlagiarismFlag.objects.create(submission_1=self.sb, submission_2=self.sa, similarity_score=0.95,
                                                flagged=True, review_status='dismissed', review_note='same template')
        DisputeRequest.objects.create(student=self.a, flag_type='behavioural', flag_id=self.bf.id, student_note='I typed it')
        DisputeRequest.objects.create(student=self.a, flag_type='similarity', flag_id=self.pf.id, student_note='x',
                                      status='upheld', resolution_note='ok')
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)
        self.data = self.api.get(f'/api/dashboard/students/{self.a.id}/').data

    def test_behavioural_flag_has_review_details_and_submission(self):
        f = self.data['behavioural_flags'][0]
        self.assertEqual((f['submission_id'], f['review_note'], f['reviewed_by']), (self.sa.id, 'pasted', 't'))

    def test_similarity_flag_has_matched_student_id_exam_and_note(self):
        f = self.data['plagiarism_flags'][0]
        self.assertEqual((f['matched_student'], f['matched_student_id']), ('b', self.b.id))
        self.assertEqual((f['exam'], f['submission_id'], f['review_note']), ('Week 1', self.sa.id, 'same template'))

    def test_question_names_its_exam(self):
        self.assertEqual(self.data['questions'][0]['exam'], 'Week 1')

    def test_disputes_and_open_count(self):
        self.assertEqual(self.data['student']['open_disputes'], 1)
        self.assertEqual(sorted((d['flag_type'], d['status']) for d in self.data['disputes']),
                         [('behavioural', 'open'), ('similarity', 'upheld')])
        resolved = next(d for d in self.data['disputes'] if d['status'] == 'upheld')
        self.assertEqual((resolved['student_note'], resolved['resolution_note']), ('x', 'ok'))


class ExamReportLiveStatusTest(TestCase):
    """The exam report's student table carries the live status the old exam operations page showed:
    attempts (refunded errors left out) and each student's latest submission."""

    def test_attempts_and_latest_submission(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, ExamEnrollment, Question
        from submissions.models import Submission
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        busy, idle = (User.objects.create_user(username=n, password='pw', role='student') for n in ('busy', 'idle'))
        exam = Exam.objects.create(title='E', created_by=trainer, is_active=True)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        for s in (busy, idle):
            ExamEnrollment.objects.create(exam=exam, student=s)
        now = timezone.now()
        for n, (status, ago) in enumerate((('error', 30), ('failed', 20), ('passed', 10)), start=1):
            sub = Submission.objects.create(student=busy, exam=exam, question=q, code='x', language='python',
                                            attempt_number=n, status=status)
            Submission.objects.filter(pk=sub.pk).update(submitted_at=now - timedelta(minutes=ago))
        api = APIClient()
        api.force_authenticate(trainer)
        rows = {s['username']: s for s in api.get(f'/api/dashboard/exams/{exam.id}/').data['students']}
        self.assertEqual((rows['busy']['attempts'], rows['busy']['last_status']), (2, 'passed'))
        self.assertIsNotNone(rows['busy']['last_submitted_at'])
        self.assertEqual((rows['idle']['attempts'], rows['idle']['last_status'], rows['idle']['last_submitted_at']),
                         (0, None, None))


class RankTieBreakConsistencyTest(TestCase):
    """Equal points on an exam are split by average solve time, the same way on the exam report
    and on each student's My results."""

    def test_report_and_my_results_agree_on_tied_points(self):
        from django.utils import timezone
        from exams.models import Exam, Question
        from submissions.models import Submission
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        exam = Exam.objects.create(title='E', created_by=trainer, start_time=timezone.now())
        q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='medium')
        fast, slow = (User.objects.create_user(username=n, password='pw', role='student', cohort='A') for n in ('fast', 'slow'))
        for student, secs in ((slow, 69), (fast, 40)):
            exam.enrollments.create(student=student)
            Submission.objects.create(student=student, exam=exam, question=q, code='x', language='javascript',
                                      attempt_number=1, status='passed', time_to_complete_seconds=secs)
        api = APIClient()
        api.force_authenticate(trainer)
        report = {r['username']: r['rank'] for r in api.get(f'/api/dashboard/exams/{exam.id}/').data['students']}
        self.assertEqual(report, {'fast': 1, 'slow': 2})
        for student in (fast, slow):
            api.force_authenticate(student)
            mine = next(e for e in api.get('/api/leaderboard/me/exams/').data if e['exam_id'] == exam.id)
            self.assertEqual(mine['rank'], report[student.username], student.username)


class StudentCaseGroupsTest(TestCase):
    """The student page's Integrity tab: one group per exam where the student has a flag,
    with the student's own status there and the key of the case they are in (the same key
    the investigation detail gives that case), plus what the trainer decided and wrote.

        Week 2 (newest): a-b pair and a-c pair pending, a has a pending behaviour flag
        Week 1:          a's behaviour flag confirmed, a-d pair dismissed  -> mixed
        Week 0 (oldest): a-b pair dismissed                               -> dismissed
        Clean exam:      a submitted, no flags                            -> no group
    """

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, ExamEnrollment, Question
        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag
        self.trainer = User.objects.create_user(username='venu', password='pw', role='trainer')
        self.a, self.b, self.c, self.d = (
            User.objects.create_user(username=n, password='pw', role='student') for n in ('a', 'b', 'c', 'd'))
        now = timezone.now()

        def exam(title, days_ago):
            e = Exam.objects.create(title=title, created_by=self.trainer, duration_minutes=60,
                                    start_time=now - timedelta(days=days_ago),
                                    end_time=now - timedelta(days=days_ago) + timedelta(hours=1))
            q = Question.objects.create(exam=e, title=f'{title} Q', description='d', difficulty='medium')
            subs = {}
            for u in (self.a, self.b, self.c, self.d):
                ExamEnrollment.objects.create(exam=e, student=u)
                subs[u.username] = Submission.objects.create(student=u, exam=e, question=q, code='x',
                                                             language='python', attempt_number=1, status='passed')
            return e, subs

        self.week2, s2 = exam('Week 2', 1)
        self.week1, s1 = exam('Week 1', 8)
        self.week0, s0 = exam('Week 0', 15)
        self.clean, _ = exam('Clean', 22)
        self.pair_ab = PlagiarismFlag.objects.create(submission_1=s2['b'], submission_2=s2['a'],
                                                     similarity_score=0.97, flagged=True)
        self.pair_ac = PlagiarismFlag.objects.create(submission_1=s2['a'], submission_2=s2['c'],
                                                     similarity_score=0.9, flagged=True)
        self.bf2 = BehaviouralFlag.objects.create(
            submission=s2['a'], risk_score=0.8, confidence='high',
            signals_triggered=['Pasted 100% of final code (485 chars)', 'Submitted 39s after starting', 'Left exam tab 3 times'])
        self.bf1 = BehaviouralFlag.objects.create(submission=s1['a'], risk_score=0.6, confidence='medium')
        self.pair_ad = PlagiarismFlag.objects.create(submission_1=s1['a'], submission_2=s1['d'],
                                                     similarity_score=0.88, flagged=True)
        self.pair_old = PlagiarismFlag.objects.create(submission_1=s0['a'], submission_2=s0['b'],
                                                      similarity_score=0.85, flagged=True)
        # not a flag: under the threshold
        PlagiarismFlag.objects.create(submission_1=s0['a'], submission_2=s0['c'], similarity_score=0.3, flagged=False)
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)
        # decided through the review endpoints, as the case file does, so each decision is in the audit log
        self.review(f'/api/plagiarism/behavioural/{self.bf1.id}/review/', 'confirmed', 'You pasted the whole answer.')
        self.review(f'/api/plagiarism/{self.pair_ad.id}/review/', 'dismissed', '')
        self.review(f'/api/plagiarism/{self.pair_old.id}/review/', 'dismissed', 'Common template, no action.')

    def review(self, url, status_, note):
        r = self.api.patch(url, {'review_status': status_, 'review_note': note}, format='json')
        self.assertEqual(r.status_code, 200)

    def groups(self, student=None):
        data = self.api.get(f'/api/dashboard/students/{(student or self.a).id}/').data
        return {g['exam_title']: g for g in data['integrity_cases']}, data

    def test_one_group_per_exam_with_a_flag_newest_first(self):
        _, data = self.groups()
        self.assertEqual([g['exam_title'] for g in data['integrity_cases']], ['Week 2', 'Week 1', 'Week 0'])
        g = data['integrity_cases'][0]
        self.assertEqual(g['exam_id'], self.week2.id)
        self.assertEqual(g['exam_date'], self.week2.start_time.isoformat())
        self.assertEqual(g['questions'], ['Week 2 Q'])

    def test_status_is_the_students_own_flags_on_that_exam(self):
        groups, _ = self.groups()
        self.assertEqual({t: g['status'] for t, g in groups.items()},
                         {'Week 2': 'pending', 'Week 1': 'mixed', 'Week 0': 'dismissed'})
        self.review(f'/api/plagiarism/{self.pair_ab.id}/review/', 'confirmed', 'Same code')
        self.assertEqual(self.groups()[0]['Week 2']['status'], 'pending')   # pair a-c and the behaviour flag still wait
        self.review(f'/api/plagiarism/{self.pair_ac.id}/review/', 'confirmed', 'Same code')
        self.review(f'/api/plagiarism/behavioural/{self.bf2.id}/review/', 'confirmed', 'Same code')
        self.assertEqual(self.groups()[0]['Week 2']['status'], 'confirmed')
        # c's only flag on Week 2 is the confirmed pair
        self.assertEqual(self.groups(self.c)[0]['Week 2']['status'], 'confirmed')

    def test_case_key_is_the_investigation_case_containing_the_student(self):
        groups, _ = self.groups()
        for exam in (self.week2, self.week1, self.week0):
            cases = self.api.get(f'/api/plagiarism/cohorts/{exam.id}/').data['cases']
            expected = next(c['key'] for c in cases if self.a.id in {m['student_id'] for m in c['members']})
            self.assertEqual(groups[exam.title]['case_key'], expected, exam.title)
        self.assertEqual(groups['Week 2']['case_key'], str(min(self.a.id, self.b.id, self.c.id)))

    def test_behaviour_summary_and_code_matches(self):
        g = self.groups()[0]['Week 2']
        self.assertEqual(g['behaviour_flags'], 1)
        self.assertEqual(g['top_signals'], ['Pasted 100% of final code (485 chars)', 'Submitted 39s after starting'])
        self.assertEqual(g['code_matches'], [
            {'student_id': self.b.id, 'username': 'b', 'score': 0.97},
            {'student_id': self.c.id, 'username': 'c', 'score': 0.9},
        ])
        self.assertEqual(self.groups()[0]['Week 0']['behaviour_flags'], 0)

    def test_points_withheld_per_exam(self):
        groups, _ = self.groups()
        self.assertEqual(groups['Week 1']['points_withheld'], 20)   # confirmed behaviour flag voids the medium question
        self.assertEqual(groups['Week 2']['points_withheld'], 0)

    def test_decided_groups_carry_the_latest_note_reviewer_and_time(self):
        groups, _ = self.groups()
        self.assertIsNone(groups['Week 2']['review'])
        week1 = groups['Week 1']['review']
        # the dismissed pair came last with no note: the note shown is the one the student got
        self.assertEqual((week1['note'], week1['reviewed_by']), ('You pasted the whole answer.', 'venu'))
        self.assertIsNotNone(week1['reviewed_at'])
        self.assertEqual(groups['Week 0']['review']['note'], 'Common template, no action.')

    def test_flags_name_their_exam_id_so_the_tab_can_group_them(self):
        _, data = self.groups()
        self.assertEqual({f['exam_id'] for f in data['behavioural_flags']}, {self.week2.id, self.week1.id})
        self.assertEqual({f['exam_id'] for f in data['plagiarism_flags']}, {self.week2.id, self.week1.id, self.week0.id})

    def test_student_with_no_flags_has_no_groups(self):
        clean = User.objects.create_user(username='clean', password='pw', role='student')
        self.assertEqual(self.groups(clean)[1]['integrity_cases'], [])

    def test_exam_report_rows_carry_the_case_key(self):
        rows = {s['username']: s for s in self.api.get(f'/api/dashboard/exams/{self.week2.id}/').data['students']}
        key = str(min(self.a.id, self.b.id, self.c.id))
        self.assertEqual({n: rows[n]['case_key'] for n in 'abcd'}, {'a': key, 'b': key, 'c': key, 'd': None})
        self.assertEqual(rows['a']['integrity_status'], 'under_review')
        # a decided case keeps its key, so the withheld badge can link to it
        rows = {s['username']: s for s in self.api.get(f'/api/dashboard/exams/{self.week1.id}/').data['students']}
        self.assertEqual(rows['a']['integrity_status'], 'withheld')
        self.assertEqual(rows['a']['case_key'], str(self.a.id))


class DemoViewsTest(TestCase):
    """The read-only demo_* database views (shown to interviewers in the Railway data browser)
    exist, have readable columns, and show the same facts as the app."""

    VIEWS = {
        'demo_accounts': ['username', 'full_name', 'role', 'section', 'email', 'is_active', 'date_joined', 'last_login'],
        'demo_students': ['username', 'full_name', 'section', 'exams_taken', 'submissions', 'passed_submissions',
                          'behaviour_flags', 'confirmed_flags', 'open_appeals'],
        'demo_exams': ['exam_id', 'title', 'status', 'start_time', 'end_time', 'duration_minutes', 'questions',
                       'enrolled', 'students_submitted', 'submissions', 'created_by'],
        'demo_submissions': ['submission_id', 'submitted_at', 'exam', 'question', 'student', 'attempt', 'language',
                             'status', 'seconds_to_solve', 'paste_chars', 'tab_switches'],
        'demo_behaviour_flags': ['flag_id', 'created_at', 'exam', 'question', 'student', 'attempt', 'confidence',
                                 'risk_score', 'signals', 'review_status', 'review_note', 'reviewed_by'],
        'demo_similarity_pairs': ['flag_id', 'checked_at', 'exam', 'question', 'student_1', 'student_2',
                                  'similarity_pct', 'review_status', 'review_note', 'reviewed_by'],
        'demo_review_log': ['logged_at', 'trainer', 'action', 'flag_type', 'flag_id', 'note'],
        'demo_appeals': ['appeal_id', 'filed_at', 'student', 'exam', 'status', 'student_note', 'decision_note',
                         'trainer_reply', 'ruled_by', 'ruled_at'],
        'demo_execution_jobs': ['job_id', 'created_at', 'status', 'tries', 'student', 'exam', 'question', 'language',
                                'result', 'sent_to_queue_at', 'started_at', 'finished_at', 'seconds_waiting',
                                'seconds_running', 'error'],
    }

    def rows(self, view):
        from django.db import connection
        with connection.cursor() as c:
            c.execute(f'SELECT * FROM {view}')
            cols = [d[0] for d in c.description]
            return cols, [dict(zip(cols, r)) for r in c.fetchall()]

    def test_views_exist_with_readable_columns(self):
        for view, cols in self.VIEWS.items():
            with self.subTest(view=view):
                self.assertEqual(self.rows(view)[0], cols)

    def test_views_show_the_facts(self):
        from django.utils import timezone
        from exams.models import Exam, Question
        from submissions.models import Submission
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        a = User.objects.create_user(username='a', password='pw', role='student', cohort='S', first_name='Ann', last_name='Lee')
        b = User.objects.create_user(username='b', password='pw', role='student', cohort='S')
        exam = Exam.objects.create(title='E', created_by=trainer, is_active=True, start_time=timezone.now())
        q = Question.objects.create(exam=exam, title='Q', description='d')
        sa = Submission.objects.create(student=a, exam=exam, question=q, code='x', language='javascript', attempt_number=1,
                                       status='passed', paste_char_count=400, time_to_complete_seconds=40)
        sb = Submission.objects.create(student=b, exam=exam, question=q, code='x', language='javascript', attempt_number=1,
                                       status='failed')
        BehaviouralFlag.objects.create(submission=sa, risk_score=0.7, confidence='high', review_status='confirmed')
        PlagiarismFlag.objects.create(submission_1=sa, submission_2=sb, similarity_score=0.951, flagged=True)

        students = {r['username']: r for r in self.rows('demo_students')[1]}
        self.assertEqual({k: students['a'][k] for k in ('full_name', 'exams_taken', 'submissions', 'passed_submissions',
                                                       'behaviour_flags', 'confirmed_flags')},
                         {'full_name': 'Ann Lee', 'exams_taken': 1, 'submissions': 1, 'passed_submissions': 1,
                          'behaviour_flags': 1, 'confirmed_flags': 1})
        self.assertNotIn('t', students)   # students only
        exam_row = self.rows('demo_exams')[1][0]
        self.assertEqual((exam_row['status'], exam_row['students_submitted'], exam_row['submissions']), ('live', 2, 2))
        pair = self.rows('demo_similarity_pairs')[1][0]
        self.assertEqual((pair['student_1'], pair['student_2'], float(pair['similarity_pct'])), ('a', 'b', 95.1))
        accounts = {r['username'] for r in self.rows('demo_accounts')[1]}
        self.assertEqual(accounts, {'t', 'a', 'b'})

    def test_execution_jobs_show_the_pipeline(self):
        from datetime import timedelta
        from django.utils import timezone
        from exams.models import Exam, Question
        from submissions.models import Submission
        from jobs.models import Job
        trainer = User.objects.create_user(username='t2', password='pw', role='trainer')
        a = User.objects.create_user(username='ana', password='pw', role='student')
        exam = Exam.objects.create(title='E2', created_by=trainer)
        q = Question.objects.create(exam=exam, title='Q2', description='d')
        sub = Submission.objects.create(student=a, exam=exam, question=q, code='x', language='python',
                                        attempt_number=1, status='passed')
        t0 = timezone.now()
        Job.objects.create(kind=Job.KIND_EXECUTE, subject_id=sub.id, status='succeeded', attempt=1,
                           published_at=t0, started_at=t0 + timedelta(seconds=2),
                           finished_at=t0 + timedelta(seconds=3, milliseconds=500))
        row = self.rows('demo_execution_jobs')[1][0]
        self.assertEqual((row['status'], row['tries'], row['student'], row['exam'], row['question'], row['language'],
                          row['result'], float(row['seconds_waiting']), float(row['seconds_running']), row['error']),
                         ('succeeded', 1, 'ana', 'E2', 'Q2', 'python', 'passed', 2.0, 1.5, None))
