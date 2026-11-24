# apps/content_editor — 본문 이미지 붙여넣기

작성 칸에 이미지 붙여넣기·끌어다 놓기. 자세한 안내: [docs/features/content-editor.md](../../docs/features/content-editor.md)

| 파일 | 하는 일 |
|---|---|
| views.py | 이미지 올리기(형식 검사), 이미지 보기(권한 검사) |
| services.py | 본문과 이미지 연결, 지운 이미지 정리 |
| models.py | `PastedImage` |
| signals.py | 글이 지워지면 이미지 파일도 지움 |
| templatetags/content_editor_tags.py | 본문 표시 |
| urls.py | `/content-editor/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "content_editor"` 바꾸지 말 것) |
| management/commands/ | `cleanup_pasted_images` (오래된 임시 이미지 정리) |
| `apps/content_editor/static/content_editor/js/rich-paste-editor.js` | 작성 칸 붙여넣기 (과제·공지·토론·퀴즈 화면이 사용) |
| `apps/content_editor/tests/` | 자동 테스트 |
