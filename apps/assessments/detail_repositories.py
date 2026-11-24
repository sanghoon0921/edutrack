from __future__ import annotations

from datetime import datetime
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .contracts import DsgStudentProfile
from .detail_contracts import (
    ExamAttemptHeader,
    ExamQuestionDetail,
    QuestionChoiceDetail,
)
from .repositories import DemoAssessmentRepository


class ExamDetailRepository(Protocol):
    """시험 상세 저장소 공통 규격입니다."""

    def get_student_profile(
        self,
        intranet_student_id: str,
    ) -> DsgStudentProfile:
        ...

    def get_attempt(
        self,
        dsg_student_id: str,
        attempt_id: str,
    ) -> ExamAttemptHeader | None:
        ...

    def list_questions(
        self,
        dsg_student_id: str,
        exam_id: str,
    ) -> list[ExamQuestionDetail]:
        ...


def _text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _int(value) -> int:
    if value is None:
        return 0

    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _duration_label(seconds: int) -> str:
    if seconds <= 0:
        return "—"

    minutes, second = divmod(
        seconds,
        60,
    )

    if minutes:
        return f"{minutes}분 {second}초"

    return f"{second}초"


class DemoExamDetailRepository:
    """자동 테스트용 시험 상세 저장소입니다."""

    def __init__(self) -> None:
        self.profile_repository = (
            DemoAssessmentRepository()
        )

    def get_student_profile(
        self,
        intranet_student_id: str,
    ) -> DsgStudentProfile:
        return (
            self.profile_repository
            .get_student_profile(
                intranet_student_id
            )
        )

    def get_attempt(
        self,
        dsg_student_id: str,
        attempt_id: str,
    ) -> ExamAttemptHeader | None:
        if (
            dsg_student_id != "5743"
            or attempt_id != "919696"
        ):
            return None

        return ExamAttemptHeader(
            attempt_id="919696",
            exam_id="1658",
            exam_name="25WT2-TEST06",
            exam_date=datetime(
                2026,
                7,
                20,
                11,
                47,
            ),
            rw_sat_score=640,
            math_sat_score=690,
            total_sat_score=1330,
            total_questions=4,
            correct_answers=1,
            wrong_answers=2,
            accuracy_rate=25.0,
            total_duration_seconds=275,
            total_duration_label="4분 35초",
        )

    def list_questions(
        self,
        dsg_student_id: str,
        exam_id: str,
    ) -> list[ExamQuestionDetail]:
        if (
            dsg_student_id != "5743"
            or exam_id != "1658"
        ):
            return []

        return [
            ExamQuestionDetail(
                question_id="101",
                question_no=1,
                section_id="1",
                section_name="Reading & Writing",
                module_id="11",
                module_name="Module 1",
                content_type="TEXT",
                question_text="첫 번째 모의 문항입니다.",
                media_url="",
                topic="Information and Ideas",
                selected_answer="B",
                correct_answer="B",
                result_code="CORRECT",
                result_label="정답",
                result_class="correct",
                earned_score=1,
                max_score=1,
                duration_seconds=55,
                duration_label="55초",
                bookmark=False,
                annotation="",
                choices=(
                    QuestionChoiceDetail(
                        choice_id="1",
                        choice_no="A",
                        content="선택지 A",
                        content_type="TEXT",
                        partial_score=0,
                        is_correct=False,
                    ),
                    QuestionChoiceDetail(
                        choice_id="2",
                        choice_no="B",
                        content="선택지 B",
                        content_type="TEXT",
                        partial_score=0,
                        is_correct=True,
                        is_selected=True,
                    ),
                ),
            ),
            ExamQuestionDetail(
                question_id="102",
                question_no=2,
                section_id="1",
                section_name="Reading & Writing",
                module_id="11",
                module_name="Module 1",
                content_type="TEXT",
                question_text="두 번째 모의 문항입니다.",
                media_url="",
                topic="Craft and Structure",
                selected_answer="A",
                correct_answer="B",
                result_code="WRONG",
                result_label="오답",
                result_class="wrong",
                earned_score=0,
                max_score=1,
                duration_seconds=80,
                duration_label="1분 20초",
                bookmark=True,
                annotation="다시 확인",
                choices=(
                    QuestionChoiceDetail(
                        choice_id="3",
                        choice_no="A",
                        content="선택지 A",
                        content_type="TEXT",
                        partial_score=0,
                        is_correct=False,
                        is_selected=True,
                    ),
                    QuestionChoiceDetail(
                        choice_id="4",
                        choice_no="B",
                        content="선택지 B",
                        content_type="TEXT",
                        partial_score=0,
                        is_correct=True,
                    ),
                ),
            ),
            ExamQuestionDetail(
                question_id="103",
                question_no=3,
                section_id="2",
                section_name="Math",
                module_id="21",
                module_name="Module 1",
                content_type="TEXT",
                question_text="부분점수 모의 문항입니다.",
                media_url="",
                topic="Algebra",
                selected_answer="2",
                correct_answer="3",
                result_code="PARTIAL",
                result_label="부분점수",
                result_class="partial",
                earned_score=1,
                max_score=2,
                duration_seconds=90,
                duration_label="1분 30초",
                bookmark=False,
                annotation="",
                choices=(),
            ),
            ExamQuestionDetail(
                question_id="104",
                question_no=4,
                section_id="2",
                section_name="Math",
                module_id="21",
                module_name="Module 1",
                content_type="TEXT",
                question_text="무응답 모의 문항입니다.",
                media_url="",
                topic="Advanced Math",
                selected_answer="",
                correct_answer="C",
                result_code="UNANSWERED",
                result_label="무응답",
                result_class="unanswered",
                earned_score=0,
                max_score=1,
                duration_seconds=50,
                duration_label="50초",
                bookmark=False,
                annotation="",
                choices=(),
            ),
        ]


class DsgExamDetailRepository:
    """실제 서비스에서는 사내 DSG(모의고사) DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def get_exam_detail_repository() -> (
    ExamDetailRepository
):
    source = getattr(
        settings,
        "ASSESSMENT_DATA_SOURCE",
        "dsg",
    ).strip().lower()

    if source == "demo":
        return DemoExamDetailRepository()

    if source == "dsg":
        return DsgExamDetailRepository()

    if source == "disabled":
        return DemoExamDetailRepository()

    raise ImproperlyConfigured(
        "ASSESSMENT_DATA_SOURCE는 "
        "'dsg', 'demo', 'disabled' 중 하나여야 합니다."
    )
