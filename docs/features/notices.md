# 공지·알림

## 무엇을 하나요

공지를 역할별로 공개하고(첨부·본문 이미지 포함), 과제·피드백·토론·퀴즈 같은 일이 생기면 대상자에게 사이트 안 알림을 보냅니다. 상단 종 아이콘 숫자 = 학습 알림 + 안 읽은 대화.

- **구분**: 공지를 쓸 때 '학원 공지'(학원 운영 전체) 또는 '반 공지'(반 선택)를 고릅니다. 목록에 학원 공지는 파란색, 반 공지는 주황색 '반 공지 · 반 이름'으로 표시되고, 위쪽 '전체 / 학원 공지 / 반 공지'로 거를 수 있습니다.
- 반 공지는 그 반 학생·학부모와 그 반 강사(개설·담당)에게만 보이고 알림도 그들에게만 갑니다. 강사는 자기 반만 고를 수 있습니다.
- **대상**: 관리자·강사·학생·학부모 중 **여러 그룹을 체크**합니다(네 그룹 모두 = '전체'). 강사는 강사·학생·학부모만 체크할 수 있고, 강사가 고친 공지에 원래 '관리자'가 체크돼 있었다면 그대로 둡니다. 저장은 `Notice.for_admin`·`for_teacher`·`for_student`·`for_parent`.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 공지 목록 / 상세 | `/communications/`, `/communications/notices/<번호>/` | `communications:notice-list`, `communications:notice-detail` |
| 공지 관리 / 등록 / 수정 / 삭제 | `/communications/manage/`, `…/new/`, `…/<번호>/edit/`, `…/<번호>/delete/` | `communications:notice-manage` 등 |
| 알림 목록 / 열기 / 모두 읽음 | `/communications/notifications/`, `…/<번호>/open/`, `…/read-all/` | `communications:notification-list` 등 |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/communications/models.py` | `Notice`, 첨부·본문 이미지, `Notification`, 읽음 |
| 화면 처리 | `apps/communications/views.py` | |
| 알림 만들기 | `apps/communications/signals.py`, `apps/communications/services.py` | 과제·토론·퀴즈 이벤트 → 알림 |
| 상단 숫자 | `apps/communications/context_processors.py` | 종·메시지 배지 숫자 |
| 입력 양식 | `apps/communications/forms.py` | |
| 본문 표시 | `apps/communications/templatetags/communication_tags.py` | |
| 화면(HTML) | `apps/communications/templates/communications/` (7개 파일) | `dashboard_notice_panel.html`은 홈 공지 칸 |
| 테스트 | `apps/communications/tests/` (3개 파일) | |

## 데이터는 어디서 오나요

자체 DB. 첨부는 `data/<모드>/media/`.

## 누가 볼 수 있나요

관리자는 모든 공지 관리, 강사는 자기 공지 관리, 학생·학부모는 대상 공지 보기.

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 알림 숫자가 안 맞음 | `apps/communications/context_processors.py`, 오래된 알림은 숨김 처리됨 |
| 공지가 학생에게 안 보임 | 공지의 대상 역할·공개 설정, 반 공지면 그 학생이 그 반 명단에 있는지 |
