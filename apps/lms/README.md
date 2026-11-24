# apps/lms — 메신저 · 반별 학습 · 문서 첨삭 · 채점

자세한 안내: [docs/features/messenger.md](../../docs/features/messenger.md), [docs/features/rooms-and-documents.md](../../docs/features/rooms-and-documents.md)

파일 이름 앞부분으로 묶여 있습니다.

| 묶음 | 파일 | 하는 일 |
|---|---|---|
| 메신저 | message_views.py | 메시지 목록·새 대화(같은 상대 1:1은 기존 대화 재사용)·전송·읽음 |
| 메신저 | message_queries.py | 권한에 맞는 대화 목록, 대화 이름(`conversation_name`) |
| 메신저 | portal_chat.py | 작은 대화창·상단 배지용 요약 (`conversation_label`) |
| 반별 학습 | room_views.py | 반 목록·게시글·명단·일정/Zoom 설정 |
| 채점 | grade_views.py | 성적표, 제출물·퀴즈 검토 |
| 문서 첨삭 | document_views.py, documents.py, document_worker.py | 문서 미리보기 이미지, 메모 저장 |
| 공통 | models.py | 반 설정·명단·게시글·대화·메시지·문서 DB 표 |
| 공통 | access.py | 반·대화 참여 권한 (매 요청마다 확인) |
| 공통 | forms.py, ui_forms.py | 입력 칸 (새 대화에는 제목 칸 없음) |
| 공통 | middleware.py | 학생 제출물·반별 학습 파일의 직접 주소 차단 (다른 업로드는 docs/architecture.md 참고) |
| 공통 | signals.py | DB 저장이 끝난 뒤에만 파생 파일 삭제 |
| 공통 | integrations.py | 다른 기능과 이어지는 명단 조회 |
| 공통 | urls.py, apps.py | `/lms/…` 주소, 앱 설정(`label = "lms"` 바꾸지 말 것) |
| 화면 | `apps/lms/templates/lms/` | 메시지·반·채점·문서 화면 |
| CSS/JS | `apps/lms/static/lms/` | 작은 대화창·Enter 처리·메시지 확인·문서 메모 |
| 테스트 | `apps/lms/tests/` | 자동 테스트 |
