from __future__ import annotations

from django.contrib.auth.mixins import AccessMixin, LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RoleRequiredMixin(LoginRequiredMixin, AccessMixin):
    """향후 class-based view에서 재사용할 역할 권한 mixin입니다."""

    allowed_roles: tuple[str, ...] = ()

    def dispatch(self, request, *args, **kwargs):
        user = request.user
        if user.is_superuser or user.role in self.allowed_roles:
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied("이 페이지에 접근할 권한이 없습니다.")
