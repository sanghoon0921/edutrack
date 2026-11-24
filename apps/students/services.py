from __future__ import annotations

from django.conf import settings

from apps.accounts.student_links import get_primary_student_no_by_username
from config.cache_utils import (
    build_cache_key,
    safe_cache_get,
    safe_cache_get_many,
    safe_cache_set,
    safe_cache_set_many,
)

from .contracts import StudentSummary
from .repositories import StudentRepository, get_student_repository


CACHE_VERSION = "v1"
_CACHE_VALUE_KEY = "value"


class StudentService:
    """학생 검색·상세 조회와 계정-학생 연결을 처리합니다."""

    def __init__(self, repository: StudentRepository | None = None) -> None:
        self._uses_default_repository = repository is None
        self.repository = repository or get_student_repository()

    @staticmethod
    def _cache_key(student_id: str) -> str:
        source = str(getattr(settings, "STUDENT_DATA_SOURCE", "intranet")).strip()
        return build_cache_key(
            "student-profile",
            CACHE_VERSION,
            source,
            student_id,
        )

    @staticmethod
    def _cache_seconds() -> int:
        return max(
            0,
            int(getattr(settings, "STUDENT_PROFILE_CACHE_SECONDS", 60)),
        )

    def search_students(self, keyword: str) -> list[StudentSummary]:
        cleaned = keyword.strip()
        if not cleaned:
            return []
        # 검색어 조합은 매우 많으므로 결과 전체를 캐시하지 않습니다.
        return self.repository.search(cleaned)

    def get_student(self, student_id: str) -> StudentSummary | None:
        cleaned = student_id.strip()
        if not cleaned:
            return None

        cache_seconds = self._cache_seconds() if self._uses_default_repository else 0
        key = self._cache_key(cleaned)
        if cache_seconds > 0:
            wrapped = safe_cache_get(key)
            if isinstance(wrapped, dict) and _CACHE_VALUE_KEY in wrapped:
                return wrapped[_CACHE_VALUE_KEY]

        student = self.repository.get_by_id(cleaned)
        if cache_seconds > 0:
            # 존재하지 않는 번호도 짧게 보관해 반복 오입력 조회를 줄입니다.
            safe_cache_set(
                key,
                {_CACHE_VALUE_KEY: student},
                timeout=cache_seconds,
            )
        return student

    def get_students(self, student_ids: list[str]) -> list[StudentSummary]:
        ordered_ids = list(
            dict.fromkeys(
                str(student_id).strip()
                for student_id in student_ids
                if str(student_id).strip()
            )
        )
        if not ordered_ids:
            return []

        if not self._uses_default_repository or self._cache_seconds() <= 0:
            return self._load_students(ordered_ids)

        keys = {
            student_id: self._cache_key(student_id)
            for student_id in ordered_ids
        }
        cached_values = safe_cache_get_many(keys.values())
        student_map: dict[str, StudentSummary | None] = {}
        missing_ids: list[str] = []

        for student_id, key in keys.items():
            wrapped = cached_values.get(key)
            if isinstance(wrapped, dict) and _CACHE_VALUE_KEY in wrapped:
                student_map[student_id] = wrapped[_CACHE_VALUE_KEY]
            else:
                missing_ids.append(student_id)

        if missing_ids:
            loaded_students = self._load_students(missing_ids)
            loaded_map = {
                student.student_id: student
                for student in loaded_students
            }
            cache_payload: dict[str, dict[str, StudentSummary | None]] = {}
            for student_id in missing_ids:
                student = loaded_map.get(student_id)
                student_map[student_id] = student
                cache_payload[keys[student_id]] = {_CACHE_VALUE_KEY: student}
            safe_cache_set_many(
                cache_payload,
                timeout=self._cache_seconds(),
            )

        return [
            student_map[student_id]
            for student_id in ordered_ids
            if student_map.get(student_id) is not None
        ]

    def _load_students(self, student_ids: list[str]) -> list[StudentSummary]:
        bulk_loader = getattr(self.repository, "list_by_ids", None)
        if callable(bulk_loader):
            return bulk_loader(student_ids)
        return [
            student
            for student_id in student_ids
            if (student := self.repository.get_by_id(student_id)) is not None
        ]

    def get_student_id_for_username(self, username: str) -> str | None:
        cleaned_username = username.strip()

        # 활성 DB 연결을 최우선으로 사용해 이전 테스트 학생 권한이 남지 않게 합니다.
        linked_student_no = get_primary_student_no_by_username(cleaned_username)
        if linked_student_no:
            return str(linked_student_no).strip()

        account_map = getattr(settings, "STUDENT_ACCOUNT_MAP", {})
        mapped_student_id = (
            account_map.get(cleaned_username)
            if isinstance(account_map, dict)
            else None
        )
        if mapped_student_id:
            return str(mapped_student_id).strip()

        if cleaned_username == getattr(
            settings,
            "DEMO_STUDENT_USERNAME",
            "student_test",
        ):
            fallback_id = str(
                getattr(settings, "STUDENT_TEST_STUDENT_ID", "6333")
            ).strip()
            if fallback_id:
                return fallback_id

        direct_student = self.get_student(cleaned_username)
        if direct_student is not None:
            return direct_student.student_id
        return None
