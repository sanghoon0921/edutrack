# 역할별 홈 화면

## 무엇을 하나요

로그인하면 처음 보이는 화면입니다. 역할마다 다른 홈을 보여 줍니다.

- 강사: 공지사항(파랑)·메시지(보라)·Zoom 바로 입장(주황) 카드를 위에, 자주 쓰는 메뉴 바로가기를 아래에
- 학생: 공지사항·Zoom 링크·메시지를 위에, 오늘 일정·오늘 마감할 학습을 아래에
- 학부모: 자녀 학습 현황 요약
- 관리자: 운영 요약

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 홈(역할별) | `/dashboard/` | `dashboard` |
| 학생 홈의 오늘 일정 데이터 | `/dashboard/home/today/` | `home-today` |
| 강사: 담당 수업 / 담당 학생 / 성적 분석 | `/dashboard/teacher/classes/`, `/dashboard/teacher/students/`, `/dashboard/teacher/grades/` | `teacher_classes`, `teacher_students`, `teacher_grades` |
| 학생: 내 수업 / 출결 / 성적 | `/dashboard/student/classes/`, `/dashboard/student/attendance/`, `/dashboard/student/grades/` | `student_classes`, `student_attendance`, `student_grades` |
| 관리자: 학생 / 운영 | `/dashboard/admin/students/`, `/dashboard/admin/operations/` | `admin_students`, `admin_operations` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/dashboard/views.py` | 역할별 홈으로 나누기, 하위 화면 |
| 강사 홈 데이터 | `apps/dashboard/teacher_home.py` | 강사 홈 카드 내용 (자체 DB만 사용) |
| 학생 홈 데이터 | `apps/dashboard/student_home.py` | 공지·Zoom·메시지·마감 |
| 오늘 일정 | `apps/dashboard/home_views.py` | 인트라넷 수업 계획 (실패해도 홈은 열림) |
| 성적 분석 입구 | `apps/dashboard/grade_hub.py` | 강사의 담당 학생 성적 분석으로 연결 |
| 화면(HTML) | `apps/dashboard/templates/dashboard/teacher.html`, `apps/dashboard/templates/dashboard/student.html`, `apps/dashboard/templates/dashboard/admin.html`, `apps/dashboard/templates/dashboard/parent_home_content.html` | 역할별 홈 |
| 홈 카드 | `apps/dashboard/templates/dashboard/portal_notices.html`, `apps/dashboard/templates/dashboard/portal_messages.html`, `apps/dashboard/templates/dashboard/portal_zoom.html` | 공지·메시지·Zoom 카드 |
| 성적 분석 화면 | `apps/dashboard/templates/dashboard/teacher_grades_live.html` | |
| JS | `apps/dashboard/static/dashboard/js/student-home.js` | 학생 홈 오늘 일정 불러오기 |
| CSS | `static/css/layers/70-home-messenger.css`, `static/css/layers/95-portal-focus.css` | 홈·카드 모양 |
| 테스트 | `apps/dashboard/tests/test_portal_focus.py`, `apps/dashboard/tests/test_home_messenger.py`, `apps/dashboard/tests/test_dashboard.py`, `apps/dashboard/tests/test_navigation.py` | |

## 데이터는 어디서 오나요

- 공지·메시지·마감: 자체 DB
- Zoom 링크·반 일정: 반 설정(`apps/lms/models.py`의 `RoomSettings`)
- 오늘 수업: 인트라넷 수업 계획(읽기)
- 성적: DSG(읽기)

## 누가 볼 수 있나요

모든 역할이 자기 홈을 봅니다. 강사의 성적 분석은 **현재 담당 학생만** 보입니다.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 학생 홈 "오늘 수업을 확인하고 있습니다…"가 계속 | real 모드의 인트라넷 연결, `apps/dashboard/home_views.py` |
| 강사 성적 분석에 학생이 없음 | 담당 학생 지정([teacher-assignment.md](teacher-assignment.md)) |
| Zoom 링크가 "링크 미등록" | 반 화면의 "스케줄·링크 설정" |
| 카드 색·배치 | `static/css/layers/95-portal-focus.css` |
