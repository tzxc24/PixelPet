import sqlite3

import pytest

from scripts import backup


def test_backup_integrity_and_exclusive_restore(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'ROOT', tmp_path)
    original = tmp_path / 'original.sqlite3'
    with sqlite3.connect(original) as db:
        db.execute('CREATE TABLE memory (text TEXT)')
        db.execute("INSERT INTO memory VALUES ('synthetic memory')")
    snapshot = backup.backup_database(original, tmp_path / 'output/backups/snapshot.sqlite3',
                                      project_root=tmp_path)
    restored = tmp_path / 'restored.sqlite3'
    with pytest.raises(ValueError, match='confirmation'):
        backup.restore_database(snapshot, restored)
    assert not restored.exists()
    backup.check_database(snapshot)
    with pytest.raises(FileExistsError):
        backup.restore_database(snapshot, original, confirmed=True)
    assert backup.restore_database(snapshot, restored, confirmed=True) == restored
    with sqlite3.connect(restored) as db:
        assert db.execute('SELECT text FROM memory').fetchone() == ('synthetic memory',)
    with pytest.raises(FileExistsError):
        backup.restore_database(snapshot, restored, confirmed=True)


def test_corrupt_backup_is_rejected_without_creating_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, 'ROOT', tmp_path)
    corrupt = tmp_path / 'broken.sqlite3'
    corrupt.write_bytes(b'invalid SQLite')
    target = tmp_path / 'restore.sqlite3'
    with pytest.raises(sqlite3.DatabaseError):
        backup.restore_database(corrupt, target, confirmed=True)
    assert not target.exists()
