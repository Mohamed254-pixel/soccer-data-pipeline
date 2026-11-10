"""Use a private JSON runtime config with the separate cloud Compose stack."""
import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys


def command_environment(path):
    path = Path(path).expanduser().resolve()
    if path.is_relative_to(Path(__file__).resolve().parents[1]):
        raise ValueError('Cloud runtime configuration must stay outside the repository.')
    metadata = path.stat()
    if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError('Runtime configuration must be owned by this user with mode 0600.')
    value = json.loads(path.read_text())
    from aws_runtime_env import REQUIRED, OPTIONAL
    if not isinstance(value, dict) or REQUIRED - set(value) or set(value) - REQUIRED - OPTIONAL:
        raise ValueError('Unexpected cloud configuration keys.')
    if any(not isinstance(x, str) or not x or any(c in x for c in '\r\n\x00') for x in value.values()):
        raise ValueError('Invalid cloud configuration value.')
    return {**os.environ, **value}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('compose_args', nargs=argparse.REMAINDER)
    args = p.parse_args()
    tail = args.compose_args[1:] if args.compose_args[:1] == ['--'] else args.compose_args
    if not tail or (tail[0] == 'config' and '--quiet' not in tail):
        raise ValueError('Supply a Compose command; expanded config output is refused. Use config --quiet.')
    file = Path(__file__).resolve().parents[1] / 'deploy/aws/compose.yaml'
    result = subprocess.run(['docker', 'compose', '--project-name', 'premier-league-cloud', '-f', str(file), *tail],
                            env=command_environment(args.config))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Cloud Compose stopped ({type(exc).__name__}); details withheld.', file=sys.stderr)
        raise SystemExit(1) from None
