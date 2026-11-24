<#
처음 설치 / 다시 설치

  .\scripts\setup.ps1

- 파이썬 3.12 가상환경(.venv)을 만들고 필요한 패키지를 설치합니다.
- data\demo 폴더를 만듭니다.
- demo DB가 없으면 새로 만들고(migrate) 데모 계정을 넣습니다.
#>
# 한국어 Windows에서도 파이썬이 파일을 UTF-8로 읽게 합니다.
$env:PYTHONUTF8 = "1"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[1/4] 파이썬 3.12 가상환경을 만듭니다..."
    py -3.12 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "가상환경을 만들지 못했습니다. 'py -0p' 로 파이썬 3.12 설치 여부를 확인하세요." }
}
$python = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "[2/4] 필요한 패키지를 설치합니다..."
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "패키지 설치에 실패했습니다." }

Write-Host "[3/4] data 폴더를 준비합니다..."
New-Item -ItemType Directory -Force -Path "data\demo\media" | Out-Null

if (-not (Test-Path "data\demo\db.sqlite3")) {
    Write-Host "[4/4] demo DB를 새로 만듭니다..."
    & $python manage.py migrate --settings=config.settings.demo
    if ($LASTEXITCODE -ne 0) { throw "demo DB를 만들지 못했습니다." }
    & $python manage.py seed_demo_users --settings=config.settings.demo
} else {
    Write-Host "[4/4] demo DB가 이미 있어 그대로 둡니다."
}
Write-Host "[완료] 실행: .\scripts\run.ps1"
