import redis
import json
import os
from django.http import StreamingHttpResponse, JsonResponse
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken
from django.contrib.auth import get_user_model
from submissions.models import Submission

User = get_user_model()


def get_user_from_token(request):
    """Authenticate via Bearer header or ?token= query param (needed for EventSource)."""
    token_str = None

    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if auth_header.startswith('Bearer '):
        token_str = auth_header.split(' ', 1)[1]
    else:
        token_str = request.GET.get('token')

    if not token_str:
        return None

    try:
        token = AccessToken(token_str)
        user_id = token['user_id']
        return User.objects.filter(pk=user_id).first()
    except (TokenError, InvalidToken, KeyError):
        return None


def submission_stream(request, submission_id):
    user = get_user_from_token(request)
    if not user:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    submission = Submission.objects.filter(pk=submission_id).first()
    if not submission:
        return JsonResponse({'error': 'Submission not found'}, status=404)

    if user.role != 'trainer' and submission.student != user:
        return JsonResponse({'error': 'Not allowed'}, status=403)

    def event_stream():
        r = redis.Redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
        pubsub = r.pubsub()
        channel = f"submission:{submission_id}"
        pubsub.subscribe(channel)

        yield f"data: {json.dumps({'status': 'waiting'})}\n\n"

        terminal = {'passed', 'failed', 'error'}
        for message in pubsub.listen():
            if message['type'] == 'message':
                payload = message['data'].decode('utf-8')
                yield f"data: {payload}\n\n"
                if json.loads(payload).get('status') in terminal:
                    break

        pubsub.unsubscribe(channel)

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response
