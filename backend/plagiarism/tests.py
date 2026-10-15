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
    'compare_min_risk':     0.35,
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

    # Confidence = confidence that the flag indicates misconduct.
    # More independent signals firing → more suspicious → higher confidence.

    def test_three_signals_gives_high_confidence(self):
        # paste + time + tab all fire (3 signals) → high confidence = most suspicious
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=48,   # 20% of 240 → 1.0
            tab_switch_count=5,
            attempt_number=1,              # no previous attempt → surprise=0.0
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'high')

    def test_four_signals_gives_high_confidence(self):
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=48,
            tab_switch_count=5,
            attempt_number=2, status='passed',
        )
        with patch('plagiarism.tasks.SequenceMatcher') as m:
            m.return_value.ratio.return_value = 0.10   # surprise fires too
            result = compute_behavioural_risk(sub, mock_submission_class('old code'), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'high')

    def test_two_signals_gives_medium_confidence(self):
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=48,   # paste + time fire
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'medium')

    def test_one_signal_gives_low_confidence(self):
        # a single signal is weak evidence → low confidence of misconduct
        sub = make_sub(
            had_paste_event=True, paste_char_count=80, code='x' * 100,
            time_to_complete_seconds=300,  # slow — no time signal
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['confidence'], 'low')

    def test_no_signals_zero_risk_and_low_confidence(self):
        sub = make_sub(
            had_paste_event=False,
            time_to_complete_seconds=300,
            tab_switch_count=0,
            attempt_number=1,
        )
        result = compute_behavioural_risk(sub, mock_submission_class(None), policy=MOCK_POLICY)
        self.assertEqual(result['risk_score'], 0.0)
        self.assertEqual(result['confidence'], 'low')

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
            confidence='high',   # paste + time + tab fired → 3 signals
            paste_score=1.0,
            time_score=0.7,
            snapshot_score=0.5,
            submission_score=0.0,
            review_status=review_status,
        )

    def _make_similarity_flag(self, sub1, sub2, score=0.92, review_status='pending'):
        return PlagiarismFlag.objects.create(
            submission_1=sub1,
            submission_2=sub2,
            similarity_score=score,
            flagged=True,
            review_status=review_status,
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
        # 0.50 + 0.30 + 0.10 + 0.10 = 1.0 — valid weight sum
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.50, 'time_weight': 0.30, 'tab_weight': 0.10, 'submission_weight': 0.10},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertAlmostEqual(float(resp.data['paste_weight']), 0.50)

    def test_put_invalidates_redis_cache(self):
        from django.core.cache import cache
        cache.set('plagiarism_policy', {'paste_weight': 0.40}, timeout=60)

        self.api.force_authenticate(user=self.trainer)
        self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.50, 'time_weight': 0.30, 'tab_weight': 0.10, 'submission_weight': 0.10},
            format='json',
        )

        self.assertIsNone(cache.get('plagiarism_policy'))

    def test_put_creates_policy_version(self):
        self.api.force_authenticate(user=self.trainer)
        self.api.put(
            '/api/plagiarism/policy/',
            {
                'paste_weight': 0.50, 'time_weight': 0.30, 'tab_weight': 0.10, 'submission_weight': 0.10,
                'change_reason': 'tuning paste sensitivity',
            },
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
        self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.55, 'time_weight': 0.30, 'tab_weight': 0.10, 'submission_weight': 0.05},
            format='json',
        )
        version = PolicyVersion.objects.last()
        self.assertAlmostEqual(float(version.snapshot_before['paste_weight']), old)
        self.assertAlmostEqual(float(version.snapshot_after['paste_weight']), 0.55)

    def test_put_weights_summing_above_1_returns_400(self):
        # mirrors the real bad data this fix targets: 0.6/0.3/0.2/0.2 = 1.30
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.6, 'time_weight': 0.3, 'tab_weight': 0.2, 'submission_weight': 0.2},
            format='json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('1.30', str(resp.data))

    def test_put_invalid_weight_sum_leaves_row_unchanged(self):
        self.api.force_authenticate(user=self.trainer)
        before = float(PlagiarismPolicy.get().paste_weight)
        self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.6, 'time_weight': 0.3, 'tab_weight': 0.2, 'submission_weight': 0.2},
            format='json',
        )
        after = float(PlagiarismPolicy.get().paste_weight)
        self.assertAlmostEqual(before, after)

    def test_put_partial_update_validated_against_merged_weights(self):
        # Only paste_weight sent, but merging it with the existing (default) weights
        # pushes the sum above 1.0 — must still be rejected.
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.put('/api/plagiarism/policy/', {'paste_weight': 0.90}, format='json')
        self.assertEqual(resp.status_code, 400)

    def test_put_weights_within_tolerance_of_1_succeeds(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.put(
            '/api/plagiarism/policy/',
            {'paste_weight': 0.4005, 'time_weight': 0.30, 'tab_weight': 0.15, 'submission_weight': 0.15},
            format='json',
        )
        self.assertEqual(resp.status_code, 200)


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
        self.assertEqual(len(resp.data['flags']), 1)

    def test_status_filter_pending(self):
        flag = self._make_behavioural_flag(self.sub_alice2)
        self._make_behavioural_flag(self.sub_bob)
        BehaviouralFlag.objects.filter(pk=flag.pk).update(review_status='confirmed')

        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/behavioural/?status=pending')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['flags']), 1)
        self.assertEqual(resp.data['flags'][0]['review_status'], 'pending')

    def test_includes_policy_weights_from_live_policy(self):
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/behavioural/')
        self.assertEqual(resp.status_code, 200)
        weights = resp.data['policy_weights']
        policy = PlagiarismPolicy.get()
        self.assertAlmostEqual(float(weights['paste']), float(policy.paste_weight))
        self.assertAlmostEqual(float(weights['time']), float(policy.time_weight))
        self.assertAlmostEqual(float(weights['tab']), float(policy.tab_weight))
        self.assertAlmostEqual(float(weights['submission']), float(policy.submission_weight))


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


class MyReviewsViewTest(BaseViewTest):
    """The trainer's verdict and note reach the student; pending flags and the other student don't."""

    def setUp(self):
        super().setUp()
        self.flag = self._make_similarity_flag(self.sub_alice2, self.sub_bob)

    def _review(self, status, note=''):
        self.api.force_authenticate(user=self.trainer)
        self.api.patch(f'/api/plagiarism/{self.flag.id}/review/',
                       {'review_status': status, 'review_note': note}, format='json')

    def _mine(self, user):
        self.api.force_authenticate(user=user)
        return self.api.get('/api/plagiarism/mine/')

    def test_pending_flag_is_hidden(self):
        self.assertEqual(self._mine(self.alice).data, [])

    def test_confirmed_note_reaches_both_students(self):
        self._review('confirmed', 'Rewrite it yourself and resubmit')
        for student, sub in ((self.alice, self.sub_alice2), (self.bob, self.sub_bob)):
            [review] = self._mine(student).data
            self.assertEqual(review['submission_id'], sub.id)
            self.assertEqual(review['review_note'], 'Rewrite it yourself and resubmit')
            self.assertEqual((review['kind'], review['review_status']), ('similarity', 'confirmed'))
            self.assertNotIn('similarity_score', review)

    def test_dismissed_shows_only_with_a_note(self):
        self._review('dismissed')
        self.assertEqual(self._mine(self.alice).data, [])
        self._review('dismissed', 'Fine, but cite sources next time')
        self.assertEqual(len(self._mine(self.alice).data), 1)

    def test_behavioural_review_reaches_only_its_student(self):
        bf = self._make_behavioural_flag(self.sub_bob)
        bf.review_status, bf.review_note = 'confirmed', 'Pasted the whole answer'
        bf.save()
        self.assertEqual([r['kind'] for r in self._mine(self.bob).data], ['behaviour'])
        self.assertEqual(self._mine(self.alice).data, [])

    def test_trainers_get_403(self):
        self.assertEqual(self._mine(self.trainer).status_code, 403)


class MyReviewsPerStudentNotesTest(BaseViewTest):
    """A case decided with a note per student (the case file's "Write separate notes"): each
    student's note rides on their own behaviour flags, a similarity pair carries a note only
    when both of its students get the same one, and a classmate who only matched gets none.
    My results then shows each student their own note, once per exam.

        alice: behaviour flag, pair with bob, pair with carol
        bob:   behaviour flag
        carol: matched only (no behaviour flag of her own)
    """

    def setUp(self):
        super().setUp()
        self.carol = User.objects.create_user(username='carol', password='pass', role='student')
        self.sub_carol = Submission.objects.create(
            student=self.carol, exam=self.exam, question=self.question,
            code='def g(c): return 1', language='python', attempt_number=1, status='passed',
        )
        self.b_alice = self._make_behavioural_flag(self.sub_alice2)
        self.b_bob = self._make_behavioural_flag(self.sub_bob)
        self.pair_ab = self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self.pair_ac = self._make_similarity_flag(self.sub_alice2, self.sub_carol)

    def _decide(self, notes):
        """Confirm every flag the way the case file does: one review request per flag."""
        self.api.force_authenticate(user=self.trainer)
        for path, note in (
            (f'/api/plagiarism/behavioural/{self.b_alice.id}/review/', notes['b_alice']),
            (f'/api/plagiarism/behavioural/{self.b_bob.id}/review/', notes['b_bob']),
            (f'/api/plagiarism/{self.pair_ab.id}/review/', notes['pair_ab']),
            (f'/api/plagiarism/{self.pair_ac.id}/review/', notes['pair_ac']),
        ):
            self.api.patch(path, {'review_status': 'confirmed', 'review_note': note}, format='json')

    def _notes(self, user):
        self.api.force_authenticate(user=user)
        return [r['review_note'] for r in self.api.get('/api/plagiarism/mine/').data if r['review_note']]

    def test_same_note_on_behaviour_and_pair_is_shown_once(self):
        self._decide({'b_alice': 'Same code.', 'b_bob': 'Same code.', 'pair_ab': 'Same code.', 'pair_ac': ''})
        self.assertEqual(self._notes(self.alice), ['Same code.'])
        self.assertEqual(self._notes(self.bob), ['Same code.'])

    def test_different_notes_reach_only_their_own_student(self):
        self._decide({'b_alice': 'You shared it.', 'b_bob': 'You copied it.', 'pair_ab': '', 'pair_ac': ''})
        self.assertEqual(self._notes(self.alice), ['You shared it.'])
        self.assertEqual(self._notes(self.bob), ['You copied it.'])

    def test_matched_only_student_sees_the_decision_but_no_note(self):
        self._decide({'b_alice': 'Same code.', 'b_bob': 'Same code.', 'pair_ab': 'Same code.', 'pair_ac': ''})
        self.api.force_authenticate(user=self.carol)
        [review] = self.api.get('/api/plagiarism/mine/').data
        self.assertEqual((review['kind'], review['review_status'], review['review_note']), ('similarity', 'confirmed', ''))

    def test_each_exam_keeps_its_own_note(self):
        """Dedupe is per exam: the same words on another exam are shown again there."""
        from exams.models import Exam, Question
        other = Exam.objects.create(title='Final', created_by=self.trainer, duration_minutes=60)
        q = Question.objects.create(exam=other, title='Q2', description='d', difficulty='easy', language='python')
        sub = Submission.objects.create(student=self.alice, exam=other, question=q, code='x',
                                        language='python', attempt_number=1, status='passed')
        flag = self._make_behavioural_flag(sub)
        self._decide({'b_alice': 'Same code.', 'b_bob': 'Same code.', 'pair_ab': 'Same code.', 'pair_ac': ''})
        self.api.patch(f'/api/plagiarism/behavioural/{flag.id}/review/',
                       {'review_status': 'confirmed', 'review_note': 'Same code.'}, format='json')
        self.assertEqual(self._notes(self.alice), ['Same code.', 'Same code.'])


# ─── CohortListView ───────────────────────────────────────────────────────────

class CohortListViewTest(BaseViewTest):

    def test_unauthenticated_returns_401(self):
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 401)

    def test_student_returns_403(self):
        self.api.force_authenticate(user=self.alice)
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 403)

    def test_took_is_unique_students_and_total_submissions_is_rows(self):
        # 3 submission rows (alice×2, bob×1) but only 2 unique students
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        self.assertEqual(resp.status_code, 200)
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['took'], 2)
        self.assertEqual(row['total_submissions'], 3)

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
        self.assertEqual(row['health'], 'green')  # flagged_students_rate=0 → green

    def test_health_red_when_flagged_students_rate_at_least_50(self):
        # Flag both students → flagged_students_rate = 2/2 = 100% → red
        self._make_behavioural_flag(self.sub_alice2)
        self._make_behavioural_flag(self.sub_bob)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['flagged_students_rate'], 100.0)
        self.assertEqual(row['health'], 'red')

    def test_flagged_students_counts_behavioural_flags_only(self):
        # A similarity pair alone does not make a student "flagged"
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self._make_behavioural_flag(self.sub_alice1)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get('/api/plagiarism/cohorts/')
        row = next(r for r in resp.data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['flagged_students'], 1)
        self.assertEqual(row['flagged_students_rate'], 50.0)
        self.assertEqual(row['similarity_count'], 1)
        self.assertNotIn('flag_rate', row)


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

    def test_took_is_distinct_students_not_submission_rows(self):
        # fixture: alice has 3 submission rows (2 from setUp + 1 extra below), bob has 1.
        # total_submissions must stay the real row count (4); took must be 2.
        Submission.objects.create(
            student=self.alice, exam=self.exam, question=self.question,
            code='def solve(a): return 2', language='python',
            attempt_number=3, status='passed',
        )
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/cohorts/{self.exam.id}/')
        self.assertEqual(resp.data['stats']['total_submissions'], 4)
        self.assertEqual(resp.data['stats']['took'], 2)

    def test_flagged_students_rate_matches_list_view(self):
        # Flag only alice (1 of 2 students) -> 50%, not 1/4 (submission rows)
        Submission.objects.create(
            student=self.alice, exam=self.exam, question=self.question,
            code='def solve(a): return 2', language='python',
            attempt_number=3, status='passed',
        )
        self._make_behavioural_flag(self.sub_alice2)
        self.api.force_authenticate(user=self.trainer)
        resp = self.api.get(f'/api/plagiarism/cohorts/{self.exam.id}/')
        self.assertEqual(resp.data['stats']['flagged_students_rate'], 50.0)
        row = next(r for r in self.api.get('/api/plagiarism/cohorts/').data if r['exam_id'] == self.exam.id)
        self.assertEqual(row['flagged_students_rate'], resp.data['stats']['flagged_students_rate'])


