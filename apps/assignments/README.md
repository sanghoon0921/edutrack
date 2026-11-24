# apps/assignments — 과제

과제 등록·대상 학생·제출·피드백. 자세한 안내: [docs/features/assignments.md](../../docs/features/assignments.md)

| 파일 | 하는 일 |
|---|---|
| models.py | `Assignment`, `AssignmentRecipient`(대상 학생), `Submission`(제출), 첨부 저장 경로 |
| views.py | 목록·등록·수정·삭제·제출·검토·첨부 내려받기 |
| services.py | 대상 학생 저장 규칙(강사는 담당 학생에게만) |
| forms.py | 과제·제출·피드백 입력 칸 |
| urls.py | `/assignments/…` 주소 (역할별 바로가기는 `apps/dashboard/urls.py`) |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "assignments"` 바꾸지 말 것) |
| management/commands/ | `check_assignment_system` 점검 명령 |
| `apps/assignments/templates/assignments/` | 과제 화면 7개 |
| `apps/assignments/tests/` | 자동 테스트 |
