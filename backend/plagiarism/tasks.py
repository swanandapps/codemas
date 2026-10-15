import ast
import re
from difflib import SequenceMatcher
from celery import shared_task
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.apps import apps
from django.core.cache import cache


# ─── Policy ───────────────────────────────────────────────────────────────────

def get_policy() -> dict:
    """
    Returns the active PlagiarismPolicy as a plain dict.
    Cached in Redis; invalidated immediately when a trainer saves a change.
    Falls back to DB on cache miss (first call, or after invalidation).
    """
    p = cache.get('plagiarism_policy')
    if p is None:
        PlagiarismPolicy = apps.get_model('plagiarism', 'PlagiarismPolicy')
        obj = PlagiarismPolicy.get()
        p = {
            'paste_weight':         obj.paste_weight,
            'time_weight':          obj.time_weight,
            'tab_weight':           obj.tab_weight,
            'submission_weight':    obj.submission_weight,
            'min_risk_score':       obj.min_risk_score,
            'similarity_threshold': obj.similarity_threshold,
            'compare_min_risk':     obj.compare_min_risk,
            'easy_baseline_s':      obj.easy_baseline_s,
            'medium_baseline_s':    obj.medium_baseline_s,
            'hard_baseline_s':      obj.hard_baseline_s,
        }
        cache.set('plagiarism_policy', p, timeout=60)
    return p


# ─── Difficulty Baselines ─────────────────────────────────────────────────────

# Fallback defaults — only used if PlagiarismPolicy row doesn't exist yet.
DIFFICULTY_BASELINE_SECONDS = {
    'easy':   90,
    'medium': 240,
    'hard':   480,
}


# ─── Behavioural Signals (each returns 0.0–1.0) ──────────────────────────────

def paste_signal(submission) -> tuple[float, list[str]]:
    """
    Measures how much of the final code arrived via paste events.

    Why ratio not absolute count: a 200-char solution pasted entirely is
    more suspicious than 200 chars pasted out of a 1000-char solution.
    The ratio normalises for problem size.
    """
    signals = []
    if not submission.had_paste_event or not submission.code:
        return 0.0, signals

    paste_ratio = submission.paste_char_count / max(len(submission.code), 1)
    shown = min(paste_ratio, 1.0)  # paste-then-delete can push the ratio past 100%; never show that

    if paste_ratio >= 0.7:
        signals.append(
            f"Pasted {int(shown * 100)}% of final code "
            f"({submission.paste_char_count} chars)"
        )
        return 1.0, signals
    elif paste_ratio >= 0.5:
        signals.append(
            f"Pasted {int(shown * 100)}% of final code "
            f"({submission.paste_char_count} chars)"
        )
        return 0.7, signals
    elif paste_ratio >= 0.3:
        signals.append(
            f"Paste detected ({int(shown * 100)}% of code)"
        )
        return 0.3, signals

    return 0.0, signals


def time_signal(submission, baselines: dict | None = None) -> tuple[float, list[str]]:
    """
    Compares time_to_complete against the difficulty baseline.

    A student who solves a hard problem in 45 seconds almost certainly
    didn't write it themselves. We don't flag slow students — only
    suspiciously fast ones.

    time_to_complete_seconds is sent by the frontend as
    (exam_duration - time_remaining) at the moment of submission.
    """
    signals = []
    if not submission.time_to_complete_seconds:
        return 0.0, signals

    effective = baselines or DIFFICULTY_BASELINE_SECONDS
    difficulty = getattr(submission.question, 'difficulty', 'medium')
    baseline = effective.get(difficulty, effective.get('medium', 240))
    elapsed = submission.time_to_complete_seconds

    # how fast relative to minimum expected time (lower = more suspicious)
    ratio = elapsed / baseline

    def fmt_time(s):
        m, sec = divmod(s, 60)
        return f"{m}m {sec}s" if m else f"{sec}s"

    # elapsed is time since the student started, at this attempt — passed or not
    fast = (f"Submitted {fmt_time(elapsed)} after starting, on a{'n' if difficulty[:1] in 'aeiou' else ''} "
            f"{difficulty} problem (typical: {fmt_time(baseline)})")
    if ratio <= 0.2:
        signals.append(fast)
        return 1.0, signals
    elif ratio <= 0.4:
        signals.append(fast)
        return 0.7, signals
    elif ratio <= 0.6:
        signals.append(
            f"Submitted faster than expected: {fmt_time(elapsed)} after starting"
        )
        return 0.3, signals

    return 0.0, signals



