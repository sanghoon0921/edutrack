# apps/students — 학생 조회·출결 · 학생 선택 부품

인트라넷 학생 검색·상세·출결, 여러 화면이 쓰는 학생 선택 부품. 자세한 안내: [docs/features/students.md](../../docs/features/students.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 학생 목록·상세·출결, 학생 검색 API |
| services.py, repositories.py | 학생 조회 (demo/인트라넷 저장소, 캐시) |
| course_services.py, course_repositories.py | 학생의 수업(진행 중·완료) |
| attendance_services.py, attendance_repositories.py | 출결 기록 |
| contracts.py | 화면에 넘기는 학생·수업 데이터 모양 |
| bulk_selector.py | 학생 선택 부품의 목록·조건 (권한 안에서만), 학생별 진행·예정 수업 조회 |
| student_rows.py | 학생 한 줄 행에 쓰는 표시 값(학교·학년, 듣는 수업, 검색어) |
| selection.py, forms.py | 학생번호 입력 정리, 선택 칸 |
| models.py | (DB 표 없음 — 학생 정보는 인트라넷에서 읽음) |
| urls.py | `/students/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "students"` 바꾸지 말 것) |
| management/commands/ | 학생 검색·수업·출결 점검, `check_portal_recovery` |
| `apps/students/templates/students/` | 학생 목록·상세·출결 화면 |
| `apps/students/tests/` | 자동 테스트 (`tests/js/`: 학생 목록 부품을 Node.js로 실행해 보는 시험 도구) |
