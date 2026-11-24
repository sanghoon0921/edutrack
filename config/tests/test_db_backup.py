"""운영 서버 실행 스크립트가 DB를 바꾸기 전에 실제 DB 백업 사본을 만든다."""
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from config.db_backup import backup_sqlite


def rows(path):
    db = sqlite3.connect(path)
    try:
        return [row[0] for row in db.execute("select x from t")]
    finally:
        db.close()


class DbBackupTests(SimpleTestCase):
    def test_backup_copies_every_row_into_a_dated_file_and_leaves_the_source_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "db.sqlite3"
            db = sqlite3.connect(source)
            db.execute("create table t (x integer)")
            db.execute("insert into t values (7)")
            db.commit()
            db.close()
            before = source.read_bytes()
            target = backup_sqlite(source, now=datetime(2026, 10, 21, 9, 30, 5))
            self.assertEqual(target, Path(tmp) / "backups" / "db-20261021-093005.sqlite3")
            self.assertEqual(rows(target), [7])
            self.assertEqual(source.read_bytes(), before)

