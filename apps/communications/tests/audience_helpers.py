"""테스트용: 예전 '대상 하나' 값(ALL·STAFF·LEARNER·…)을 대상 그룹 체크 칸으로 바꿉니다."""
GROUPS = {
    "ALL": ["ADMIN", "TEACHER", "STUDENT", "PARENT"],
    "STAFF": ["ADMIN", "TEACHER"],
    "LEARNER": ["STUDENT", "PARENT"],
    "ADMIN": ["ADMIN"],
    "TEACHER": ["TEACHER"],
    "STUDENT": ["STUDENT"],
    "PARENT": ["PARENT"],
}


def audience_post(old):
    """폼으로 보낼 'audiences' 값."""
    return list(GROUPS[old])


def audience_flags(old):
    """Notice.objects.create(...)에 넘길 for_* 칸."""
    return {f"for_{group.lower()}": True for group in GROUPS[old]}
