# EduTrack 전체 구조

## 1. 한 장 그림

```
브라우저
  │  주소 요청 (예: /lms/messages/)
  ▼
config/urls.py ──► apps/<기능>/urls.py ──► 화면 처리 함수(views)
                                              │
                ┌─────────────────────────────┼─────────────────────────────┐
                ▼                             ▼                             ▼
      인트라넷 MySQL (읽기 전용)      DSG MySQL (읽기 전용)        자체 DB (SQLite, data/<모드>/db.sqlite3)
      학생·수업·출결·수납·클래스      시험·성적                    계정·과제·토론·퀴즈·메시지·공지·자료
                                              │
                                              ▼
                              화면(HTML) = templates/ + apps/<기능>/templates/
                              모양(CSS)·동작(JS) = static/ + apps/<기능>/static/
```

- 인트라넷·DSG는 EduTrack이 **쓰지 않고 읽기만** 합니다. 접속 정보는 `.env`에 있습니다. (공개용 사본에는 이 연동 코드가 없고, `config/excluded.py`의 안내 오류로 대신합니다.)
- demo 모드에서는 인트라넷·DSG 대신 코드 안의 가짜 데이터(demo repository)를 씁니다. 그래서 `.env` 없이도 화면을 고칠 수 있습니다.
- 업로드 파일은 `data/<모드>/media/`에 저장되고, 파일 이름은 모두 추측할 수 없는 무작위 이름입니다. 폴더에 따라 보호 방식이 다릅니다.
  - **직접 주소로 못 엶** (`apps/lms/middleware.py`가 막고, 권한을 확인하는 화면을 거쳐서만 내려받음): 학생 과제 제출물 `assignments/submissions/`, 토론 첨부 `learning/discussions/`·`learning/discussion-comments/`, 반별 학습 첨부·제출·첨삭 문서 `lms_private/`
  - **주소만 알면 열림** (개발 서버인 demo·real 모드와 다른 PC용 share·office 모드에서 `config/media.py`가 `/media/`를 그대로 내보냄, 로그인 확인 없음): 과제 자료 `assignments/materials/`, 수업 자료 `classroom/resources/`, 공지 첨부·이미지 `communications/notices/`, 본문에 붙여 넣은 이미지 `content-editor/pasted/`
  - 같은 PC에서만 쓸 때는 괜찮습니다. 다른 사람이 접속할 수 있게 열거나(Cloudflare 터널 등) 서버에 배포하기 전에는 두 번째 묶음도 보호해야 합니다. 차단 폴더를 바꾸면 `config/tests/test_architecture_doc.py`가 이 설명과 맞는지 확인합니다.

## 2. 실행 모드

| 모드 | 설정 파일 | 학생·성적 데이터 | 자체 DB · 업로드 | 오류 화면 |
|---|---|---|---|---|
| demo | `config/settings/demo.py` | 가짜(demo) | `data/demo/db.sqlite3`, `data/demo/media/` | 파일·줄 번호 표시 |
| real *(공개본 제외)* | 사내 설정 | 인트라넷·DSG 읽기 | `data/real/` | 파일·줄 번호 표시 |
| share | `config/settings/share.py` + `scripts/share.ps1` | 가짜(demo) | `data/share/db.sqlite3`, `data/share/media/` (처음 켤 때 demo에서 복사) | "Server Error (500)"만, 기록은 `data/share/server.log` |
| office *(공개본 제외)* | 사내 설정 | 인트라넷·DSG 읽기 | real과 같음 | "Server Error (500)"만, 기록은 서버 로그 파일 |
| test | `config/settings/test.py` | 가짜(demo) | 테스트 중에만 쓰는 임시 DB | — |

- 공통 값은 `config/settings/base.py`에 있고, 모드 파일은 바뀌는 값만 덮어씁니다.
- `manage.py`를 그냥 실행하면 demo 모드입니다(실수로 실제 데이터에 붙지 않게).
- 파이썬은 UTF-8 모드(`PYTHONUTF8=1`)로 실행합니다. `scripts/*.ps1`이 자동으로 켭니다.

## 3. 역할과 권한

| 역할 | 볼 수 있는 학생 | 주요 화면 |
|---|---|---|
| 관리자 | 전체 | 운영·사용자 관리, 클래스 검색, CSV 등록, 모든 기능 |
| 강사 | 담당 학생만 (`apps/operations/models.py`의 `TeacherStudentAccess`) | 담당 학생 지정, 반별 학습, 과제·채점, 메시지 |
| 학생 | 본인 (계정에 연결된 학생번호) | 내 수업·출결·성적, 과제 제출, 메시지 |
| 학부모 | 연결된 자녀 | 자녀 학습 현황, 수납 내역 (메시지는 사용 안 함) |

권한 검사가 있는 곳:

- `apps/operations/access.py` — 강사·학생·학부모가 어떤 학생을 볼 수 있는지
- `apps/lms/access.py` — 반·대화 참여 권한 (매 요청마다 다시 확인)
- `apps/accounts/decorators.py`, `apps/accounts/mixins.py` — 화면별 역할 제한
- 각 기능의 views 안 역할 검사

## 4. 화면(HTML) 위치

- 모든 화면 공통: `templates/layouts/base.html`(전체 틀), `templates/components/`(머리글·작은 대화창·학생 선택 부품 등), `templates/errors/`(403·404·503)
- 기능별 화면: `apps/<기능>/templates/<기능>/…` — 코드에서는 `"lms/inbox.html"`처럼 `<기능>/파일` 이름으로 부릅니다.

