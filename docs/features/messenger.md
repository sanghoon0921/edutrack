# 메신저 (작은 대화창 포함)

## 무엇을 하나요

학생과 담당 강사·TA가 사이트 안에서 1:1 또는 반(그룹) 대화를 합니다.

- 학생은 대화 목록·창·화면에 **'이름 · 학생번호'**(예: 김지훈D · 6333)로 보입니다(대표 학생번호 기준).
- **작은 대화창**: 상단 메시지 버튼·홈의 메시지 카드·오른쪽 아래 "메시지" 버튼을 누르면, 지금 화면 위에 움직일 수 있는 작은 창이 열립니다.
- **전체 메시지 화면**: 왼쪽에 대화 목록, 오른쪽에 대화 내용.
- **Enter 한 번 = 전송**(한글 조합 중에도 한 번), **Shift + Enter = 줄바꿈**, 전송 중 반복 Enter·빈 입력은 무시합니다.
- 같은 상대와의 1:1 대화는 새로 만들지 않고 **기존 대화를 다시 씁니다**.
- 홈·알림에서 미리보기만 보면 읽음 처리하지 않고, 대화를 열어 최신 메시지를 볼 때 읽음 처리합니다.
- 새 메시지 확인: 열려 있는 대화는 1초, 그 밖(홈·목록·상단 배지)은 5초 간격.
- 학부모 계정은 메시지를 쓰지 않습니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 메시지 목록 | `/lms/messages/` | `lms:inbox` |
| 새 대화 | `/lms/messages/new/` | `lms:new-conversation` |
| 대화 | `/lms/messages/<번호>/` | `lms:conversation` |
| (데이터) 새 메시지 / 읽음 / 목록 요약 | `/lms/messages/<번호>/feed/`, `/lms/messages/<번호>/read/`, `/lms/messages/summary/` | `lms:conversation-feed`, `lms:conversation-read`, `lms:inbox-feed` |
| (데이터) 작은 대화창·상단 배지 | `/lms/messenger/summary/`, `/lms/messages/<번호>/snapshot/` | `lms:chat-summary`, `lms:chat-snapshot` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/lms/models.py` | `Conversation`, `ConversationMember`(읽은 위치), `Message` |
| 전체 화면 처리 | `apps/lms/message_views.py` | 목록·새 대화(기존 1:1 재사용)·전송·읽음 |
| 목록·이름 | `apps/lms/message_queries.py` | 권한에 맞는 대화 목록, 대화 이름(`conversation_name`) |
| 작은 대화창 데이터 | `apps/lms/portal_chat.py` | 요약·최근 메시지 (이름은 `conversation_label`) |
| 대화 권한 | `apps/lms/access.py` | 대화 상대(`contacts_for`), 참여 권한(`can_converse`) |
| 입력 양식 | `apps/lms/forms.py` | 새 대화(제목 칸 없음)·메시지 |
| 화면(HTML) | `apps/lms/templates/lms/inbox.html`, `apps/lms/templates/lms/conversation.html`, `apps/lms/templates/lms/new_chat.html` | 전체 메시지 화면 |
| 작은 대화창(HTML) | `templates/components/chat_widget_v2.html` | 모든 화면에 들어가는 창 |
| 상단 배지·알림 | `templates/components/header.html`, `apps/communications/context_processors.py` | 안 읽은 대화 수 |
| Enter 처리 | `apps/lms/static/lms/js/chat-composer.js` | 한글 조합 중 Enter 한 번 전송, Shift+Enter 줄바꿈 |
| 작은 대화창 동작 | `apps/lms/static/lms/js/chat-widget.js` | 열기·끌어서 옮기기·초안 유지 |
| 전체 대화 화면 동작 | `apps/lms/static/lms/js/messages.js` | 전송·재시도(중복 방지)·이전 메시지·1초 확인 |
| 5초 확인 | `apps/lms/static/lms/js/polling.js`, `apps/lms/static/lms/js/message-summary.js` | |
| CSS | `static/css/layers/70-home-messenger.css`, `static/css/layers/95-portal-focus.css` | |
| 테스트 | `apps/lms/tests/test_usability.py`, `apps/dashboard/tests/test_home_messenger.py`, `apps/dashboard/tests/test_portal_focus.py` | |

## 데이터는 어디서 오나요

자체 DB(`lms_conversation`, `lms_conversationmember`, `lms_message`). 대화 상대 범위는 반 명단·담당 관계로 정합니다.

## 누가 볼 수 있나요

| 역할 | 할 수 있는 일 |
|---|---|
| 학생 | 담당 강사·TA와 대화, 반 대화 |
| 강사·TA | 담당 학생과 대화, 반 그룹 대화 만들기 |
| 관리자 | 대화 가능 |
| 학부모 | 사용 안 함 |

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| Enter를 눌러도 안 보내짐 / 두 번 보내짐 | `apps/lms/static/lms/js/chat-composer.js` (Enter 처리는 여기 한 곳) |
| 대화 상대가 목록에 없음 | 반 명단·담당 학생 지정, `apps/lms/access.py` |
| 안 읽음 숫자가 안 줄어듦 | 대화를 열어 맨 아래까지 봤는지, `/lms/messages/<번호>/read/` 요청 |
| 메시지가 늦게 보임 | 확인 간격(1초/5초)은 의도된 동작. 실시간 서버(WebSocket)는 없음 |

알려진 정리 거리: 대화 이름 함수가 `conversation_name`(전체 화면)과 `conversation_label`(작은 대화창) 두 개입니다.
