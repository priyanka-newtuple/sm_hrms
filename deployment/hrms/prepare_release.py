"""Scoped HRMS archive retention and upload preflight; never touches application data."""
import argparse
import re
import shutil
from pathlib import Path

SHA = re.compile(r"[a-f0-9]{40}")
GIB = 1024 ** 3


def prepare(base, incoming, upload_bytes, keep=3, reserve_bytes=3 * GIB):
    if not SHA.fullmatch(incoming) or upload_bytes < 0 or keep < 3:
        raise ValueError("Invalid release preparation arguments")
    base = Path(base).resolve(strict=True)
    releases = base / "releases"
    if releases.is_symlink():
        raise ValueError("Release directory must not be a symlink")
    releases.mkdir(exist_ok=True)
    protected = {incoming}
    for pointer in (base / "current", base / "previous-release"):
        if not pointer.exists() and not pointer.is_symlink():
            continue
        target = pointer.resolve(strict=True) if pointer.is_symlink() else Path(pointer.read_text().strip())
        if not target.is_absolute():
            target = base / target
        target = target.resolve(strict=True)
        if target.parent != releases or not SHA.fullmatch(target.name):
            raise ValueError("Invalid release pointer; refusing cleanup")
        protected.add(target.name)
    folders = sorted((p for p in releases.iterdir() if not p.is_symlink() and p.is_dir() and SHA.fullmatch(p.name) and (p / 'images.tar.gz').is_file()),
                     key=lambda p: p.stat().st_mtime, reverse=True)
    protected.update(p.name for p in folders[:keep])
    reclaimed = 0
    for folder in folders:
        if folder.name in protected:
            continue
        archive = folder / "images.tar.gz"
        if archive.is_symlink():
            continue
        if archive.is_file():
            size = archive.stat().st_size
            archive.unlink()
            reclaimed += size
            print(f"Removed obsolete HRMS image archive: {folder.name} ({size} bytes)")
    # Preserve release manifests, backups, uploads, private configuration and all Docker volumes.
    free = shutil.disk_usage(base).free
    required = upload_bytes + reserve_bytes
    print(f"HRMS storage: reclaimed={reclaimed} free={free} required={required} bytes")
    if free < required:
        raise RuntimeError("Insufficient space after safe archive cleanup. Expand storage or review retained backups/images; no database data or backups were deleted.")
    target = releases / incoming
    if target.is_symlink():
        raise ValueError("Incoming release must not be a symlink")
    target.mkdir(exist_ok=True)
    # Prove deployment-user write access before uploading the large artifact.
    import tempfile
    with tempfile.TemporaryFile(dir=target):
        pass
    return reclaimed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sha")
    parser.add_argument("upload_bytes", type=int)
    args = parser.parse_args()
    prepare("/opt/newtuple-hrms", args.sha, args.upload_bytes)
