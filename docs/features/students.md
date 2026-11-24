# 학생 조회·출결

## 무엇을 하나요

인트라넷 학생을 검색하고, 학생 상세(수업·출결·성적 요약)를 보여 줍니다. 과제·토론·자료 화면에서 쓰는 "학생 선택" 부품도 여기 있습니다.

화면 사용법 (담당 학생, 강사):

- 담당 학생이 처음부터 한 줄 표(이름 · 학생번호 · 학교·학년 · 지점 · 듣는 수업)로 모두 보입니다.
- **수업·반** 드롭다운: "인트라넷 수업"(내 담당 학생이 듣는 진행·예정 수업)이나 "EduTrack 반"을 고르면 그 학생만 남습니다.
- 이름·번호·학교 칸은 치는 즉시 걸러집니다(검색 버튼 없음). 한글 이름은 다 치고 잠깐(0.25초) 멈추면 조회됩니다. 학생번호 확인이 필요한 학생은 "확인 필요"로 표시됩니다.
- 연결이 안 되면 목록 자리에 "서버에 연결하지 못했습니다" 안내와 [다시 시도]가 나옵니다("학생 없음"과 다름). 이미 고른 학생은 그대로입니다.
- 관리자의 "학생 검색"은 같은 줄 모양으로 인트라넷 전체 학생을 바로 조회합니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 학생 목록 | `/students/` | `students:list` |
| 학생 상세 | `/students/<학생번호>/` | `students:detail` |
| 내 정보(학생) | `/students/me/` | `students:my-detail` |
| 수업별 출결 | `/students/<학생번호>/courses/<배정번호>/attendance/` | `students:attendance` |
| 학생 선택 부품(검색·목록·조건) | `/students/api/student-selector/`, `/students/selector/browse/`, `/students/selector/options/` | `students:selector-search`, `students:selector-browse`, `students:selector-options` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/students/views.py` | 목록·상세·출결 |
| 학생 조회 | `apps/students/services.py`, `apps/students/repositories.py` | 인트라넷/demo 학생 정보 |
| 수업 조회 | `apps/students/course_services.py`, `apps/students/course_repositories.py` | 진행 중·완료 수업 |
| 출결 조회 | `apps/students/attendance_services.py`, `apps/students/attendance_repositories.py` | 출결 기록 |
| 데이터 모양 | `apps/students/contracts.py` | 화면에 쓰는 학생·수업 정보 |
| 학생 선택 부품 | `apps/students/bulk_selector.py`, `apps/students/selection.py`, `apps/students/forms.py`, `apps/students/student_rows.py` | 여러 화면의 학생 고르기, 한 줄 행 표시 값, 담당 학생 목록 |
| 화면(HTML) | `apps/students/templates/students/student_list.html`, `apps/students/templates/students/student_detail.html`, `apps/students/templates/students/attendance_detail.html` | |
| 공용 부품 | `templates/components/student_transfer_selector.html`, `templates/components/student_filters.html`, `templates/components/student_row.html` | 학생 고르기 화면 조각, 한 줄 행 |
| JS·CSS | `static/js/components/student-transfer-selector.js`, `static/js/global/student-browser.js`, `static/css/components/student-transfer-selector.css`, `static/css/components/learning-overview.css` | |
| 점검 명령 | `apps/students/management/commands/check_student_attendance.py`, `apps/students/management/commands/check_portal_recovery.py` | |
| 테스트 | `apps/students/tests/` | 학생 목록 부품의 화면 동작(한글 즉시 검색, 연결 실패 안내)은 `test_student_browser_script.py`가 Node.js로 `tests/js/student_browser_harness.js`를 실행해 확인합니다(Node.js가 없으면 건너뜀) |

## 데이터는 어디서 오나요

인트라넷(읽기 전용). demo 모드는 가짜 학생을 씁니다(`STUDENT_DATA_SOURCE`). 짧은 캐시가 있어 인트라넷 변경이 몇십 초 늦게 보일 수 있습니다(`STUDENT_PROFILE_CACHE_SECONDS` 등).

## 누가 볼 수 있나요

| 역할 | 볼 수 있는 학생 |
|---|---|
| 관리자 | 전체 |
| 강사 | 담당 학생만 ([teacher-assignment.md](teacher-assignment.md)) |
| 학생 | 본인 |
| 학부모 | 연결된 자녀 |

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 목록 자리에 "서버에 연결하지 못했습니다" | 인터넷·서버 연결을 확인하고 [다시 시도]. 계속되면 서버가 켜져 있는지 |
| 수업·반 드롭다운이 비고 "수업·반 목록을 불러오지 못했습니다" | 이름 검색은 됩니다. 거르기 막대의 [다시 시도]를 누르세요 |
| 강사가 학생을 못 봄 | 담당 학생 지정 여부 (`apps/operations/access.py`) |
