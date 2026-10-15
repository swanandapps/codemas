"""Per-job tokens for the internal job API.

The relay (trusted, holds JOB_SIGNING_SECRET) puts job_token(job_id) in each message. The executor
sends it back on claim, complete and fail; Django recomputes it. The executor never holds the secret,
so student code that reads the executor's memory or environment gets at most its own job's token."""
import hashlib
import hmac

from django.conf import settings


def job_token(job_id):
    """HMAC-SHA256(JOB_SIGNING_SECRET, "job:<job_id>"), hex. job_id is a UUID or its canonical str()."""
    return hmac.new(settings.JOB_SIGNING_SECRET.encode(), f'job:{job_id}'.encode(), hashlib.sha256).hexdigest()


def token_ok(job_id, token):
    """Constant-time check of a token sent by the executor. Anything that isn't a str is refused."""
    if not isinstance(token, str) or not token:
        return False
    return hmac.compare_digest(job_token(job_id).encode(), token.encode('utf-8', 'replace'))


DEV_DEFAULT_SECRET = 'dev-only-change-me'
MIN_SECRET_LENGTH = 32


def secret_problem(secret):
    """Why this secret must not mint production job tokens, or None when it is fine."""
    if not secret:
        return 'JOB_SIGNING_SECRET is empty'
    if secret.startswith(DEV_DEFAULT_SECRET):
        return 'JOB_SIGNING_SECRET is the development default'
    if len(secret) < MIN_SECRET_LENGTH:
        return f'JOB_SIGNING_SECRET is shorter than {MIN_SECRET_LENGTH} characters'
    return None
