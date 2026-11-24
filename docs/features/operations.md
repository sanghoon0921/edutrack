# 운영·사용자 관리

## 무엇을 하나요

관리자가 계정을 만들고 고치며(역할·비밀번호), 학생·학부모 계정에 학생번호를 연결하고, 강사의 담당 학생을 조정합니다. 모든 변경은 감사 로그에 남습니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 운영 첫 화면 | `/operations/` | `operations:dashboard` |
| 사용자 목록 / 만들기 / 상세 / 수정 | `/operations/users/`, `…/create/`, `…/<번호>/`, `…/<번호>/edit/` | `operations:user-list` 등 |
| 학생번호 연결 추가 / 대표 지정 / 해제 | `/operations/users/<번호>/links/…` | `operations:link-add` 등 |
| 강사 담당 학생 추가 / 제거 | `/operations/users/<번호>/teacher-students/…` | `operations:teacher-access-add` 등 |
| 감사 로그 | `/operations/audit/` | `operations:audit-list` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/operations/views.py` | |
| 규칙 | `apps/operations/services.py` | 계정 만들기, 감사 기록, 관리자 최소 1명 유지 |
| 입력 양식 | `apps/operations/forms.py` | 사용자·학생 연결 칸 |
| DB 표 | `apps/operations/models.py` | `AccountAuditLog`, `TeacherStudentAccess` |
| 권한 판단 | `apps/operations/access.py` | 역할별로 볼 수 있는 학생 |
| 화면(HTML) | `apps/operations/templates/operations/` (dashboard, user_list, user_form, user_detail, audit_list) | |
| 테스트 | `apps/operations/tests/test_operations.py` | |

## 데이터는 어디서 오나요

자체 DB. 학생번호 확인은 인트라넷(읽기).

## 누가 볼 수 있나요

관리자만.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 마지막 관리자를 못 바꿈 | 의도된 보호(관리자 최소 1명) |
| 학생 연결 후에도 정보가 없음 | 연결이 "대표"인지, 학생번호가 맞는지 |