class CohortDetailCasesTest(BaseViewTest):
    """The exam case file: a case = students linked by (not dismissed) similarity pairs,
    plus each behaviourally flagged student who is in no such group."""

    def setUp(self):
        super().setUp()
        self.carol = User.objects.create_user(username='carol', password='pass', role='student', first_name='Carol')
        self.dave = User.objects.create_user(username='dave', password='pass', role='student')
        self.sub_carol = Submission.objects.create(
            student=self.carol, exam=self.exam, question=self.question,
            code='def g(c): return 1', language='python', attempt_number=1, status='passed',
        )
        self.sub_dave = Submission.objects.create(
            student=self.dave, exam=self.exam, question=self.question,
            code='def h(d): return 1', language='python', attempt_number=1, status='passed',
        )
        self.api.force_authenticate(user=self.trainer)

    def _get(self):
        return self.api.get(f'/api/plagiarism/cohorts/{self.exam.id}/').data

    def test_linked_students_form_one_case_with_their_flags(self):
        pair = self._make_similarity_flag(self.sub_alice2, self.sub_bob, score=0.97)
        b = self._make_behavioural_flag(self.sub_alice2)
        data = self._get()
        self.assertEqual(len(data['cases']), 1)
        case = data['cases'][0]
        self.assertEqual(case['key'], str(min(self.alice.id, self.bob.id)))
        self.assertEqual(case['number'], 1)
        self.assertEqual({m['student_id'] for m in case['members']}, {self.alice.id, self.bob.id})
        self.assertEqual([p['id'] for p in case['pairs']], [pair.id])
        self.assertEqual(case['pairs'][0]['similarity_score'], 0.97)
        self.assertEqual([f['id'] for f in case['behavioural']], [b.id])
        self.assertEqual(case['behavioural'][0]['signals_triggered'], [])
        self.assertEqual(case['pending'], 2)
        self.assertEqual(case['status'], 'pending')
        self.assertEqual(case['max_similarity'], 0.97)
        self.assertEqual(case['max_risk'], 75)
        self.assertEqual(data['stats']['cases_to_decide'], 1)

    def test_member_carries_first_name(self):
        self._make_similarity_flag(self.sub_carol, self.sub_dave)
        members = {m['username']: m for m in self._get()['cases'][0]['members']}
        self.assertEqual(members['carol']['first_name'], 'Carol')
        self.assertEqual(members['dave']['first_name'], '')

    def test_chain_of_pairs_is_one_case(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self._make_similarity_flag(self.sub_bob, self.sub_carol)
        cases = self._get()['cases']
        self.assertEqual(len(cases), 1)
        self.assertEqual(len(cases[0]['members']), 3)
        self.assertEqual(len(cases[0]['pairs']), 2)

    def test_behavioural_flag_outside_any_pair_is_a_single_student_case(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self._make_behavioural_flag(self.sub_carol)
        cases = self._get()['cases']
        self.assertEqual(len(cases), 2)
        solo = next(c for c in cases if len(c['members']) == 1)
        self.assertEqual(solo['key'], str(self.carol.id))
        self.assertEqual(solo['pairs'], [])
        self.assertEqual(solo['max_similarity'], 0)

    def test_dismissed_pair_does_not_link_students(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob, review_status='dismissed')
        self._make_similarity_flag(self.sub_bob, self.sub_carol)
        cases = self._get()['cases']
        open_case = next(c for c in cases if c['status'] == 'pending')
        self.assertEqual({m['student_id'] for m in open_case['members']}, {self.bob.id, self.carol.id})
        self.assertFalse(any(self.alice.id in {m['student_id'] for m in c['members']} for c in cases))

    def test_fully_dismissed_case_stays_listed_as_decided(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob, review_status='dismissed')
        self._make_behavioural_flag(self.sub_alice2, review_status='dismissed')
        data = self._get()
        self.assertEqual(len(data['cases']), 1)
        case = data['cases'][0]
        self.assertEqual(case['status'], 'dismissed')
        self.assertEqual(case['pending'], 0)
        self.assertEqual(case['key'], str(min(self.alice.id, self.bob.id)))
        self.assertEqual(data['stats']['cases_to_decide'], 0)

    def test_decided_case_outcome(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob, review_status='confirmed')
        self._make_behavioural_flag(self.sub_alice2, review_status='dismissed')
        case = self._get()['cases'][0]
        self.assertEqual(case['status'], 'mixed')
        self._make_behavioural_flag(self.sub_carol, review_status='confirmed')
        solo = next(c for c in self._get()['cases'] if c['key'] == str(self.carol.id))
        self.assertEqual(solo['status'], 'confirmed')

    def test_pending_cases_first_then_by_severity(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob, score=0.85)
        self._make_similarity_flag(self.sub_carol, self.sub_dave, score=0.99, review_status='confirmed')
        b = self._make_behavioural_flag(self.sub_carol, review_status='confirmed')
        cases = self._get()['cases']
        self.assertEqual(cases[0]['status'], 'pending')
        self.assertEqual(cases[1]['status'], 'confirmed')
        # numbers follow severity and don't move when a case is decided
        self.assertEqual(cases[1]['number'], 1)
        self.assertEqual(cases[0]['number'], 2)
        self.assertEqual(b.review_status, 'confirmed')

    def test_students_and_rings_link_to_their_case(self):
        self._make_similarity_flag(self.sub_alice2, self.sub_bob)
        self._make_behavioural_flag(self.sub_carol)
        data = self._get()
        key = str(min(self.alice.id, self.bob.id))
        rows = {s['student_id']: s for s in data['students']}
        self.assertEqual(rows[self.alice.id]['case'], key)
        self.assertEqual(rows[self.carol.id]['case'], str(self.carol.id))
        self.assertEqual(data['rings'][0]['case'], key)

    def test_exam_header_fields(self):
        from django.utils import timezone
        done = timezone.now()
        PlagiarismRun.objects.create(exam=self.exam, status='completed', completed_at=done)
        PlagiarismRun.objects.create(exam=self.exam, status='running')
        exam = self._get()['exam']
        self.assertEqual(exam['status'], 'draft')
        self.assertEqual(exam['question_count'], 1)
        self.assertEqual(exam['duration_minutes'], 60)
        self.assertEqual(exam['last_checked_at'], done.isoformat())

    def test_never_checked_exam_has_no_last_check(self):
        self.assertIsNone(self._get()['exam']['last_checked_at'])


# ─── RerunExamChecksView ──────────────────────────────────────────────────────

class RerunExamChecksViewTest(BaseViewTest):

    @patch('plagiarism.tasks.run_question_plagiarism_check')
    def test_manual_run_is_not_staggered_but_exam_close_is(self, q_task):
        from plagiarism.tasks import run_exam_plagiarism_check
        Question.objects.create(exam=self.exam, title='Q2', description='d', language='python')
        run_exam_plagiarism_check(self.exam.id, trigger='manual_rerun', notify=False)
        self.assertEqual([c.kwargs['countdown'] for c in q_task.apply_async.call_args_list], [0, 0])
        q_task.reset_mock()
        run_exam_plagiarism_check(self.exam.id, trigger='exam_close', notify=False)
        self.assertEqual([c.kwargs['countdown'] for c in q_task.apply_async.call_args_list], [0, 30])

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


# ─── Phase 2 suspect selection ────────────────────────────────────────────────

class Phase2SuspectSelectionTest(TestCase):
    """
    run_question_plagiarism_check compares students whose risk is at least the
    policy's compare_min_risk (0.35), or who fired 3+ signals.

    Fixture: two identical-code pairs on one question.
      suspect3 (3 signals)              shares code A with source_a (no flag)
      suspect1 (1 signal: fast, 0.30)   shares code B with source_b (no flag)
    suspect1 is flagged (0.30 > 0.20) but below 0.35, so only the
    suspect3 ↔ source_a pair may be flagged.
    """
    CODE_A = (
        'def solve(nums):\n'
        '    total = 0\n'
        '    for n in nums:\n'
        '        if n % 2 == 0:\n'
        '            total += n * n\n'
        '    return total\n'
    )
    CODE_B = (
        'def solve(text):\n'
        '    words = text.split()\n'
        '    return " ".join(reversed(words)).upper().strip()\n'
    )

    def setUp(self):
        from plagiarism.tasks import run_behavioural_check
        trainer = User.objects.create_user(username='t', password='p', role='trainer')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60)
        self.question = Question.objects.create(
            exam=exam, title='Q', description='d', difficulty='medium', language='python',
        )

        def sub(name, code, **behaviour):
            student = User.objects.create_user(username=name, password='p', role='student')
            return Submission.objects.create(
                student=student, exam=exam, question=self.question, code=code,
                language='python', attempt_number=1, status='passed', **behaviour,
            )

        self.suspect3 = sub('suspect3', self.CODE_A, had_paste_event=True,
                            paste_char_count=len(self.CODE_A), time_to_complete_seconds=30,
                            tab_switch_count=6)
        self.source_a = sub('source_a', self.CODE_A, time_to_complete_seconds=600)
        self.suspect1 = sub('suspect1', self.CODE_B, time_to_complete_seconds=30)
        self.source_b = sub('source_b', self.CODE_B, time_to_complete_seconds=600)

        self.policy = patch('plagiarism.tasks.get_policy', return_value=MOCK_POLICY)
        self.policy.start()
        self.addCleanup(self.policy.stop)
        for s in (self.suspect3, self.source_a, self.suspect1, self.source_b):
            run_behavioural_check(s.id)

    def test_fixture_confidences_follow_signal_count(self):
        self.assertEqual(BehaviouralFlag.objects.get(submission=self.suspect3).confidence, 'high')
        weak = BehaviouralFlag.objects.get(submission=self.suspect1)
        self.assertEqual((weak.confidence, weak.risk_score), ('low', 0.3))
        self.assertFalse(BehaviouralFlag.objects.filter(
            submission__in=[self.source_a, self.source_b]).exists())

    @patch('ai.tasks.explain_plagiarism')
    @patch('codemas.notifications.notify_plagiarism_flagged')
    def test_compares_high_confidence_suspects_only(self, _notify, _explain):
        from plagiarism.tasks import run_question_plagiarism_check
        run_question_plagiarism_check(self.question.id)

        pairs = {
            frozenset((f.submission_1_id, f.submission_2_id))
            for f in PlagiarismFlag.objects.filter(flagged=True)
        }
        self.assertIn(frozenset((self.suspect3.id, self.source_a.id)), pairs)
        self.assertNotIn(frozenset((self.suspect1.id, self.source_b.id)), pairs)

    @patch('ai.tasks.explain_plagiarism')
    @patch('codemas.notifications.notify_plagiarism_flagged')
    def test_notify_false_flags_pairs_without_email_or_ai(self, notify, explain):
        # seed_data runs the real Phase 2 synchronously but must not email
        # trainers or queue LLM explanations for demo data
        from plagiarism.tasks import run_question_plagiarism_check
        run_question_plagiarism_check(self.question.id, notify=False)

        self.assertTrue(PlagiarismFlag.objects.filter(
            submission_1__in=[self.suspect3, self.source_a],
            submission_2__in=[self.suspect3, self.source_a]).exists())
        notify.assert_not_called()
        explain.delay.assert_not_called()

    @patch('ai.tasks.explain_plagiarism')
    @patch('codemas.notifications.notify_plagiarism_flagged')
    def test_notify_defaults_to_on_for_production(self, notify, explain):
        from plagiarism.tasks import run_question_plagiarism_check
        run_question_plagiarism_check(self.question.id)
        notify.assert_called_once()
        explain.delay.assert_called_once()

    @patch('ai.tasks.explain_plagiarism')
    @patch('codemas.notifications.notify_plagiarism_flagged')
    def test_student_with_several_attempts_is_compared_once(self, _notify, _explain):
        # Submission.Meta.ordering (-submitted_at) must not leak into the
        # DISTINCT student query: a multi-attempt student would otherwise be
        # vectorised several times and paired with themselves.
        from datetime import timedelta
        from django.utils import timezone
        from plagiarism.tasks import run_question_plagiarism_check
        retry = Submission.objects.create(
            student=self.suspect3.student, exam=self.suspect3.exam, question=self.question,
            code='def solve(nums):\n    return 0\n', language='python',
            attempt_number=2, status='failed',
        )
        Submission.objects.filter(pk=retry.pk).update(submitted_at=timezone.now() + timedelta(minutes=5))

        run_question_plagiarism_check(self.question.id, notify=False)

        flags = list(PlagiarismFlag.objects.all())
        self.assertFalse([f for f in flags if f.submission_1_id == f.submission_2_id])
        pairs = [frozenset((f.submission_1_id, f.submission_2_id)) for f in flags]
        self.assertEqual(len(pairs), len(set(pairs)))
        self.assertEqual(set(pairs), {frozenset((self.suspect3.id, self.source_a.id))})

    @patch('ai.tasks.explain_plagiarism')
    @patch('codemas.notifications.notify_plagiarism_flagged')
    def test_exam_close_entry_point_passes_notify_false_through(self, notify, explain):
        # seed_data runs the real exam-close task eagerly with notify=False:
        # it must record a completed run and flag the pair without emailing
        # trainers or queueing LLM explanations
        from codemas.celery import app
        from plagiarism.models import PlagiarismRun
        from plagiarism.tasks import run_exam_plagiarism_check
        saved = app.conf.task_always_eager
        app.conf.task_always_eager = True
        self.addCleanup(setattr, app.conf, 'task_always_eager', saved)

        run_exam_plagiarism_check(self.question.exam_id, trigger='exam_close', notify=False)

        run = PlagiarismRun.objects.get(exam_id=self.question.exam_id)
        self.assertEqual((run.trigger, run.status, run.questions_done, run.s_flags_total),
                         ('exam_close', 'completed', 1, 1))
        self.assertTrue(PlagiarismFlag.objects.filter(
            submission_1__in=[self.suspect3, self.source_a],
            submission_2__in=[self.suspect3, self.source_a]).exists())
        notify.assert_not_called()
        explain.delay.assert_not_called()

    @patch('plagiarism.tasks.run_question_plagiarism_check')
    def test_exam_close_entry_point_notifies_by_default(self, question_task):
        from plagiarism.tasks import run_exam_plagiarism_check
        run_exam_plagiarism_check(self.question.exam_id)
        call = question_task.apply_async.call_args
        self.assertEqual(call.kwargs['args'][0], self.question.id)
        self.assertEqual(call.kwargs['kwargs'], {'notify': True})


class PolicyDecidesWhoIsComparedTest(TestCase):
    """The trainer's weights decide who is compared (risk >= compare_min_risk), and a
    rerun under a stricter policy clears flags nobody has acted on."""
    CODE = (
        'def solve(nums):\n'
        '    best = nums[0]\n'
        '    for n in nums[1:]:\n'
        '        if n > best:\n'
        '            best = n\n'
        '    return best * 2\n'
    )

    def setUp(self):
        trainer = User.objects.create_user(username='t', password='p', role='trainer')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60)
        self.question = Question.objects.create(
            exam=exam, title='Q', description='d', difficulty='medium', language='python')
        self.exam = exam

    def sub(self, name, **behaviour):
        student = User.objects.create_user(username=name, password='p', role='student')
        return Submission.objects.create(
            student=student, exam=self.exam, question=self.question, code=self.CODE,
            language='python', attempt_number=1, status='passed',
            **{'time_to_complete_seconds': 600, **behaviour})

    def run_checks(self, policy):
        from plagiarism.tasks import run_behavioural_check, run_question_plagiarism_check
        with patch('plagiarism.tasks.get_policy', return_value=policy), \
                patch('ai.tasks.explain_plagiarism'), \
                patch('codemas.notifications.notify_plagiarism_flagged'):
            for s in Submission.objects.filter(question=self.question):
                run_behavioural_check(s.id)
            run_question_plagiarism_check(self.question.id, notify=False)

    def pairs(self):
        return {frozenset((f.submission_1_id, f.submission_2_id)) for f in PlagiarismFlag.objects.all()}

    def test_rerun_after_a_new_best_submission_updates_the_reviewed_pair(self):
        # trainer runs the check on a live exam and confirms the pair; the paster then passes
        # a later attempt. The exam-close run must update that pair, not add a pending one.
        paster = self.sub('paster', had_paste_event=True, paste_char_count=len(self.CODE))
        Submission.objects.filter(pk=paster.pk).update(status='failed')
        source = self.sub('source')
        self.run_checks(MOCK_POLICY)
        flag = PlagiarismFlag.objects.get()
        PlagiarismFlag.objects.filter(pk=flag.pk).update(review_status='confirmed', review_note='copied')
        later = Submission.objects.create(
            student=paster.student, exam=self.exam, question=self.question, code=self.CODE, language='python',
            attempt_number=2, status='passed', time_to_complete_seconds=600,
            had_paste_event=True, paste_char_count=len(self.CODE))
        self.run_checks(MOCK_POLICY)
        flag = PlagiarismFlag.objects.get()
        self.assertEqual((flag.review_status, flag.review_note), ('confirmed', 'copied'))
        self.assertEqual({flag.submission_1_id, flag.submission_2_id}, {later.id, source.id})

    def test_a_pair_stored_in_either_order_is_one_pair(self):
        paster = self.sub('paster', had_paste_event=True, paste_char_count=len(self.CODE))
        source = self.sub('source')
        lower, higher = sorted((paster, source), key=lambda s: s.student_id)
        PlagiarismFlag.objects.create(submission_1=higher, submission_2=lower, similarity_score=0.9,
                                      flagged=True, review_status='dismissed')
        self.run_checks(MOCK_POLICY)
        flag = PlagiarismFlag.objects.get()
        self.assertEqual(flag.review_status, 'dismissed')
        self.assertEqual((flag.submission_1_id, flag.submission_2_id), (lower.id, higher.id))

    def test_heavy_paste_alone_is_compared(self):
        # 100% pasted, normal time, no tab switches: 1 signal, risk 0.40
        paster = self.sub('paster', had_paste_event=True, paste_char_count=len(self.CODE))
        source = self.sub('source')
        self.run_checks(MOCK_POLICY)
        flag = BehaviouralFlag.objects.get(submission=paster)
        self.assertEqual((flag.confidence, flag.risk_score), ('low', 0.4))
        self.assertIn(frozenset((paster.id, source.id)), self.pairs())

    def test_raising_a_weight_brings_a_student_into_the_comparison(self):
        switcher = self.sub('switcher', tab_switch_count=6)   # tab signal only
        source = self.sub('source')
        self.run_checks(MOCK_POLICY)                         # tab weight 0.15: risk 0.15, not flagged
        self.assertFalse(self.pairs())
        stricter = {**MOCK_POLICY, 'tab_weight': 0.45, 'paste_weight': 0.25, 'time_weight': 0.15}
        self.run_checks(stricter)                            # rerun: risk 0.45, compared
        self.assertIn(frozenset((switcher.id, source.id)), self.pairs())

    def test_stricter_rerun_clears_only_unreviewed_flags(self):
        from support.models import DisputeRequest
        fast = [self.sub(f'fast{i}', time_to_complete_seconds=30) for i in range(3)]  # risk 0.30 each
        self.run_checks(MOCK_POLICY)
        flags = {f.submission_id: f for f in BehaviouralFlag.objects.all()}
        self.assertEqual(set(flags), {s.id for s in fast})
        BehaviouralFlag.objects.filter(submission=fast[1]).update(review_status='confirmed')
        DisputeRequest.objects.create(student=fast[2].student, flag_type='behavioural',
                                      flag_id=flags[fast[2].id].id, student_note='n')
        self.run_checks({**MOCK_POLICY, 'min_risk_score': 0.50})
        self.assertEqual(set(BehaviouralFlag.objects.values_list('submission_id', flat=True)),
                         {fast[1].id, fast[2].id})          # pending one cleared; reviewed and disputed kept
