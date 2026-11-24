"""DB를 바꾸기(migrate) 전에 SQLite DB 백업 사본을 만듭니다.

SQLite 백업 기능을 써서 다른 프로그램이 DB를 쓰고 있어도 깨지지 않은 사본을 만듭니다. 원본은 읽기만 합니다.
실행: python -m config.db_backup data/real/db.sqlite3
      → data/real/backups/db-YYYYMMDD-HHMMSS.sqlite3 를 만들고 그 경로를 출력 (운영 서버 실행 스크립트가 사용)
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def backup_sqlite(source: Path, backup_dir: Path | None = None, *, now: datetime | None = None) -> Path:
    backup_dir = backup_dir or source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"db-{(now or datetime.now()):%Y%m%d-%H%M%S}.sqlite3"
    original = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
    copy = sqlite3.connect(target)
    try:
        original.backup(copy)
    finally:
        copy.close()
        original.close()
    return target


# ── 매일 백업(11/24 전체 점검): 사무실 서버를 켜 둔 동안 하루 한 번 DB 사본 + 업로드 파일 묶음, 14일 보관 ──
DAILY_KEEP_DAYS = 14


def daily_backup(source: Path, media_dir: Path | None = None, backup_dir: Path | None = None, *,
                 now: datetime | None = None, keep_days: int = DAILY_KEEP_DAYS) -> bool:
    """오늘 백업이 없으면 daily-db-YYYYMMDD.sqlite3 와 daily-media-YYYYMMDD.zip 을 만들고 True.
    오래된 daily-* 만 지웁니다(migrate 전 백업 db-*.sqlite3 는 건드리지 않음)."""
    import zipfile
    from datetime import timedelta

    now = now or datetime.now()
    backup_dir = backup_dir or source.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = f"{now:%Y%m%d}"
    db_copy = backup_dir / f"daily-db-{stamp}.sqlite3"
    made = False
    if not db_copy.exists():
        temp = backup_dir / f"daily-db-{stamp}.partial"
        original = sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)
        copy = sqlite3.connect(temp)
        try:
            original.backup(copy)
        finally:
            copy.close()
            original.close()
        temp.replace(db_copy)
        made = True
        if media_dir and Path(media_dir).is_dir():
            media_dir = Path(media_dir)
            with zipfile.ZipFile(backup_dir / f"daily-media-{stamp}.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
                for file in sorted(media_dir.rglob("*")):
                    if file.is_file():
                        bundle.write(file, file.relative_to(media_dir).as_posix())
    oldest = (now - timedelta(days=keep_days - 1)).strftime("%Y%m%d")
    for old in list(backup_dir.glob("daily-db-*.sqlite3")) + list(backup_dir.glob("daily-media-*.zip")):
        date = old.stem.rsplit("-", 1)[-1]
        if date.isdigit() and date < oldest:
            old.unlink(missing_ok=True)
    return made


def start_daily(check_seconds: int = 3600):
    """settings.DAILY_BACKUP 가 켜져 있으면(사무실 서버) 백그라운드에서 한 시간마다 오늘 백업이 있는지 보고 없으면 만듭니다."""
    import logging
    import threading

    from django.conf import settings

    if not getattr(settings, "DAILY_BACKUP", False):
        return None
    log = logging.getLogger("edutrack.backup")
    source = Path(settings.DATABASES["default"]["NAME"])
    media = Path(settings.MEDIA_ROOT)

    def run():
        while True:
            try:
                if daily_backup(source, media):
                    log.info("매일 백업을 만들었습니다: %s", source.parent / "backups")
            except Exception as exc:  # 백업이 실패해도 서버는 계속 동작합니다
                log.warning("매일 백업 실패: %s", exc)
            threading.Event().wait(check_seconds)

    thread = threading.Thread(target=run, name="daily-backup", daemon=True)
    thread.start()
    return thread


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        print("사용법: python -m config.db_backup <DB 파일 경로>", file=sys.stderr)
        raise SystemExit(2)
    print(backup_sqlite(Path(sys.argv[1])))
