"""Small original stdlib PEP 517 wheel backend; no network or dependencies."""
import base64
import csv
import hashlib
import io
from pathlib import Path
import zipfile

NAME = "probability_calibration_auditor"
VERSION = "0.1.0"
DIST_INFO = f"{NAME}-{VERSION}.dist-info"
METADATA = ("Metadata-Version: 2.1\nName: probability-calibration-auditor\n"
            "Version: 0.1.0\nSummary: Binary probability scores and reliability diagnostics\n"
            "Requires-Python: >=3.11\n\n")
WHEEL = "Wheel-Version: 1.0\nGenerator: probability-calibration-auditor\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
ENTRY = "[console_scripts]\nprobability-calibration-auditor = probability_calibration_auditor.cli:main\n"


def get_requires_for_build_wheel(config_settings=None):
    return []


def metadata_files():
    return {f"{DIST_INFO}/METADATA": METADATA.encode(),
            f"{DIST_INFO}/WHEEL": WHEEL.encode(),
            f"{DIST_INFO}/entry_points.txt": ENTRY.encode()}


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    for name, raw in metadata_files().items():
        path = Path(metadata_directory) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    return DIST_INFO


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    source = Path(__file__).resolve().parent / "src" / NAME
    files = metadata_files()
    for path in sorted(source.glob("*.py")):
        if path.is_symlink() or not path.is_file():
            raise ValueError("source must be regular files")
        files[f"{NAME}/{path.name}"] = path.read_bytes()
    if not files.get(f"{NAME}/core.py"):
        raise ValueError("missing source")
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, raw in sorted(files.items()):
        digest = base64.urlsafe_b64encode(hashlib.sha256(raw).digest()).rstrip(b"=").decode("ascii")
        writer.writerow([name, "sha256=" + digest, str(len(raw))])
    writer.writerow([f"{DIST_INFO}/RECORD", "", ""])
    files[f"{DIST_INFO}/RECORD"] = record.getvalue().encode()
    filename = f"{NAME}-{VERSION}-py3-none-any.whl"
    target = Path(wheel_directory) / filename
    with target.open("xb") as handle, zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, raw)
    return filename
