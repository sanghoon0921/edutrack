from __future__ import annotations

from datetime import datetime
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .contracts import (
    DsgStudentProfile,
    ExamAttemptSummary,
    ModuleAttemptSummary,
)


class AssessmentRepository(Protocol):
    """시험·성적 저장소의 공통 규격입니다."""

    def get_student_profile(
        self,
        intranet_student_id: str,
    ) -> DsgStudentProfile:
        ...

    def list_exam_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ExamAttemptSummary]:
        ...

    def list_module_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ModuleAttemptSummary]:
        ...


def _to_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _to_int(value) -> int:
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _to_float(value) -> float | None:
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value) -> datetime | None:
    if value is None:
        return None

    if isinstance(value, datetime):
        return value

    cleaned = str(value).strip()

    if not cleaned:
        return None

    for date_format in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                cleaned,
                date_format,
            )
        except ValueError:
            continue

    return None


def _classify_score(
    *,
    rw_attempted: bool,
    math_attempted: bool,
    rw_score: int | None,
    math_score: int | None,
    total_score: int | None,
) -> tuple[str, str, int | None, int]:
    if (
        rw_attempted
        and math_attempted
        and total_score is not None
    ):
        return (
            "FULL",
            "전체 SAT",
            total_score,
            1600,
        )

    if (
        rw_attempted
        and not math_attempted
        and rw_score is not None
    ):
        return (
            "RW",
            "RW 단독",
            rw_score,
            800,
        )

    if (
        math_attempted
        and not rw_attempted
        and math_score is not None
    ):
        return (
            "MATH",
            "Math 단독",
            math_score,
            800,
        )

    if total_score is not None:
        return (
            "FULL",
            "SAT",
            total_score,
            1600,
        )

    if rw_score is not None:
        return (
            "RW",
            "RW 단독",
            rw_score,
            800,
        )

    if math_score is not None:
        return (
            "MATH",
            "Math 단독",
            math_score,
            800,
        )

    return (
        "UNKNOWN",
        "점수 미확인",
        None,
        1600,
    )


def _module_attempt(row) -> ModuleAttemptSummary:
    """Module 시험 한 줄(칸 순서가 정해진 튜플)을 화면용 요약으로 바꿉니다."""
    (
        attempt_id, module_id, module_name, taken_at,
        rw_total, rw_correct, math_total, math_correct,
        total_questions, correct_answers, wrong_answers, accuracy_rate,
        *rest,
    ) = row
    answered = rest[0] if rest else 0
    has_rw, has_math = _to_int(rw_total) > 0, _to_int(math_total) > 0
    section = "RW·Math" if has_rw and has_math else ("RW" if has_rw else ("Math" if has_math else ""))
    return ModuleAttemptSummary(
        attempt_id=_to_text(attempt_id),
        module_id=_to_text(module_id),
        module_name=_to_text(module_name),
        taken_at=_to_datetime(taken_at),
        section_label=section,
        total_questions=_to_int(total_questions),
        correct_answers=_to_int(correct_answers),
        wrong_answers=_to_int(wrong_answers),
        accuracy_rate=_to_float(accuracy_rate),
        answered_questions=_to_int(answered),
    )


class EmptyAssessmentRepository:
    """성적 기능이 비활성화된 환경에서 사용합니다."""

    def get_student_profile(
        self,
        intranet_student_id: str,
    ) -> DsgStudentProfile:
        return DsgStudentProfile(
            status="disabled",
        )

    def list_exam_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ExamAttemptSummary]:
        return []

    def list_module_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ModuleAttemptSummary]:
        return []


