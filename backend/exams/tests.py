from django.test import TestCase
from django.utils import timezone
from datetime import timedelta

from accounts.models import User
from exams.models import Exam, ExamEnrollment
from exams.management.commands.seed_data import Command


class SeedDataDemoOpenExamTest(TestCase):
    """
    Exercises Command._create_demo_open_exam directly rather than running the
    full `seed_data` command (which is not run against this project's shared
    local database by policy — this test only touches the isolated test DB
    Django spins up for the test run).
    """

    def setUp(self):
        self.trainer = User.objects.create_user(username='trainer', password='pass', role='trainer')
        self.students = [
            User.objects.create_user(username=f'student{i}', password='pass', role='student', cohort='batch1')
            for i in range(3)
        ]
        self.cmd = Command()

    def test_creates_exactly_one_open_exam(self):
        self.cmd._create_demo_open_exam(self.trainer, self.students)
        open_exams = Exam.objects.filter(is_active=True)
        self.assertEqual(open_exams.count(), 1)

    def test_open_exam_window_is_now_minus_1_day_to_plus_14_days(self):
        before = timezone.now()
        exam = self.cmd._create_demo_open_exam(self.trainer, self.students)
        after = timezone.now()
        self.assertTrue(before - timedelta(days=1, seconds=5) <= exam.start_time <= after - timedelta(days=1))
        self.assertTrue(before + timedelta(days=14) <= exam.end_time <= after + timedelta(days=14, seconds=5))

    def test_all_given_students_are_enrolled(self):
        exam = self.cmd._create_demo_open_exam(self.trainer, self.students)
        enrolled_ids = set(ExamEnrollment.objects.filter(exam=exam).values_list('student_id', flat=True))
        self.assertEqual(enrolled_ids, {s.id for s in self.students})

    def test_exam_has_questions_and_test_cases(self):
        exam = self.cmd._create_demo_open_exam(self.trainer, self.students)
        questions = list(exam.questions.all())
        self.assertGreaterEqual(len(questions), 1)
        for q in questions:
            self.assertGreaterEqual(q.test_cases.count(), 1)


import re
import shutil
from io import StringIO
from pathlib import Path
from unittest import skipIf

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from exams.management.commands import seed_data as seed
from exams.management.commands import _seed_programs as programs
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, PlagiarismPolicy, PlagiarismRun, POLICY_FIELDS
from results.models import Result
from submissions.models import Submission

NODE_MISSING = shutil.which('node') is None
SEED_ROSTER = 20


def _coverage_programs(problem):
    """
    A small set of programs that exercises every fragment of a problem: every
    core correct and with each of its bugs, and every entry (layout x reader),
    parser and printer at least once in a correct program.
    """
    spec = programs.PROBLEMS[problem]
    cores = list(spec['cores'])
    n_parse = len(programs.PARSERS[spec['input']])
    printers = list(programs.PRINTERS)
    out = []
    for i, core in enumerate(cores):
        author = programs.make_author(problem, (core, programs.ENTRIES[i % len(programs.ENTRIES)], i % n_parse), 1000 + i)
        out.append((programs.build_program(problem, author), True))
        for bug in programs.bugs_for(problem, core):
            out.append((programs.build_program(problem, author, bug=bug), False))
    for i, entry in enumerate(programs.ENTRIES):
        author = programs.make_author(problem, (cores[i % len(cores)], entry, i % n_parse), 2000 + i)
        author['printer'] = printers[i % len(printers)]
        author['extras'] = tuple(programs.EXTRAS)[: i % (len(programs.EXTRAS) + 1)]
        out.append((programs.build_program(problem, author), True))
    return out


