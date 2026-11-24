# 담당 학생 지정

## 무엇을 하나요

강사가 인트라넷 학생을 찾아 자기 "담당 학생"으로 등록·제외합니다. 담당 학생만 학생 상세·성적·과제 대상에 나옵니다. 변경은 모두 감사 로그에 남습니다. (반 명단·과제·수업 배정은 자동으로 바뀌지 않습니다.)

화면 사용법:

- 한 화면 세 칸: **① 수업 찾기** → **② 학생** → **③ 현재 담당 학생** (좁은 화면에서는 위아래로)
- ① 수업명은 치는 즉시 검색, 상태·Term·Subject는 인트라넷 값 드롭다운(정확히 같은 값). 수업마다 학생 수가 보이고, 20개씩 [더 보기]
- ② 수업을 누르면 그 명단, [× 해제]를 누르면 인트라넷 전체 학생. 이름 칸은 수업을 골랐으면 그 명단 안에서 찾습니다. 이미 담당인 학생은 "담당 중"
- ③ 이름·번호로 즉시 거르기. **전체선택은 체크만** 합니다(거른 결과만). 실제 저장은 [선택 추가 →] / [← 선택 제외]
- 학생 **더블클릭** 또는 Enter = 바로 등록(②) 또는 제외(③), ② ↔ ③ **끌기**도 됩니다
- 서버 저장이 성공한 뒤에만 목록이 바뀌고, 실패하면 그대로 둡니다. 한 번에 최대 100명.
- 연결이 안 되거나 20초가 넘으면 ①·② 칸 안에 안내와 [다시 시도]가 나옵니다("수업·학생 없음"과 다름).

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 담당 학생 지정 | `/operations/my-students/` | `operations:teacher-student-assignment` |
| (데이터) 수업 검색 | `/operations/my-students/classes/` | `operations:teacher-class-search` |
| (데이터) 학생 명단·검색 | `/students/selector/browse/?mode=teacher` (공용 학생 목록 부품) | `students:selector-browse` |
| (데이터) 저장 | `/operations/my-students/update/` | `operations:teacher-student-assignment-update` |
| 관리자가 강사 담당 학생 조정 | `/operations/users/<번호>/teacher-students/add/` 등 | `operations:teacher-access-add` 등 |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면·저장 | `apps/operations/teacher_self_assignment.py` | 목록·검색·등록/제외 저장·감사 로그 |
| 수업 찾기 | `apps/operations/class_student_search.py` | 인트라넷 수업 읽기(정확 일치 Term·Subject, 학생 수) |
| 권한 판단 | `apps/operations/access.py` | 강사가 볼 수 있는 학생 |
| DB 표 | `apps/operations/models.py` | `TeacherStudentAccess`(담당 관계), `AccountAuditLog` |
| 화면(HTML) | `apps/operations/templates/operations/teacher_student_assignment.html` | |
| JS | `apps/operations/static/operations/js/teacher-assignment.js`, `static/js/global/student-browser.js` | 세 칸 연결, 전체선택·더블클릭·끌기 (학생 줄·검색은 공용 부품) |
| CSS | `static/css/layers/95-portal-focus.css` | 화면 모양 |
| 테스트 | `apps/operations/tests/test_teacher_assignment.py`, `apps/operations/tests/test_self_assignment_and_resources.py`, `apps/dashboard/tests/test_portal_focus.py` | |

## 데이터는 어디서 오나요

학생·수업 명단은 인트라넷(읽기), 담당 관계는 자체 DB.

## 누가 볼 수 있나요

강사(본인 담당만 변경), 관리자(모든 강사 조정은 운영 화면에서).

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 수업 검색 결과가 없음 | 수업명 일부만 넣어도 되는지, real 모드 인트라넷 연결 |
| 명단에 예전 학생도 보임 | 명단은 수업 배정 기록 기준이라 과거 배정이 포함될 수 있음 |
| 드래그가 안 됨(휴대폰) | 휴대폰은 체크 + [선택 추가]/[선택 제외] 버튼 사용 |
| 칸 안에 "서버에 연결하지 못했습니다" | 인터넷·서버 연결 확인 후 그 칸의 [다시 시도] |
