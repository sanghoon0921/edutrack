# 반별 학습 · 문서 첨삭 · 채점

## 무엇을 하나요

- **반별 학습**: 학습 그룹을 "반"으로 보고, 반마다 게시글·첨부·명단·일정·Zoom 링크를 관리합니다.
- **문서 첨삭**: 제출물(PDF·문서)을 페이지 이미지로 만들어 화면에서 표시·메모(annotation)합니다.
- **채점·성적표**: 과제 제출물과 퀴즈 응시를 검토하고, 반별 성적표(gradebook)를 봅니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 내 반 목록 | `/lms/` | `lms:rooms` |
| 반 화면 / 설정(일정·Zoom) / 명단 | `/lms/groups/<번호>/`, `…/settings/`, `…/roster/` | `lms:room`, `lms:room-settings`, `lms:roster` |
| 게시글 쓰기·보기·삭제 | `/lms/groups/<번호>/posts/new/`, `/lms/posts/<번호>/` | `lms:post-new`, `lms:post` |
| 성적표 | `/lms/gradebook/` | `lms:gradebook` |
| 제출물 검토 / 퀴즈 응시 검토 | `/lms/submissions/<번호>/`, `/lms/quiz-attempts/<번호>/` | `lms:submission-review`, `lms:quiz-review` |
| 문서 보기·첨삭 | `/lms/documents/<번호>/` | `lms:document` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/lms/models.py` | `RoomSettings`(일정·Zoom), `GroupMember`, `GroupStaff`, `ClassPost`, `PostFile`, 문서·제출 파일 |
| 반 화면 | `apps/lms/room_views.py` | 반 목록·게시글·명단·설정 |
| 채점 | `apps/lms/grade_views.py` | 성적표·검토 |
| 문서 | `apps/lms/document_views.py`, `apps/lms/documents.py`, `apps/lms/document_worker.py` | 미리보기 이미지 만들기, 메모 저장 |
| 권한 | `apps/lms/access.py` | 매 요청마다 반 참여 여부 확인 |
| 파일 보호 | `apps/lms/middleware.py` | 학생 제출물·반별 학습 파일의 직접 주소 차단 (다른 업로드는 `docs/architecture.md` 참고) |
| 화면(HTML) | `apps/lms/templates/lms/` (rooms, room, roster, post, form, gradebook, review, quiz_review, document, preview_error, base) | |
| CSS·JS | `apps/lms/static/lms/css/workspace.css`, `apps/lms/static/lms/js/annotation.js` | 반 화면 모양, 문서 메모 |
| 테스트 | `apps/lms/tests/test_lms.py` | |

## 데이터는 어디서 오나요

자체 DB. 파일은 `data/<모드>/media/`에 저장되고 권한 검사가 있는 주소로만 열립니다. 문서 변환 설정: `LMS_OFFICE_CONVERTER`, `LMS_UPLOAD_MAX_MB`(`config/settings/base.py`).

## 누가 볼 수 있나요

반 담당 강사·TA는 관리, 반 학생은 참여, 관리자는 전체.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 문서 미리보기 실패 | `apps/lms/templates/lms/preview_error.html`이 뜸 → 파일 형식·크기, `apps/lms/documents.py` |
| 파일 주소를 직접 열면 404 | 의도된 보호(`apps/lms/middleware.py`) |
| 반에 학생이 안 보임 | 명단(`/lms/groups/<번호>/roster/`) |
