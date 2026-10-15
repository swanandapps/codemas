import json
import uuid

from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import TestCase, override_settings

from jobs.checks import check_job_signing_secret
from jobs.signing import job_token

STRONG = 'a1' * 32


class SigningSecretGuardTest(TestCase):
    def test_weak_secrets_are_errors_when_required(self):
        for secret in ('', 'dev-only-change-me', 'short-but-not-default'):
            with self.subTest(secret=secret), override_settings(JOB_SIGNING_SECRET_REQUIRED=True,
                                                                JOB_SIGNING_SECRET=secret):
                self.assertEqual([e.id for e in check_job_signing_secret(None)], ['jobs.E001'])

    def test_strong_secret_or_debug_passes(self):
        with override_settings(JOB_SIGNING_SECRET_REQUIRED=True, JOB_SIGNING_SECRET=STRONG):
            self.assertEqual(check_job_signing_secret(None), [])
        with override_settings(JOB_SIGNING_SECRET_REQUIRED=False, JOB_SIGNING_SECRET='dev-only-change-me'):
            self.assertEqual(check_job_signing_secret(None), [])

    @override_settings(JOB_SIGNING_SECRET_REQUIRED=True, JOB_SIGNING_SECRET='dev-only-change-me')
    def test_startup_commands_refuse(self):
        # migrate and run_relay run the same checks before doing anything
        with self.assertRaisesMessage(SystemCheckError, 'jobs.E001'):
            call_command('check')

    @override_settings(JOB_SIGNING_SECRET_REQUIRED=True, JOB_SIGNING_SECRET='dev-only-change-me')
    def test_internal_api_refuses_even_a_valid_token(self):
        job_id = str(uuid.uuid4())
        body = json.dumps({'job_id': job_id, 'token': job_token(job_id), 'lease_token': str(uuid.uuid4())}).encode()
        for path in ('claim', 'complete', 'fail'):
            resp = self.client.post(f'/internal/jobs/{path}/', body, content_type='application/json')
            self.assertEqual(resp.status_code, 503, path)
