"""Create a deterministic, self-contained install ZIP for Maya."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.1.2'
NAME = 'BDFR_AdvancedAutoRig'
FILES = {
    'install.py': ROOT / 'maya_packaging' / 'install.py',
    'README_MAYA.txt': ROOT / 'maya_packaging' / 'README_MAYA.txt',
    NAME + '.mod': ROOT / 'maya_packaging' / (NAME + '.mod'),
    NAME + '/icons/BDFR_AutoRig_64.png': ROOT / 'maya_packaging' / 'icons' / 'BDFR_AutoRig_64.png',
    NAME + '/icons/BDFR_AutoRig_128.png': ROOT / 'maya_packaging' / 'icons' / 'BDFR_AutoRig_128.png',
    NAME + '/plug-ins/bdfr_advanced_autorig.py': ROOT / 'maya_packaging' / 'bdfr_advanced_autorig.py',
    **{NAME + '/scripts/maya_autorig/' + name: ROOT / 'maya_autorig' / name
       for name in ('__init__.py', 'core.py', 'scene.py', 'export.py', 'ui.py')},
}


def build_zip(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w') as archive:
        for name, source in sorted(FILES.items()):
            meta = ZipInfo(name, date_time=(2024, 1, 1, 0, 0, 0))
            meta.compress_type = ZIP_DEFLATED
            meta.external_attr = 0o644 << 16
            archive.writestr(meta, source.read_bytes())
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'dist' / ('BDFR_AdvancedAutoRig_Maya-' + VERSION + '.zip')))
    args = parser.parse_args()
    print(build_zip(args.output))