class SeedProgramTest(SimpleTestCase):
    """Every seeded question has its own program generator that really solves (or fails) it."""

    def test_every_question_has_its_own_problem(self):
        for edata in seed.EXAM_DATA:
            for qdata in edata['questions']:
                problem = seed.pool_for_question(edata['title'], qdata['title'])
                self.assertEqual(problem, qdata['pool'])
                self.assertIn(problem, programs.PROBLEMS)
                for core in programs.PROBLEMS[problem]['cores']:
                    self.assertTrue(programs.bugs_for(problem, core), (problem, core))

    def test_unknown_question_raises(self):
        with self.assertRaises(CommandError):
            seed.pool_for_question('Advanced JavaScript: Closures & Scope', 'Not A Question')

    def test_program_code_matches_question_topic(self):
        # guards against a question being served some other problem's code
        markers = {
            'two_sum': 'target', 'memoize_fib': 'memoize', 'curry_multiply': 'curry',
            'promise_all': 'romiseAll', 'debounce': 'debounce', 'throttle': 'throttle',
            # the one-liners (.flat(Infinity), String(arr).split) define no function
            'flatten_deep': ('flat', "split(','", 'isarray'), 'flatten_no_builtin': 'flat', 'deep_clone': 'deepClone',
            'event_emitter': 'EventEmitter', 'lru_cache': 'LRUCache', 'observer': 'ubscribe',
            'promise_all_timeout': 'promiseAllWithTimeout',
        }
        self.assertEqual(set(markers), set(programs.PROBLEMS))
        for problem in programs.PROBLEMS:
            wanted = markers[problem] if isinstance(markers[problem], tuple) else (markers[problem],)
            for code, _ in _coverage_programs(problem):
                self.assertTrue(any(m.lower() in code.lower() for m in wanted), (problem, code))

    def test_interview_flatten_never_uses_builtin_flat(self):
        for core, entry, parse in programs.structures('flatten_no_builtin'):
            author = programs.make_author('flatten_no_builtin', (core, entry, parse), 7)
            self.assertNotIn('.flat(', programs.build_program('flatten_no_builtin', author))

    def test_programs_are_deterministic(self):
        author = programs.make_author('lru_cache', programs.structures('lru_cache')[5], 42)
        self.assertEqual(programs.build_program('lru_cache', author), programs.build_program('lru_cache', author))
        self.assertEqual(seed.plan_seed(5)['attempts'], seed.plan_seed(5)['attempts'])

    @skipIf(NODE_MISSING, 'node is required to execute the programs')
    def test_every_fragment_executes_as_intended(self):
        jobs = []
        for key, spec in seed.QUESTION_SPECS.items():
            for code, expect in _coverage_programs(spec['pool']):
                jobs.append((key, code, expect))
        for problem, code in programs.LEAKED.items():
            jobs.extend((key, code, True) for key, spec in seed.QUESTION_SPECS.items() if spec['pool'] == problem)
        seed.execute_and_verify(jobs)  # raises CommandError on any code/status mismatch

    def test_honest_programs_are_distinct_and_mostly_below_the_threshold(self):
        import numpy as np
        threshold = seed.policy_defaults()['similarity_threshold']
        plan = seed.plan_seed(len(seed.INDIAN_STUDENTS))
        members = {(p['exam'], p['question']): set(p['members']) for p in plan['plants']}
        below = total = 0
        for key in seed.QUESTION_SPECS:
            finals = seed._final_attempts(plan['attempts'], key)
            codes = [finals[s]['code'] for s in sorted(finals) if s not in members.get(key, set())]
            self.assertEqual(len(codes), len(set(codes)), f'two honest students hand in the same program: {key}')
            sim = seed.production_similarity(codes)
            pairs = sim[np.triu_indices(len(codes), 1)]
            total += len(pairs)
            below += int((pairs < threshold).sum())
            self.assertGreater((pairs < threshold).mean(), 0.85, key)
        self.assertGreater(below / total, 0.94)

    def test_planted_code_resembles_no_honest_student(self):
        threshold = seed.policy_defaults()['similarity_threshold']
        plan = seed.plan_seed(len(seed.INDIAN_STUDENTS))
        self.assertTrue(all(p['code'] for p in plan['plants']), 'every case is planted for the full roster')
        for p in plan['plants']:
            key = (p['exam'], p['question'])
            finals = seed._final_attempts(plan['attempts'], key)
            others = [s for s in sorted(finals) if s not in p['members']]
            sims = seed.production_similarity([finals[s]['code'] for s in others] + [p['code']])[-1][:-1]
            honest = [v for s, v in zip(others, sims) if s != p['source']]
            self.assertLess(max(honest), threshold, key)
            if p['kind'] == 'edited':
                self.assertNotEqual(finals[p['source']]['code'], p['code'])
                self.assertGreaterEqual(sims[others.index(p['source'])], threshold)

    def test_seed_never_writes_flags_itself(self):
        # flags must come from the production tasks; the seed may only delete them in --clear
        here = Path(seed.__file__).parent
        source = (here / 'seed_data.py').read_text() + (here / '_seed_programs.py').read_text()
        writes = re.findall(
            r'(?:BehaviouralFlag|PlagiarismFlag)(?:\(|\.objects\.(?:create|get_or_create|update_or_create|'
            r'bulk_create|bulk_update|update)\b|\.objects\.filter\([^)]*\)\.update\b)', source)
        self.assertEqual(writes, [])


