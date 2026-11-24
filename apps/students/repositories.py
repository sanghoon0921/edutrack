from __future__ import annotations

from typing import Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .contracts import StudentSummary


class StudentRepository(Protocol):
    """학생 저장소 공통 규격입니다."""

    def search(
        self,
        keyword: str,
    ) -> list[StudentSummary]:
        ...

    def get_by_id(
        self,
        student_id: str,
    ) -> StudentSummary | None:
        ...

    def list_by_ids(
        self,
        student_ids: list[str],
    ) -> list[StudentSummary]:
        ...


def _to_text(value) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _fetch_all_as_dicts(cursor) -> list[dict]:
    columns = [
        column[0]
        for column in cursor.description
    ]

    return [
        dict(zip(columns, row))
        for row in cursor.fetchall()
    ]


DEMO_STUDENTS: tuple[
    StudentSummary,
    ...,
] = (
    StudentSummary(
        student_id="6333",
        name="김지훈",
        english_name="Jeehoon Kim",
        grade="10학년",
        country="태국",
        city="방콕",
        school="Ekamai International School",
        branch="본원",
        status="재원",
        dsg_id="5743",
        dsg_connected=True,
    ),
    StudentSummary(
        student_id="7102",
        name="이서연",
        english_name="Seoyeon Lee",
        grade="11학년",
        country="미국",
        city="뉴욕",
        school="International School",
        branch="온라인",
        status="재원",
        dsg_id="",
        dsg_connected=False,
    ),
    StudentSummary(
        student_id="8201",
        name="박민준",
        english_name="Minjun Park",
        grade="9학년",
        country="한국",
        city="서울",
        school="International Academy",
        branch="본원",
        status="휴원",
        dsg_id="",
        dsg_connected=False,
    ),
)


def extra_demo_students(count: int) -> tuple[StudentSummary, ...]:
    """테스트 서버(가짜 자료)에서 쪽 넘김을 시험할 가짜 학생(11/11). 학생번호 9001부터, 실제 사람과 무관한 조합 이름."""
    surnames = "김이박최정강조윤장임한오서신권황안송류홍"
    given = ["민준", "서연", "도윤", "하은", "시우", "지유", "주원", "서윤", "예준", "지안", "하준", "수아", "지호", "아린", "건우", "유나"]
    schools = ["International School", "Global Academy", "American School", "British School", "Prep Academy"]
    places = [("한국", "서울"), ("미국", "뉴욕"), ("태국", "방콕"), ("베트남", "호치민"), ("중국", "상하이"), ("싱가포르", "싱가포르")]
    out = []
    for i in range(count):
        country, city = places[i % len(places)]
        out.append(StudentSummary(
            student_id=str(9001 + i), name=f"{surnames[i % len(surnames)]}{given[(i // len(surnames)) % len(given)]}",
            english_name="", grade=f"{7 + i % 6}학년", country=country, city=city, school=schools[i % len(schools)],
            branch="온라인" if i % 3 else "본원", status="휴원" if i % 11 == 0 else "재원", dsg_id="", dsg_connected=False))
    return tuple(out)


# 테스트 서버(config.settings.share)만 가짜 학생을 더 둡니다. 자동 테스트·데모는 3명 그대로.
_EXTRA = int(getattr(settings, "DEMO_EXTRA_STUDENTS", 0) or 0)
if _EXTRA > 0:
    DEMO_STUDENTS = DEMO_STUDENTS + extra_demo_students(_EXTRA)


class DemoStudentRepository:
    """자동 테스트용 모의 학생 저장소입니다."""

    def search(
        self,
        keyword: str,
    ) -> list[StudentSummary]:
        cleaned = keyword.strip().casefold()

        if not cleaned:
            return []

        results = []

        for student in DEMO_STUDENTS:
            haystack = " ".join(
                (
                    student.student_id,
                    student.name,
                    student.english_name,
                    student.school,
                    student.grade,
                    student.country,
                    student.city,
                    student.branch,
                    student.status,
                    student.dsg_id,
                )
            ).casefold()

            if cleaned in haystack:
                results.append(student)

        return results

    def get_by_id(
        self,
        student_id: str,
    ) -> StudentSummary | None:
        cleaned = student_id.strip()

        return next(
            (
                student
                for student in DEMO_STUDENTS
                if student.student_id
                == cleaned
            ),
            None,
        )

    def list_by_ids(
        self,
        student_ids: list[str],
    ) -> list[StudentSummary]:
        ordered_ids = list(
            dict.fromkeys(
                str(student_id).strip()
                for student_id in student_ids
                if str(student_id).strip()
            )
        )
        student_map = {
            student.student_id: student
            for student in DEMO_STUDENTS
        }
        return [
            student_map[student_id]
            for student_id in ordered_ids
            if student_id in student_map
        ]

    # 기존 코드와의 호환용 별칭입니다.
    def search_students(
        self,
        keyword: str,
    ) -> list[StudentSummary]:
        return self.search(keyword)

    def get_student(
        self,
        student_id: str,
    ) -> StudentSummary | None:
        return self.get_by_id(student_id)


class IntranetStudentRepository:
    """실제 서비스에서는 사내 인트라넷 DB를 읽기 전용으로 조회하는 구현이 이 자리에 있습니다.

    공개용 사본에서는 회사 내부 DB 구조가 드러나지 않도록 구현을 뺐습니다.
    화면과 테스트는 같은 틀(Protocol)을 따르는 Demo 저장소(가짜 자료)로 똑같이 동작합니다.
    """

    def __init__(self, *args, **kwargs):
        from config.excluded import ExternalSourceExcluded

        raise ExternalSourceExcluded(type(self).__name__)


def get_student_repository() -> (
    StudentRepository
):
    data_source = getattr(
        settings,
        "STUDENT_DATA_SOURCE",
        "intranet",
    ).strip().lower()

    if data_source == "demo":
        return DemoStudentRepository()

    if data_source == "intranet":
        return IntranetStudentRepository()

    raise ImproperlyConfigured(
        "STUDENT_DATA_SOURCE는 "
        "'demo' 또는 'intranet'이어야 합니다."
    )
