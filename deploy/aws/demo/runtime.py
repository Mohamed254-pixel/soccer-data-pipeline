"""Materialize demo-only secrets privately and invoke the exact Compose project."""
import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPOSITORY = HERE.parents[2]
PASSWORD_FILES = {
    "DEMO_ROOT_PASSWORD": "mysql-root",
    "DEMO_APP_PASSWORD": "mysql-app",
    "DEMO_BOOTSTRAP_PASSWORD": "mysql-bootstrap",
}
PASSWORDS = set(PASSWORD_FILES) | {"DEMO_METADATA_PASSWORD", "DEMO_JWT_SECRET"}
SECRET_KEYS = PASSWORDS | {"DEMO_FERNET_KEY", "DEMO_FOOTBALL_TOKEN"}
IMAGE_KEYS = {"DEMO_IMAGE", "DEMO_MYSQL_IMAGE", "DEMO_POSTGRES_IMAGE"}
BUCKET_KEY = "DEMO_RAW_BUCKET"
ACCOUNT_KEY = "DEMO_AWS_ACCOUNT_ID"
SETTING_KEYS = IMAGE_KEYS | {BUCKET_KEY, ACCOUNT_KEY}


def validate(secrets, settings):
    if set(secrets) != SECRET_KEYS or set(settings) != SETTING_KEYS:
        raise ValueError("Unexpected runtime keys")
    for value in (*secrets.values(), *settings.values()):
        if not isinstance(value, str) or not value or any(ch in value for ch in "\r\n\x00"):
            raise ValueError("Invalid runtime value")
    if any(not re.fullmatch(r"[a-f0-9]{64}", secrets[key]) for key in PASSWORDS):
        raise ValueError("Expected independent 32-byte hex secrets")
    from cryptography.fernet import Fernet
    Fernet(secrets["DEMO_FERNET_KEY"].encode())
    if len(set(secrets.values())) != len(secrets):
        raise ValueError("Demo secrets must be independent")
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", settings[BUCKET_KEY]):
        raise ValueError("Invalid bucket name")
    if not re.fullmatch(r"[0-9]{12}", settings[ACCOUNT_KEY]):
        raise ValueError("Expected the verified AWS account ID")
    if not re.fullmatch(r"premier-league-demo:[a-f0-9]{7,40}", settings["DEMO_IMAGE"]):
        raise ValueError("Use the reviewed commit tag for the local build")
    for key, repository in (("DEMO_MYSQL_IMAGE", "mysql"), ("DEMO_POSTGRES_IMAGE", "postgres")):
        if not re.fullmatch(rf"{repository}@sha256:[a-f0-9]{{64}}", settings[key]):
            raise ValueError("Pin the database images to reviewed digests")


def prepare(directory, secrets, settings):
    validate(secrets, settings)
    directory.mkdir(mode=0o700)
    created = []
    try:
        for key, name in PASSWORD_FILES.items():
            path = directory / name
            # Only the target containers can access bind mounts under this
            # root-only directory, including MySQL's unprivileged entrypoint.
            with path.open("x") as handle:
                created.append(path)
                os.fchmod(handle.fileno(), 0o444)
                handle.write(secrets[key] + "\n")
        path = directory / "runtime.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created.append(path)
        with os.fdopen(fd, "w") as handle:
            json.dump({**settings, **{k: v for k, v in secrets.items() if k not in PASSWORD_FILES},
                       "DEMO_APP_PASSWORD": secrets["DEMO_APP_PASSWORD"]}, handle)
    except BaseException:
        for path in created:
            path.unlink()
        directory.rmdir()
        raise


def run_compose(directory, args):
    path = directory / "runtime.json"
    if path.stat().st_uid != os.getuid() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise ValueError("Runtime config must be privately owned")
    runtime = json.loads(path.read_text())
    if set(runtime) != (SECRET_KEYS - set(PASSWORD_FILES)) | SETTING_KEYS | {"DEMO_APP_PASSWORD"}:
        raise ValueError("Unexpected Compose environment keys")
    if not args or (args[0] == "config" and "--quiet" not in args):
        raise ValueError("Use config --quiet to avoid printing credentials")
    # Ignore production .env, inherited pipeline settings and alternate Docker contexts.
    env = {key: os.environ[key] for key in ("PATH", "HOME", "USER", "TERM") if key in os.environ}
    env.update(runtime, DEMO_PRIVATE_DIR=str(directory))
    return subprocess.call(
        ["docker", "--host", "unix:///var/run/docker.sock", "compose", "--env-file", "/dev/null",
         "--project-name", "premier-league-aws-demo", "-f", str(HERE / "compose.yaml"), *args],
        env=env,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", required=True, type=Path)
    parser.add_argument("--settings", type=Path, help="Prepare from a reviewed settings file and secret JSON on stdin")
    parser.add_argument("compose_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if directory.is_relative_to(REPOSITORY) or os.geteuid() != 0:
        raise ValueError("Use sudo on the dedicated demo host with a private directory outside the repo")
    if args.settings:
        if args.compose_args:
            raise ValueError("Prepare and Compose are separate operations")
        prepare(directory, json.load(sys.stdin), json.loads(args.settings.read_text()))
        return 0
    return run_compose(directory, args.compose_args[1:] if args.compose_args[:1] == ["--"] else args.compose_args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        sys.exit(f"Demo command stopped ({type(exc).__name__}); details withheld.")
