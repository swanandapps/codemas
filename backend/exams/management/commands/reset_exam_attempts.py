"""Put named students back to "never attempted" on one exam, for demo rehearsals.

Removes those students' submissions on the exam and everything hanging off them:
results, rubric reviews, hints, behavioural flags, similarity pairs (and their AI
explanations), plus the records that point at those by id without a foreign key:
execution jobs, trainer review log entries and appeals (theirs on this exam too). Also drops the students'
cached exam summaries and the exam's manual plagiarism reruns (rehearsal runs; the
real run is the one at exam close).

Dry run by default; pass --yes to delete. Code drafts live in the browser, not here:
clear site data for the app in each browser profile you rehearsed in.

    python manage.py reset_exam_attempts --exam 21 --users riya_verma,kabir_malhotra
    python manage.py reset_exam_attempts --exam 21 --users riya_verma,kabir_malhotra --yes
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from accounts.models import User
from ai.models import AIHint, ExamSummary, PlagiarismExplanation, RubricScore
from exams.models import Exam, ExamEnrollment
from jobs.models import Job
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, PlagiarismRun, ReviewAuditLog
from results.models import Result
from submissions.models import Submission
from support.models import DisputeRequest


class Command(BaseCommand):
    help = 'Reset named students to "never attempted" on one exam (dry run unless --yes).'

    def add_arguments(self, parser):
        parser.add_argument('--exam', type=int, required=True, help='Exam id')
        parser.add_argument('--users', required=True, help='Comma-separated usernames')
        parser.add_argument('--yes', action='store_true', help='Actually delete')

    def handle(self, *args, **opts):
        exam = Exam.objects.filter(pk=opts['exam']).first()
        if not exam:
            raise CommandError(f"No exam {opts['exam']}")
        names = [n.strip() for n in opts['users'].split(',') if n.strip()]
        students = list(User.objects.filter(username__in=names))
        missing = set(names) - {s.username for s in students}
        if missing:
            raise CommandError(f"Unknown usernames: {', '.join(sorted(missing))}")

        subs = Submission.objects.filter(exam=exam, student__in=students)
        sub_ids = list(subs.values_list('id', flat=True))
        b_ids = list(BehaviouralFlag.objects.filter(submission_id__in=sub_ids).values_list('id', flat=True))
        p_flags = PlagiarismFlag.objects.filter(Q(submission_1_id__in=sub_ids) | Q(submission_2_id__in=sub_ids))
        p_ids = list(p_flags.values_list('id', flat=True))
        by_flag = Q(flag_type='behavioural', flag_id__in=b_ids) | Q(flag_type='similarity', flag_id__in=p_ids)

        plan = [
            ('submissions', subs),
            ('test results', Result.objects.filter(submission_id__in=sub_ids)),
            ('rubric reviews', RubricScore.objects.filter(submission_id__in=sub_ids)),
            ('hints', AIHint.objects.filter(submission_id__in=sub_ids)),
            ('behavioural flags', BehaviouralFlag.objects.filter(id__in=b_ids)),
            ('similarity pairs', p_flags),
            ('AI pair explanations', PlagiarismExplanation.objects.filter(flag_id__in=p_ids)),
            ('execution jobs', Job.objects.filter(kind=Job.KIND_EXECUTE, subject_id__in=sub_ids)),
            ('review log entries', ReviewAuditLog.objects.filter(by_flag)),
            ('disputes', DisputeRequest.objects.filter(by_flag | Q(exam=exam, student__in=students))),
            ('exam summaries', ExamSummary.objects.filter(exam=exam, student__in=students)),
            ('manual plagiarism reruns', PlagiarismRun.objects.filter(exam=exam, trigger='manual_rerun')),
        ]
        self.stdout.write(f'Exam {exam.id} "{exam.title}", students: {", ".join(sorted(s.username for s in students))}')
        ended = ExamEnrollment.objects.filter(exam=exam, student__in=students, finished_at__isnull=False).count()
        self.stdout.write(f'  {ended:>5}  ended exams (End exam is undone)')
        for label, qs in plan:
            self.stdout.write(f'  {qs.count():>5}  {label}')

        if not opts['yes']:
            self.stdout.write('Dry run: nothing deleted. Re-run with --yes to delete.')
            return

        with transaction.atomic():
            # Rows that point at flags/submissions by plain id first; the rest cascade
            # from the submissions (results, rubric, hints, flags, explanations).
            for label in ('execution jobs', 'review log entries', 'disputes', 'exam summaries',
                          'manual plagiarism reruns'):
                dict(plan)[label].delete()
            subs.delete()
            ExamEnrollment.objects.filter(exam=exam, student__in=students).update(finished_at=None)
        self.stdout.write(self.style.SUCCESS(
            f'Reset {len(students)} students on exam {exam.id}: they have every attempt back.'
        ))
