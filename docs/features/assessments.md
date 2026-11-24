# DSG 성적·분석

## 무엇을 하나요

DSG 시험 성적을 보여 줍니다: 학생별 점수 요약, 시험 상세(문항별 결과), 누적 학습 분석(영역별 추세).

- 학생 상세의 '최근 시험'은 **Exam 시험 / Module 시험** 탭으로 나뉩니다. Module 시험은 DSG에서 Module만 따로 본 시험(최근 10개)으로, 맞은 수·정답률을 보여 줍니다. Module 시험만 있고 Exam이 없어도 Module 탭은 보입니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 누적 학습 분석 | `/assessments/students/<학생번호>/insights/` | `assessments:student-insight` |
| 시험 상세 | `/assessments/students/<학생번호>/attempts/<응시번호>/` | `assessments:attempt-detail` |
| 학생 성적(학생용) | `/dashboard/student/grades/` | `student_grades` |
| 성적 분석(강사용) | `/dashboard/teacher/grades/` | `teacher_grades` |

학생 상세 화면의 점수 요약은 `apps/assessments/templatetags/assessment_tags.py`가 그립니다.

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/assessments/views.py` | 시험 상세·누적 분석 (권한 검사 포함) |
| 점수 요약 | `apps/assessments/services.py`, `apps/assessments/repositories.py` | DSG 점수 조회 |
| 시험 상세 | `apps/assessments/detail_services.py`, `apps/assessments/detail_repositories.py` | 문항별 결과 (캐시) |
| 분석 | `apps/assessments/insight_services.py`, `apps/assessments/cumulative_services.py` | 영역별 인사이트·추세 |
| 데이터 모양 | `apps/assessments/contracts.py`, `apps/assessments/detail_contracts.py`, `apps/assessments/insight_contracts.py`, `apps/assessments/cumulative_contracts.py` | |
| 화면(HTML) | `apps/assessments/templates/assessments/exam_attempt_detail.html`, `apps/assessments/templates/assessments/student_learning_insight.html`, `apps/assessments/templates/assessments/student_score_overview.html` | |
| JS | `apps/assessments/static/assessments/js/exam-detail.js`, `apps/assessments/static/assessments/js/learning-insight.js` | |
| 점검 명령 | `apps/assessments/management/commands/` (DSG 연결·매핑 확인, 캐시 비우기) | |
| 테스트 | `apps/assessments/tests/` (7개 파일) | |

## 데이터는 어디서 오나요

DSG DB(읽기 전용). demo 모드는 가짜 시험 데이터를 씁니다(`ASSESSMENT_DATA_SOURCE`). 시험 상세·분석은 캐시합니다(`EXAM_DETAIL_CACHE_SECONDS`, `STUDENT_INSIGHT_CACHE_SECONDS`).

## 누가 볼 수 있나요

학생 본인, 연결된 학부모, 담당 강사, 관리자.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 고친 성적이 바로 안 바뀜 | 캐시: `manage.py clear_exam_detail_cache`, `manage.py clear_student_learning_insight_cache` |
| demo 모드에서 일부 시험 상세가 404 | demo 데이터에 상세가 없는 시험입니다(원래부터 그렇게 동작) |
