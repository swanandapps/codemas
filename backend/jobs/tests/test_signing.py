import hashlib
import hmac
import uuid

from django.test import SimpleTestCase, override_settings

from jobs.signing import job_token, token_ok

SECRET = 's3cret'
JOB = '6f1c2f0e-8a4b-4c1e-9d3a-0b5e7c9a1d2f'


@override_settings(JOB_SIGNING_SECRET=SECRET)
class JobTokenTest(SimpleTestCase):
    def test_token_is_hmac_sha256_of_job_prefix_and_id_in_hex(self):
        expected = hmac.new(SECRET.encode(), f'job:{JOB}'.encode(), hashlib.sha256).hexdigest()
        self.assertEqual(job_token(JOB), expected)
        self.assertEqual(job_token(uuid.UUID(JOB)), expected)  # a UUID and its str() give the same token

    def test_round_trip(self):
        self.assertTrue(token_ok(JOB, job_token(JOB)))

    def test_another_jobs_token_is_refused(self):
        self.assertFalse(token_ok(JOB, job_token(str(uuid.uuid4()))))

    def test_a_token_minted_with_another_secret_is_refused(self):
        with override_settings(JOB_SIGNING_SECRET='other'):
            forged = job_token(JOB)
        self.assertFalse(token_ok(JOB, forged))

    def test_missing_or_garbage_tokens_are_refused_without_raising(self):
        for token in (None, '', 'abc', 123, ['x'], {'t': 1}, 'é' * 64, job_token(JOB).upper()):
            self.assertFalse(token_ok(JOB, token), repr(token))
