# apps/operations — 운영·사용자 관리 · 담당 학생 지정

자세한 안내: [docs/features/operations.md](../../docs/features/operations.md), [docs/features/teacher-assignment.md](../../docs/features/teacher-assignment.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 운영 첫 화면, 사용자 관리, 학생 연결, 강사 담당 조정, 감사 로그 |
| services.py | 계정 만들기, 감사 기록, 관리자 최소 1명 유지 |
| forms.py | 사용자·학생 연결 입력 칸 |
| models.py | `AccountAuditLog`(변경 기록), `TeacherStudentAccess`(강사 ↔ 담당 학생) |
| access.py | 역할별로 볼 수 있는 학생 판단 (여러 기능이 사용) |
| teacher_self_assignment.py | 강사 본인의 담당 학생 지정 화면·저장 |
| class_student_search.py | 담당 학생 지정 ① 수업 찾기(수업명·상태·Term·Subject, 학생 수) |
| urls.py | `/operations/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "operations"` 바꾸지 말 것) |
| `apps/operations/templates/operations/` | 운영 화면, 담당 학생 지정 화면 |
| `apps/operations/static/operations/js/teacher-assignment.js` | 세 칸 화면: 수업 찾기·명단·담당 학생 옮기기 |
| `apps/operations/tests/` | 자동 테스트 |
