"""Prepare and verify the isolated Airflow staging volume permissions."""
import argparse
import os
from pathlib import Path
import stat
import tempfile

STAGING = Path("/opt/soccer/data/staging")
APP_UID = 50000
APP_GID = 0
MODE = 0o750


def verify(path=STAGING, uid=APP_UID, gid=APP_GID, mode=MODE, check_write=False):
    path = Path(path)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise RuntimeError("Staging path must be a real directory.")
    if (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)) != (uid, gid, mode):
        raise RuntimeError("Staging directory ownership or mode is incorrect.")
    if check_write:
        with tempfile.NamedTemporaryFile(prefix=".permission-check-", dir=path):
            pass


def prepare(path=STAGING, uid=APP_UID, gid=APP_GID, mode=MODE):
    """Own only the staging leaf; never recurse into data already staged."""
    path = Path(path)
    if path.is_symlink():
        raise RuntimeError("Refusing a symlink as the staging directory.")
    path.mkdir(mode=mode, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir():
        raise RuntimeError("Staging path must be a real directory.")
    os.chmod(path, mode, follow_symlinks=False)
    os.chown(path, uid, gid, follow_symlinks=False)
    verify(path, uid, gid, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check"))
    args = parser.parse_args()
    if args.action == "prepare":
        if os.geteuid() != 0:
            raise SystemExit("Run the narrow setup helper as root.")
        prepare()
        print("Staging directory prepared for UID 50000, GID 0, mode 0750.")
    else:
        if (os.geteuid(), os.getegid()) != (APP_UID, APP_GID):
            raise SystemExit("Run the write check as UID 50000, GID 0.")
        verify(check_write=True)
        print("Staging directory ownership and application-user write check passed.")


if __name__ == "__main__":
    main()
