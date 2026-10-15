from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from django.db.models import Count, Q, Avg
from django.utils import timezone
from django.core.cache import cache
from datetime import timedelta
from .models import PlagiarismFlag, BehaviouralFlag, PlagiarismPolicy, ReviewAuditLog, PolicyVersion, POLICY_FIELDS
from .serializers import (
    PlagiarismFlagSerializer, BehaviouralFlagSerializer,
    PlagiarismPolicySerializer, ReviewAuditLogSerializer,
)
from .tasks import normalize_code
from exams.models import newest_exam_first, exam_status
from analytics import metrics


def _log_review(reviewer, flag_type, flag_id, action, note):
    ReviewAuditLog.objects.create(
        reviewed_by=reviewer,
        flag_type=flag_type,
        flag_id=flag_id,
        action=action,
        note=note,
    )


# The trainer decisions a student sees (My results): every confirmed flag, and a dismissed one
# when the trainer left a note. Pending flags, scores and the other student stay trainer-only.
SHOWN_TO_STUDENT = Q(review_status='confirmed') | (Q(review_status='dismissed') & ~Q(review_note=''))


def _outcome_changed(student_ids, exam_id):
    """A review changed these students' integrity outcome on the exam: their stored exam
    summary no longer matches it, so it is rewritten on the next view."""
    from ai.tasks import forget_exam_summaries
    forget_exam_summaries(student_ids, exam_id)


class PlagiarismFlagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view plagiarism flags'}, status=status.HTTP_403_FORBIDDEN)

        flags = PlagiarismFlag.objects.filter(flagged=True).select_related(
            'submission_1__student', 'submission_1__question', 'submission_1__exam',
            'submission_2__student', 'submission_2__question',
        ).order_by(newest_exam_first('submission_1__exam__'), '-similarity_score', '-id')  # newest exam, worst first
        serializer = PlagiarismFlagSerializer(flags, many=True)
        return Response(serializer.data)


class PlagiarismFlagReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can review flags'}, status=status.HTTP_403_FORBIDDEN)

        flag = PlagiarismFlag.objects.filter(pk=pk).first()
        if not flag:
            return Response({'error': 'Flag not found'}, status=status.HTTP_404_NOT_FOUND)

        review_status = request.data.get('review_status')
        if review_status not in ['confirmed', 'dismissed']:
            return Response({'error': 'review_status must be confirmed or dismissed'}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get('review_note', '')
        flag.review_status = review_status
        flag.review_note = note
        flag.reviewed_by = request.user
        flag.save()

        _log_review(request.user, 'similarity', flag.id, review_status, note)
        s1, s2 = flag.submission_1, flag.submission_2
        _outcome_changed([s1.student_id, s2.student_id], s1.exam_id)
        return Response(PlagiarismFlagSerializer(flag).data)


class MyReviewsView(APIView):
    """GET /api/plagiarism/mine/ — a student's integrity reviews: what the trainer decided and wrote.

    Only reviewed flags reach the student (SHOWN_TO_STUDENT).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'student':
            return Response({'error': 'Only students have integrity reviews'}, status=status.HTTP_403_FORBIDDEN)

        shown = SHOWN_TO_STUDENT
        mine = Q(submission_1__student=request.user) | Q(submission_2__student=request.user)
        reviews = []
        for f in BehaviouralFlag.objects.filter(shown, submission__student=request.user).select_related(
            'submission__question',
        ):
            reviews.append(_my_review(f, f.submission, 'behaviour'))
        for f in PlagiarismFlag.objects.filter(shown & mine).select_related(
            'submission_1__question', 'submission_2__question',
        ):
            sub = f.submission_1 if f.submission_1.student_id == request.user.id else f.submission_2
            reviews.append(_my_review(f, sub, 'similarity'))
        reviews.sort(key=lambda r: r.pop('_at'), reverse=True)  # latest attempt first, behaviour before pairs

        # A case decision writes the student's note on each of their flags, so the same words
        # can sit on a behaviour flag and a pair: show each note once per exam.
        seen = set()
        for r in reviews:
            key = (r['exam_id'], r['review_note'])
            if r['review_note'] and key in seen:
                r['review_note'] = ''
            seen.add(key)
        return Response(reviews)


def _my_review(flag, sub, kind):
    return {
        'kind': kind,
        'exam_id': sub.exam_id,
        'question_id': sub.question_id,
        'question_title': sub.question.title,
        'submission_id': sub.id,
        'attempt_number': sub.attempt_number,
        'review_status': flag.review_status,
        'review_note': flag.review_note,
        '_at': sub.submitted_at,  # sort key, removed before the response
    }


class BehaviouralFlagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view behavioural flags'}, status=status.HTTP_403_FORBIDDEN)

        qs = BehaviouralFlag.objects.select_related(
            'submission__student', 'submission__question', 'submission__exam'
        ).order_by(newest_exam_first('submission__exam__'), '-risk_score', '-submission__submitted_at')

        review_status = request.query_params.get('status')
        if review_status and review_status != 'all':
            qs = qs.filter(review_status=review_status)

        serializer = BehaviouralFlagSerializer(qs, many=True)
        policy = PlagiarismPolicy.get()
        return Response({
            'flags': serializer.data,
            'policy_weights': {
                'paste': policy.paste_weight,
                'time': policy.time_weight,
                'tab': policy.tab_weight,
                'submission': policy.submission_weight,
            },
        })


class BehaviouralFlagReviewView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can review flags'}, status=status.HTTP_403_FORBIDDEN)

        flag = BehaviouralFlag.objects.filter(pk=pk).first()
        if not flag:
            return Response({'error': 'Flag not found'}, status=status.HTTP_404_NOT_FOUND)

        review_status = request.data.get('review_status')
        if review_status not in ['confirmed', 'dismissed']:
            return Response({'error': 'review_status must be confirmed or dismissed'}, status=status.HTTP_400_BAD_REQUEST)

        note = request.data.get('review_note', '')
        flag.review_status = review_status
        flag.review_note = note
        flag.reviewed_by = request.user
        flag.save()

        _log_review(request.user, 'behavioural', flag.id, review_status, note)
        _outcome_changed([flag.submission.student_id], flag.submission.exam_id)
        return Response(BehaviouralFlagSerializer(flag).data)


class PolicyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        policy = PlagiarismPolicy.get()
        return Response(PlagiarismPolicySerializer(policy).data)

    def put(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        reason = request.data.get('change_reason', '')
        policy = PlagiarismPolicy.get()
        snapshot_before = {f: getattr(policy, f) for f in POLICY_FIELDS}
        serializer = PlagiarismPolicySerializer(policy, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save(updated_by=request.user)
            cache.delete('plagiarism_policy')  # tasks pick up new values on next run
            policy.refresh_from_db()
            snapshot_after = {f: getattr(policy, f) for f in POLICY_FIELDS}
            PolicyVersion.objects.create(
                changed_by=request.user,
                change_reason=reason,
                snapshot_before=snapshot_before,
                snapshot_after=snapshot_after,
            )
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class AuditLogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
        logs = ReviewAuditLog.objects.select_related('reviewed_by').order_by('-created_at')[:200]
        return Response(ReviewAuditLogSerializer(logs, many=True).data)


class PolicyChangelogView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from exams.models import Exam

        versions = list(PolicyVersion.objects.select_related('changed_by').order_by('-changed_at')[:100])
        now = timezone.now()
        rows = []

        for i, v in enumerate(versions):
            # This policy was active from v.changed_at until the next newer version superseded it
            period_start = v.changed_at
            period_end   = versions[i - 1].changed_at if i > 0 else now

            # Exams whose window overlaps the policy's active period
            overlapping = Exam.objects.filter(
                start_time__lt=period_end,
                end_time__gt=period_start,
            ).order_by(newest_exam_first(), '-id').values('id', 'title', 'start_time', 'end_time', 'is_active')

            exam_rows = []
            for ex in overlapping:
                if ex['start_time'] >= period_start:
                    status_label = 'started under this policy'
                else:
                    status_label = 'in-flight at change'
                exam_rows.append({
                    'id':     ex['id'],
                    'title':  ex['title'],
                    'status': status_label,
                })

            changes = []
            for field in POLICY_FIELDS:
                before = v.snapshot_before.get(field)
                after  = v.snapshot_after.get(field)
                if before != after:
                    changes.append({'field': field, 'before': before, 'after': after})

            rows.append({
                'id':            v.id,
                'changed_by':    v.changed_by.username if v.changed_by else None,
                'changed_at':    v.changed_at.isoformat(),
                'change_reason': v.change_reason,
                'changes':       changes,
                'affected_exams': exam_rows,
            })
        return Response(rows)


class SubmissionPlagiarismView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, submission_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from submissions.models import Submission
        sub = Submission.objects.filter(pk=submission_id).first()
        if not sub:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        # behavioural flag (one-to-one)
        behavioural = None
        try:
            bf = sub.behavioural_flag
            behavioural = {
                'risk_score':       round(bf.risk_score, 3),
                'confidence':       bf.confidence,
                'signals':          bf.signals_triggered,
                'review_status':    bf.review_status,
                'review_note':      bf.review_note,
                'paste_score':      round(bf.paste_score, 3),
                'time_score':       round(bf.time_score, 3),
                'snapshot_score':   round(bf.snapshot_score, 3),
                'submission_score': round(bf.submission_score, 3),
            }
        except Exception:
            pass

        # similarity flags (this submission may appear as either side)
        sim_flags = PlagiarismFlag.objects.filter(
            flagged=True
        ).filter(
            submission_1_id=submission_id
        ) | PlagiarismFlag.objects.filter(
            flagged=True
        ).filter(
            submission_2_id=submission_id
        )
        sim_flags = sim_flags.select_related(
            'submission_1__student', 'submission_2__student'
        ).order_by('-checked_at', '-id')

        similarity = []
        for f in sim_flags:
            other = f.submission_2 if f.submission_1_id == submission_id else f.submission_1
            similarity.append({
                'flag_id':          f.id,
                'similarity_score': round(f.similarity_score, 3),
                'review_status':    f.review_status,
                'other_submission': other.id,
                'other_student':    other.student.username,
            })

        return Response({'behavioural': behavioural, 'similarity': similarity})


class CodeSimilaritySearchView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        query_code = request.data.get('code', '').strip()
        language   = request.data.get('language', '')
        top_k      = min(int(request.data.get('top_k', 10)), 50)

        if not query_code:
            return Response({'error': 'code is required'}, status=status.HTTP_400_BAD_REQUEST)

        from submissions.models import Submission
        from django.core.cache import cache
        import pickle, hashlib

        qs = Submission.objects.select_related('student', 'question', 'exam').exclude(code='')
        if language:
            qs = qs.filter(language=language)

        submissions = list(qs[:2000])
        if not submissions:
            return Response({'results': []})

        normalized_query = normalize_code(query_code, language)

        # use pre-normalized code stored at submission time; fall back to on-the-fly for old submissions
        normalized_corpus = [
            s.normalized_code if s.normalized_code else normalize_code(s.code, s.language)
            for s in submissions
        ]

        # cache key based on submission IDs + languages — invalidates when corpus changes
        cache_key = 'tfidf:' + hashlib.md5(
            ','.join(f'{s.id}:{s.language}' for s in submissions).encode()
        ).hexdigest()

        cached = cache.get(cache_key)
        if cached:
            vectorizer, corpus_matrix = pickle.loads(cached)
            query_vec = vectorizer.transform([normalized_query])
        else:
            vectorizer = TfidfVectorizer()
            corpus_matrix = vectorizer.fit_transform(normalized_corpus)
            cache.set(cache_key, pickle.dumps((vectorizer, corpus_matrix)), timeout=300)
            query_vec = vectorizer.transform([normalized_query])

        scores = cosine_similarity(query_vec, corpus_matrix)[0]

        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for idx, score in indexed:
            if score < 0.1:
                break
            sub = submissions[idx]
            results.append({
                'submission_id':  sub.id,
                'similarity':     round(float(score), 4),
                'student':        sub.student.username,
                'question':       sub.question.title,
                'exam':           sub.exam.title,
                'language':       sub.language,
                'status':         sub.status,
                'submitted_at':   sub.submitted_at.isoformat(),
                'code_preview':   sub.code[:300],
            })

        return Response({'results': results, 'total_searched': len(submissions)})


class RerunExamChecksView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from exams.models import Exam
        from plagiarism.tasks import run_exam_plagiarism_check

        exam = Exam.objects.filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        run_exam_plagiarism_check.delay(exam_id, triggered_by_id=request.user.id, trigger='manual_rerun')
        return Response({'queued': True, 'exam': exam.title}, status=status.HTTP_202_ACCEPTED)


class PlagiarismRunListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from .models import PlagiarismRun
        exam_id = request.query_params.get('exam_id')
        qs = PlagiarismRun.objects.select_related('exam', 'triggered_by').order_by('-ran_at')
        if exam_id:
            qs = qs.filter(exam_id=exam_id)

        rows = []
        for r in qs[:100]:
            rows.append({
                'id':                r.id,
                'exam_id':           r.exam_id,
                'exam_title':        r.exam.title,
                'trigger':           r.trigger,
                'triggered_by':      r.triggered_by.username if r.triggered_by else None,
                'status':            r.status,
                'ran_at':            r.ran_at.isoformat(),
                'completed_at':      r.completed_at.isoformat() if r.completed_at else None,
                'policy_snapshot':   r.policy_snapshot,
                'total_submissions': r.total_submissions,
                'unique_students':   r.unique_students,
                'pass_rate':         r.pass_rate,
                'avg_execution_ms':  r.avg_execution_ms,
                'avg_solve_time_s':  r.avg_solve_time_s,
                'avg_attempts':      r.avg_attempts,
                'avg_time_remaining':r.avg_time_remaining,
                'b_flags_total':     r.b_flags_total,
                'b_flags_new':       r.b_flags_new,
                'b_high_confidence': r.b_high_confidence,
                'b_medium_confidence':r.b_medium_confidence,
                'b_low_confidence':  r.b_low_confidence,
                'b_avg_risk_score':  r.b_avg_risk_score,
                's_flags_total':     r.s_flags_total,
                's_flags_new':       r.s_flags_new,
                's_pairs_90_plus':   r.s_pairs_90_plus,
                's_pairs_80_90':     r.s_pairs_80_90,
                's_avg_similarity':  r.s_avg_similarity,
                'questions_total':   r.questions_total,
                'questions_done':    r.questions_done,
            })
        return Response(rows)


def _rings(edges):
    """Connected components of size >= 2 in an undirected student graph given as (a, b) pairs."""
    adj = {}
    for a, b in edges:
        adj.setdefault(a, set()).add(b)
        adj.setdefault(b, set()).add(a)
    visited = set()
    components = []
    for start in adj:
        if start in visited:
            continue
        stack, component = [start], []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(adj.get(node, set()) - visited)
        if len(component) >= 2:
            components.append(component)
    return components


def _case_status(statuses):
    """A case's outcome from its flags' review statuses: pending while any flag waits."""
    if 'pending' in statuses:
        return 'pending'
    if set(statuses) == {'dismissed'}:
        return 'dismissed'
    if set(statuses) == {'confirmed'}:
        return 'confirmed'
    return 'mixed'


def _cases(pairs, b_flags, usernames):
    """Cases to decide on one exam. A case is one group of students linked by similarity
    pairs that count (not dismissed), plus each student with a counted behavioural flag
    who is in no such group. Students whose flags were all dismissed still form decided
    cases (linked by their dismissed pairs) so a dismissed case stays on the page.
    Every flag belongs to at most one case; a dismissed pair between two different cases
    is in none. The key is the lowest student id, so it survives decisions."""
    case_of = {}
    groups = []

    def add(group):
        for sid in group:
            case_of[sid] = len(groups)
        groups.append(group)

    counted = [p for p in pairs if p.review_status != 'dismissed']
    for group in _rings((p.submission_1.student_id, p.submission_2.student_id) for p in counted):
        add(group)
    for f in b_flags:
        if f.review_status != 'dismissed' and f.submission.student_id not in case_of:
            add([f.submission.student_id])
    dismissed = [p for p in pairs if p.review_status == 'dismissed'
                 and p.submission_1.student_id not in case_of and p.submission_2.student_id not in case_of]
    for group in _rings((p.submission_1.student_id, p.submission_2.student_id) for p in dismissed):
        add(group)
    for f in b_flags:
        if f.submission.student_id not in case_of:
            add([f.submission.student_id])

    case_pairs = [[] for _ in groups]
    case_flags = [[] for _ in groups]
    for p in pairs:
        a, b = case_of.get(p.submission_1.student_id), case_of.get(p.submission_2.student_id)
        if a is not None and a == b:
            case_pairs[a].append(p)
    for f in b_flags:
        case_flags[case_of[f.submission.student_id]].append(f)

    cases = []
    for group, cp, cf in zip(groups, case_pairs, case_flags):
        cp.sort(key=lambda p: -p.similarity_score)
        cf.sort(key=lambda f: -f.risk_score)
        statuses = [p.review_status for p in cp] + [f.review_status for f in cf]
        cases.append({
            'key': str(min(group)),
            'members': [
                {'student_id': sid, 'username': usernames[sid][0], 'first_name': usernames[sid][1]}
                for sid in sorted(group, key=lambda sid: usernames[sid][0])
            ],
            'pairs': [{
                'id': p.id,
                'submission_1': p.submission_1_id,
                'submission_2': p.submission_2_id,
                'student_1_id': p.submission_1.student_id,
                'student_2_id': p.submission_2.student_id,
                'attempt_1': p.submission_1.attempt_number,
                'attempt_2': p.submission_2.attempt_number,
                'question_title': p.submission_1.question.title,
                'similarity_score': round(p.similarity_score, 3),
                'review_status': p.review_status,
                'review_note': p.review_note,
            } for p in cp],
            'behavioural': BehaviouralFlagSerializer(cf, many=True).data,
            'pending': statuses.count('pending'),
            'status': _case_status(statuses),
            'max_similarity': round(max((p.similarity_score for p in cp), default=0), 3),
            'max_risk': metrics.risk(cf[0].risk_score) if cf else None,
        })

    # Numbered by severity (strongest code match, then behavioural risk) so a case keeps
    # its number when it is decided; listed with the ones still waiting first.
    cases.sort(key=lambda c: (-c['max_similarity'], -(c['max_risk'] or 0), c['key']))
    for n, c in enumerate(cases, 1):
        c['number'] = n
    cases.sort(key=lambda c: c['status'] != 'pending')
    return cases


def exam_cases(exam_id, students=None):
    """The cases on one exam, as the investigation detail lists them (see _cases). Every flag
    on the exam counts, dismissed ones too, between students of the student population who
    submitted on it. `students` is {student_id: (username, first_name)} for those students;
    it is looked up when not given. The student page and the exam report use this too, so a
    case has the same key on every page."""
    from submissions.models import Submission

    if students is None:
        students = {
            sid: (username, first_name) for sid, username, first_name in
            metrics.student_submissions(Submission.objects.filter(exam_id=exam_id)).order_by()
            .values_list('student_id', 'student__username', 'student__first_name').distinct()
        }
    pairs = [
        p for p in PlagiarismFlag.objects.filter(flagged=True, submission_1__exam_id=exam_id)
        .select_related('submission_1__question', 'submission_2')
        if p.submission_1.student_id in students and p.submission_2.student_id in students
    ]
    b_flags = [
        f for f in BehaviouralFlag.objects.filter(submission__exam_id=exam_id)
        .select_related('submission__student', 'submission__question', 'submission__exam')
        if f.submission.student_id in students
    ]
    return _cases(pairs, b_flags, students)


def case_keys(cases):
    """{student_id: key of the case they are in}."""
    return {m['student_id']: c['key'] for c in cases for m in c['members']}


def pending_cases(cases):
    """Cases to decide: cases with a flag still pending review."""
    return sum(1 for c in cases if c['status'] == 'pending')


def cases_to_decide():
    """Cases to decide across every exam (the Investigation sidebar count): the sum of each
    exam's case-file count. Only an exam with a pending flag can have one, so only those
    exams are grouped into cases."""
    from submissions.models import Submission
    pending = Q(behavioural_flag__review_status='pending') | Q(
        plagiarism_as_first__flagged=True, plagiarism_as_first__review_status='pending')
    exam_ids = set(
        metrics.student_submissions(Submission.objects.filter(pending))
        .order_by().values_list('exam_id', flat=True).distinct()
    )
    return sum(pending_cases(exam_cases(eid)) for eid in exam_ids)


class CohortListView(APIView):
    """Investigations list: one row per exam that students took. Integrity rate
    is the canonical flagged-students rate (analytics.metrics)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from submissions.models import Submission
        from exams.models import Exam
        from analytics import metrics

        exams = list(Exam.objects.order_by(newest_exam_first(), '-id'))
        summaries = metrics.exam_summaries([e.id for e in exams])
        subs = metrics.student_submissions(Submission.objects.all())
        sub_counts = {r['exam_id']: r['n'] for r in subs.order_by().values('exam_id').annotate(n=Count('id'))}
        b_counts = {
            r['exam_id']: r['n'] for r in
            subs.filter(metrics.FLAGGED).order_by().values('exam_id').annotate(n=Count('id'))
        }
        edges_by_exam = {}   # dismissed flags don't count, here or on any other page
        for exam_id, s1, s2 in metrics.similarity_flags().values_list(
            'submission_1__exam_id', 'submission_1__student_id', 'submission_2__student_id',
        ):
            edges_by_exam.setdefault(exam_id, []).append((s1, s2))

        rows = []
        for exam in exams:
            summary = summaries[exam.id]
            if summary['took'] == 0:
                continue
            edges = edges_by_exam.get(exam.id, [])
            rows.append({
                'exam_id': exam.id,
                'exam_title': exam.title,
                **summary,
                'total_submissions': sub_counts.get(exam.id, 0),
                'behavioural_count': b_counts.get(exam.id, 0),
                'similarity_count': len(edges),
                'ring_count': len(_rings(edges)),
                'health': metrics.integrity_health(summary['flagged_students_rate']),
            })

        return Response(rows)


class CohortDetailView(APIView):
    """Investigation detail for one exam. stats carry the canonical metrics;
    `students` lists everyone with a behavioural or similarity signal, ranked
    by combined risk, for the trainer to work through."""
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from submissions.models import Submission
        from exams.models import Exam
        from analytics import metrics

        exam = Exam.objects.filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        subs = list(metrics.student_submissions(Submission.objects.filter(exam=exam)).select_related('student'))
        total = len(subs)

        student_data = {}
        for sub in subs:
            sid = sub.student_id
            if sid not in student_data:
                student_data[sid] = {
                    'student_id': sid,
                    'username': sub.student.username,
                    'submission_id': sub.id,
                    'behavioural_risk': None,
                    'risk': None,
                    'behavioural_confidence': None,
                    'similarity_pairs': 0,
                    'max_similarity': 0.0,
                    'past_flags': 0,
                }

        behavioural_count = 0
        for bf in metrics.behavioural_flags().filter(submission__exam=exam).select_related('submission'):
            sid = bf.submission.student_id
            if sid in student_data:
                behavioural_count += 1
                # a student can carry several flags on one exam: keep the riskiest
                if student_data[sid]['behavioural_risk'] is None or bf.risk_score > student_data[sid]['behavioural_risk']:
                    student_data[sid]['behavioural_risk'] = round(bf.risk_score, 3)
                    student_data[sid]['risk'] = metrics.risk(bf.risk_score)
                    student_data[sid]['behavioural_confidence'] = bf.confidence

        sim_flags = list(
            metrics.similarity_flags().filter(submission_1__exam=exam)
            .select_related('submission_1', 'submission_2')
        )
        for flag in sim_flags:
            score = flag.similarity_score
            for sid in (flag.submission_1.student_id, flag.submission_2.student_id):
                if sid in student_data:
                    student_data[sid]['similarity_pairs'] += 1
                    if score > student_data[sid]['max_similarity']:
                        student_data[sid]['max_similarity'] = score

        # Past flags across other exams
        sub_ids_this_exam = {s.id for s in subs}
        for sid in student_data:
            past_sim = metrics.similarity_flags().filter(
                Q(submission_1__student_id=sid) | Q(submission_2__student_id=sid)
            ).exclude(
                Q(submission_1_id__in=sub_ids_this_exam) | Q(submission_2_id__in=sub_ids_this_exam)
            ).count()
            past_b = metrics.behavioural_flags().filter(
                submission__student_id=sid
            ).exclude(submission__exam=exam).count()
            student_data[sid]['past_flags'] = past_sim + past_b

        # Compute combined risk and build output list
        student_list = []
        for s in student_data.values():
            b_risk = s['behavioural_risk'] or 0.0
            sim_factor = min(s['similarity_pairs'] / 5.0, 1.0)
            s['combined_risk'] = round(b_risk * 0.6 + sim_factor * 0.4, 3)
            s['max_similarity'] = round(s['max_similarity'], 3)
            student_list.append(s)

        student_list.sort(key=lambda s: s['combined_risk'], reverse=True)
        students_to_review = [s for s in student_list if s['combined_risk'] > 0]

        # Cases see every flag on the exam (dismissed ones too, as decided cases), students only
        first_names = {sub.student_id: sub.student.first_name for sub in subs}
        cases = exam_cases(exam.id, {
            sid: (s['username'], first_names.get(sid, '')) for sid, s in student_data.items()
        })
        case_of = case_keys(cases)
        for s in students_to_review:
            s['case'] = case_of.get(s['student_id'])

        rings = []
        for component in _rings((f.submission_1.student_id, f.submission_2.student_id) for f in sim_flags):
            comp_set = set(component)
            ring_edges = [f for f in sim_flags
                          if f.submission_1.student_id in comp_set
                          and f.submission_2.student_id in comp_set]
            members = [
                {'student_id': sid, 'username': student_data[sid]['username']}
                for sid in component if sid in student_data
            ]
            rings.append({
                'size': len(members),
                'members': members,
                'avg_similarity': round(sum(f.similarity_score for f in ring_edges) / len(ring_edges), 3) if ring_edges else 0,
                'max_similarity': round(max((f.similarity_score for f in ring_edges), default=0), 3),
                'confirmed': sum(1 for f in ring_edges if f.review_status == 'confirmed'),
                'case': case_of.get(members[0]['student_id']) if members else None,
            })

        rings.sort(key=lambda r: r['size'], reverse=True)

        from .models import PlagiarismRun
        last_run = (PlagiarismRun.objects.filter(exam=exam, status='completed')
                    .exclude(completed_at=None).order_by('-completed_at').first())

        summary = metrics.exam_summary(exam.id)
        return Response({
            'exam': {
                'id': exam.id,
                'title': exam.title,
                'status': exam_status(exam),
                'question_count': exam.questions.count(),
                'duration_minutes': exam.duration_minutes,
                'start_time': exam.start_time.isoformat() if exam.start_time else None,
                'end_time': exam.end_time.isoformat() if exam.end_time else None,
                'last_checked_at': last_run.completed_at.isoformat() if last_run else None,
            },
            'stats': {
                **summary,
                'total_submissions': total,
                'behavioural_count': behavioural_count,
                'similarity_count': len(sim_flags),
                'ring_count': len(rings),
                'cases_to_decide': pending_cases(cases),
                'health': metrics.integrity_health(summary['flagged_students_rate']),
            },
            'students': students_to_review,
            'rings': rings,
            'cases': cases,
            # open appeals on this exam: the case shows "Appeal pending" with the student's response
            'appeals': [
                {'id': a.id, 'student_id': a.student_id, 'student_note': a.student_note,
                 'created_at': a.created_at.isoformat()}
                for a in exam.appeals.filter(status='open').order_by('created_at')
            ],
        })


class MonitoringView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        last7  = now - timedelta(days=7)
        prev7  = now - timedelta(days=14)

        from analytics import metrics

        # ── Behavioural summary ──────────────────────────────────────────────
        bq = BehaviouralFlag.objects.all()
        b_total     = bq.count()
        b_confirmed = bq.filter(review_status='confirmed').count()
        b_dismissed = bq.filter(review_status='dismissed').count()
        b_pending   = bq.filter(review_status='pending').count()
        b_reviewed  = b_confirmed + b_dismissed
        b_precision = round(b_confirmed / b_reviewed, 3) if b_reviewed else None

        # ── Similarity summary ───────────────────────────────────────────────
        sq = PlagiarismFlag.objects.filter(flagged=True)
        s_total     = sq.count()
        s_confirmed = sq.filter(review_status='confirmed').count()
        s_dismissed = sq.filter(review_status='dismissed').count()
        s_pending   = sq.filter(review_status='pending').count()
        s_reviewed  = s_confirmed + s_dismissed
        s_precision = round(s_confirmed / s_reviewed, 3) if s_reviewed else None

        # ── Signal effectiveness (which signals predict real cheating) ───────
        signals = [
            ('paste',      'paste_score'),
            ('time',       'time_score'),
            ('snapshot',   'snapshot_score'),
            ('submission', 'submission_score'),
        ]
        signal_rows = []
        for label, field in signals:
            fired = bq.filter(**{f'{field}__gt': 0})
            total = fired.count()
            confirmed = fired.filter(review_status='confirmed').count()
            dismissed = fired.filter(review_status='dismissed').count()
            reviewed  = confirmed + dismissed
            signal_rows.append({
                'signal':    label,
                'total':     total,
                'confirmed': confirmed,
                'dismissed': dismissed,
                'precision': round(confirmed / reviewed, 3) if reviewed else None,
            })

        # ── Confidence breakdown ─────────────────────────────────────────────
        confidence_rows = {}
        for level in ('high', 'medium', 'low'):
            grp = bq.filter(confidence=level)
            total = grp.count()
            confirmed = grp.filter(review_status='confirmed').count()
            dismissed = grp.filter(review_status='dismissed').count()
            reviewed  = confirmed + dismissed
            confidence_rows[level] = {
                'total':     total,
                'confirmed': confirmed,
                'precision': round(confirmed / reviewed, 3) if reviewed else None,
            }

        # ── Similarity by score range ────────────────────────────────────────
        ranges = [
            ('0.9 – 1.0', 0.9, 1.01),
            ('0.8 – 0.9', 0.8, 0.9),
            ('0.5 – 0.8', 0.5, 0.8),
        ]
        sim_ranges = []
        for label, lo, hi in ranges:
            grp = sq.filter(similarity_score__gte=lo, similarity_score__lt=hi)
            total = grp.count()
            confirmed = grp.filter(review_status='confirmed').count()
            dismissed = grp.filter(review_status='dismissed').count()
            reviewed  = confirmed + dismissed
            sim_ranges.append({
                'range':     label,
                'total':     total,
                'confirmed': confirmed,
                'dismissed': dismissed,
                'precision': round(confirmed / reviewed, 3) if reviewed else None,
            })

        # ── Coverage ─────────────────────────────────────────────────────────
        from submissions.models import Submission
        total_subs  = Submission.objects.count()
        b_done      = Submission.objects.filter(behavioural_check_done=True).count()
        s_done      = Submission.objects.filter(similarity_check_done=True).count()

        # ── Per-exam coverage ────────────────────────────────────────────────
        from exams.models import Exam
        exam_rows = []
        for exam in Exam.objects.order_by(newest_exam_first(), '-id')[:20]:
            subs = Submission.objects.filter(exam=exam)
            total = subs.count()
            if total == 0:
                continue
            b_pct = round(subs.filter(behavioural_check_done=True).count() / total * 100, 1)
            s_pct = round(subs.filter(similarity_check_done=True).count()  / total * 100, 1)
            exam_rows.append({
                'exam_id':        exam.id,
                'exam_title':     exam.title,
                'total':          total,
                'behavioural_pct': b_pct,
                'similarity_pct':  s_pct,
            })

        # ── Drift (last 7d vs prev 7d) ───────────────────────────────────────
        b_last7  = bq.filter(created_at__gte=last7).count()
        b_prev7  = bq.filter(created_at__gte=prev7, created_at__lt=last7).count()
        s_last7  = sq.filter(checked_at__gte=last7).count()
        s_prev7  = sq.filter(checked_at__gte=prev7, checked_at__lt=last7).count()
        avg_risk_last7 = bq.filter(created_at__gte=last7).aggregate(v=Avg('risk_score'))['v']
        avg_risk_prev7 = bq.filter(created_at__gte=prev7, created_at__lt=last7).aggregate(v=Avg('risk_score'))['v']

        return Response({
            'summary': {
                'behavioural': {
                    'total': b_total, 'pending': b_pending,
                    'flags_to_review': metrics.flags_to_review(),
                    'confirmed': b_confirmed, 'dismissed': b_dismissed,
                    'precision': b_precision,
                },
                'similarity': {
                    'total': s_total, 'pending': s_pending,
                    'confirmed': s_confirmed, 'dismissed': s_dismissed,
                    'precision': s_precision,
                },
            },
            'signal_effectiveness': signal_rows,
            'confidence_breakdown': confidence_rows,
            'similarity_by_range': sim_ranges,
            'coverage': {
                'total_submissions': total_subs,
                'behavioural_done':  b_done,
                'similarity_done':   s_done,
                'behavioural_pct':   round(b_done / total_subs * 100, 1) if total_subs else 0,
                'similarity_pct':    round(s_done  / total_subs * 100, 1) if total_subs else 0,
            },
            'exam_coverage': exam_rows,
            'drift': {
                'behavioural_last7d': b_last7,
                'behavioural_prev7d': b_prev7,
                'similarity_last7d':  s_last7,
                'similarity_prev7d':  s_prev7,
                'avg_risk_last7d':    round(avg_risk_last7, 3) if avg_risk_last7 else None,
                'avg_risk_prev7d':    round(avg_risk_prev7, 3) if avg_risk_prev7 else None,
            },
        })
