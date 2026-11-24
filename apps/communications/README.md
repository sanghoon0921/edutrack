# apps/communications — 공지·알림

공지(첨부·본문 이미지), 사이트 안 알림, 상단 알림 숫자. 자세한 안내: [docs/features/notices.md](../../docs/features/notices.md)

| 파일 | 하는 일 |
|---|---|
| models.py | `Notice`, 첨부·본문 이미지, `Notification`, 읽음 기록 |
| views.py | 공지 목록·상세·관리, 알림 목록 |
| services.py | 사용자에게 보일 공지·알림 고르기 |
| signals.py | 과제·토론·퀴즈 이벤트 → 알림 만들기 |
| context_processors.py | 상단 종·메시지 배지 숫자 |
| forms.py | 공지 입력 칸(여러 파일 첨부) |
| templatetags/communication_tags.py | 공지 본문 표시 |
| urls.py | `/communications/…` 주소 |
| admin.py, apps.py | 관리자 화면 등록, 앱 설정(`label = "communications"` 바꾸지 말 것) |
| `apps/communications/templates/communications/` | 공지·알림 화면 (홈 공지 칸 포함) |
| `apps/communications/tests/` | 자동 테스트 |