def tab_switch_signal(submission) -> tuple[float, list[str]]:
    """
    Counts how many times the student left the exam tab during this question.

    Tab switching alone isn't proof of cheating — students look things up.
    But combined with paste or time signals it becomes meaningful.
    Thresholds are intentionally lenient: 1-2 switches is normal, 5+ is suspicious.
    """
    signals = []
    count = submission.tab_switch_count or 0

    if count >= 5:
        signals.append(f"Left exam tab {count} times during this question")
        return 1.0, signals
    elif count >= 3:
        signals.append(f"Left exam tab {count} times during this question")
        return 0.5, signals
    elif count >= 1:
        return 0.2, signals

    return 0.0, signals


def submission_surprise_signal(submission, Submission) -> tuple[float, list[str]]:
    """
    Compares current submission code against the student's own previous
    attempt for the same question.

    Genuine debugging looks like: small targeted edits, same structure,
    fixing one thing at a time.

    Copying looks like: previous attempt abandoned entirely, completely
    different code appears with a passing result.

    SequenceMatcher.ratio() gives a value 0–1 where 1.0 = identical,
    0.0 = nothing in common. We flag when the ratio is very low AND
    the new attempt passes (sudden perfection from unrelated code).
    """
    signals = []

    # get the immediately previous attempt by the same student for this question
    previous = (
        Submission.objects
        .filter(
            student=submission.student,
            question=submission.question,
            attempt_number=submission.attempt_number - 1,
        )
        .first()
    )

    if not previous or not previous.code or not submission.code:
        return 0.0, signals  # no previous attempt to compare against

    similarity = SequenceMatcher(None, previous.code, submission.code).ratio()

    if similarity < 0.25 and submission.status == 'passed':
        # completely different code AND it passed — very suspicious
        signals.append(
            f"Attempt {submission.attempt_number} code is completely different "
            f"from attempt {previous.attempt_number} ({int(similarity * 100)}% similar) "
            f"but suddenly passes"
        )
        return 1.0, signals
    elif similarity < 0.4:
        signals.append(
            f"Large code change between attempt {previous.attempt_number} "
            f"and attempt {submission.attempt_number} "
            f"({int(similarity * 100)}% code similarity)"
        )
        return 0.6, signals
    elif similarity < 0.55:
        return 0.2, signals

    return 0.0, signals


# ─── Combined Scorer ──────────────────────────────────────────────────────────

def compute_behavioural_risk(submission, Submission, policy: dict | None = None) -> dict:
    """
    Runs four signals and combines them into a single risk score.
    Weights and baselines come from PlagiarismPolicy (via Redis cache).
    Confidence = confidence that the flag indicates misconduct, based on how
    many independent signals fired (not the total score):
      high   = 3+ signals (most suspicious)
      medium = 2 signals
      low    = 0-1 signals
    """
    p = policy or get_policy()
    baselines = {
        'easy':   p['easy_baseline_s'],
        'medium': p['medium_baseline_s'],
        'hard':   p['hard_baseline_s'],
    }

    p_score,   p_signals   = paste_signal(submission)
    t_score,   t_signals   = time_signal(submission, baselines)
    tab_score, tab_signals = tab_switch_signal(submission)
    sub_score, sub_signals = submission_surprise_signal(submission, Submission)

    risk_score = round(
        (p['paste_weight']      * p_score) +
        (p['time_weight']       * t_score) +
        (p['tab_weight']        * tab_score) +
        (p['submission_weight'] * sub_score),
        4
    )

    all_signals = p_signals + t_signals + tab_signals + sub_signals
    signals_fired = sum(1 for s in [p_score, t_score, tab_score, sub_score] if s > 0)

    if signals_fired >= 3:
        confidence = 'high'    # strong evidence of misconduct — most suspicious
    elif signals_fired == 2:
        confidence = 'medium'
    else:
        confidence = 'low'     # a single signal is weak evidence on its own

    return {
        'risk_score':        risk_score,
        'confidence':        confidence,
        'paste_score':       p_score,
        'time_score':        t_score,
        'snapshot_score':    tab_score,   # field reused for tab_switch — avoids new migration
        'submission_score':  sub_score,
        'signals_triggered': all_signals,
    }


