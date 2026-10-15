from unittest.mock import patch

from django.test import SimpleTestCase, override_settings


class NotificationLinkTest(SimpleTestCase):
    """Email links point at the live site (FRONTEND_URL), never a developer's localhost."""

    @override_settings(FRONTEND_URL='https://codemas.example')
    def test_links_use_frontend_url(self):
        from types import SimpleNamespace as NS
        from codemas import notifications
        exam = NS(id=7, title='E', duration_minutes=30, enrollments=None)
        student = NS(username='s', email='s@x.y')
        sub = NS(student=student, question=NS(title='Q'), attempt_number=1, status='passed')
        flag = NS(similarity_score=0.9, submission_1=NS(student=student, exam_id=7), submission_2=NS(student=student))
        with patch.object(notifications, '_send') as send, \
             patch('django.contrib.auth.get_user_model') as users:
            users.return_value.objects.filter.return_value.values_list.return_value = ['t@x.y']
            for call, arg in ((notifications.notify_result_ready, sub), (notifications.notify_plagiarism_flagged, flag)):
                send.reset_mock()
                call(arg)
                body = send.call_args.kwargs['body']
                self.assertNotIn('localhost', body)
                self.assertIn('https://codemas.example/', body)
            self.assertIn('https://codemas.example/dashboard/plagiarism/cohorts/7', body)
