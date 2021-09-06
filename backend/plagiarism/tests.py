from django.test import SimpleTestCase, TestCase
from unittest.mock import MagicMock, patch
from types import SimpleNamespace
from rest_framework.test import APIClient

from plagiarism.tasks import (
    paste_signal,
    time_signal,
    tab_switch_signal,
    submission_surprise_signal,
    compute_behavioural_risk,
    normalize_python,
    normalize_javascript,
)

MOCK_POLICY = {
    'paste_weight':         0.40,
    'time_weight':          0.30,
    'tab_weight':           0.15,
    'submission_weight':    0.15,
    'min_risk_score':       0.20,
    'similarity_threshold': 0.80,
    'easy_baseline_s':      90,
    'medium_baseline_s':    240,
    'hard_baseline_s':      480,
}


def make_sub(**kwargs):
    defaults = {
        'had_paste_event':          False,
        'paste_char_count':         0,
        'code':                     'x = 1',
        'time_to_complete_seconds': None,
        'tab_switch_count':         0,
        'status':                   'passed',
        'attempt_number':           2,
        'question':                 SimpleNamespace(difficulty='medium'),
        'student':                  SimpleNamespace(username='alice'),
        'student_id':               1,
        'question_id':              1,
        'language':                 'python',
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def mock_submission_class(previous_code=None):
    MockSub = MagicMock()
    prev = SimpleNamespace(code=previous_code, attempt_number=1) if previous_code is not None else None
    MockSub.objects.filter.return_value.first.return_value = prev
    return MockSub


# ─── paste_signal ─────────────────────────────────────────────────────────────

class PasteSignalTest(SimpleTestCase):

    def test_no_paste_event_returns_zero(self):
        score, signals = paste_signal(make_sub(had_paste_event=False))
        self.assertEqual(score, 0.0)
        self.assertEqual(signals, [])

    def test_empty_code_returns_zero(self):
        score, _ = paste_signal(make_sub(had_paste_event=True, code='', paste_char_count=0))
        self.assertEqual(score, 0.0)

    def test_ratio_at_70_percent_returns_1(self):
        sub = make_sub(had_paste_event=True, code='x' * 100, paste_char_count=70)
        score, signals = paste_signal(sub)
        self.assertEqual(score, 1.0)
        self.assertTrue(len(signals) > 0)

    def test_ratio_above_70_percent_returns_1(self):
        sub = make_sub(had_paste_event=True, code='x' * 100, paste_char_count=90)
        score, _ = paste_signal(sub)
        self.assertEqual(score, 1.0)

    def test_ratio_between_50_and_70_returns_0_7(self):
        sub = make_sub(had_paste_event=True, code='x' * 100, paste_char_count=60)
        score, _ = paste_signal(sub)
        self.assertEqual(score, 0.7)

    def test_ratio_between_30_and_50_returns_0_3(self):
        sub = make_sub(had_paste_event=True, code='x' * 100, paste_char_count=40)
        score, _ = paste_signal(sub)
        self.assertEqual(score, 0.3)

    def test_ratio_below_30_returns_zero(self):
        sub = make_sub(had_paste_event=True, code='x' * 100, paste_char_count=20)
        score, _ = paste_signal(sub)
        self.assertEqual(score, 0.0)


# ─── time_signal ──────────────────────────────────────────────────────────────

class TimeSignalTest(SimpleTestCase):
    BASELINES = {'easy': 90, 'medium': 240, 'hard': 480}

    def test_no_time_recorded_returns_zero(self):
        score, _ = time_signal(make_sub(time_to_complete_seconds=None), self.BASELINES)
        self.assertEqual(score, 0.0)

    def test_ratio_exactly_20_percent_returns_1(self):
        # 48 / 240 = 0.20 — boundary of the <= 0.2 check
        sub = make_sub(time_to_complete_seconds=48)
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 1.0)

    def test_ratio_below_20_percent_returns_1(self):
        sub = make_sub(time_to_complete_seconds=30)
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 1.0)

    def test_ratio_between_20_and_40_returns_0_7(self):
        # 72 / 240 = 0.30
        sub = make_sub(time_to_complete_seconds=72)
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 0.7)

    def test_ratio_between_40_and_60_returns_0_3(self):
        # 120 / 240 = 0.50
        sub = make_sub(time_to_complete_seconds=120)
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 0.3)

    def test_ratio_above_60_percent_returns_zero(self):
        # 192 / 240 = 0.80 — normal pace
        sub = make_sub(time_to_complete_seconds=192)
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 0.0)

    def test_hard_problem_uses_480s_baseline(self):
        # 20% of 480 = 96s — right at the threshold
        sub = make_sub(
            time_to_complete_seconds=96,
            question=SimpleNamespace(difficulty='hard'),
        )
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 1.0)

    def test_easy_problem_uses_90s_baseline(self):
        # 50% of 90 = 45s — should be 0.3 (between 40%-60%)
        sub = make_sub(
            time_to_complete_seconds=45,
            question=SimpleNamespace(difficulty='easy'),
        )
        score, _ = time_signal(sub, self.BASELINES)
        self.assertEqual(score, 0.3)


