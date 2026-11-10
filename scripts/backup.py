"""Create a consistent SQLite backup, excluding application secrets and media."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def backup_database(source: Path, destination: Path, *, project_root: Path = ROOT) -> Path:
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    backup_root = (Path(project_root) / 'output' / 'backups').resolve()
    if not destination.is_relative_to(backup_root) or destination == backup_root:
        raise ValueError('Backup destination must be inside output/backups.')
    if source == destination:
        raise ValueError('Backup destination must differ from source.')
    return copy_database(source, destination)


def check_database(source: Path) -> None:
    source = source.resolve(strict=True)
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as database:
        if database.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
            raise ValueError('SQLite integrity check failed.')


def copy_database(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ('-wal', '-shm', '-journal'):
        if Path(str(destination) + suffix).exists():
            raise FileExistsError('Destination has an existing SQLite sidecar.')
    # Exclusive reservation protects existing files, including under concurrent runs.
    with destination.open('xb'):
        pass
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
            with closing(sqlite3.connect(destination)) as backup:
                original.backup(backup)
        check_database(destination)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    return destination


def restore_database(source: Path, destination: Path, *, confirmed: bool = False) -> Path:
    if not confirmed:
        raise ValueError('Restore requires explicit confirmation.')
    source = source.resolve(strict=True)
    destination = destination.resolve()
    if not destination.is_relative_to(ROOT):
        raise ValueError('Restore destination must be inside the project.')
    check_database(source)
    return copy_database(source, destination)


def main():
    from backend.core.config import Settings
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path)
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument('--check', type=Path, metavar='BACKUP')
    operations.add_argument('--restore', type=Path, metavar='BACKUP')
    parser.add_argument('--confirm-restore', action='store_true')
    options = parser.parse_args()
    if options.check:
        check_database(options.check)
        print('SQLite integrity check passed.')
        return
    if options.restore:
        if not options.destination or not options.confirm_restore:
            parser.error('--restore requires a new --destination and --confirm-restore')
        print(restore_database(options.restore, options.destination, confirmed=True))
        return
    target = options.destination or ROOT / 'output' / 'backups' / (datetime.now(timezone.utc).strftime('pixelpet-%Y%m%dT%H%M%S-%fZ') + '.sqlite3')
    print(backup_database(Settings().resolved_database_path(), target))


if __name__ == '__main__':
    main()
