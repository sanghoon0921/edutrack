# 과제

## 무엇을 하나요

강사·관리자가 과제를 등록하고 대상 학생을 고르면, 학생이 제출하고 강사가 피드백을 줍니다. 공개 시점·마감 이후에는 읽기 전용이 됩니다. 학생·학부모에게 알림이 갑니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 과제 목록(관리) | `/assignments/` | `assignments:list` |
| 과제 등록 / 수정 / 삭제 | `/assignments/new/`, `/assignments/<번호>/edit/`, `/assignments/<번호>/delete/` | `assignments:create`, `assignments:update`, `assignments:delete` |
| 과제 상세 | `/assignments/<번호>/` | `assignments:detail` |
| 내 과제(학생) | `/assignments/my/`, `/assignments/my/<번호>/` | `assignments:my`, `assignments:my-detail` |
| 제출물 검토 | `/assignments/submissions/<번호>/review/` | `assignments:review` |
| 역할별 바로가기 | `/dashboard/admin/assignments/`, `/dashboard/teacher/assignments/`, `/dashboard/student/assignments/` | |

첨부파일은 모두 권한 검사가 있는 주소(`…/attachment/`, `…/file/`)로만 내려받습니다.

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/assignments/models.py` | `Assignment`, `AssignmentRecipient`(대상 학생), `Submission`(제출) |
| 화면 처리 | `apps/assignments/views.py` | 목록·등록·제출·검토·내려받기 |
| 규칙 | `apps/assignments/services.py` | 대상 학생 저장, 강사는 담당 학생에게만 |
| 입력 양식 | `apps/assignments/forms.py` | 과제·제출·피드백 칸 |
| 화면(HTML) | `apps/assignments/templates/assignments/` (7개 파일) | |
| 본문 이미지 붙여넣기 | `apps/content_editor/static/content_editor/js/rich-paste-editor.js` | [content-editor.md](content-editor.md) |
| 학생 고르기 | `templates/components/student_transfer_selector.html` | [students.md](students.md) |
| 점검 명령 | `apps/assignments/management/commands/check_assignment_system.py` | |
| 테스트 | `apps/assignments/tests/test_assignments.py`, `apps/assignments/tests/test_permissions.py` | |

## 데이터는 어디서 오나요

자체 DB. 첨부·제출 파일은 `data/<모드>/media/`.

## 누가 볼 수 있나요

| 역할 | 할 수 있는 일 |
|---|---|
| 관리자 | 모든 과제 관리 |
| 강사 | 자기 과제 관리, 담당 학생에게만 배정, 제출물 검토 |
| 학생 | 받은 과제 보기·제출 |
| 학부모 | 자녀 과제 읽기 |

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 강사가 특정 학생을 대상으로 못 고름 | 담당 학생 지정 여부 |
| 마감 후 제출 버튼이 없음 | 의도된 동작(마감 이후 읽기 전용) |
| 첨부 업로드 실패 | 크기 제한 `.env`의 `MAX_REQUEST_UPLOAD_MB` |