# ─── tab_switch_signal ────────────────────────────────────────────────────────

class TabSwitchSignalTest(SimpleTestCase):

    def test_zero_switches_returns_zero(self):
        score, _ = tab_switch_signal(make_sub(tab_switch_count=0))
        self.assertEqual(score, 0.0)

    def test_none_treated_as_zero(self):
        score, _ = tab_switch_signal(make_sub(tab_switch_count=None))
        self.assertEqual(score, 0.0)

    def test_one_switch_returns_0_2(self):
        score, _ = tab_switch_signal(make_sub(tab_switch_count=1))
        self.assertEqual(score, 0.2)

    def test_two_switches_returns_0_2(self):
        score, _ = tab_switch_signal(make_sub(tab_switch_count=2))
        self.assertEqual(score, 0.2)

    def test_three_switches_returns_0_5(self):
        score, signals = tab_switch_signal(make_sub(tab_switch_count=3))
        self.assertEqual(score, 0.5)
        self.assertTrue(len(signals) > 0)

    def test_five_switches_returns_1(self):
        score, signals = tab_switch_signal(make_sub(tab_switch_count=5))
        self.assertEqual(score, 1.0)
        self.assertTrue(len(signals) > 0)

    def test_ten_switches_returns_1(self):
        score, _ = tab_switch_signal(make_sub(tab_switch_count=10))
        self.assertEqual(score, 1.0)


# ─── submission_surprise_signal ───────────────────────────────────────────────

class SubmissionSurpriseSignalTest(SimpleTestCase):

    def test_no_previous_attempt_returns_zero(self):
        sub = make_sub(attempt_number=2)
        score, _ = submission_surprise_signal(sub, mock_submission_class(None))
        self.assertEqual(score, 0.0)

    def test_very_low_similarity_and_passed_returns_1(self):
        sub = make_sub(attempt_number=2, status='passed')
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.10  # < 0.25, passed
            score, signals = submission_surprise_signal(sub, mock_submission_class('old code'))
        self.assertEqual(score, 1.0)
        self.assertTrue(len(signals) > 0)

    def test_very_low_similarity_but_failed_falls_to_0_6(self):
        # < 0.25 but status != passed → skips first branch, hits elif < 0.4
        sub = make_sub(attempt_number=2, status='failed')
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.10
            score, _ = submission_surprise_signal(sub, mock_submission_class('old code'))
        self.assertEqual(score, 0.6)

    def test_low_similarity_returns_0_6(self):
        sub = make_sub(attempt_number=2, status='passed')
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.35  # 0.25 ≤ x < 0.4
            score, _ = submission_surprise_signal(sub, mock_submission_class('old code'))
        self.assertEqual(score, 0.6)

    def test_medium_similarity_returns_0_2(self):
        sub = make_sub(attempt_number=2)
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.45  # 0.4 ≤ x < 0.55
            score, _ = submission_surprise_signal(sub, mock_submission_class('old code'))
        self.assertEqual(score, 0.2)

    def test_high_similarity_returns_zero(self):
        sub = make_sub(attempt_number=2)
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.90  # normal iteration
            score, _ = submission_surprise_signal(sub, mock_submission_class('old code'))
        self.assertEqual(score, 0.0)


