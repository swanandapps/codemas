import json
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from . import services
from .execute import payload_for
from .models import Job
from .signing import secret_problem, token_ok


class BadRequest(ValueError):
    pass


def _body(request):
    """The JSON object and its job_id, canonicalised. BadRequest (400) if either is malformed."""
    try:
        data = json.loads(request.body or b'{}')
    except ValueError as e:
        raise BadRequest(f'body is not JSON: {e}')
    if not isinstance(data, dict):
        raise BadRequest('body must be a JSON object')
    try:
        job_id = str(uuid.UUID(str(data['job_id'])))
    except KeyError:
        raise BadRequest("'job_id' is required")
    except ValueError:
        raise BadRequest('job_id is not a UUID')
    return {**data, 'job_id': job_id}


class JobTokenView(View):
    """Internal endpoints for the executor. Authenticated by the per-job token in the body
    (jobs.signing.job_token), which only the relay can mint; complete and fail also need the lease."""
    def post(self, request):
        if settings.JOB_SIGNING_SECRET_REQUIRED and secret_problem(settings.JOB_SIGNING_SECRET):
            # fail closed even if the process was started with --skip-checks (jobs.E001 stops it otherwise)
            return JsonResponse({'error': 'internal API disabled: signing secret not configured'}, status=503)
        try:
            data = _body(request)
        except BadRequest as e:
            return JsonResponse({'error': f'bad request: {e}'}, status=400)
        if not token_ok(data['job_id'], data.get('token')):
            return JsonResponse({'error': 'bad token'}, status=401)
        try:
            return self.handle(data)
        except Job.DoesNotExist:
            return JsonResponse({'error': 'unknown job'}, status=404)
        except (ValueError, KeyError, TypeError, ValidationError) as e:  # e.g. no lease_token
            return JsonResponse({'error': f'bad request: {e}'}, status=400)


@method_decorator(csrf_exempt, name='dispatch')
class ClaimView(JobTokenView):
    def handle(self, data):
        try:
            job, submission = services.claim(data['job_id'])
        except services.JobDone:
            return JsonResponse({'error': 'done'}, status=409)
        except services.JobBusy:
            return JsonResponse({'error': 'busy'}, status=409)
        except services.JobGone:
            return JsonResponse({'error': 'gone'}, status=410)
        except services.JobDead:
            return JsonResponse({'error': 'dead'}, status=410)
        return JsonResponse({'job_id': str(job.id), 'lease_token': str(job.lease_token), 'kind': job.kind,
                             **payload_for(submission)})


@method_decorator(csrf_exempt, name='dispatch')
class CompleteView(JobTokenView):
    def handle(self, data):
        try:
            job, submission_status = services.complete(data['job_id'], data['lease_token'], data.get('results', []))
        except services.StaleLease:
            return JsonResponse({'error': 'stale'}, status=409)
        return JsonResponse({'status': job.status, 'submission_status': submission_status})


@method_decorator(csrf_exempt, name='dispatch')
class FailView(JobTokenView):
    def handle(self, data):
        try:
            services.fail(data['job_id'], data['lease_token'], data.get('error', ''))
        except services.StaleLease:
            return JsonResponse({'error': 'stale'}, status=409)
        return JsonResponse({'status': 'released'})
