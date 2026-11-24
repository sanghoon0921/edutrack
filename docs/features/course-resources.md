# 과목 자료

## 무엇을 하나요

과목별 자료 공간을 만들고(기본 카테고리 TEXTBOOK·수업 자료·VOCAB), PDF·파일·외부 링크를 올립니다. PDF는 브라우저에서 미리보고 원래 이름으로 내려받습니다.

과목을 만들거나 고칠 때 Term·Subject는 인트라넷에 등록된 값에서 고릅니다. 이미 저장된 값이 목록에 없으면 "(기존 값)"으로 남아 그대로 저장할 수 있고, 인트라넷 목록을 못 불러오면 글자 입력 칸으로 바뀝니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 과목 목록 / 만들기 | `/courses/`, `/courses/new/` | `classroom:board-list`, `classroom:board-create` |
| 과목 상세 / 수정 / 삭제 | `/courses/<번호>/`, `…/edit/`, `…/delete/` | `classroom:board-detail` 등 |
| 카테고리 추가·수정·삭제 | `/courses/<번호>/categories/…` | `classroom:category-create` 등 |
| 자료 올리기 / 상세 / 미리보기 / 내려받기 | `/courses/<번호>/categories/<번호>/resources/new/`, `/courses/resources/<번호>/`, `…/preview/`, `…/download/` | `classroom:resource-create` 등 |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/classroom/models.py` | `CourseBoard`, `CourseCategory`, `CourseResource`, 대상 학생 |
| 화면 처리 | `apps/classroom/views.py` | |
| 규칙 | `apps/classroom/services.py` | 관리 권한, 대상 학생 |
| 입력 양식 | `apps/classroom/forms.py` | 일반 화면은 항상 "공개"로 저장 |
| 파일 정리 | `apps/classroom/signals.py` | 자료 삭제 시 파일도 삭제 |
| 화면(HTML) | `apps/classroom/templates/classroom/` (6개 파일) | |
| JS·CSS | `apps/classroom/static/classroom/js/resource-form.js`, `static/css/components/compact-pages.css` | |
| 테스트 | `apps/classroom/tests/test_classroom.py` | |

## 데이터는 어디서 오나요

자체 DB, 파일은 `data/<모드>/media/`. 크기 제한 `COURSE_RESOURCE_MAX_MB`.

## 누가 볼 수 있나요

관리자는 전체 관리, 강사는 자기 과목 관리, 대상 학생·학부모는 보기.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| PDF 미리보기가 안 됨 | 실제 PDF인지(형식 검사), 크기 제한 |
| 학생에게 과목이 안 보임 | 과목 대상 학생 |
| Term·Subject가 글자 칸으로 보임 | 인트라넷 연결(`.env`). 목록은 10분 동안 저장되므로 인트라넷에 새로 넣은 값은 최대 10분 뒤에 보임 |
