from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from config.cache_utils import build_cache_key


@dataclass(frozen=True)
class ClassCatalogFilters:
    start_date: date | None = None
    end_date: date | None = None
    status: str = ""
    learning_method: str = ""
    keyword: str = ""


@dataclass(frozen=True)
class ClassCatalogItem:
    class_id: str
    branch_name: str
    start_date: date | None
    end_date: date | None
    term_name: str
    subject_name: str
    class_name: str
    schedule_summary: str
    lesson_summary: str
    teacher_names: str
    status_code: str
    status_label: str
    learning_methods: str
    weekdays: str
    assigned_student_count: int


class ClassCatalogRepository(Protocol):
    def search(
        self,
        filters: ClassCatalogFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ClassCatalogItem], int]:
        ...


DEMO_CLASSES: tuple[ClassCatalogItem, ...] = (
    ClassCatalogItem(
        class_id="1001",
        branch_name="본원",
        start_date=date(2026, 8, 22),
        end_date=date(2026, 12, 5),
        term_name="2026 가을 정규",
        subject_name="AP",
        class_name="AP Human Geography",
        schedule_summary="20:00–22:00",
        lesson_summary="Lecture",
        teacher_names="이강사",
        status_code="W",
        status_label="대기",
        learning_methods="온라인",
        weekdays="토",
        assigned_student_count=30,
    ),
    ClassCatalogItem(
        class_id="999",
        branch_name="본원",
        start_date=date(2026, 9, 13),
        end_date=date(2026, 12, 6),
        term_name="2026 가을 정규",
        subject_name="The NOBEL",
        class_name="미주 Journal Reading",
        schedule_summary="10:00–12:00",
        lesson_summary="Lecture",
        teacher_names="최강사",
        status_code="W",
        status_label="대기",
        learning_methods="온라인",
        weekdays="일",
        assigned_student_count=10,
    ),
)


class DemoClassCatalogRepository:
    def search(
        self,
        filters: ClassCatalogFilters,
        *,
        limit: int,
        offset: int,
    ) -> tuple[list[ClassCatalogItem], int]:
        items = list(DEMO_CLASSES)
        keyword = filters.keyword.strip().casefold()
        if keyword:
            items = [
                item
                for item in items
                if keyword
                in " ".join(
                    (
                        item.class_id,
                        item.branch_name,
                        item.term_name,
                        item.subject_name,
                        item.class_name,
                        item.teacher_names,
                    )
                ).casefold()
            ]
        if filters.status:
            items = [item for item in items if item.status_code == filters.status]
        if filters.learning_method:
            method_label = {
                "ONLINE": "온라인",
                "OFFLINE": "오프라인",
                "ALL": "온·오프라인",
            }.get(filters.learning_method, filters.learning_method)
            items = [item for item in items if method_label in item.learning_methods]
        if filters.start_date:
            items = [
                item
                for item in items
                if item.end_date is None or item.end_date >= filters.start_date
            ]
        if filters.end_date:
            items = [
                item
                for item in items
                if item.start_date is None or item.start_date <= filters.end_date
            ]
        total = len(items)
        return items[offset : offset + limit], total


def _to_text(value) -> str:
    return "" if value is None else str(value).strip()


def _to_int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _to_date(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    cleaned = str(value).strip()
    if not cleaned:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


class IntranetClassCatalogRepository:
    """실제 서비스에서는 사내 인트라넷 DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def catalog_source() -> str:
    return str(
        getattr(settings, "CLASS_CATALOG_DATA_SOURCE", getattr(settings, "STUDENT_DATA_SOURCE", "demo"))
    ).strip().lower()


def get_class_catalog_repository() -> ClassCatalogRepository:
    source = catalog_source()
    if source == "demo":
        return DemoClassCatalogRepository()
    if source == "intranet":
        return IntranetClassCatalogRepository()
    raise ImproperlyConfigured(
        "CLASS_CATALOG_DATA_SOURCE는 'demo' 또는 'intranet'이어야 합니다."
    )


class ClassCatalogService:
    def __init__(self, repository: ClassCatalogRepository | None = None) -> None:
        self.repository = repository or get_class_catalog_repository()

    def search(
        self,
        filters: ClassCatalogFilters,
        *,
        page: int = 1,
        page_size: int = 30,
    ) -> tuple[list[ClassCatalogItem], int]:
        safe_page = max(1, int(page))
        safe_size = max(1, min(int(page_size), 100))
        return self.repository.search(
            filters,
            limit=safe_size,
            offset=(safe_page - 1) * safe_size,
        )


logger = logging.getLogger(__name__)
TERM_SUBJECT_TTL = 600
TERM_SUBJECT_LIMIT = 200


@dataclass(frozen=True)
class TermSubjectOptions:
    terms: tuple[str, ...]
    subjects: tuple[str, ...]
    ok: bool


def term_subject_cache_key(source: str) -> str:
    return build_cache_key("class-catalog", "term-subject", "v1", source)


def _demo_term_subject() -> TermSubjectOptions:
    from apps.students.course_repositories import DEMO_COURSES

    courses = [course for group in DEMO_COURSES.values() for course in group]
    terms = {c.term_name for c in courses} | {c.term_name for c in DEMO_CLASSES}
    subjects = {c.subject_name for c in courses} | {c.subject_name for c in DEMO_CLASSES}
    return TermSubjectOptions(
        tuple(sorted((t for t in terms if t), reverse=True)),
        tuple(sorted(s for s in subjects if s)),
        True,
    )


def term_subject_options() -> TermSubjectOptions:
    """Term·Subject 드롭다운 값. 인트라넷 값은 10분 동안 캐시하고, 실패하면 ok=False(캐시 안 함)."""
    source = catalog_source()
    if source == "demo":
        return _demo_term_subject()
    # 실제 서비스에서는 여기서 사내 DB를 읽기 전용으로 조회합니다(공개용 사본에서는 뺐습니다).
    from config.excluded import ExternalSourceExcluded

    raise ExternalSourceExcluded('term_subject_options')