@skipIf(NODE_MISSING, 'node is required to execute the programs')
class SeedDataCommandTest(TestCase):
    """Runs the full seed (small roster) against the isolated test DB."""

    @classmethod
    def setUpTestData(cls):
        # A superuser created before the UserManager change, still on the default role.
        User.objects.create_user(username='admin', password='x', role='student',
                                 is_superuser=True, is_staff=True)
        # A drifted policy (weights sum to 1.6) that the seed must reset.
        PlagiarismPolicy.objects.create(pk=1, paste_weight=0.9, time_weight=0.4,
                                        easy_baseline_s=180, hard_baseline_s=900)
        call_command('seed_data', '--clear', '--students', str(SEED_ROSTER), stdout=StringIO())
        cls.plan = seed.plan_seed(SEED_ROSTER)
        cls.usernames = [f'{f.lower()}_{l.lower()}{i}' for i, (f, l) in enumerate(seed.INDIAN_STUDENTS[:SEED_ROSTER])]

    def test_admin_superuser_preserved_as_trainer(self):
        admin = User.objects.get(username='admin')
        self.assertTrue(admin.is_superuser)
        self.assertEqual(admin.role, 'trainer')

    def test_seed_logins(self):
        self.assertTrue(User.objects.get(username='venugopal').check_password('trainer123'))
        student = User.objects.filter(role='student').first()
        self.assertTrue(student.check_password('student123'))

    def test_policy_reset_to_model_defaults(self):
        policy = PlagiarismPolicy.get()
        self.assertEqual({f: getattr(policy, f) for f in POLICY_FIELDS}, seed.policy_defaults())

    def test_submissions_are_exactly_the_verified_plan(self):
        expected = sorted(
            (self.usernames[a['student']], a['key'][0], a['key'][1], a['attempt'], a['code'],
             'passed' if a['expect_pass'] else 'failed', a['tabs'], a['paste_chars'], a['clock'])
            for a in self.plan['attempts'])
        actual = sorted(Submission.objects.values_list(
            'student__username', 'exam__title', 'question__title', 'attempt_number', 'code', 'status',
            'tab_switch_count', 'paste_char_count', 'time_to_complete_seconds'))
        self.assertEqual(actual, expected)

    def test_results_consistent_with_status(self):
        for sub in Submission.objects.prefetch_related('results__test_case', 'question__test_cases'):
            results = list(sub.results.all())
            self.assertEqual(len(results), sub.question.test_cases.count())
            for r in results:
                self.assertEqual(r.passed, seed.outputs_match(r.actual_output, r.test_case.expected_output))
            self.assertEqual(sub.status == 'passed', all(r.passed for r in results))

    def test_flags_are_exactly_what_production_scoring_produces(self):
        from plagiarism.tasks import compute_behavioural_risk
        policy = seed.policy_defaults()
        flags = BehaviouralFlag.objects.select_related('submission__question', 'submission__student')
        self.assertGreater(flags.count(), 0)
        for flag in flags:
            expected = compute_behavioural_risk(flag.submission, Submission, policy)
            self.assertEqual(flag.risk_score, expected['risk_score'])
            self.assertEqual(flag.confidence, expected['confidence'])
            self.assertEqual(flag.signals_triggered, expected['signals_triggered'])
            self.assertLessEqual(flag.risk_score, 1.0)
            self.assertGreater(flag.risk_score, policy['min_risk_score'])
        # every submission above threshold has a flag, none below
        for sub in Submission.objects.select_related('question', 'student'):
            risk = compute_behavioural_risk(sub, Submission, policy)['risk_score']
            self.assertEqual(hasattr(sub, 'behavioural_flag'), risk > policy['min_risk_score'])

    def test_no_signal_mentions_a_non_policy_baseline(self):
        for signals in BehaviouralFlag.objects.values_list('signals_triggered', flat=True):
            for s in signals:
                self.assertNotIn('baseline 180s', s)
                self.assertNotIn('baseline 900s', s)

    def _planted_submissions(self, plant):
        return Submission.objects.filter(
            exam__title=plant['exam'], question__title=plant['question'], code=plant['code'],
            student__username__in=[self.usernames[m] for m in plant['members']],
        ).select_related('student')

    def test_every_case_is_planted(self):
        self.assertEqual(len(self.plan['plants']), len(seed.PLANTS))
        for plant in self.plan['plants']:
            self.assertTrue(plant['code'], plant['question'])
            self.assertEqual(self._planted_submissions(plant).count(), len(plant['members']), plant['question'])

    def test_planted_copiers_score_high_confidence_on_their_own(self):
        for plant in self.plan['plants']:
            for sub in self._planted_submissions(plant):
                # scored by production compute_behavioural_risk (see the test above)
                self.assertEqual(sub.behavioural_flag.confidence, 'high', sub.student.username)

    def test_phase2_catches_every_planted_copier(self):
        for plant in self.plan['plants']:
            flagged = set()
            for a, b in PlagiarismFlag.objects.filter(
                    submission_1__exam__title=plant['exam'], submission_1__question__title=plant['question'],
            ).values_list('submission_1__student__username', 'submission_2__student__username'):
                flagged |= {a, b}
            for m in plant['members']:
                self.assertIn(self.usernames[m], flagged, plant['question'])
            if plant['source'] is not None:
                self.assertIn(self.usernames[plant['source']], flagged)

    def test_every_similarity_flag_has_a_high_confidence_suspect_above_threshold(self):
        # production Phase 2 compares HIGH suspects with the whole cohort, so a
        # source with clean behaviour can be the other side of a pair
        threshold = seed.policy_defaults()['similarity_threshold']
        flags = list(PlagiarismFlag.objects.select_related('submission_1__student', 'submission_2__student'))
        self.assertGreater(len(flags), 0)
        for pf in flags:
            self.assertEqual(pf.submission_1.question_id, pf.submission_2.question_id)
            self.assertGreaterEqual(pf.similarity_score, threshold)
            self.assertEqual(pf.detection_method, 'behavioural_filtered_tfidf')
            self.assertTrue(any(BehaviouralFlag.objects.filter(
                submission__student=sub.student, submission__question_id=sub.question_id, confidence='high',
            ).exists() for sub in (pf.submission_1, pf.submission_2)))

    def test_similarity_flags_are_exactly_what_production_phase2_produces(self):
        import contextlib, io
        from plagiarism.tasks import run_question_plagiarism_check

        def snapshot():
            return {
                (f.submission_1_id, f.submission_2_id): round(f.similarity_score, 6)
                for f in PlagiarismFlag.objects.all()
            }
        seeded = snapshot()
        self.assertTrue(seeded)
        PlagiarismFlag.objects.all().delete()
        with contextlib.redirect_stdout(io.StringIO()):
            for q in Question.objects.filter(exam__is_active=False):
                run_question_plagiarism_check(q.id, notify=False)
        self.assertEqual(snapshot(), seeded)

    def test_every_closed_exam_has_one_completed_exam_close_run(self):
        for exam in Exam.objects.filter(is_active=False):
            runs = list(PlagiarismRun.objects.filter(exam=exam))
            self.assertEqual(len(runs), 1, exam.title)
            run = runs[0]
            self.assertEqual((run.trigger, run.status, run.triggered_by_id), ('exam_close', 'completed', None))
            self.assertEqual(run.questions_done, run.questions_total)
            self.assertEqual(run.questions_total, exam.questions.count())
            self.assertEqual(run.s_flags_total, PlagiarismFlag.objects.filter(submission_1__exam=exam).count())
        self.assertFalse(PlagiarismRun.objects.filter(exam__is_active=True).exists())

    def test_exactly_one_open_exam_with_all_students(self):
        open_exams = list(Exam.objects.filter(is_active=True))
        self.assertEqual([e.title for e in open_exams], ['Python Binary Search Exam'])
        self.assertEqual(
            list(open_exams[0].questions.order_by('id').values_list('title', flat=True)),
            ['Find Target in Sorted Array', 'Count Occurrences of Target', 'Find First and Last Position'])
        self.assertFalse(Submission.objects.filter(exam=open_exams[0]).exists())
        enrolled = set(ExamEnrollment.objects.filter(exam=open_exams[0]).values_list('student_id', flat=True))
        self.assertEqual(enrolled, set(User.objects.filter(role='student').values_list('id', flat=True)))

    def test_every_student_enrolled_in_every_exam_and_every_submission_is_enrolled(self):
        students = set(User.objects.filter(role='student', is_superuser=False).values_list('id', flat=True))
        for exam in Exam.objects.all():
            enrolled = set(ExamEnrollment.objects.filter(exam=exam).values_list('student_id', flat=True))
            self.assertEqual(enrolled, students, exam.title)
        pairs = set(ExamEnrollment.objects.values_list('student_id', 'exam_id'))
        stray = Submission.objects.exclude(exam_id=F('question__exam_id')).count() + sum(
            1 for p in Submission.objects.values_list('student_id', 'exam_id') if p not in pairs)
        self.assertEqual(stray, 0)