class DemoAssessmentRepository:
    """자동 테스트용 모의 성적 저장소입니다."""

    def get_student_profile(
        self,
        intranet_student_id: str,
    ) -> DsgStudentProfile:
        if intranet_student_id != "6333":
            return DsgStudentProfile(
                status="not_connected",
            )

        return DsgStudentProfile(
            status="ok",
            dsg_student_id="5743",
            dsg_key="5743",
            name="김지훈",
            school="Ekamai International School",
            grade="10",
            matched_field="id",
        )

    def list_exam_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ExamAttemptSummary]:
        if dsg_student_id != "5743":
            return []

        rows = [
            (
                "919690",
                "1580",
                "25WT2-TEST03",
                datetime(2026, 3, 10, 10, 0),
                520,
                670,
                1190,
                98,
                64,
                34,
                65.31,
                True,
                True,
            ),
            (
                "919691",
                "1582",
                "[RW]25FA-TEST03",
                datetime(2026, 4, 2, 10, 0),
                540,
                0,
                540,
                54,
                29,
                25,
                53.70,
                True,
                False,
            ),
            (
                "919693",
                "1655",
                "25WT2-TEST04",
                datetime(2026, 5, 8, 10, 0),
                570,
                680,
                1250,
                98,
                69,
                29,
                70.41,
                True,
                True,
            ),
            (
                "919695",
                "1657",
                "25WT2-TEST05",
                datetime(2026, 6, 12, 10, 0),
                500,
                690,
                1190,
                98,
                65,
                33,
                66.33,
                True,
                True,
            ),
            (
                "919696",
                "1658",
                "25WT2-TEST06",
                datetime(2026, 7, 20, 11, 47),
                640,
                690,
                1330,
                98,
                74,
                24,
                75.51,
                True,
                True,
            ),
        ]

        attempts: list[ExamAttemptSummary] = []

        for row in rows:
            (
                attempt_id,
                exam_id,
                exam_name,
                exam_date,
                rw_score,
                math_score,
                total_score,
                total_questions,
                correct_answers,
                wrong_answers,
                accuracy_rate,
                rw_attempted,
                math_attempted,
            ) = row

            score_type, label, display_score, max_score = (
                _classify_score(
                    rw_attempted=rw_attempted,
                    math_attempted=math_attempted,
                    rw_score=rw_score or None,
                    math_score=math_score or None,
                    total_score=total_score or None,
                )
            )

            attempts.append(
                ExamAttemptSummary(
                    attempt_id=attempt_id,
                    exam_id=exam_id,
                    exam_name=exam_name,
                    exam_date=exam_date,
                    rw_sat_score=rw_score or None,
                    math_sat_score=math_score or None,
                    total_sat_score=total_score or None,
                    total_questions=total_questions,
                    correct_answers=correct_answers,
                    wrong_answers=wrong_answers,
                    accuracy_rate=accuracy_rate,
                    rw_attempted=rw_attempted,
                    math_attempted=math_attempted,
                    score_type=score_type,
                    score_type_label=label,
                    display_score=display_score,
                    max_score=max_score,
                )
            )

        return attempts

    def list_module_attempts(
        self,
        dsg_student_id: str,
    ) -> list[ModuleAttemptSummary]:
        if dsg_student_id != "5743":
            return []
        rows = [
            ("51", "7", "Math Module 1", datetime(2026, 6, 20, 10, 0), 0, 0, 22, 15, 22, 15, 7, 68.18, 22),
            ("52", "9", "RW Module 2 · Hard", datetime(2026, 7, 3, 10, 0), 27, 20, 0, 0, 27, 20, 7, 74.07, 27),
        ]
        return [_module_attempt(row) for row in rows]


class DsgAssessmentRepository:
    """실제 서비스에서는 사내 DSG(모의고사) DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def get_assessment_repository() -> (
    AssessmentRepository
):
    data_source = getattr(
        settings,
        "ASSESSMENT_DATA_SOURCE",
        "dsg",
    ).strip().lower()

    if data_source == "dsg":
        return DsgAssessmentRepository()

    if data_source == "demo":
        return DemoAssessmentRepository()

    if data_source == "disabled":
        return EmptyAssessmentRepository()

    raise ImproperlyConfigured(
        "ASSESSMENT_DATA_SOURCE는 "
        "'dsg', 'demo', 'disabled' 중 하나여야 합니다."
    )
