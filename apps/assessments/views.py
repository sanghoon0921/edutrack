from __future__ import annotations

from django.contrib.auth.decorators import (
    login_required,
)
from django.core.exceptions import (
    PermissionDenied,
)
from django.db.utils import DatabaseError
from django.http import (
    Http404,
    HttpRequest,
    HttpResponse,
)
from django.shortcuts import render

from apps.accounts.models import User
from apps.operations.access import require_student_access
from apps.students.services import StudentService

from .detail_contracts import (
    ExamQuestionDetail,
)
from .detail_services import (
    ExamDetailService,
)
from .insight_services import (
    ExamInsightService,
)
from .cumulative_services import (
    StudentLearningInsightService,
)


def get_student_service() -> StudentService:
    return StudentService()


def get_exam_detail_service() -> (
    ExamDetailService
):
    return ExamDetailService()


def get_student_learning_insight_service() -> (
    StudentLearningInsightService
):
    return StudentLearningInsightService()


def ensure_student_access(
    request: HttpRequest,
    *,
    student,
    student_service: StudentService,
) -> None:
    require_student_access(
        request.user,
        student.student_id,
    )


def _question_payload(
    question: ExamQuestionDetail,
    *,
    is_slow: bool,
) -> dict:
    return {
        "question_id": (
            question.question_id
        ),
        "question_no": (
            question.question_no
        ),
        "result_label": (
            question.result_label
        ),
        "result_class": (
            question.result_class
        ),
        "earned_score": (
            question.earned_score
        ),
        "max_score": (
            question.max_score
        ),
        "topic": question.topic,
        "section_name": (
            question.section_name
        ),
        "module_name": (
            question.module_name
        ),
        "duration_label": (
            question.duration_label
        ),
        "bookmark": (
            question.bookmark
        ),
        "question_text": (
            question.question_text
        ),
        "media_url": (
            question.media_url
        ),
        "selected_answer": (
            question.selected_answer
        ),
        "correct_answer": (
            question.correct_answer
        ),
        "annotation": (
            question.annotation
        ),
        "is_slow": is_slow,
        "choices": [
            {
                "choice_no": (
                    choice.choice_no
                ),
                "content": (
                    choice.content
                ),
                "is_correct": (
                    choice.is_correct
                ),
                "is_selected": (
                    choice.is_selected
                ),
            }
            for choice in question.choices
        ],
    }


@login_required
def attempt_detail(
    request: HttpRequest,
    student_id: str,
    attempt_id: str,
) -> HttpResponse:
    try:
        student_service = (
            get_student_service()
        )

        student = (
            student_service.get_student(
                student_id
            )
        )

    except DatabaseError:
        return render(
            request,
            "errors/503.html",
            {
                "page_title": (
                    "학생 데이터 연결 오류"
                ),
            },
            status=503,
        )

    if student is None:
        raise Http404(
            "학생 정보를 찾을 수 없습니다."
        )

    ensure_student_access(
        request,
        student=student,
        student_service=student_service,
    )

    force_refresh = (
        request.GET.get("refresh")
        == "1"
        and (
            request.user.is_superuser
            or request.user.role
            == User.Role.ADMIN
        )
    )

    try:
        detail = (
            get_exam_detail_service()
            .get_attempt_detail(
                student.student_id,
                attempt_id,
                force_refresh=force_refresh,
            )
        )

    except (
        DatabaseError,
        ValueError,
    ):
        return render(
            request,
            "errors/503.html",
            {
                "page_title": (
                    "DSG 시험 데이터 연결 오류"
                ),
            },
            status=503,
        )

    if detail.status == "not_found":
        raise Http404(
            detail.message
        )

    selected_question_id = (
        request.GET.get(
            "question",
            "",
        ).strip()
    )

    selected_question = None

    if detail.status == "ok":
        selected_question = next(
            (
                item
                for item in detail.questions
                if item.question_id
                == selected_question_id
            ),
            None,
        )

        if selected_question is None:
            selected_question = next(
                (
                    item
                    for item in detail.questions
                    if item.result_code
                    in {
                        "WRONG",
                        "PARTIAL",
                        "UNANSWERED",
                    }
                ),
                detail.questions[0]
                if detail.questions
                else None,
            )

    exam_insight = (
        ExamInsightService().build(
            detail.questions
        )
        if detail.status == "ok"
        else ExamInsightService().build(
            []
        )
    )

    slow_question_ids = set(
        exam_insight.slow_question_ids
    )

    payload = [
        _question_payload(
            item,
            is_slow=(
                item.question_id
                in slow_question_ids
            ),
        )
        for item in detail.questions
    ] if detail.status == "ok" else []

    return render(
        request,
        "assessments/exam_attempt_detail.html",
        {
            "page_title": (
                f"{student.name} · "
                f"{detail.attempt.exam_name}"
                if (
                    detail.status == "ok"
                    and detail.attempt
                )
                else "시험 상세"
            ),
            "student": student,
            "detail": detail,
            "selected_question": (
                selected_question
            ),
            "selected_question_id": (
                selected_question.question_id
                if selected_question
                else ""
            ),
            "question_payload": payload,
            "exam_insight": exam_insight,
            "cache_seconds": 900,
        },
    )

@login_required
def student_learning_insight(
    request: HttpRequest,
    student_id: str,
) -> HttpResponse:
    try:
        student_service = (
            get_student_service()
        )

        student = (
            student_service.get_student(
                student_id
            )
        )

    except DatabaseError:
        return render(
            request,
            "errors/503.html",
            {
                "page_title": (
                    "학생 데이터 연결 오류"
                ),
            },
            status=503,
        )

    if student is None:
        raise Http404(
            "학생 정보를 찾을 수 없습니다."
        )

    ensure_student_access(
        request,
        student=student,
        student_service=student_service,
    )

    force_refresh = (
        request.GET.get("refresh")
        == "1"
        and (
            request.user.is_superuser
            or request.user.role
            == User.Role.ADMIN
        )
    )

    try:
        insight = (
            get_student_learning_insight_service()
            .get_student_insight(
                student.student_id,
                force_refresh=force_refresh,
            )
        )

    except (
        DatabaseError,
        ValueError,
    ):
        return render(
            request,
            "errors/503.html",
            {
                "page_title": (
                    "DSG 누적 분석 연결 오류"
                ),
            },
            status=503,
        )

    return render(
        request,
        "assessments/student_learning_insight.html",
        {
            "page_title": (
                f"{student.name} 누적 학습 인사이트"
            ),
            "student": student,
            "learning_insight": insight,
        },
    )