from django.db.models import F
from rest_framework.test import APIClient
from exams.models import Question


class StudentExamVisibilityTest(TestCase):
    """Students only see (and can open) active exams they are enrolled in; trainers are unaffected."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='vt', password='pw', role='trainer')
        self.student = User.objects.create_user(username='vs', password='pw', role='student', cohort='C')
        self.enrolled = Exam.objects.create(title='Enrolled', created_by=self.trainer, is_active=True)
        self.unenrolled = Exam.objects.create(title='Not enrolled', created_by=self.trainer, is_active=True)
        self.closed = Exam.objects.create(title='Closed', created_by=self.trainer, is_active=False)
        for exam in (self.enrolled, self.unenrolled, self.closed):
            Question.objects.create(exam=exam, title=f'Q {exam.title}', description='d')
        ExamEnrollment.objects.create(exam=self.enrolled, student=self.student)
        ExamEnrollment.objects.create(exam=self.closed, student=self.student)
        self.api = APIClient()

    def as_(self, user):
        self.api.force_authenticate(user)
        return self.api

    def test_exam_list_shows_only_active_enrolled_exams(self):
        r = self.as_(self.student).get('/api/exams/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([e['id'] for e in r.data], [self.enrolled.id])

    def test_exam_list_is_empty_when_not_enrolled_anywhere(self):
        other = User.objects.create_user(username='vs2', password='pw', role='student', cohort='C')
        self.assertEqual(self.as_(other).get('/api/exams/').data, [])

    def test_detail_is_404_for_an_unenrolled_student(self):
        r = self.as_(self.student).get(f'/api/exams/{self.unenrolled.id}/')
        self.assertEqual(r.status_code, 404)
        self.assertNotIn('title', r.data)

    def test_detail_is_200_for_an_enrolled_student(self):
        r = self.as_(self.student).get(f'/api/exams/{self.enrolled.id}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['title'], 'Enrolled')

    def test_questions_list_is_404_for_an_unenrolled_student(self):
        self.assertEqual(self.as_(self.student).get(f'/api/exams/{self.unenrolled.id}/questions/').status_code, 404)
        r = self.as_(self.student).get(f'/api/exams/{self.enrolled.id}/questions/')
        self.assertEqual((r.status_code, len(r.data)), (200, 1))

    def test_trainer_list_detail_and_questions_are_unchanged(self):
        api = self.as_(self.trainer)
        ids = {e['id'] for e in api.get('/api/exams/').data}
        self.assertEqual(ids, {self.enrolled.id, self.unenrolled.id, self.closed.id})  # own exams, any state
        for exam in (self.enrolled, self.unenrolled, self.closed):
            self.assertEqual(api.get(f'/api/exams/{exam.id}/').status_code, 200)
            self.assertEqual(api.get(f'/api/exams/{exam.id}/questions/').status_code, 200)


class ResetExamAttemptsTest(TestCase):
    """reset_exam_attempts: rehearsal students go back to "never attempted"; nobody else changes."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from exams.models import Exam, Question
        from submissions.models import Submission
        trainer = cls.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        cls.riya = User.objects.create_user(username='riya', password='pw', role='student', cohort='Section A')
        cls.kabir = User.objects.create_user(username='kabir', password='pw', role='student', cohort='Section B')
        cls.other = User.objects.create_user(username='other', password='pw', role='student', cohort='Section C')
        cls.exam = Exam.objects.create(title='Demo', created_by=trainer, is_active=True)
        cls.q = Question.objects.create(exam=cls.exam, title='Q', description='d', difficulty='medium')

        def sub(student):
            return Submission.objects.create(student=student, exam=cls.exam, question=cls.q, code='x',
                                             language='python', attempt_number=1, status='failed')
        cls.s_riya, cls.s_kabir, cls.s_other = sub(cls.riya), sub(cls.kabir), sub(cls.other)

    def build_rehearsal(self):
        from ai.models import AIHint, ExamSummary
        from jobs.models import Job
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag, PlagiarismRun, ReviewAuditLog
        from support.models import DisputeRequest
        b = BehaviouralFlag.objects.create(submission=self.s_kabir, risk_score=0.9, confidence='high')
        BehaviouralFlag.objects.create(submission=self.s_other, risk_score=0.5, confidence='medium')
        p = PlagiarismFlag.objects.create(submission_1=self.s_kabir, submission_2=self.s_riya, similarity_score=0.95)
        AIHint.objects.create(submission=self.s_kabir, hint='h')
        Job.objects.create(kind=Job.KIND_EXECUTE, subject_id=self.s_kabir.id)
        Job.objects.create(kind=Job.KIND_EXECUTE, subject_id=self.s_other.id)
        ReviewAuditLog.objects.create(flag_type='similarity', flag_id=p.id, action='confirm', reviewed_by=self.trainer)
        DisputeRequest.objects.create(student=self.kabir, flag_type='behavioural', flag_id=b.id, student_note='n')
        ExamSummary.objects.create(student=self.kabir, exam=self.exam, summary='s')
        PlagiarismRun.objects.create(exam=self.exam, trigger='manual_rerun')
        PlagiarismRun.objects.create(exam=self.exam, trigger='exam_close')

    def reset(self, *extra):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('reset_exam_attempts', '--exam', str(self.exam.id), '--users', 'riya,kabir', *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_deletes_nothing(self):
        from submissions.models import Submission
        self.build_rehearsal()
        out = self.reset()
        self.assertIn('Dry run', out)
        self.assertEqual(Submission.objects.count(), 3)

    def test_yes_clears_rehearsal_students_only(self):
        from ai.models import AIHint, ExamSummary
        from jobs.models import Job
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag, PlagiarismRun, ReviewAuditLog
        from submissions.models import Submission
        from support.models import DisputeRequest
        self.build_rehearsal()
        self.reset('--yes')
        self.assertEqual(list(Submission.objects.values_list('student__username', flat=True)), ['other'])
        self.assertEqual(list(BehaviouralFlag.objects.values_list('submission_id', flat=True)), [self.s_other.id])
        self.assertFalse(PlagiarismFlag.objects.exists())
        self.assertFalse(AIHint.objects.exists())
        self.assertEqual(list(Job.objects.values_list('subject_id', flat=True)), [self.s_other.id])
        self.assertFalse(ReviewAuditLog.objects.exists())
        self.assertFalse(DisputeRequest.objects.exists())
        self.assertFalse(ExamSummary.objects.exists())
        self.assertEqual(list(PlagiarismRun.objects.values_list('trigger', flat=True)), ['exam_close'])

    def test_yes_undoes_end_exam(self):
        from django.utils import timezone
        from exams.models import ExamEnrollment
        for s in (self.riya, self.other):
            ExamEnrollment.objects.create(exam=self.exam, student=s, finished_at=timezone.now())
        self.reset('--yes')
        self.assertEqual({e.student.username: e.finished_at is None for e in ExamEnrollment.objects.all()},
                         {'riya': True, 'other': False})


class StarterCodeTest(TestCase):
    """Editor starter code: per-question, with a generic fallback, and the demo starters really run."""

    # Reference bodies dropped into each demo starter's function
    SOLUTIONS = {
        'Find Target in Sorted Array': (
            '    return arr.indexOf(target);',
            '    return arr.index(target) if target in arr else -1'),
        'Count Occurrences of Target': (
            '    return arr.filter((x) => x === target).length;',
            '    return arr.count(target)'),
        'Find First and Last Position': (
            '    return arr.includes(target) ? [arr.indexOf(target), arr.lastIndexOf(target)] : [-1, -1];',
            '    return [arr.index(target), len(arr) - 1 - arr[::-1].index(target)] if target in arr else [-1, -1]'),
    }
    CASES = {
        'Find Target in Sorted Array': [('5\n1 2 3 4 5\n3\n', '2'), ('7\n10 20 30 40 50 60 70\n25\n', '-1')],
        'Count Occurrences of Target': [('6\n1 1 2 2 2 3\n2\n', '3'), ('4\n1 2 3 4\n5\n', '0')],
        'Find First and Last Position': [('7\n5 7 7 8 8 10 10\n8\n', '3 4'), ('5\n1 2 3 4 5\n6\n', '-1 -1')],
    }

    def test_question_without_starters_gets_the_generic_one(self):
        from accounts.models import User
        from exams.models import Exam, Question
        from exams.starter_code import GENERIC
        t = User.objects.create_user(username='t', password='pw', role='trainer')
        exam = Exam.objects.create(title='E', created_by=t)
        q = Question.objects.create(exam=exam, title='Q', description='d', starter_code_javascript='// mine')
        c = APIClient()
        c.force_authenticate(t)
        data = c.get(f'/api/exams/{exam.id}/').data['questions'][0]
        self.assertEqual(data['starter_code'], {'javascript': '// mine', 'python': GENERIC['python']})
        self.assertNotIn('starter_code_javascript', data)

    def test_create_full_stores_starter_code(self):
        from accounts.models import User
        from exams.models import Question
        t = User.objects.create_user(username='t', password='pw', role='trainer')
        c = APIClient()
        c.force_authenticate(t)
        r = c.post('/api/exams/create-full/', {'title': 'E', 'questions': [
            {'title': 'Q', 'description': 'd', 'starter_code': {'javascript': '// js', 'python': '# py'}}]}, format='json')
        self.assertEqual(r.status_code, 201)
        q = Question.objects.get(title='Q')
        self.assertEqual((q.starter_code_javascript, q.starter_code_python), ('// js', '# py'))

    def run_code(self, cmd, code, stdin):
        import subprocess
        return subprocess.run(cmd + [code], input=stdin, capture_output=True, text=True, timeout=10).stdout.strip()

    def test_demo_starters_pass_their_tests_with_a_reference_body(self):
        import re
        import shutil
        import sys
        from exams.starter_code import DEMO_STARTERS
        node = shutil.which('node')
        for title, starter in DEMO_STARTERS.items():
            js_body, py_body = self.SOLUTIONS[title]
            py = starter['python'].replace('    pass\n', py_body + '\n')
            js = re.sub(r'    // Write your code here\..*\n', js_body + '\n', starter['javascript'])
            for stdin, expected in self.CASES[title]:
                with self.subTest(title=title, lang='python', stdin=stdin):
                    self.assertEqual(self.run_code([sys.executable, '-c'], py, stdin), expected)
                if node:
                    with self.subTest(title=title, lang='javascript', stdin=stdin):
                        self.assertEqual(self.run_code([node, '-e'], js, stdin), expected)


class EndExamTest(TestCase):
    """End exam: the student stops early; no more submissions; results stay."""

    @classmethod
    def setUpTestData(cls):
        from accounts.models import User
        from exams.models import Exam, ExamEnrollment, Question
        from django.utils import timezone
        from datetime import timedelta
        t = User.objects.create_user(username='t', password='pw', role='trainer')
        cls.student = User.objects.create_user(username='s', password='pw', role='student')
        cls.other = User.objects.create_user(username='o', password='pw', role='student')
        now = timezone.now()
        cls.exam = Exam.objects.create(title='E', created_by=t, is_active=True,
                                       start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1))
        cls.q = Question.objects.create(exam=cls.exam, title='Q', description='d')
        ExamEnrollment.objects.create(exam=cls.exam, student=cls.student)
        cls.still_writing = User.objects.create_user(username='w', password='pw', role='student')
        ExamEnrollment.objects.create(exam=cls.exam, student=cls.still_writing)  # keeps the exam open

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_ending_blocks_submissions_and_is_idempotent(self):
        c = self.api(self.student)
        first = c.post(f'/api/exams/{self.exam.id}/finish/').data['finished_at']
        self.assertIsNotNone(first)
        self.assertEqual(c.post(f'/api/exams/{self.exam.id}/finish/').data['finished_at'], first)
        self.assertEqual(c.get(f'/api/exams/{self.exam.id}/').data['finished_at'], first)
        self.assertEqual(c.get('/api/exams/').data[0]['finished_at'], first)
        r = c.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(1)', 'language': 'python'},
                   format='json')
        self.assertEqual((r.status_code, r.data), (403, {'error': 'You have already submitted this exam.'}))

    def test_only_enrolled_students_can_end(self):
        self.assertEqual(self.api(self.other).post(f'/api/exams/{self.exam.id}/finish/').status_code, 404)
        from accounts.models import User
        trainer = User.objects.get(username='t')
        self.assertEqual(self.api(trainer).post(f'/api/exams/{self.exam.id}/finish/').status_code, 403)


