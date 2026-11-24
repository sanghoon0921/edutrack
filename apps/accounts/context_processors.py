from __future__ import annotations

from typing import Any

from .models import User


ADMIN_NAVIGATION = [
    {"label": "홈", "url_name": "dashboard"},
    {"label": "학생 관리", "url_name": "students:list", "active_prefixes": ("students:", "assessments:")},
    {"label": "수업 관리", "url_name": "admin_classes"},
    {"label": "계정관리", "url_name": "operations:dashboard", "active_prefixes": ("operations:", "data_imports:")},
]

TEACHER_NAVIGATION = [
    {"label": "홈", "url_name": "dashboard"},
    {"label": "담당 수업", "url_name": "teacher_classes"},
    {"label": "담당 학생", "url_name": "students:list", "active_prefixes": ("students:", "assessments:")},
    {"label": "담당 학생 지정", "url_name": "operations:teacher-student-assignment", "active_prefixes": ("operations:teacher-student-assignment",)},
    {"label": "성적 분석", "url_name": "teacher_grades"},
    {"label": "공지사항", "url_name": "communications:notice-list", "active_prefixes": ("communications:",)},
]

STUDENT_NAVIGATION = [
    {"label": "홈", "url_name": "dashboard"},
    {"label": "내 정보", "url_name": "students:my-detail", "active_prefixes": ("students:",)},
    {"label": "내 수업", "url_name": "student_classes"},
    {"label": "내 출결", "url_name": "student_attendance"},
    {"label": "내 학습", "url_name": "assignments:my", "active_prefixes": ("assignments:", "learning:")},
    {"label": "수업 자료", "url_name": "classroom:board-list", "active_prefixes": ("classroom:",)},
    {"label": "내 성적", "url_name": "student_grades", "active_prefixes": ("assessments:",)},
    {"label": "공지사항", "url_name": "communications:notice-list", "active_prefixes": ("communications:",)},
]

TA_NAVIGATION = [
    {"label": "홈", "url_name": "dashboard"},
    # 11/19 TA 권한: 담당 반 학생 정보·DSG, 반별 학습 전체(과제·토론·퀴즈·자료·반 공지), 리포트카드, 메신저·공지
    {"label": "담당 학생", "url_name": "students:list", "active_prefixes": ("students:",)},
    {"label": "성적 분석", "url_name": "teacher_grades", "active_prefixes": ("assessments:",)},
    {"label": "반별 학습", "url_name": "lms:rooms", "active_prefixes": (
        "lms:room", "lms:post", "lms:gradebook", "lms:submission", "lms:quiz", "lms:document", "assignments:", "learning:")},
    {"label": "리포트카드", "url_name": "reports:list", "active_prefixes": ("reports:",)},
]

PARENT_NAVIGATION = [
    {"label": "홈", "url_name": "dashboard"},
    {"label": "자녀 정보", "url_name": "students:my-detail", "active_prefixes": ("students:",)},
    {"label": "현재 수업", "url_name": "student_classes"},
    {"label": "출결", "url_name": "student_attendance"},
    {"label": "학습", "url_name": "assignments:my", "active_prefixes": ("assignments:", "learning:")},
    {"label": "수업 자료", "url_name": "classroom:board-list", "active_prefixes": ("classroom:",)},
    {"label": "성적", "url_name": "student_grades", "active_prefixes": ("assessments:",)},
    {"label": "수납내역", "url_name": "billing:my-history", "active_prefixes": ("billing:",)},
    {"label": "공지사항", "url_name": "communications:notice-list", "active_prefixes": ("communications:",)},
]


# No new DB reads in the common header.
# 관리자·강사: 과제·학습, 과목 자료, 성적·제출현황을 반별 학습 하나로 모읍니다(운영팀 10/29). 그 화면들은 반 화면의 탭에서 열리고,
# 열려 있을 때 '반별 학습' 메뉴가 켜집니다. 학생·학부모 메뉴는 그대로입니다.
for _nav in (ADMIN_NAVIGATION, TEACHER_NAVIGATION):
    _nav.append({"label": "반별 학습", "url_name": "lms:rooms", "active_prefixes": (
        "lms:room", "lms:post", "lms:roster", "lms:gradebook", "lms:submission", "lms:quiz", "lms:document", "assignments:", "learning:", "classroom:")})
for _nav in (STUDENT_NAVIGATION, PARENT_NAVIGATION):
    _nav.append({"label": "반별 학습", "url_name": "lms:rooms", "active_prefixes": ("lms:room", "lms:post", "lms:roster")})
    _nav.append({"label": "성적·제출현황", "url_name": "lms:gradebook", "active_prefixes": ("lms:gradebook", "lms:submission", "lms:quiz", "lms:document")})
for _nav in (ADMIN_NAVIGATION, TEACHER_NAVIGATION):
    _nav.append({"label": "리포트카드", "url_name": "reports:list", "active_prefixes": ("reports:",)})
for _nav in (STUDENT_NAVIGATION, PARENT_NAVIGATION):
    _nav.append({"label": "리포트카드", "url_name": "reports:my", "active_prefixes": ("reports:my",)})
