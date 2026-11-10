"""Run the local RC server and retain a bounded, metadata-only error log."""
import argparse
from contextlib import closing
from logging import Formatter
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sqlite3

import uvicorn

from backend.error_log import logger
from backend.core.config import ROOT, Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, required=True)
    args = parser.parse_args()
    try:
        settings = Settings()
        database = settings.resolved_database_path()
        if database.exists():
            with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=2)) as connection:
                connection.execute('PRAGMA schema_version').fetchone()
        if not (ROOT / 'frontend' / 'index.html').is_file():
            raise FileNotFoundError
    except Exception:
        parser.exit(3, 'PixelPet preflight failed. Check configuration, database access, and frontend files.\n')
    key = settings.deepseek_api_key if settings.llm_provider == 'deepseek' else settings.llm_api_key
    if settings.llm_mode == 'mock':
        print('AI mode: Mock (explicitly selected).', flush=True)
    elif not key.get_secret_value().strip():
        if settings.llm_mode != 'auto':
            parser.exit(3, 'AI provider selected but its API credential is missing.\n')
        print('AI mode: Mock (no configured API credential).', flush=True)
    else:
        print(f'AI mode: {settings.llm_provider} (configured).', flush=True)
    directory = Path(__file__).resolve().parents[1] / 'output' / 'logs'
    directory.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(directory / 'service-errors.log', maxBytes=512 * 1024,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(Formatter('%(asctime)s %(levelname)s %(message)s'))
    logger.addHandler(handler)
    logger.propagate = False
    try:
        uvicorn.run('backend.main:app', host='127.0.0.1', port=args.port,
                    ws_max_size=16384, access_log=False)
    finally:
        logger.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    main()
