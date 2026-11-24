# 본문 이미지 붙여넣기

## 무엇을 하나요

공지·과제·토론·퀴즈 작성 칸에 `Ctrl + V`나 끌어다 놓기로 이미지를 넣습니다. 실제 이미지 형식인지 검사하고, 임의 파일 이름으로 저장하며, 볼 권한이 있는 사람에게만 보여 줍니다. 본문에서 지운 이미지와 오래된 임시 이미지는 정리됩니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| (데이터) 이미지 올리기 | `/content-editor/upload/` | `content-editor:upload` |
| (데이터) 이미지 보기 | `/content-editor/images/<토큰>/` | `content-editor:image` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| 화면 처리 | `apps/content_editor/views.py` | 형식 검사, 볼 권한 검사 |
| 규칙 | `apps/content_editor/services.py` | 본문과 이미지 연결·정리 |
| DB 표 | `apps/content_editor/models.py` | `PastedImage` |
| 파일 정리 | `apps/content_editor/signals.py`, `apps/content_editor/management/commands/cleanup_pasted_images.py` | |
| 본문 표시 | `apps/content_editor/templatetags/content_editor_tags.py` | |
| JS | `apps/content_editor/static/content_editor/js/rich-paste-editor.js` | 작성 칸의 붙여넣기 (과제·공지·토론·퀴즈 화면이 사용) |
| 테스트 | `apps/content_editor/tests/test_content_editor.py` | |

## 데이터는 어디서 오나요

자체 DB, 파일은 `data/<모드>/media/`. 설정 `PASTED_IMAGE_MAX_MB`, `PASTED_IMAGE_DRAFT_TTL_HOURS`.

## 누가 볼 수 있나요

작성 권한이 있는 사람이 올리고, 그 글을 볼 수 있는 사람만 이미지를 봅니다.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 붙여넣기가 안 됨 | 이미지 크기 제한, 브라우저 콘솔 오류 |
| 지운 이미지가 남아 있음 | `manage.py cleanup_pasted_images` |
