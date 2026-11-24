# 로그인·계정·권한

## 무엇을 하나요

로그인·로그아웃, 내 정보 수정, 역할(관리자·강사·학생·학부모)별 메뉴를 담당합니다. 학생·학부모 계정은 인트라넷 학생번호와 연결돼야 자기(자녀) 정보를 볼 수 있습니다.

## 화면 주소

| 화면 | 주소 | URL 이름 |
|---|---|---|
| 로그인 | `/accounts/login/` | `login` |
| 로그아웃 | `/accounts/logout/` | `logout` |
| 내 정보 수정 | `/accounts/profile/` | `profile` |

## 관련 파일

| 종류 | 파일 | 하는 일 |
|---|---|---|
| DB 표 | `apps/accounts/models.py` | `User`(역할 `User.Role`), `StudentAccountLink`(계정 ↔ 학생번호) |
| 화면 처리 | `apps/accounts/views.py` | 로그인 화면, 내 정보 수정 |
| 입력 양식 | `apps/accounts/forms.py` | 로그인·정보 수정 칸 |
| 권한 도구 | `apps/accounts/decorators.py`, `apps/accounts/mixins.py` | 역할별 화면 제한 |
| 학생번호 찾기 | `apps/accounts/student_links.py` | 로그인한 계정의 대표 학생번호 |
| 메뉴 | `apps/accounts/context_processors.py` | 역할별 왼쪽 메뉴 |
| 화면(HTML) | `apps/accounts/templates/accounts/login.html`, `apps/accounts/templates/accounts/profile_form.html` | 로그인·정보 수정 |
| JS | `apps/accounts/static/accounts/js/login.js` | 비밀번호 "보기" 버튼 |
| 데모 계정 | `apps/accounts/management/commands/seed_demo_users.py` | demo DB에 테스트 계정 생성 |
| 테스트 | `apps/accounts/tests/test_parent_portal.py`, `apps/accounts/tests/test_profile_update.py` | |

## 데이터는 어디서 오나요

자체 DB(`data/<모드>/db.sqlite3`)의 `accounts_user`, `accounts_studentaccountlink` 표입니다.

## 누가 볼 수 있나요

| 역할 | 할 수 있는 일 |
|---|---|
| 모두 | 로그인, 내 정보 수정 |
| 관리자 | 계정 만들기·수정·학생 연결 ([operations.md](operations.md)) |

## 자주 생기는 문제

| 증상 | 먼저 볼 곳 |
|---|---|
| 로그인 후 "권한 없음(403)" | 계정의 역할, `apps/accounts/decorators.py` |
| 학생·학부모 화면에 정보가 없음 | 운영 → 사용자 상세에서 학생번호 연결 |
| 비밀번호를 잊음 | 관리자가 운영 화면(`/operations/users/`)에서 변경 |
| 로그인 화면 모양 | `apps/accounts/templates/accounts/login.html`과 CSS 층 00·50·60·80 |