# ─── compute_behavioural_risk ─────────────────────────────────────────────────

class ComputeBehaviouralRiskTest(SimpleTestCase):

    def test_three_signals_gives_low_confidence(self):
        # paste + time + tab all fire (3 signals) → low confidence = most suspicious
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=48,   # 20% of 240 → 1.0
            tab_switch_count=5,
            attempt_number=1,              # no previous attempt → surprise=0.0
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'low')

    def test_two_signals_gives_medium_confidence(self):
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=48,   # paste + time fire
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'medium')

    def test_one_signal_gives_high_confidence(self):
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=300,  # slow — no time signal
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'high')

    def test_no_signals_zero_risk_and_high_confidence(self):
        sub = make_sub(
            had_paste_event=False,
            time_to_complete_seconds=300,
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['risk_score'], 0.0)
        self.assertEqual(result['confidence'], 'high')

    def test_weighted_score_is_correct(self):
        # paste=0.7 (60%), time=0.0 (slow), tab=0.5 (3 switches), surprise=0.0
        sub = make_sub(
            had_paste_event=True, paste_char_count=60, code='x' * 100,
            time_to_complete_seconds=300,
            tab_switch_count=3,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        expected = round(0.40 * 0.7 + 0.30 * 0.0 + 0.15 * 0.5 + 0.15 * 0.0, 4)
        self.assertAlmostEqual(result['risk_score'], expected)

    def test_result_contains_all_expected_keys(self):
        sub = make_sub(attempt_number=1)
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        for key in ('risk_score', 'confidence', 'paste_score', 'time_score',
                    'snapshot_score', 'submission_score', 'signals_triggered'):
            self.assertIn(key, result)


# ─── normalize_python ─────────────────────────────────────────────────────────

class NormalizePythonTest(SimpleTestCase):

    def test_renames_user_defined_names(self):
        result = normalize_python("x = 1\ny = x + 1")
        self.assertNotIn('x', result)
        self.assertNotIn('y', result)
        self.assertIn('VAR_0', result)

    def test_preserves_builtins(self):
        result = normalize_python("result = len(range(10))")
        self.assertIn('len', result)
        self.assertIn('range', result)

    def test_strips_inline_comments(self):
        result = normalize_python("x = 1  # suspicious comment\ny = 2")
        self.assertNotIn('suspicious', result)
        self.assertNotIn('#', result)

    def test_strips_docstrings(self):
        result = normalize_python('def foo():\n    """secret docstring."""\n    return 1')
        self.assertNotIn('secret docstring', result)

    def test_invalid_syntax_returns_comment_stripped_original(self):
        result = normalize_python("def foo(: invalid syntax")
        self.assertIn('invalid syntax', result)

    def test_same_logic_different_variable_names_normalize_equal(self):
        code_a = (
            "def solve(nums):\n"
            "    total = 0\n"
            "    for n in nums:\n"
            "        total += n\n"
            "    return total"
        )
        code_b = (
            "def compute(values):\n"
            "    acc = 0\n"
            "    for v in values:\n"
            "        acc += v\n"
            "    return acc"
        )
        self.assertEqual(normalize_python(code_a), normalize_python(code_b))

    def test_same_code_normalizes_to_same_output(self):
        code = "def foo(x):\n    return x * 2"
        self.assertEqual(normalize_python(code), normalize_python(code))


# ─── normalize_javascript ─────────────────────────────────────────────────────

class NormalizeJavascriptTest(SimpleTestCase):

    def test_renames_user_identifiers(self):
        result = normalize_javascript("let myVar = 1;")
        self.assertNotIn('myVar', result)
        self.assertIn('VAR_', result)

    def test_preserves_keywords(self):
        result = normalize_javascript("let x = 1; return x;")
        self.assertIn('let', result)
        self.assertIn('return', result)

    def test_strips_single_line_comments(self):
        result = normalize_javascript("let x = 1; // secret comment\nlet y = 2;")
        self.assertNotIn('secret comment', result)

    def test_strips_block_comments(self):
        result = normalize_javascript("/* block comment */\nlet x = 1;")
        self.assertNotIn('block comment', result)

    def test_same_logic_different_names_normalize_equal(self):
        code_a = "function solve(nums) { let total = 0; for (let n of nums) { total += n; } return total; }"
        code_b = "function compute(vals) { let acc = 0; for (let v of vals) { acc += v; } return acc; }"
        self.assertEqual(normalize_javascript(code_a), normalize_javascript(code_b))


# ═══════════════════════════════════════════════════════════════════════════════
# Integration Tests — API views hitting the real test database
# ═══════════════════════════════════════════════════════════════════════════════

from accounts.models import User
from exams.models import Exam, Question
from submissions.models import Submission
from plagiarism.models import (
    PlagiarismPolicy, BehaviouralFlag, PlagiarismFlag,
    PlagiarismRun, ReviewAuditLog, PolicyVersion,
)


class BaseViewTest(TestCase):
    """
    Shared fixture: trainer, two students, one exam, one question, three submissions.
    alice has 2 attempts (failed, passed); bob has 1 attempt (passed).
    Total submission rows = 3; unique students = 2.
    """
    def setUp(self):
        self.api = APIClient()
        self.trainer = User.objects.create_user(
            username='trainer', password='pass', role='trainer'
        )
        self.alice = User.objects.create_user(
            username='alice', password='pass', role='student'
        )
        self.bob = User.objects.create_user(
            username='bob', password='pass', role='student'
        )
        self.exam = Exam.objects.create(
            title='Midterm', created_by=self.trainer, duration_minutes=60
        )
        self.question = Question.objects.create(
            exam=self.exam, title='Two Sum',
            description='Return indices.',
            difficulty='medium', language='python',
        )
        self.sub_alice1 = Submission.objects.create(
            student=self.alice, exam=self.exam, question=self.question,
            code='def solve(a): pass', language='python',
            attempt_number=1, status='failed',
        )
        self.sub_alice2 = Submission.objects.create(
            student=self.alice, exam=self.exam, question=self.question,
            code='def solve(a): return 1', language='python',
            attempt_number=2, status='passed',
        )
        self.sub_bob = Submission.objects.create(
            student=self.bob, exam=self.exam, question=self.question,
            code='def f(b): return 1', language='python',
            attempt_number=1, status='passed',
        )

    def _make_behavioural_flag(self, submission, review_status='pending'):
        return BehaviouralFlag.objects.create(
            submission=submission,
            risk_score=0.75,
            confidence='low',
            paste_score=1.0,
            time_score=0.7,
            snapshot_score=0.5,
            submission_score=0.0,
        )

    def _make_similarity_flag(self, sub1, sub2, score=0.92):
        return PlagiarismFlag.objects.create(
            submission_1=sub1,
            submission_2=sub2,
            similarity_score=score,
            flagged=True,
        )


# ─── PolicyView ───────────────────────────────────────────────────────────────

class PolicyViewTest(BaseViewTest):

    def test_get_unauthenticated_returns_401(self):
        resp = self.api.get('/api/plagiarism/policy/')
        self.assertEqual(resp.status_code, 401)

    def test_get_by_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.get('/api/plagiarism/policy/')
        self.assertEqual(resp.status_code, 403)

    def test_get_returns_policy_fields(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/policy/')
        self.assertEqual(resp.status_code, 200)
        for field in ('paste_weight', 'time_weight', 'tab_weight', 'similarity_threshold'):
            self.assertIn(field, resp.data)

    def test_put_updates_field(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.put('/api/plagiarism/policy/', {'paste_weight': 0.50}, format='json')
        self.assertEqual(resp.status_code, 200)
        self.assertAlmostEqual(float(resp.data['paste_weight']), 0.50)

    def test_put_invalidates_redis_cache(self):
        from django.core.cache import cache
        cache.set('plagiarism_policy', {'paste_weight': 0.40}, timeout=60)

        self.api.force_authenticate(user=self.trainer)
        self.api.put('/api/plagiarism/policy/', {'paste_weight': 0.50}, format='json')

        self.assertIsNone(cache.get('plagiarism_policy'))

    def test_put_creates_policy_version(self):
        self.api.force_authenticate(user=self.trainer)
        self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.50, 'change_reason': 'tuning paste sensitivity'},
            format='json',
        )
        version = PolicyVersion.objects.last()
        self.assertIsNotNone(version)
        self.assertEqual(version.change_reason, 'tuning paste sensitivity')
        self.assertEqual(version.changed_by, self.trainer)
        self.assertIn('paste_weight', version.snapshot_before)
        self.assertIn('paste_weight', version.snapshot_after)

    def test_put_snapshot_records_actual_change(self):
        self.api.force_authenticate(user=self.trainer)
        old = float(PlagiarismPolicy.get().paste_weight)
        self.api.put('/api/plagiarism/policy/', {'paste_weight': 0.55}, format='json')
        version = PolicyVersion.objects.last()
        self.assertAlmostEqual(float(version.snapshot_before['paste_weight']), old)
        self.assertAlmostEqual(float(version.snapshot_after['paste_weight']), 0.55)


# ─── BehaviouralFlagListView ──────────────────────────────────────────────────

class BehaviouralFlagListViewTest(BaseViewTest):

    def test_unauthenticated_returns_401(self):
        resp = self.api.get('/api/plagiarism/behavioural/')
        self.assertEqual(resp.status_code, 401)

    def test_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.get('/api/plagiarism/behavioural/')
        self.assertEqual(resp.status_code, 403)

    def test_returns_all_flags(self):
        self._make_behavioural_flag(self.sub_alice2)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/behavioural/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)

    def test_status_filter_pending(self):
        flag = self._make_behavioural_flag(self.sub_alice2)
        self._make_behavioural_flag(self.sub_bob)
        BehaviouralFlag.objects.filter(pk=flag.pk).update(review_status='confirmed')

        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/behavioural/?status=pending')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 1)
        self.assertEqual(resp.data[0]['review_status'], 'pending')


