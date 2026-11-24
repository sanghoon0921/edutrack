# apps/dashboard — 역할별 홈 · 관리자 클래스 검색

로그인 후 첫 화면(역할별 홈)과 관리자 수업 관리. 자세한 안내: [docs/features/home.md](../../docs/features/home.md), [docs/features/class-catalog.md](../../docs/features/class-catalog.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 역할별 홈으로 나누기, 강사·학생·관리자 하위 화면, 403/404 화면 |
| teacher_home.py | 강사 홈 카드(공지·메시지·Zoom) 데이터 |
| student_home.py | 학생 홈 데이터(공지·Zoom·메시지·마감) |
| home_views.py | 학생 홈 "오늘 일정" (인트라넷 실패해도 홈은 열림) |
| grade_hub.py | 강사 성적 분석 입구(현재 담당 학생만) |
| class_catalog.py | 관리자 클래스 검색(인트라넷/demo), Term·Subject 드롭다운 값(term_subject_options, 10분 캐시) |
| admin_class_detail.py | 클래스 상세(읽기 전용) |
| forms.py | 클래스 검색 조건 |
| urls.py | `/dashboard/…` 주소 |
| apps.py | 앱 설정(`label = "dashboard"` 바꾸지 말 것) |
| management/commands/ | `check_class_catalog` 점검 명령 |
| `apps/dashboard/templates/dashboard/` | 홈·하위 화면·홈 카드(`portal_*.html`) |
| `apps/dashboard/static/dashboard/` | 클래스 검색 CSS, 학생 홈 JS |
| `apps/dashboard/tests/` | 자동 테스트 (화면 배치·CSS 순서 검사 포함) |
