from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Any

from django.conf import settings

from config.cache_utils import (
    build_cache_key,
    safe_cache_get,
    safe_cache_get_many,
    safe_cache_set,
    safe_cache_set_many,
)

from .attendance_repositories import (
    AttendanceRepository,
    get_attendance_repository,
)
from .contracts import (
    AttendanceRecord,
    AttendanceSummary,
)


class AttendanceService:
    """출결 목록, 요약, 날짜 묶음을 계산합니다."""

    STATUS_PRIORITY = {
        "absent": 1,
        "late": 2,
        "recorded": 3,
        "present": 4,
        "unprocessed": 5,
        "carried": 6,
        "refunded": 6,
        "cancelled": 6,
        "holiday": 7,
        "upcoming": 8,
        "other": 9,
    }

    STATUS_LABELS = {
        "present": "출석",
        "absent": "결석",
        "late": "지각",
        "recorded": "녹화",
        "upcoming": "예정",
        "unprocessed": "미처리",
        "carried": "이월",
        "refunded": "환불",
        "cancelled": "개별취소",
        "holiday": "학원휴강",
        "mixed": "혼합",
        "other": "기타",
    }

    def __init__(
        self,
        repository: AttendanceRepository | None = None,
    ) -> None:
        self._uses_default_repository = repository is None
        self.repository = repository or get_attendance_repository()

    @staticmethod
    def _cache_key(student_id: str, assign_id: str) -> str:
        source = str(getattr(settings, "STUDENT_DATA_SOURCE", "intranet")).strip()
        return build_cache_key(
            "attendance",
            "v1",
            source,
            student_id,
            assign_id,
        )

    def _cache_seconds(self) -> int:
        if not self._uses_default_repository:
            return 0
        return max(0, int(getattr(settings, "ATTENDANCE_CACHE_SECONDS", 60)))

    def get_attendance(
        self,
        student_id: str,
        assign_id: str,
    ) -> tuple[
        list[AttendanceRecord],
        AttendanceSummary,
    ]:
        cleaned_student_id = str(student_id).strip()
        cleaned_assign_id = str(assign_id).strip()
        if not cleaned_student_id or not cleaned_assign_id:
            records: list[AttendanceRecord] = []
            return records, self._build_summary(records)

        timeout = self._cache_seconds()
        key = self._cache_key(cleaned_student_id, cleaned_assign_id)
        if timeout > 0:
            cached = safe_cache_get(key)
            if isinstance(cached, list):
                return cached, self._build_summary(cached)

        records = self.repository.list_by_student_and_assign(
            cleaned_student_id,
            cleaned_assign_id,
        )
        if timeout > 0:
            safe_cache_set(key, records, timeout=timeout)
        return records, self._build_summary(records)

    def get_attendance_for_courses(
        self,
        student_id: str,
        assign_ids: list[str],
    ) -> dict[str, tuple[list[AttendanceRecord], AttendanceSummary]]:
        """여러 수업 출결을 한 번에 조회하고 수업 단위로 짧게 캐시합니다."""

        cleaned_student_id = str(student_id).strip()
        ordered_ids = list(
            dict.fromkeys(
                str(assign_id).strip()
                for assign_id in assign_ids
                if str(assign_id).strip()
            )
        )
        if not cleaned_student_id or not ordered_ids:
            return {}

        timeout = self._cache_seconds()
        key_by_assign = {
            assign_id: self._cache_key(cleaned_student_id, assign_id)
            for assign_id in ordered_ids
        }
        cached_by_key = (
            safe_cache_get_many(key_by_assign.values())
            if timeout > 0
            else {}
        )
        records_by_assign: dict[str, list[AttendanceRecord]] = {}
        missing_ids: list[str] = []

        for assign_id, key in key_by_assign.items():
            cached = cached_by_key.get(key)
            if isinstance(cached, list):
                records_by_assign[assign_id] = cached
            else:
                missing_ids.append(assign_id)

        if missing_ids:
            bulk_loader = getattr(
                self.repository,
                "list_by_student_and_assigns",
                None,
            )
            if callable(bulk_loader):
                loaded = bulk_loader(cleaned_student_id, missing_ids)
            else:
                loaded = {
                    assign_id: self.repository.list_by_student_and_assign(
                        cleaned_student_id,
                        assign_id,
                    )
                    for assign_id in missing_ids
                }

            cache_payload: dict[str, list[AttendanceRecord]] = {}
            for assign_id in missing_ids:
                records = loaded.get(assign_id, [])
                records_by_assign[assign_id] = records
                cache_payload[key_by_assign[assign_id]] = records
            if timeout > 0:
                safe_cache_set_many(cache_payload, timeout=timeout)

        return {
            assign_id: (
                records_by_assign.get(assign_id, []),
                self._build_summary(records_by_assign.get(assign_id, [])),
            )
            for assign_id in ordered_ids
        }

    def _build_summary(
        self,
        records: list[AttendanceRecord],
    ) -> AttendanceSummary:
        present_count = self._count(records, "present")
        absent_count = self._count(records, "absent")
        late_count = self._count(records, "late")
        recorded_count = self._count(records, "recorded")
        upcoming_count = self._count(records, "upcoming")
        unprocessed_count = self._count(records, "unprocessed")
        cancelled_count = self._count(records, "cancelled")
        holiday_count = self._count(records, "holiday")
        completed_count = present_count + absent_count + late_count + recorded_count
        recognized_count = present_count + late_count + recorded_count
        attendance_rate = (
            recognized_count / completed_count * 100
            if completed_count > 0
            else None
        )
        return AttendanceSummary(
            scheduled_count=len(records),
            completed_count=completed_count,
            recognized_count=recognized_count,
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            recorded_count=recorded_count,
            upcoming_count=upcoming_count,
            unprocessed_count=unprocessed_count,
            cancelled_count=cancelled_count,
            holiday_count=holiday_count,
            attendance_rate=attendance_rate,
        )

    def calculate_extended_metrics(
        self,
        summary: AttendanceSummary,
    ) -> dict[str, float | None]:
        """
        예정 회차를 포함한 전체 과정 기준 지표를 계산합니다.

        현재 출석률:
            이미 처리된 회차 중 출석 인정 비율

        전체 출석 달성률:
            전체 계획 회차 중 현재까지 출석 인정한 비율
            예정 회차가 분모에 포함됩니다.

        수강 진행률:
            전체 계획 회차 중 출결 처리가 끝난 비율
        """

        scheduled_count = (
            summary.scheduled_count
        )

        if scheduled_count <= 0:
            return {
                "attendance_rate": None,
                "overall_achievement_rate": None,
                "course_progress_rate": None,
            }

        overall_achievement_rate = (
            summary.recognized_count
            / scheduled_count
            * 100
        )

        course_progress_rate = (
            summary.completed_count
            / scheduled_count
            * 100
        )

        return {
            "attendance_rate": (
                summary.attendance_rate
            ),
            "overall_achievement_rate": (
                overall_achievement_rate
            ),
            "course_progress_rate": (
                course_progress_rate
            ),
        }

    def build_day_groups(
        self,
        records: list[AttendanceRecord],
        *,
        reverse: bool = False,
    ) -> list[dict[str, Any]]:
        """
        같은 날짜의 여러 레슨을 날짜 카드 하나로 묶습니다.
        """

        grouped: OrderedDict[
            date | None,
            list[AttendanceRecord],
        ] = OrderedDict()

        sorted_records = sorted(
            records,
            key=lambda record: (
                record.lesson_date
                or date.min,
                record.time_summary,
                record.lesson_id,
            ),
            reverse=reverse,
        )

        for record in sorted_records:
            grouped.setdefault(
                record.lesson_date,
                [],
            ).append(record)

        day_groups: list[
            dict[str, Any]
        ] = []

        for lesson_date, day_records in grouped.items():
            status_kinds = {
                record.status_kind
                for record in day_records
            }

            if len(status_kinds) == 1:
                status_kind = next(
                    iter(status_kinds)
                )
            else:
                status_kind = "mixed"

            status_labels = list(
                dict.fromkeys(
                    record.attendance_label
                    for record in day_records
                )
            )

            day_groups.append(
                {
                    "lesson_date": lesson_date,
                    "records": day_records,
                    "session_count": len(
                        day_records
                    ),
                    "status_kind": (
                        status_kind
                    ),
                    "status_label": (
                        self.STATUS_LABELS.get(
                            status_kind,
                            "혼합",
                        )
                    ),
                    "status_summary": " · ".join(
                        status_labels
                    ),
                }
            )

        return day_groups

    def split_grouped_records(
        self,
        records: list[AttendanceRecord],
    ) -> dict[str, list[dict[str, Any]]]:
        """
        예정 수업과 지난 출결 기록을 완전히 분리합니다.
        """

        upcoming_records = [
            record
            for record in records
            if record.status_kind
            == "upcoming"
        ]

        history_records = [
            record
            for record in records
            if record.status_kind
            != "upcoming"
        ]

        return {
            "upcoming_groups": (
                self.build_day_groups(
                    upcoming_records,
                    reverse=False,
                )
            ),
            "history_groups": (
                self.build_day_groups(
                    history_records,
                    reverse=True,
                )
            ),
        }

    @staticmethod
    def _count(
        records: list[AttendanceRecord],
        status_kind: str,
    ) -> int:
        return sum(
            1
            for record in records
            if record.status_kind
            == status_kind
        )