# ─── Per-Submission Task (O(1)) ───────────────────────────────────────────────

@shared_task
def run_behavioural_check(submission_id: int):
    """
    Runs immediately after every submission. Cost is O(1) — we only
    look at this student's own data, no comparison with others needed.

    Only stores a BehaviouralFlag if risk_score > 0.2 to avoid
    cluttering the DB with noise for students who show no signals.
    """
    Submission = apps.get_model('submissions', 'Submission')
    BehaviouralFlag = apps.get_model('plagiarism', 'BehaviouralFlag')

    try:
        submission = Submission.objects.select_related(
            'student', 'question', 'exam'
        ).get(id=submission_id)
    except Submission.DoesNotExist:
        return

    policy = get_policy()
    result = compute_behavioural_risk(submission, Submission, policy)

    Submission.objects.filter(pk=submission_id).update(behavioural_check_done=True)

    if result['risk_score'] <= policy['min_risk_score']:
        # below threshold — not worth storing. On a rerun under a different policy, a
        # flag nobody has acted on no longer stands; a reviewed or disputed one keeps
        # the trainer's decision.
        stale = BehaviouralFlag.objects.filter(submission=submission, review_status='pending')
        if stale.exists():
            from django.db.models import Q
            from support.models import DisputeRequest
            disputed = DisputeRequest.objects.filter(   # a legacy per-flag dispute, or an appeal on the exam
                Q(flag_type='behavioural', flag_id__in=stale.values_list('id', flat=True))
                | Q(student_id=submission.student_id, exam_id=submission.exam_id)).exists()
            if not disputed:
                stale.delete()
        print(f'[BEHAVIOURAL] {submission.student.username} Q{submission.question_id} '
              f'— clean (score={result["risk_score"]:.2f})')
        return

    # upsert — if re-run, update with latest scores
    BehaviouralFlag.objects.update_or_create(
        submission=submission,
        defaults=result,
    )

    print(
        f'[BEHAVIOURAL] FLAGGED {submission.student.username} | '
        f'Q{submission.question_id} | attempt {submission.attempt_number} | '
        f'confidence={result["confidence"]} score={result["risk_score"]:.2f} | '
        f'signals: {result["signals_triggered"]}'
    )


# ─── Code Normalization (for cross-comparison) ───────────────────────────────

class VariableNormalizer(ast.NodeTransformer):
    """
    Replaces all user-defined names with VAR_0, VAR_1... before TF-IDF.
    Only runs on HIGH-risk students identified by behavioural scoring.
    """
    BUILTINS = {
        'print', 'len', 'range', 'enumerate', 'zip', 'map', 'filter',
        'sorted', 'reversed', 'list', 'dict', 'set', 'tuple', 'str',
        'int', 'float', 'bool', 'type', 'isinstance', 'append', 'None',
        'True', 'False', 'self', 'cls',
    }

    def __init__(self):
        self.mapping = {}
        self.counter = 0

    def _normalize(self, name):
        if name in self.BUILTINS:
            return name
        if name not in self.mapping:
            self.mapping[name] = f'VAR_{self.counter}'
            self.counter += 1
        return self.mapping[name]

    def visit_Name(self, node):
        node.id = self._normalize(node.id)
        return node

    def visit_arg(self, node):
        node.arg = self._normalize(node.arg)
        return node

    def visit_FunctionDef(self, node):
        node.name = self._normalize(node.name)
        self.generic_visit(node)
        return node


