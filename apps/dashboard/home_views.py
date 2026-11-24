"""Optional external-data panel: a database failure never blocks the local student home."""
import logging
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from apps.accounts.models import User
from .student_home import today_sessions
logger=logging.getLogger(__name__)

@login_required
@never_cache
@require_GET
def today_schedule(request):
    if not request.user.is_active or request.user.role!=User.Role.STUDENT or request.user.is_superuser:
        return JsonResponse({'error':'학생 본인 계정에서 확인할 수 있습니다.'},status=403)
    try:
        return JsonResponse(today_sessions(request.user))
    except Exception as error:
        logger.warning('home_schedule_unavailable type=%s',type(error).__name__)
        return JsonResponse({'error':'수업 일정을 확인하지 못했습니다. 잠시 후 다시 확인해 주세요.'},status=503)


@login_required
@never_cache
@require_GET
def home_insights(request):
    """학생·학부모 홈 '한눈에 보기' 조각(HTML). 홈이 먼저 뜬 뒤 불러옵니다."""
    if request.user.role not in (User.Role.STUDENT, User.Role.PARENT) or request.user.is_superuser:
        raise Http404('학생·학부모 홈에서만 씁니다.')
    from .learner_insights import insight_context
    return render(request, 'dashboard/_learner_insights.html', {'insight': insight_context(request.user),
                                                                 'is_parent': request.user.role == User.Role.PARENT})