# ─── BehaviouralFlagReviewView ────────────────────────────────────────────────

class BehaviouralFlagReviewViewTest(BaseViewTest):

    def setUp(self):
        super().setUp()
        self.flag = self._make_behavioural_flag(self.sub_alice2)

    def test_review_confirmed_updates_db(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.patch(
            f'/api/plagiarism/behavioural/{self.flag.id}/review/',
            {'review_status': 'confirmed', 'review_note': 'clear case'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.review_status, 'confirmed')
        self.assertEqual(self.flag.review_note, 'clear case')
        self.assertEqual(self.flag.reviewed_by, self.trainer)

    def test_review_dismissed_updates_db(self):
        self.api.force_authenticate(user=self.trainer)
        self.api.patch(
            f'/api/plagiarism/behavioural/{self.flag.id}/review/',
            {'review_status': 'dismissed'},
            format='json',
        )
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.review_status, 'dismissed')

    def test_review_creates_audit_log(self):
        self.api.force_authenticate(user=self.trainer)
        self.api.patch(
            f'/api/plagiarism/behavioural/{self.flag.id}/review/',
            {'review_status': 'confirmed', 'review_note': 'audit test'},
            format='json',
        )
        log = ReviewAuditLog.objects.last()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, 'confirmed')
        self.assertEqual(log.flag_type, 'behavioural')
        self.assertEqual(log.flag_id, self.flag.id)
        self.assertEqual(log.reviewed_by, self.trainer)
        self.assertEqual(log.note, 'audit test')

    def test_invalid_status_returns_400(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.patch(
            f'/api/plagiarism/behavioural/{self.flag.id}/review/',
            {'review_status': 'approved'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)

    def test_missing_flag_returns_404(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.patch(
            '/api/plagiarism/behavioural/99999/review/',
            {'review_status': 'confirmed'},
            format='json',
        )
        self.assertEqual(resp.status_code, 404)


# ─── PlagiarismFlagReviewView ─────────────────────────────────────────────────

class PlagiarismFlagReviewViewTest(BaseViewTest):

    def setUp(self):
        super().setUp()
        self.flag = self._make_similarity_flag(self.sub_alice2, self.sub_bob)

    def test_review_confirmed_updates_db(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.patch(
            f'/api/plagiarism/{self.flag.id}/review/',
            {'review_status': 'confirmed', 'review_note': 'identical code'},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.flag.refresh_from_db()
        self.assertEqual(self.flag.review_status, 'confirmed')
        self.assertEqual(self.flag.reviewed_by, self.trainer)

    def test_review_creates_audit_log(self):
        self.api.force_authenticate(user=self.trainer)
        self.api.patch(
            f'/api/plagiarism/{self.flag.id}/review/',
            {'review_status': 'dismissed'},
            format='json',
        )
        log = ReviewAuditLog.objects.last()
        self.assertEqual(log.flag_type, 'similarity')
        self.assertEqual(log.action, 'dismissed')

    def test_invalid_status_returns_400(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.patch(
            f'/api/plagiarism/{self.flag.id}/review/',
            {'review_status': 'maybe'},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)


# ─── CohortListView ───────────────────────────────────────────────────────────

class CohortListViewTest(BaseViewTest):

    def test_unauthenticated_returns_401(self):
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 401)

    def test_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 403)

    def test_unique_student_count_not_submission_row_count(self):
        # 3 submission rows (alice×2, bob×1) but only 2 unique students
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['total_submissions'], 2)  # unique students, not rows

    def test_ring_count_from_connected_similarity_flags(self):
        # alice ↔ bob forms one ring
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['ring_count'], 1)

    def test_health_green_when_no_flags(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['health'], 'green')  # flag_rate=0 → green

    def test_health_red_when_flag_rate_above_25_percent(self):
        # Flag both students → flag_rate = 2/2 = 1.0 → red
        self._make_behavioural_flag(self.sub_alice2)
        self._make_behavioural_flag(self.sub_bob)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['health'], 'red')


# ─── CohortDetailView ─────────────────────────────────────────────────────────

class CohortDetailViewTest(BaseViewTest):

    def test_missing_exam_returns_404(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/99999/')
        self.assertEqual(resp.status_code, 404)

    def test_returns_exam_info_and_stats(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/cohorts/{self.exam.id}/')
        self.assertEqual(resp.status_code, 200)
        self.assertIn('exam', resp.data)
        self.assertIn('stats', resp.data)
        self.assertIn('students', resp.data)
        self.assertIn('rings', resp.data)
        self.assertEqual(resp.data['exam']['id'], self.exam.id)

    def test_rings_populated_from_similarity_flags(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/cohorts/{self.exam.id}/')
        self.assertEqual(len(resp.data['rings']), 1)
        self.assertEqual(resp.data['rings'][0]['size'], 2)


# ─── RerunExamChecksView ──────────────────────────────────────────────────────

class RerunExamChecksViewTest(BaseViewTest):

    def test_missing_exam_returns_404(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.post('/api/plagiarism/cohorts/99999/rerun/')
        self.assertEqual(resp.status_code, 404)

    def test_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.post(f'/api/plagiarism/cohorts/{self.exam.id}/rerun/')
        self.assertEqual(resp.status_code, 403)

    @patch('plagiarism.tasks.run_exam_plagiarism_check')
    def test_queues_task_and_returns_202(self, mock_task):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.post(f'/api/plagiarism/cohorts/{self.exam.id}/rerun/')
        self.assertEqual(resp.status_code, 202)
        self.assertTrue(resp.data['queued'])
        mock_task.delay.assert_called_once_with(
            self.exam.id,
            triggered_by_id=self.trainer.id,
            trigger='manual_rerun',
        )


# ─── PlagiarismRunListView ────────────────────────────────────────────────────

class PlagiarismRunListViewTest(BaseViewTest):

    def setUp(self):
        super().setUp()
        self.run1 = PlagiarismRun.objects.create(
            exam=self.exam,
            triggered_by=self.trainer,
            trigger='exam_close',
            policy_snapshot={'paste_weight': 0.40},
        )
        self.run2 = PlagiarismRun.objects.create(
            exam=self.exam,
            triggered_by=self.trainer,
            trigger='manual_rerun',
            policy_snapshot={'paste_weight': 0.50},
        )

    def test_returns_all_runs(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/runs/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)

    def test_filters_by_exam_id(self):
        other_exam = Exam.objects.create(
            title='Other Exam', created_by=self.trainer, duration_minutes=60
        )
        PlagiarismRun.objects.create(
            exam=other_exam, trigger='exam_close', policy_snapshot={}
        )
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/runs/?exam_id={self.exam.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data), 2)
        self.assertTrue(all(r['exam_id'] == self.exam.id for r in resp.data))

    def test_response_includes_policy_snapshot(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/runs/?exam_id={self.exam.id}')
        # most recent run first (manual_rerun has paste_weight=0.50)
        latest = resp.data[0]
        self.assertIn('policy_snapshot', latest)
        self.assertAlmostEqual(float(latest['policy_snapshot']['paste_weight']), 0.50)

    def test_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.get('/api/plagiarism/runs/')
        self.assertEqual(resp.status_code, 403)


# ─── MonitoringView ───────────────────────────────────────────────────────────

class MonitoringViewTest(BaseViewTest):

    def test_unauthenticated_returns_401(self):
        resp = self.api.get('/api/plagiarism/monitoring/')
        self.assertEqual(resp.status_code, 401)

    def test_returns_expected_top_level_keys(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/monitoring/')
        self.assertEqual(resp.status_code, 200)
        for key in ('summary', 'signal_effectiveness', 'confidence_breakdown',
                    'coverage', 'drift'):
            self.assertIn(key, resp.data)

    def test_precision_uses_reviewed_denominator_not_total_fired(self):
        # 3 flags: 1 confirmed, 1 dismissed, 1 pending
        # precision = confirmed / (confirmed + dismissed) = 1 / 2 = 0.5
        # NOT 1 / 3 (which would be wrong — pending not reviewed yet)
        f1 = self._make_behavioural_flag(self.sub_alice1)
        f2 = self._make_behavioural_flag(self.sub_alice2)
        f3 = self._make_behavioural_flag(self.sub_bob)
        BehaviouralFlag.objects.filter(pk=f1.pk).update(
            review_status='confirmed', reviewed_by=self.trainer
        )
        BehaviouralFlag.objects.filter(pk=f2.pk).update(
            review_status='dismissed', reviewed_by=self.trainer
        )
        # f3 stays 'pending'

        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/monitoring/')
        precision = resp.data['summary']['behavioural']['precision']
        self.assertAlmostEqual(precision, 0.5)

    def test_precision_none_when_nothing_reviewed(self):
        # No flags at all → precision should be None (can't divide by zero)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/monitoring/')
        self.assertIsNone(resp.data['summary']['behavioural']['precision'])

    def test_coverage_reflects_behavioural_check_done_field(self):
        # Mark alice2 as behaviourally checked
        Submission.objects.filter(pk=self.sub_alice2.pk).update(behavioural_check_done=True)

        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/monitoring/')
        cov = resp.data['coverage']
        self.assertEqual(cov['total_submissions'], 3)
        self.assertEqual(cov['behavioural_done'], 1)
        self.assertAlmostEqual(cov['behavioural_pct'], round(1 / 3 * 100, 1))