def normalize_python(code: str) -> str:
    code = re.sub(r'#.*', '', code)
    code = '\n'.join(line for line in code.splitlines() if line.strip())
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
                if (node.body
                        and isinstance(node.body[0], ast.Expr)
                        and isinstance(node.body[0].value, ast.Constant)
                        and isinstance(node.body[0].value.value, str)):
                    node.body.pop(0)
        normalizer = VariableNormalizer()
        normalized_tree = normalizer.visit(tree)
        ast.fix_missing_locations(normalized_tree)
        return ast.unparse(normalized_tree)
    except SyntaxError:
        return code


def normalize_javascript(code: str) -> str:
    code = re.sub(r'//.*', '', code)
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    code = '\n'.join(line for line in code.splitlines() if line.strip())
    JS_KEYWORDS = {
        'var', 'let', 'const', 'function', 'return', 'if', 'else', 'for',
        'while', 'of', 'in', 'new', 'this', 'true', 'false', 'null',
        'undefined', 'console', 'log', 'length', 'push', 'pop',
        'map', 'filter', 'reduce', 'forEach', 'indexOf', 'includes',
    }
    mapping = {}
    counter = 0

    def replace_name(match):
        nonlocal counter
        name = match.group(0)
        if name in JS_KEYWORDS:
            return name
        if name not in mapping:
            mapping[name] = f'VAR_{counter}'
            counter += 1
        return mapping[name]

    return re.sub(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b', replace_name, code)


def normalize_code(code: str, language: str) -> str:
    if language == 'python':
        return normalize_python(code)
    elif language == 'javascript':
        return normalize_javascript(code)
    return code


# ─── Batch Cross-Comparison (only HIGH-risk students) ────────────────────────

@shared_task
def run_exam_plagiarism_check(exam_id: int, triggered_by_id: int = None, trigger: str = 'exam_close',
                              notify: bool = True):
    """
    Triggered when exam closes. Two phases run sequentially in this task:

    Phase 1 (here): behavioural check for every submission in the exam.
      Running post-exam gives full context — cross-question patterns are
      visible and all attempt data is final. O(N) where N = submissions.

    Phase 2 (per-question sub-tasks): TF-IDF cross-compare, restricted to
      HIGH-confidence behavioural suspects. Phase 1 must complete first so
      the confidence filters in Phase 2 have data to work with.

    HIGH confidence = 3+ behavioural signals fired, i.e. the students most
    likely to have committed misconduct.

    Why only HIGH confidence in Phase 2: reduces O(N²) all-pairs to
    O(K·N) where K << N. For 200 students with 10 suspects: 2,000 checks
    instead of 19,900. Same signal quality, ~10x less compute.

    notify is passed through to every per-question task (see
    run_question_plagiarism_check). seed_data passes notify=False and runs
    this task eagerly so demo data gets the real exam-close run without
    emailing trainers or calling the LLM.
    """
    from django.db.models import Avg, Count
    from django.utils import timezone
    Exam = apps.get_model('exams', 'Exam')
    Submission = apps.get_model('submissions', 'Submission')
    PlagiarismRun = apps.get_model('plagiarism', 'PlagiarismRun')

    try:
        exam = Exam.objects.get(id=exam_id)
    except Exam.DoesNotExist:
        print(f'[PLAGIARISM] exam {exam_id} not found')
        return

    print(f'[PLAGIARISM] batch check started — exam: {exam.title}')

    # Snapshot current policy
    policy = get_policy()

    # Collect exam performance context from submissions
    all_subs = Submission.objects.filter(exam=exam)
    total_submissions = all_subs.count()
    unique_students   = all_subs.values('student_id').distinct().count()

    passed_student_ids = set(all_subs.filter(status='passed').values_list('student_id', flat=True))
    pass_rate = round(len(passed_student_ids) / unique_students, 4) if unique_students else None

    agg = all_subs.aggregate(
        avg_exec=Avg('execution_time_ms'),
        avg_time_remaining=Avg('time_remaining_seconds'),
    )
    avg_solve = all_subs.filter(status='passed').aggregate(avg=Avg('time_to_complete_seconds'))['avg']
    avg_attempts = all_subs.values('student_id', 'question_id').annotate(c=Count('id')).aggregate(avg=Avg('c'))['avg']

    questions_count = exam.questions.count()

    # Create run record
    run = PlagiarismRun.objects.create(
        exam_id=exam_id,
        triggered_by_id=triggered_by_id,
        trigger=trigger,
        policy_snapshot=policy,
        total_submissions=total_submissions,
        unique_students=unique_students,
        pass_rate=pass_rate,
        avg_execution_ms=round(agg['avg_exec']) if agg['avg_exec'] else None,
        avg_solve_time_s=round(avg_solve) if avg_solve else None,
        avg_attempts=round(avg_attempts, 1) if avg_attempts else None,
        avg_time_remaining=round(agg['avg_time_remaining']) if agg['avg_time_remaining'] else None,
        questions_total=questions_count,
    )

    # Phase 1 — run synchronously so flags exist before Phase 2 queries them
    submissions = all_subs.select_related('student', 'question')
    print(f'[PLAGIARISM] Phase 1 — behavioural check for {total_submissions} submissions')
    for sub in submissions:
        run_behavioural_check(sub.id)
    print(f'[PLAGIARISM] Phase 1 complete')

    # Collect behavioural results
    BehaviouralFlag = apps.get_model('plagiarism', 'BehaviouralFlag')
    b_flags = BehaviouralFlag.objects.filter(submission__exam=exam)
    b_agg = b_flags.aggregate(avg_risk=Avg('risk_score'))
    PlagiarismRun.objects.filter(pk=run.pk).update(
        b_flags_total=b_flags.count(),
        b_high_confidence=b_flags.filter(confidence='high').count(),
        b_medium_confidence=b_flags.filter(confidence='medium').count(),
        b_low_confidence=b_flags.filter(confidence='low').count(),
        b_avg_risk_score=round(b_agg['avg_risk'], 4) if b_agg['avg_risk'] else None,
    )

    # Phase 2 — queue per-question cross-compare tasks. Exam-close runs are staggered so many
    # exams closing together don't spike the worker; a trainer-started run is one exam they're
    # waiting on, so it goes at once.
    stagger = 0 if trigger == 'manual_rerun' else 30
    for i, question in enumerate(exam.questions.all()):
        run_question_plagiarism_check.apply_async(
            args=[question.id, run.pk],
            kwargs={'notify': notify},
            countdown=i * stagger,
        )

    print(f'[PLAGIARISM] Phase 2 queued — {questions_count} questions for exam {exam_id}')


@shared_task
def run_question_plagiarism_check(question_id: int, run_id: int = None, notify: bool = True):
    """
    Cross-compares flagged students against the FULL cohort for this question.

    notify=False skips the trainer email and the AI explanation for new pairs.
    Detection is identical; seed_data uses it to run this exact Phase 2
    synchronously without emailing or calling the LLM for demo data.

    Why not just compare flagged vs flagged:
      A flagged student may have copied from someone with clean behaviour signals
      (typed slowly, no paste events). The source would be invisible if we only
      compared suspects against each other.

    Strategy:
      1. Identify HIGH-confidence (3+ signal) behavioural suspects (K students)
      2. Pull ALL submissions for the question (N students)
      3. TF-IDF vectorize the full cohort once — O(N·V)
      4. Check only pairs where at least one side is a suspect — O(K·N)
      5. Flag pairs above threshold

    At 100 students with 12 suspects: 12×100 = 1,200 checks
    vs old approach (suspects only): 12×12 = 144 checks (misses unflagged sources)
    vs all-pairs: 100×100 = 10,000 checks (unnecessary, slow)
    """
    policy = get_policy()
    Submission = apps.get_model('submissions', 'Submission')
    PlagiarismFlag = apps.get_model('plagiarism', 'PlagiarismFlag')
    BehaviouralFlag = apps.get_model('plagiarism', 'BehaviouralFlag')
    Question = apps.get_model('exams', 'Question')

    try:
        question = Question.objects.get(id=question_id)
    except Question.DoesNotExist:
        return

    print(f'[PLAGIARISM] cross-compare for question: {question.title}')

    # who are our suspects: risk at or above the policy's compare threshold (so the
    # weights decide, e.g. a heavy paste alone), or 3+ signals (high confidence)
    from django.db.models import Q
    high_risk_student_ids = set(
        BehaviouralFlag.objects
        .filter(submission__question=question)
        .filter(Q(risk_score__gte=policy.get('compare_min_risk', 0.35)) | Q(confidence='high'))
        .values_list('submission__student_id', flat=True)
    )

    print(f'[PLAGIARISM] {len(high_risk_student_ids)} high-risk students for Q{question_id}')

    if not high_risk_student_ids:
        print(f'[PLAGIARISM] skipping Q{question_id} — no high-risk students')
        if run_id:
            _update_run_question_done(run_id, new_flags=0, pairs_90=0, pairs_80=0)
        return

    # fetch the best submission for EVERY student who answered this question
    # (passed attempt if any, otherwise latest attempt)
    # in student id order, so every pair is (lower student id, higher student id) on every run
    all_student_ids = (
        Submission.objects
        .filter(question=question)
        .order_by('student_id')  # replaces Meta ordering (-submitted_at), which would make DISTINCT per (student, time)
        .values_list('student_id', flat=True)
        .distinct()
    )

    all_subs = []
    for student_id in all_student_ids:
        sub = (
            Submission.objects
            .filter(question=question, student_id=student_id, status='passed')
            .order_by('attempt_number')
            .first()
        ) or (
            Submission.objects
            .filter(question=question, student_id=student_id)
            .order_by('-attempt_number')
            .first()
        )
        if sub and sub.code:
            all_subs.append(sub)

    if len(all_subs) < 2:
        if run_id:
            _update_run_question_done(run_id, new_flags=0, pairs_90=0, pairs_80=0)
        return

    print(f'[PLAGIARISM] vectorizing {len(all_subs)} submissions for Q{question_id}')

    normalized = [normalize_code(sub.code, sub.language) for sub in all_subs]

    try:
        vectorizer = TfidfVectorizer()
        matrix = vectorizer.fit_transform(normalized)
        sim_matrix = cosine_similarity(matrix)
    except Exception as e:
        print(f'[PLAGIARISM] vectorization error Q{question_id}: {e}')
        if run_id:  # still count the question, or the run stays "running" forever
            _update_run_question_done(run_id, new_flags=0, pairs_90=0, pairs_80=0)
        return

    flagged = 0
    pairs_90 = 0
    pairs_80 = 0

    # upper-triangle loop — each pair checked once
    # only process the pair if AT LEAST ONE side is a high-risk suspect
    for i in range(len(all_subs)):
        for j in range(i + 1, len(all_subs)):
            sub_a = all_subs[i]
            sub_b = all_subs[j]

            a_is_suspect = sub_a.student_id in high_risk_student_ids
            b_is_suspect = sub_b.student_id in high_risk_student_ids

            if not a_is_suspect and not b_is_suspect:
                continue  # neither side is flagged — skip this pair entirely

            similarity = float(sim_matrix[i][j])

            if similarity >= policy['similarity_threshold']:
                pf, created = _save_pair_flag(PlagiarismFlag, question, sub_a, sub_b, similarity)
                if created:
                    flagged += 1
                    print(
                        f'[PLAGIARISM] PAIR FLAGGED '
                        f'{sub_a.student.username} ({"suspect" if a_is_suspect else "source"}) '
                        f'vs {sub_b.student.username} ({"suspect" if b_is_suspect else "source"}) '
                        f'sim={similarity:.2f}'
                    )
                    if notify:
                        from codemas.notifications import notify_plagiarism_flagged
                        notify_plagiarism_flagged(pf)

                        # AI explanation (async, best-effort) — generated alongside this
                        # Layer 2 pass for the newly flagged pair. Never blocks detection.
                        try:
                            from ai.tasks import explain_plagiarism
                            explain_plagiarism.delay(pf.id)
                        except Exception as e:
                            print(f'[AI] failed to enqueue plagiarism explanation: {e}')

                if similarity >= 0.90:
                    pairs_90 += 1
                else:
                    pairs_80 += 1

    checked_ids = [s.id for s in all_subs]
    Submission.objects.filter(pk__in=checked_ids).update(similarity_check_done=True)

    if run_id:
        _update_run_question_done(run_id, new_flags=flagged, pairs_90=pairs_90, pairs_80=pairs_80)

    print(f'[PLAGIARISM] Q{question_id} done — {flagged} new pair flags')


def _save_pair_flag(PlagiarismFlag, question, sub_a, sub_b, similarity):
    """One flag per (question, student pair), whichever submissions it was raised on.

    A rerun after a student's best submission changed updates the pair's existing flag
    (new submissions and score) and keeps the trainer's review status, note and reviewer.
    sub_a belongs to the lower student id. Unreviewed duplicates left by older runs are
    removed. Returns (flag, created)."""
    from django.db.models import Q
    a, b = sub_a.student_id, sub_b.student_id
    same_pair = list(
        PlagiarismFlag.objects.filter(submission_1__question=question)
        .filter(Q(submission_1__student_id=a, submission_2__student_id=b)
                | Q(submission_1__student_id=b, submission_2__student_id=a))
    )
    if not same_pair:
        return PlagiarismFlag.objects.create(
            submission_1=sub_a, submission_2=sub_b, similarity_score=similarity,
            flagged=True, detection_method='behavioural_filtered_tfidf',
        ), True

    # keep a reviewed flag over a pending one, then the one already on these submissions, then the oldest
    exact = lambda f: (f.submission_1_id, f.submission_2_id) == (sub_a.id, sub_b.id)
    keep = min(same_pair, key=lambda f: (f.review_status == 'pending', not exact(f), f.id))
    PlagiarismFlag.objects.filter(pk__in=[f.pk for f in same_pair if f is not keep and f.review_status == 'pending']).delete()
    keep.submission_1, keep.submission_2 = sub_a, sub_b
    keep.similarity_score = similarity
    keep.flagged = True
    keep.save(update_fields=['submission_1', 'submission_2', 'similarity_score', 'flagged'])
    return keep, False


def _update_run_question_done(run_id: int, new_flags: int, pairs_90: int, pairs_80: int):
    from django.db.models import F
    from django.utils import timezone
    PlagiarismRun = apps.get_model('plagiarism', 'PlagiarismRun')
    PlagiarismRun.objects.filter(pk=run_id).update(
        s_flags_new=F('s_flags_new') + new_flags,
        s_pairs_90_plus=F('s_pairs_90_plus') + pairs_90,
        s_pairs_80_90=F('s_pairs_80_90') + pairs_80,
        questions_done=F('questions_done') + 1,
    )
    run = PlagiarismRun.objects.get(pk=run_id)
    if run.questions_done >= run.questions_total:
        # all question tasks finished — compute final similarity totals and mark complete
        PlagiarismFlag = apps.get_model('plagiarism', 'PlagiarismFlag')
        from django.db.models import Avg
        s_flags = PlagiarismFlag.objects.filter(flagged=True, submission_1__exam_id=run.exam_id)
        s_agg   = s_flags.aggregate(avg=Avg('similarity_score'))
        PlagiarismRun.objects.filter(pk=run_id).update(
            s_flags_total=s_flags.count(),
            s_avg_similarity=round(s_agg['avg'], 4) if s_agg['avg'] else None,
            status='completed',
            completed_at=timezone.now(),
        )
