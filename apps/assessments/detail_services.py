from __future__ import annotations

from django.conf import settings
from config.cache_utils import safe_cache_delete, safe_cache_get, safe_cache_set

from .detail_contracts import (
    ExamAttemptDetail,
)
from .detail_repositories import (
    ExamDetailRepository,
    get_exam_detail_repository,
)


CACHE_VERSION = "v4"


class ExamDetailService:
    """시험 응시 상세와 문항 요약을 계산하고 캐시합니다."""

    def __init__(
        self,
        repository: ExamDetailRepository | None = None,
    ) -> None:
        self.repository = (
            repository
            or get_exam_detail_repository()
        )

    @staticmethod
    def cache_key(
        intranet_student_id: str,
        attempt_id: str,
    ) -> str:
        return (
            "edutrack:exam-detail:"
            f"{CACHE_VERSION}:"
            f"{intranet_student_id.strip()}:"
            f"{attempt_id.strip()}"
        )

    def clear_attempt_cache(
        self,
        intranet_student_id: str,
        attempt_id: str,
    ) -> None:
        safe_cache_delete(
            self.cache_key(
                intranet_student_id,
                attempt_id,
            )
        )

    def get_attempt_detail(
        self,
        intranet_student_id: str,
        attempt_id: str,
        *,
        force_refresh: bool = False,
    ) -> ExamAttemptDetail:
        cleaned_student_id = (
            intranet_student_id.strip()
        )
        cleaned_attempt_id = (
            attempt_id.strip()
        )

        key = self.cache_key(
            cleaned_student_id,
            cleaned_attempt_id,
        )

        if not force_refresh:
            cached = safe_cache_get(key)

            if cached is not None:
                return cached

        detail = self._load_attempt_detail(
            cleaned_student_id,
            cleaned_attempt_id,
        )

        cache_seconds = int(
            getattr(
                settings,
                "EXAM_DETAIL_CACHE_SECONDS",
                900,
            )
        )

        if cache_seconds > 0:
            safe_cache_set(
                key,
                detail,
                timeout=cache_seconds,
            )

        return detail

    def _load_attempt_detail(
        self,
        intranet_student_id: str,
        attempt_id: str,
    ) -> ExamAttemptDetail:
        profile = (
            self.repository
            .get_student_profile(
                intranet_student_id
            )
        )

        if profile.status != "ok":
            messages = {
                "not_connected": (
                    "DSG 학생 계정이 연결되지 않았습니다."
                ),
                "mapping_not_found": (
                    "인트라넷 학생과 DSG 학생 매핑을 찾지 못했습니다."
                ),
                "not_found": (
                    "학생 정보를 찾지 못했습니다."
                ),
                "disabled": (
                    "DSG 성적 기능이 비활성화되어 있습니다."
                ),
            }

            return ExamAttemptDetail(
                status=profile.status,
                message=messages.get(
                    profile.status,
                    "DSG 학생 연결 상태를 확인해 주세요.",
                ),
            )

        attempt = (
            self.repository.get_attempt(
                profile.dsg_student_id,
                attempt_id,
            )
        )

        if attempt is None:
            return ExamAttemptDetail(
                status="not_found",
                message=(
                    "해당 학생의 시험 응시 결과를 찾지 못했습니다."
                ),
            )

        questions = (
            self.repository.list_questions(
                profile.dsg_student_id,
                attempt.exam_id,
            )
        )

        correct_count = sum(
            item.result_code
            == "CORRECT"
            for item in questions
        )
        partial_count = sum(
            item.result_code
            == "PARTIAL"
            for item in questions
        )
        wrong_count = sum(
            item.result_code
            == "WRONG"
            for item in questions
        )
        unanswered_count = sum(
            item.result_code
            == "UNANSWERED"
            for item in questions
        )
        free_response_count = sum(
            item.result_code
            == "FREE_RESPONSE"
            for item in questions
        )
        earned_score = sum(
            item.earned_score
            for item in questions
        )
        max_score = sum(
            item.max_score
            for item in questions
        )

        item_score_rate = (
            earned_score
            / max_score
            * 100
            if max_score > 0
            else None
        )

        return ExamAttemptDetail(
            status="ok",
            student_id=(
                intranet_student_id
            ),
            student_name=profile.name,
            dsg_student_id=(
                profile.dsg_student_id
            ),
            attempt=attempt,
            questions=tuple(
                questions
            ),
            correct_count=(
                correct_count
            ),
            partial_count=(
                partial_count
            ),
            wrong_count=wrong_count,
            unanswered_count=(
                unanswered_count
            ),
            free_response_count=(
                free_response_count
            ),
            earned_score=(
                earned_score
            ),
            max_score=max_score,
            item_score_rate=(
                item_score_rate
            ),
        )
