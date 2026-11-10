"""Create a source-only RC archive and compare configured secrets without printing them."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from dotenv import dotenv_values
from backend.core.config import ROOT, Settings
from backend.release import RELEASE


def main():
    output = ROOT / 'output' / 'v1.2'
    output.mkdir(parents=True, exist_ok=True)
    extensions = {'.py', '.ps1', '.bat', '.js', '.cjs', '.css', '.html', '.md',
                  '.json', '.h', '.cpp', '.c', '.txt', '.ini', '.defaults'}
    special = {'sdkconfig', 'Kconfig.projbuild', 'LICENSE'}
    roots = ('backend', 'frontend', 'scripts', 'tests', 'firmware', 'hardware', 'shared', 'config', 'docs')
    source = {
        file for folder in roots for file in (ROOT / folder).rglob('*')
        if file.is_file() and file.resolve().is_relative_to(ROOT)
        and not set(file.relative_to(ROOT).parts) & {'build', 'managed_components', '__pycache__', '.git'}
        and not file.name.startswith('.env')
        and (file.suffix in extensions or file.name in special)
    }
    source.update(ROOT / name for name in
                  ('.env.example', '.gitignore', 'README.md', 'requirements.txt', 'pytest.ini', 'start_pixelpet.bat'))
    settings = Settings()
    local = dotenv_values(ROOT / '.env', encoding='utf-8-sig', interpolate=False)
    names = ('LLM_API_KEY', 'DEEPSEEK_API_KEY', 'PIXELPET_ACCESS_TOKEN')
    secrets = {value.encode() for value in
               [settings.llm_api_key.get_secret_value(), settings.deepseek_api_key.get_secret_value(),
                settings.access_token.get_secret_value(), *(local.get(name) or '' for name in names)]
               if len(value) >= 8}
    logs = {file for file in (ROOT / 'output').rglob('*')
            if file.is_file() and file.suffix in {'.txt', '.log', '.json', '.md'}
            and file.stat().st_size <= 16 * 1024 * 1024}
    hits = [str(file.relative_to(ROOT)) for file in sorted(source | logs)
            if any(secret in file.read_bytes() for secret in secrets)]
    if hits:
        raise SystemExit('Configured credential match in: ' + ', '.join(hits))
    archive = output / 'PixelPet-V1.2-RC2-source.zip'
    with ZipFile(archive, 'x', ZIP_DEFLATED) as target:
        for file in sorted(source):
            target.write(file, file.relative_to(ROOT).as_posix())
    with ZipFile(archive) as target:
        if target.testzip() is not None:
            raise RuntimeError('Archive CRC check failed')
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    manifest = {'release': RELEASE, 'members': len(source), 'sha256': digest,
                'files_scanned': len(source | logs), 'secret_values_compared': len(secrets),
                'configured_secret_matches': 0}
    (output / 'release-verification.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest))


if __name__ == '__main__':
    main()