from unittest.mock import patch


class ExamCloseTest(TestCase):
    """Closing early: the last finisher closes the exam, and the scheduler never re-opens it."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.a = User.objects.create_user(username='a', password='pw', role='student')
        self.b = User.objects.create_user(username='b', password='pw', role='student')
        now = timezone.now()
        self.exam = Exam.objects.create(title='E', created_by=self.trainer, is_active=True,
                                        start_time=now - timedelta(minutes=5), end_time=now + timedelta(hours=1))
        for s in (self.a, self.b):
            ExamEnrollment.objects.create(exam=self.exam, student=s)

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    @patch('plagiarism.tasks.run_exam_plagiarism_check')
    def test_last_finisher_closes_exam_and_queues_checks(self, check):
        self.api(self.a).post(f'/api/exams/{self.exam.id}/finish/')
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)
        check.delay.assert_not_called()

        self.api(self.b).post(f'/api/exams/{self.exam.id}/finish/')
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)
        self.assertLessEqual(self.exam.end_time, timezone.now())
        check.delay.assert_called_once_with(self.exam.id)

    @patch('plagiarism.tasks.run_exam_plagiarism_check')
    def test_manual_close_is_not_undone_by_scheduler(self, check):
        from exams.tasks import auto_manage_exams
        r = self.api(self.trainer).patch(f'/api/exams/{self.exam.id}/', {'is_active': False}, format='json')
        self.assertEqual(r.status_code, 200)
        auto_manage_exams()
        self.exam.refresh_from_db()
        self.assertFalse(self.exam.is_active)
        self.assertLessEqual(self.exam.end_time, timezone.now())
        check.delay.assert_called_once_with(self.exam.id)

    @patch('plagiarism.tasks.run_exam_plagiarism_check')
    def test_reactivating_after_window_clears_stale_end(self, check):
        self.api(self.trainer).patch(f'/api/exams/{self.exam.id}/', {'is_active': False}, format='json')
        self.api(self.trainer).patch(f'/api/exams/{self.exam.id}/', {'is_active': True}, format='json')
        from exams.tasks import auto_manage_exams
        auto_manage_exams()
        self.exam.refresh_from_db()
        self.assertTrue(self.exam.is_active)
        self.assertIsNone(self.exam.end_time)


class AutoEnrollTest(TestCase):
    """Going live puts the exam in front of its sections (or the whole cohort) with no manual step."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.a1 = User.objects.create_user(username='a1', password='pw', role='student', cohort='Section A')
        self.a2 = User.objects.create_user(username='a2', password='pw', role='student', cohort='Section A')
        self.b1 = User.objects.create_user(username='b1', password='pw', role='student', cohort='Section B')
        self.exam = Exam.objects.create(title='Draft', created_by=self.trainer)
        self.c = APIClient()
        self.c.force_authenticate(self.trainer)

    def enrolled(self):
        return set(ExamEnrollment.objects.filter(exam=self.exam).values_list('student__username', flat=True))

    def test_draft_enrolls_nobody(self):
        self.assertEqual(self.enrolled(), set())

    def test_activating_without_sections_enrolls_whole_cohort(self):
        self.c.patch(f'/api/exams/{self.exam.id}/', {'is_active': True}, format='json')
        self.assertEqual(self.enrolled(), {'a1', 'a2', 'b1'})

    def test_activating_with_sections_enrolls_only_them(self):
        r = self.c.patch(f'/api/exams/{self.exam.id}/', {'is_active': True, 'sections': ['Section A']}, format='json')
        self.assertEqual(r.data['sections'], ['Section A'])
        self.assertEqual(self.enrolled(), {'a1', 'a2'})
        s = APIClient()
        s.force_authenticate(self.a1)
        self.assertEqual([e['id'] for e in s.get('/api/exams/').data], [self.exam.id])
        s.force_authenticate(self.b1)
        self.assertEqual(s.get('/api/exams/').data, [])

    def test_scheduler_auto_open_enrolls(self):
        from exams.tasks import auto_manage_exams
        now = timezone.now()
        Exam.objects.filter(pk=self.exam.pk).update(sections=['Section B'], start_time=now - timedelta(minutes=1),
                                                    end_time=now + timedelta(hours=1))
        auto_manage_exams()
        self.assertEqual(self.enrolled(), {'b1'})

    def test_created_live_enrolls(self):
        r = self.c.post('/api/exams/', {'title': 'Live', 'is_active': True, 'sections': ['Section B']}, format='json')
        self.assertEqual(set(ExamEnrollment.objects.filter(exam_id=r.data['id'])
                             .values_list('student__username', flat=True)), {'b1'})

    def test_bad_sections_rejected(self):
        r = self.c.patch(f'/api/exams/{self.exam.id}/', {'sections': 'Section A'}, format='json')
        self.assertEqual(r.status_code, 400)

    def test_sections_list(self):
        self.assertEqual(self.c.get('/api/exams/sections/').data,
                         [{'name': 'Section A', 'students': 2}, {'name': 'Section B', 'students': 1}])
        s = APIClient()
        s.force_authenticate(self.a1)
        self.assertEqual(s.get('/api/exams/sections/').status_code, 403)