## 5. CSS 적용 순서 (디자인 층)

`templates/layouts/base.html`이 모든 화면에 아래 순서로 CSS를 불러옵니다. 같은 규칙이 여러 층에 있으면 **나중에 불러온 층(번호가 큰 층)이 이깁니다.** 특정 화면만 바꾸려면 그 기능 폴더의 CSS를 고치세요.

| 순서 | 파일 | 하는 일 |
|---|---|---|
| 1 | `static/css/layers/00-base.css` | 색·글꼴 기본값 |
| 2 | `static/css/layers/10-premium-portal.css` | 포털 기본 디자인(출결·카드 등) |
| 3 | `static/css/layers/20-workflow.css` | 큰 글씨·관리 목록 |
| — | (화면별 `extra_css` 자리) | 기능 폴더의 CSS가 여기 들어감 |
| 4 | `static/css/layers/30-stability.css` | 안정화·가독성 |
| 5 | `static/css/layers/40-navigation-editor.css` | 메뉴·본문 이미지·강사 선택·과목 자료 |
| — | (화면별 `page_css` 자리) | |
| 6 | `static/css/layers/50-intranet-theme.css` | 인트라넷과 같은 배치·색 |
| 7 | `static/css/layers/60-visual-refresh.css` | 화면 다듬기 |
| 8 | `static/css/layers/70-home-messenger.css` | 홈·메신저 |
| 9 | `static/css/layers/80-readability.css` | 글자 크기·대비 |
| 10 | `static/css/layers/90-usability.css` | 입력칸·버튼 크기 |
| 11 | `static/css/layers/95-portal-focus.css` | 홈 카드·작은 대화창·담당 학생 지정 (마지막) |

로그인 화면(`apps/accounts/templates/accounts/login.html`)은 base.html을 쓰지 않고 00·50·60·80 층만 직접 불러옵니다.

## 6. CSS/JS 이름 바뀐 표 (2026-10-13 정리)

| 예전 이름 | 지금 위치 |
|---|---|
| static/css/app.css | `static/css/layers/00-base.css` |
| static/css/recovery_premium.css | `static/css/layers/10-premium-portal.css` |
| static/css/workflow_refinement.css | `static/css/layers/20-workflow.css` |
| static/css/performance_stability.css | `static/css/layers/30-stability.css` |
| static/css/stage14_features.css | `static/css/layers/40-navigation-editor.css` |
| static/css/intranet_ui_v2.css | `static/css/layers/50-intranet-theme.css` |
| static/css/visual_refresh_v1.css | `static/css/layers/60-visual-refresh.css` |
| static/css/home_messenger_v1.css | `static/css/layers/70-home-messenger.css` |
| static/css/readability_v2.css | `static/css/layers/80-readability.css` |
| static/css/usability_v1.css | `static/css/layers/90-usability.css` |
| static/css/portal_focus_v2.css | `static/css/layers/95-portal-focus.css` |
| static/css/operating-v5-compact.css | `static/css/components/compact-pages.css` |
| static/css/student-transfer-selector.css | `static/css/components/student-transfer-selector.css` |
| static/css/student-learning-overview.css | `static/css/components/learning-overview.css` |
| static/js/student-transfer-selector.js | `static/js/components/student-transfer-selector.js` |
| static/js/intranet_ui_v2.js | `static/js/global/ui-shell.js` |
| static/js/student-browser.js | `static/js/global/student-browser.js` |
| static/js/usability_v1.js | `static/js/global/form-usability.js` |
| static/css/lms_operations.css | `apps/lms/static/lms/css/workspace.css` |
| static/js/portal_polling.js | `apps/lms/static/lms/js/polling.js` |
| static/js/message_summary.js | `apps/lms/static/lms/js/message-summary.js` |
| static/js/lms_messages.js | `apps/lms/static/lms/js/messages.js` |
| static/js/chat_composer_v2.js | `apps/lms/static/lms/js/chat-composer.js` |
| static/js/portal_chat_v2.js | `apps/lms/static/lms/js/chat-widget.js` |
| static/js/lms_annotation.js | `apps/lms/static/lms/js/annotation.js` |
| static/css/class_catalog.css | `apps/dashboard/static/dashboard/css/class-catalog.css` |
| static/js/student_home.js | `apps/dashboard/static/dashboard/js/student-home.js` |
| static/js/teacher-student-self-assignment.js | `apps/operations/static/operations/js/teacher-assignment.js` |
| static/js/rich-paste-editor.js | `apps/content_editor/static/content_editor/js/rich-paste-editor.js` |
| static/js/course-resource-form.js | `apps/classroom/static/classroom/js/resource-form.js` |
| static/js/exam_detail_fast.js | `apps/assessments/static/assessments/js/exam-detail.js` |
| static/js/student_learning_insight.js | `apps/assessments/static/assessments/js/learning-insight.js` |
| static/js/visual_refresh_v1.js | `apps/accounts/static/accounts/js/login.js` |

화면에서는 `{% static 'lms/js/messages.js' %}`처럼 `static/` 뒤 경로로 부릅니다. 경로를 잘못 적으면 `config/tests/test_static_references.py` 테스트가 실패해서 알려 줍니다.

## 7. 기능 폴더 이름과 DB

- 파이썬에서는 `apps.lms`처럼 부르지만, DB 표 이름과 연결된 이름(`label`)은 예전 그대로 `lms`입니다(`apps/lms/apps.py`).
- 그래서 DB 표 이름(`lms_conversation` 등)과 저장된 데이터는 정리 전과 같습니다. `label`은 바꾸지 마세요.
