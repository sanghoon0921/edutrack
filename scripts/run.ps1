<#
EduTrack 실행 도우미 (가짜 자료 demo 모드)

  .\scripts\run.ps1      demo 모드 개발 서버

브라우저 주소: http://127.0.0.1:8000/
끄기: 이 창에서 Ctrl + C
#>
# 한국어 Windows에서도 파이썬이 파일을 UTF-8로 읽게 합니다.
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "파이썬 가상환경(.venv)이 없습니다. 먼저 .\scripts\setup.ps1 을 실행하세요."
}
$db = Join-Path $root "data\demo\db.sqlite3"
if (-not (Test-Path $db)) {
    throw "DB 파일이 없습니다: $db  (먼저 .\scripts\setup.ps1 을 실행하세요)"
}

$settings = "config.settings.demo"
Write-Host "[EduTrack] demo 모드 / DB: $db"
Write-Host "[EduTrack] 오류가 나면 브라우저 화면에 파일 이름과 줄 번호가 표시됩니다."
& $python manage.py runserver 127.0.0.1:8000 --settings=$settings
exit $LASTEXITCODE