class ExamDeleteTest(TestCase):
    """A trainer can delete an exam that already has enrollments, graded submissions, flags and a run."""

    def test_delete_exam_with_history(self):
        from jobs.models import Job
        from plagiarism.models import BehaviouralFlag, PlagiarismFlag, PlagiarismRun
        from results.models import Result
        from exams.models import Question, TestCase as TC
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        a = User.objects.create_user(username='a', password='pw', role='student')
        b = User.objects.create_user(username='b', password='pw', role='student')
        exam = Exam.objects.create(title='E', created_by=trainer, is_active=True)
        q = Question.objects.create(exam=exam, title='Q', description='d', language='python')
        tc = TC.objects.create(question=q, input_data='1', expected_output='1')
        subs = []
        for s in (a, b):
            ExamEnrollment.objects.create(exam=exam, student=s, finished_at=timezone.now())
            sub = Submission.objects.create(student=s, exam=exam, question=q, code='print(1)', language='python',
                                            attempt_number=1, status='passed')
            Result.objects.create(submission=sub, test_case=tc, passed=True, actual_output='1')
            Job.objects.create(kind=Job.KIND_EXECUTE, subject_id=sub.id, status='done')
            BehaviouralFlag.objects.create(submission=sub, risk_score=0.5, confidence='high')
            subs.append(sub)
        PlagiarismFlag.objects.create(submission_1=subs[0], submission_2=subs[1], similarity_score=0.95, flagged=True,
                                      review_status='confirmed', review_note='n')
        PlagiarismRun.objects.create(exam=exam, trigger='manual_rerun', status='completed')
        c = APIClient()
        c.force_authenticate(trainer)
        flag = PlagiarismFlag.objects.get()
        c.patch(f'/api/plagiarism/{flag.id}/review/', {'review_status': 'confirmed', 'review_note': 'n'}, format='json')
        from plagiarism.models import ReviewAuditLog
        self.assertEqual(ReviewAuditLog.objects.count(), 1)
        r = c.delete(f'/api/exams/{exam.id}/')
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Exam.objects.filter(pk=exam.pk).exists())
        # rows that point at the exam's submissions/flags by plain id go too
        self.assertEqual((Job.objects.count(), ReviewAuditLog.objects.count()), (0, 0))


