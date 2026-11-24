# 토론·퀴즈

## 무엇을 하나요

학습 그룹을 만들고, 토론(댓글·첨부)과 퀴즈(문항·선택지·자동 채점)를 대상 학생에게 냅니다. 학부모는 읽기 전용으로 봅니다. 반별 학습(`apps/lms/`)도 이 학습 그룹을 "반"으로 씁니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 학습 그룹 관리 | `/learning/groups/`, `/learning/groups/<번호>/edit/` | `learning:group-manage`, `learning:group-update` |
| 토론 목록 / 등록 / 상세 / 수정 | `/learning/discussions/`, `…/new/`, `…/<번호>/`, `…/<번호>/edit/` | `learning:discussion-list`, `learning:discussion-create`, `learning:discussion-detail`, `learning:discussion-update` |
| 내 토론(학생) | `/learning/my/discussions/` | `learning:my-discussions` |
| 퀴즈 목록 / 등록 / 상세 / 수정 | `/learning/quizzes/`, `…/new/`, `…/<번호>/`, `…/<번호>/edit/` | `learning:quiz-list`, `learning:quiz-create`, `learning:quiz-detail`, `learning:quiz-update` |
| 퀴즈 문항 추가·수정·삭제 | `/learning/quizzes/<번호>/questions/…` | `learning:quiz-question-create` 등 |
| 내 퀴즈(학생) | `/learning/my/quizzes/` | `learning:my-quizzes` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/learning/models.py` | `LearningGroup`, `Discussion`, `Quiz`, 문항·선택지·응시 |
| 화면 처리 | `apps/learning/views.py` | |
| 규칙 | `apps/learning/services.py` | 대상 학생 범위·작성자 권한 |
| 입력 양식 | `apps/learning/forms.py` | |
| 화면(HTML) | `apps/learning/templates/learning/` (13개 파일) | `_tabs.html`은 과제·토론·퀴즈 공용 탭 |
| 테스트 | `apps/learning/tests/test_learning.py` | |

## 데이터는 어디서 오나요

자체 DB. 토론 첨부는 `data/<모드>/media/`.

## 누가 볼 수 있나요

관리자·강사는 관리, 대상 학생은 참여, 학부모는 읽기.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 퀴즈 점수가 이상함 | `apps/learning/models.py`의 채점 부분, 문항 정답 설정 |
| 학생이 토론을 못 봄 | 대상 학생·공개 시점 |
