from __future__ import annotations

import logging

from django.db.utils import DatabaseError
from django.utils.connection import ConnectionDoesNotExist
from django.core.exceptions import ImproperlyConfigured
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
)
from django.shortcuts import render

from apps.accounts.decorators import parent_required
from apps.accounts.student_links import (
    get_primary_student_no,
)
from apps.students.services import StudentService

from .services import BillingService


logger = logging.getLogger(__name__)


def get_billing_service() -> BillingService:
    return BillingService()


def get_student_service() -> StudentService:
    return StudentService()


@parent_required
def my_payment_history(
    request: HttpRequest,
) -> HttpResponse:
    student_no = get_primary_student_no(
        request.user
    )

    if student_no is None:
        raise Http404(
            "학부모 계정에 연결된 학생 정보가 없습니다."
        )

    try:
        billing_service = (
            get_billing_service()
        )
        histories = (
            billing_service
            .get_payment_histories(
                student_no
            )
        )

        student = (
            get_student_service()
            .get_student(student_no)
        )

    except (DatabaseError, ConnectionDoesNotExist, ImproperlyConfigured):
        logger.exception(
            "학부모 수납내역 조회 중 DB 오류 발생"
        )

        return render(
            request,
            "errors/503.html",
            {
                "page_title": (
                    "수납 데이터 연결 오류"
                ),
            },
            status=503,
        )

    return render(
        request,
        "billing/my_payment_history.html",
        {
            "page_title": "수납내역",
            "student_no": student_no,
            "student": student,
            "histories": histories,
            "billing_is_demo": bool(getattr(billing_service, "is_demo", False)),
            "totals": (
                billing_service
                .build_totals(histories)
            ),
        },
    )