class ScheduleOpensOnlyTest(TestCase):
    """An exam scheduled with only "Opens at" opens on time and stays closed after a manual close."""

    @patch('plagiarism.tasks.run_exam_plagiarism_check')
    def test_open_only_schedule(self, check):
        from exams.tasks import auto_manage_exams
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        User.objects.create_user(username='s', password='pw', role='student')
        exam = Exam.objects.create(title='E', created_by=trainer, start_time=timezone.now() - timedelta(minutes=1))
        auto_manage_exams()
        exam.refresh_from_db()
        self.assertTrue(exam.is_active)
        self.assertEqual(ExamEnrollment.objects.filter(exam=exam).count(), 1)

        c = APIClient()
        c.force_authenticate(trainer)
        c.patch(f'/api/exams/{exam.id}/', {'is_active': False}, format='json')
        auto_manage_exams()
        exam.refresh_from_db()
        self.assertFalse(exam.is_active)


class ExamGoesLiveStartTimeTest(TestCase):
    """An exam opened without a schedule gets a start time, so the overview and student pages list it."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)

    def test_activating_a_draft_stamps_start_time(self):
        from dashboard.health import build_dashboard_health
        exam = Exam.objects.create(title='Live now', created_by=self.trainer)
        self.assertIsNone(exam.start_time)
        r = self.api.patch(f'/api/exams/{exam.id}/', {'is_active': True}, format='json')
        self.assertEqual(r.status_code, 200)
        exam.refresh_from_db()
        self.assertIsNotNone(exam.start_time)
        self.assertIn(exam.id, [e['exam_id'] for e in build_dashboard_health()['exams']])

    def test_created_live_stamps_start_time(self):
        exam = Exam.objects.create(title='Live', created_by=self.trainer, is_active=True)
        self.assertIsNotNone(exam.start_time)

    def test_draft_and_scheduled_exams_keep_their_start_time(self):
        later = timezone.now() + timedelta(days=1)
        self.assertIsNone(Exam.objects.create(title='Draft', created_by=self.trainer).start_time)
        exam = Exam.objects.create(title='Scheduled', created_by=self.trainer, is_active=True, start_time=later)
        self.assertEqual(exam.start_time, later)


class ExamStatusTest(TestCase):
    """Every exam page reads one status: draft, live or ended (exams.models.exam_status)."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)

    def status(self, exam):
        return self.api.get(f'/api/exams/{exam.id}/').data['status']

    def test_draft_live_and_ended(self):
        now = timezone.now()
        draft = Exam.objects.create(title='Draft', created_by=self.trainer)
        live = Exam.objects.create(title='Live, no end time', created_by=self.trainer, is_active=True)
        ended = Exam.objects.create(title='Closed', created_by=self.trainer,
                                    start_time=now - timedelta(hours=2), end_time=now - timedelta(hours=1))
        self.assertEqual(self.status(draft), 'draft')
        self.assertEqual(self.status(live), 'live')
        self.assertEqual(self.status(ended), 'ended')

    def test_closing_a_live_exam_makes_it_ended_not_draft(self):
        exam = Exam.objects.create(title='Live', created_by=self.trainer, is_active=True)
        self.api.patch(f'/api/exams/{exam.id}/', {'is_active': False}, format='json')
        self.assertEqual(self.status(exam), 'ended')


class AttemptLimitTest(TestCase):
    """The limit a page shows is the one the server enforces: the policy's max_attempts."""

    def test_question_max_attempts_is_the_policy_limit(self):
        from exams.models import Question
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        exam = Exam.objects.create(title='E', created_by=trainer, is_active=True)
        Question.objects.create(exam=exam, title='Hard', description='d', difficulty='hard', max_attempts=2)
        policy = PlagiarismPolicy.get()
        policy.max_attempts = 5
        policy.save()
        api = APIClient()
        api.force_authenticate(trainer)
        self.assertEqual([q['max_attempts'] for q in api.get(f'/api/exams/{exam.id}/').data['questions']], [5])
        self.assertEqual([q['max_attempts'] for q in api.get(f'/api/exams/{exam.id}/questions/').data], [5])
