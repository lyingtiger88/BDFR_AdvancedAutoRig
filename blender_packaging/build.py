"""Build an installable Blender ZIP from the current add-on source."""

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.6.0'
SOURCE = ROOT / 'vehicle_auto_rig' / '__init__.py'
ENTRY = 'vehicle_auto_rig/__init__.py'


def build_zip(output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    info = ZipInfo(ENTRY, date_time=(2024, 1, 1, 0, 0, 0))
    info.compress_type = ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    with ZipFile(output, 'w') as archive:
        archive.writestr(info, SOURCE.read_bytes())
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'dist' / ('BDFR_AdvancedAutoRig-' + VERSION + '.zip')))
    args = parser.parse_args()
    print(build_zip(args.output))
