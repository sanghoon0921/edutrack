# apps/accounts — 로그인·계정·권한

로그인, 내 정보 수정, 역할별 메뉴, 계정 ↔ 학생번호 연결. 자세한 안내: [docs/features/accounts.md](../../docs/features/accounts.md)

| 파일 | 하는 일 |
|---|---|
| models.py | `User`(역할 4개), `StudentAccountLink`(계정 ↔ 인트라넷 학생번호) |
| views.py | 로그인 화면(`EduTrackLoginView`), 내 정보 수정 |
| forms.py | 로그인·정보 수정 입력 칸 |
| urls.py | `/accounts/…` 주소 |
| decorators.py, mixins.py | 역할별 화면 제한 도구 |
| student_links.py | 로그인한 계정의 대표 학생번호 찾기 |
| demo_account_binding.py | 테스트 계정을 관리자가 연 학생에게 잠시 연결(demo/real 모드에서는 꺼짐) |
| context_processors.py | 역할별 왼쪽 메뉴 |
| admin.py, apps.py | Django 관리자 화면 등록, 앱 설정(`label = "accounts"` 바꾸지 말 것) |
| management/commands/ | `seed_demo_users`, `seed_parent_demo` (demo 계정 만들기) |
| `apps/accounts/templates/accounts/` | 로그인·정보 수정 화면 |
| `apps/accounts/static/accounts/js/login.js` | 비밀번호 "보기" 버튼 |
| `apps/accounts/tests/` | 자동 테스트 |
