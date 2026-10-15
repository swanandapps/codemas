from django.conf import settings
from django.core.checks import Error, Tags, register

from .signing import secret_problem


@register(Tags.security)
def check_job_signing_secret(app_configs, **kwargs):
    """jobs.E001: stops migrate (so web never reaches gunicorn) and run_relay when the signing
    secret is missing, the dev default, or short. collectstatic runs only the staticfiles checks,
    so the Docker build step is unaffected."""
    if not settings.JOB_SIGNING_SECRET_REQUIRED:
        return []
    problem = secret_problem(settings.JOB_SIGNING_SECRET)
    if problem is None:
        return []
    return [Error(
        f'{problem}: anyone could mint job tokens for /internal/jobs/* (read code and tests, write grades).',
        hint='Set JOB_SIGNING_SECRET on web and relay to one value (openssl rand -hex 32). The Lambda never gets it.',
        id='jobs.E001',
    )]
