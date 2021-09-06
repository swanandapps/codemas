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


def _log_review(reviewer, flag_type, flag_id, action, note):
    ReviewAuditLog.objects.create(
        reviewed_by=reviewer,
        flag_type=flag_type,
        flag_id=flag_id,
        action=action,
        note=note,
    )


class PlagiarismFlagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view plagiarism flags'}, status=status.HTTP_403_FORBIDDEN)

        flags = PlagiarismFlag.objects.filter(flagged=True).select_related(
            'submission_1__student', 'submission_1__question', 'submission_1__exam',
            'submission_2__student', 'submission_2__question',
        ).order_by('-similarity_score')
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
        return Response(PlagiarismFlagSerializer(flag).data)


class BehaviouralFlagListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Only trainers can view behavioural flags'}, status=status.HTTP_403_FORBIDDEN)

        qs = BehaviouralFlag.objects.select_related(
            'submission__student', 'submission__question', 'submission__exam'
        ).order_by('-risk_score', '-submission__submitted_at')

        review_status = request.query_params.get('status')
        if review_status and review_status != 'all':
            qs = qs.filter(review_status=review_status)

        serializer = BehaviouralFlagSerializer(qs, many=True)
        return Response(serializer.data)


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
            ).values('id', 'title', 'start_time', 'end_time', 'is_active')

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
        )

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


class CohortListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from submissions.models import Submission
        from exams.models import Exam

        rows = []
        for exam in Exam.objects.order_by('-start_time'):
            total = Submission.objects.filter(exam=exam).values('student_id').distinct().count()
            if total == 0:
                continue

            b_flags = BehaviouralFlag.objects.filter(submission__exam=exam)
            b_count = b_flags.count()
            b_student_ids = set(b_flags.values_list('submission__student_id', flat=True))

            s_flags = list(PlagiarismFlag.objects.filter(flagged=True, submission_1__exam=exam).select_related('submission_1', 'submission_2'))
            s_count = len(s_flags)
            s_student_ids = set()
            adj = {}
            for flag in s_flags:
                s1 = flag.submission_1.student_id
                s2 = flag.submission_2.student_id
                s_student_ids.add(s1)
                s_student_ids.add(s2)
                adj.setdefault(s1, set()).add(s2)
                adj.setdefault(s2, set()).add(s1)

            # connected components = rings
            visited = set()
            ring_count = 0
            for start in adj:
                if start in visited:
                    continue
                stack = [start]
                component = []
                while stack:
                    node = stack.pop()
                    if node in visited:
                        continue
                    visited.add(node)
                    component.append(node)
                    stack.extend(adj.get(node, set()) - visited)
                if len(component) >= 2:
                    ring_count += 1

            flagged_count = len(b_student_ids | s_student_ids)
            flag_rate = round(flagged_count / total, 3) if total else 0
            health = 'red' if flag_rate >= 0.25 else ('amber' if flag_rate >= 0.10 else 'green')

            rows.append({
                'exam_id': exam.id,
                'exam_title': exam.title,
                'total_submissions': total,
                'flagged_students': flagged_count,
                'flag_rate': flag_rate,
                'behavioural_count': b_count,
                'similarity_count': s_count,
                'ring_count': ring_count,
                'health': health,
            })

        rows.sort(key=lambda r: r['flag_rate'], reverse=True)
        return Response(rows)


class CohortDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, exam_id):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        from submissions.models import Submission
        from exams.models import Exam

        exam = Exam.objects.filter(pk=exam_id).first()
        if not exam:
            return Response({'error': 'Exam not found'}, status=status.HTTP_404_NOT_FOUND)

        subs = list(Submission.objects.filter(exam=exam).select_related('student'))
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
                    'behavioural_confidence': None,
                    'similarity_pairs': 0,
                    'max_similarity': 0.0,
                    'past_flags': 0,
                }

        for bf in BehaviouralFlag.objects.filter(submission__exam=exam).select_related('submission'):
            sid = bf.submission.student_id
            if sid in student_data:
                student_data[sid]['behavioural_risk'] = round(bf.risk_score, 3)
                student_data[sid]['behavioural_confidence'] = bf.confidence

        # Build similarity adjacency list for ring detection
        adj = {}
        sim_flags = list(
            PlagiarismFlag.objects.filter(flagged=True, submission_1__exam=exam)
            .select_related('submission_1', 'submission_2')
        )
        for flag in sim_flags:
            s1_id = flag.submission_1.student_id
            s2_id = flag.submission_2.student_id
            score = flag.similarity_score

            for sid in (s1_id, s2_id):
                if sid in student_data:
                    student_data[sid]['similarity_pairs'] += 1
                    if score > student_data[sid]['max_similarity']:
                        student_data[sid]['max_similarity'] = score

            adj.setdefault(s1_id, set()).add(s2_id)
            adj.setdefault(s2_id, set()).add(s1_id)

        # Past flags across other exams
        sub_ids_this_exam = {s.id for s in subs}
        for sid in student_data:
            past_sim = PlagiarismFlag.objects.filter(
                flagged=True
            ).filter(
                Q(submission_1__student_id=sid) | Q(submission_2__student_id=sid)
            ).exclude(
                Q(submission_1_id__in=sub_ids_this_exam) | Q(submission_2_id__in=sub_ids_this_exam)
            ).count()
            past_b = BehaviouralFlag.objects.filter(
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
        flagged_students = [s for s in student_list if s['combined_risk'] > 0]

        # Connected-component ring detection
        visited = set()
        rings = []
        component_set = {}  # node -> component index

        for start_id in adj:
            if start_id in visited:
                continue
            component = []
            stack = [start_id]
            while stack:
                node = stack.pop()
                if node in visited:
                    continue
                visited.add(node)
                component.append(node)
                stack.extend(adj.get(node, set()) - visited)

            if len(component) < 2:
                continue

            comp_set = set(component)
            ring_edges = [f for f in sim_flags
                          if f.submission_1.student_id in comp_set
                          and f.submission_2.student_id in comp_set]

            avg_sim = round(sum(f.similarity_score for f in ring_edges) / len(ring_edges), 3) if ring_edges else 0
            max_sim = round(max((f.similarity_score for f in ring_edges), default=0), 3)
            confirmed = sum(1 for f in ring_edges if f.review_status == 'confirmed')

            members = [
                {'student_id': sid, 'username': student_data[sid]['username']}
                for sid in component if sid in student_data
            ]
            rings.append({
                'size': len(members),
                'members': members,
                'avg_similarity': avg_sim,
                'max_similarity': max_sim,
                'confirmed': confirmed,
            })

        rings.sort(key=lambda r: r['size'], reverse=True)

        return Response({
            'exam': {
                'id': exam.id,
                'title': exam.title,
                'start_time': exam.start_time.isoformat() if exam.start_time else None,
                'end_time': exam.end_time.isoformat() if exam.end_time else None,
            },
            'stats': {
                'total_submissions': total,
                'flagged_students': len(flagged_students),
                'flag_rate': round(len(flagged_students) / total, 3) if total else 0,
                'behavioural_count': BehaviouralFlag.objects.filter(submission__exam=exam).count(),
                'similarity_count': len(sim_flags),
                'ring_count': len(rings),
            },
            'students': flagged_students,
            'rings': rings,
        })


class MonitoringView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.user.role != 'trainer':
            return Response({'error': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

        now = timezone.now()
        last7  = now - timedelta(days=7)
        prev7  = now - timedelta(days=14)

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
        for exam in Exam.objects.order_by('-id')[:20]:
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