for _nav in (ADMIN_NAVIGATION, TEACHER_NAVIGATION, STUDENT_NAVIGATION, TA_NAVIGATION):
    _nav.append({"label": "메시지", "url_name": "lms:inbox", "active_prefixes": ("lms:inbox", "lms:conversation", "lms:new-conversation")})


# 메뉴별 아이콘(templates/components/icon_sprite.html 의 i-*)과 색 구역(static/css/layers/97-polish.css 의 data-area)
NAV_META = {
    "dashboard": ("home", "home"),
    "students:list": ("users", "students"),
    "students:my-detail": ("user", "students"),
    "operations:teacher-student-assignment": ("user-plus", "students"),
    "admin_classes": ("calendar", "classes"),
    "teacher_classes": ("calendar", "classes"),
    "student_classes": ("calendar", "classes"),
    "student_attendance": ("calendar-check", "classes"),
    "assignments:list": ("clipboard", "learning"),
    "assignments:my": ("clipboard", "learning"),
    "lms:rooms": ("layers", "learning"),
    "classroom:board-list": ("folder", "resources"),
    "teacher_grades": ("chart", "grades"),
    "student_grades": ("chart", "grades"),
    "lms:gradebook": ("list-check", "grades"),
    "reports:list": ("file", "grades"),
    "reports:my": ("file", "grades"),
    "billing:my-history": ("receipt", "billing"),
    "lms:inbox": ("message", "messages"),
    "communications:notice-list": ("megaphone", "notices"),
    "operations:dashboard": ("settings", "ops"),
}


def _build_navigation(items: list[dict[str, Any]], current_view_name: str) -> list[dict[str, Any]]:
    navigation_items: list[dict[str, Any]] = []
    for item in items:
        prefixes = tuple(item.get("active_prefixes", ()))
        is_active = current_view_name == item["url_name"] or any(
            current_view_name.startswith(prefix) for prefix in prefixes
        )
        icon, area = NAV_META.get(item["url_name"], ("dot", "home"))
        navigation_items.append({**item, "is_active": is_active, "icon": icon, "area": area})
    return navigation_items


def _sidebar_navigation(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group display links without changing URLs or permission checks."""
    ordinary, messenger, settings_links = [], [], []
    for item in items:
        name = item["url_name"]
        if name in {"lms:inbox", "communications:notice-list"}:
            messenger.append(item)
        elif name == "operations:dashboard":
            settings_links.append(item)
        else:
            ordinary.append({"kind": "link", **item})
    if messenger:
        messenger.sort(key=lambda x: x["url_name"] != "lms:inbox")
        ordinary.append({"kind": "group", "key": "messenger", "label": "메신저", "children": messenger,
                         "is_active": any(x["is_active"] for x in messenger)})
    if settings_links:
        ordinary.append({"kind": "group", "key": "settings", "label": "설정", "children": settings_links,
                         "is_active": any(x["is_active"] for x in settings_links)})
    return ordinary


def navigation(request) -> dict[str, Any]:
    user = request.user
    if not user.is_authenticated:
        return {"role_navigation": [], "sidebar_navigation": [], "current_url_name": "", "current_area": "home"}

    if user.is_superuser or user.role == User.Role.ADMIN:
        items = ADMIN_NAVIGATION
    elif user.role == User.Role.TEACHER:
        items = TEACHER_NAVIGATION
    elif user.role == User.Role.TA:
        items = TA_NAVIGATION
    elif user.role == User.Role.PARENT:
        items = PARENT_NAVIGATION
    else:
        items = STUDENT_NAVIGATION

    current_view_name = ""
    if request.resolver_match is not None:
        current_view_name = request.resolver_match.view_name or ""

    # Admin did not previously have a notice-list sidebar shortcut.
    items = [dict(item) for item in items]
    if not any(item["url_name"] == "communications:notice-list" for item in items):
        items.append({"label": "공지사항", "url_name": "communications:notice-list", "active_prefixes": ("communications:",)})
    # Account management always belongs at the end; existing operations screens stay intact.
    items.sort(key=lambda item: item["url_name"] == "operations:dashboard")
    built = _build_navigation(items, current_view_name)
    # 공지사항 아래 '전체 공지'(학원 공지)·'반 공지'(11/10): 마우스를 올리거나 누르면 펼쳐지고, 공지 화면에서는 펼쳐 둡니다.
    kind = request.GET.get("kind", "") if current_view_name == "communications:notice-list" else ""
    for item in built:
        if item["url_name"] == "communications:notice-list":
            item["subs"] = [
                {"label": "전체 공지", "query": "?kind=academy", "is_active": kind == "academy"},
                {"label": "반 공지", "query": "?kind=class", "is_active": kind == "class"},
            ]
    active = next((item for item in built if item["is_active"]), None)
    return {
        "role_navigation": built,
        "sidebar_navigation": _sidebar_navigation(built),
        "current_url_name": current_view_name,
        "current_area": active["area"] if active else "home",
    }
