# apps/learning — 토론·퀴즈 · 학습 그룹

학습 그룹, 토론, 퀴즈(문항·자동 채점). 학습 그룹은 반별 학습(`apps/lms/`)의 "반"이기도 합니다. 자세한 안내: [docs/features/learning.md](../../docs/features/learning.md)

| 파일 | 하는 일 |
|---|---|
| models.py | `LearningGroup`, `Discussion`, `Quiz`, 문항·선택지·응시 |
| views.py | 그룹·토론·퀴즈 화면 |
| services.py | 대상 학생 범위·작성자 권한 |
| forms.py | 입력 칸 |
| urls.py | `/learning/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "learning"` 바꾸지 말 것) |
| `apps/learning/templates/learning/` | 화면 13개 (`_tabs.html`은 과제·토론·퀴즈 공용 탭) |
| `apps/learning/tests/` | 자동 테스트 |
