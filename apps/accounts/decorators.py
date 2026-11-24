from __future__ import annotations

from functools import wraps
from typing import Callable

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse

from .models import User


ViewFunction = Callable[..., HttpResponse]


def role_required(
    *allowed_roles: str,
) -> Callable[[ViewFunction], ViewFunction]:
    """로그인 여부와 사용자 역할을 서버에서 검증합니다."""

    def decorator(
        view_func: ViewFunction,
    ) -> ViewFunction:
        @login_required
        @wraps(view_func)
        def wrapped(
            request: HttpRequest,
            *args,
            **kwargs,
        ) -> HttpResponse:
            user = request.user

            if (
                user.is_superuser
                or user.role in allowed_roles
            ):
                return view_func(
                    request,
                    *args,
                    **kwargs,
                )

            raise PermissionDenied(
                "이 페이지에 접근할 권한이 없습니다."
            )

        return wrapped

    return decorator


def parent_required(
    view_func: ViewFunction,
) -> ViewFunction:
    """학부모 개인 화면은 PARENT 역할만 접근하도록 제한합니다."""

    @login_required
    @wraps(view_func)
    def wrapped(
        request: HttpRequest,
        *args,
        **kwargs,
    ) -> HttpResponse:
        if request.user.role == User.Role.PARENT:
            return view_func(
                request,
                *args,
                **kwargs,
            )

        raise PermissionDenied(
            "학부모 계정만 접근할 수 있습니다."
        )

    return wrapped


admin_required = role_required(
    User.Role.ADMIN,
)
teacher_required = role_required(
    User.Role.ADMIN,
    User.Role.TEACHER,
)
# 반별 학습의 과제 화면(만들기·첨삭): 관리자·강사에 더해 TA 계정도(11/17). 어느 반인지는 각 화면이 staff_group_ids 로 다시 거릅니다.
class_staff_required = role_required(
    User.Role.ADMIN,
    User.Role.TEACHER,
    User.Role.TA,
)
student_required = role_required(
    User.Role.ADMIN,
    User.Role.STUDENT,
    User.Role.PARENT,
)
learner_required = role_required(
    User.Role.STUDENT,
    User.Role.PARENT,
)
