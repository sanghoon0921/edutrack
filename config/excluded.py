"""공개용 사본 전용: 회사 내부 DB(인트라넷·DSG) 연동 코드를 뺀 자리를 부르면 나는 오류입니다.

이 사본은 demo 모드(코드 안의 가짜 자료)로만 동작합니다.
"""


from django.db import DatabaseError


class ExternalSourceExcluded(DatabaseError):
    def __init__(self, name: str = ""):
        super().__init__(f"{name}: 공개용 사본에서는 사내 DB 연동 코드를 뺐습니다. demo 모드로 실행하세요.")
