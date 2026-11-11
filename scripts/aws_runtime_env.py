"""Write existing runtime environment values as private JSON; never print secrets."""
import argparse
import os
from pathlib import Path
import json
import sys

REQUIRED = {'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME', 'FOOTBALL_DATA_API_KEY',
            'FERNET_KEY', 'AIRFLOW__API_AUTH__JWT_SECRET', 'AIRFLOW_METADATA_URI',
            'AIRFLOW_RESULT_URI', 'AIRFLOW_BROKER_URI', 'AIRFLOW_POSTGRES_PASSWORD',
            'AIRFLOW_REDIS_PASSWORD', 'PIPELINE_RAW_S3_BUCKET', 'PIPELINE_S3_EXPECTED_OWNER',
            'PIPELINE_IMAGE', 'AWS_REGION', 'PIPELINE_LOG_GROUP', 'LOG_STREAM_PREFIX'}
OPTIONAL = {'FOOTBALL_SOURCE', 'FOOTBALL_SEASONS', 'DB_PORT', 'PIPELINE_RAW_S3_PREFIX'}


def write_private_environment(values, destination):
    if not isinstance(values, dict) or REQUIRED - set(values) or set(values) - REQUIRED - OPTIONAL:
        raise ValueError('Runtime secret has missing or unapproved keys.')
    if any(not isinstance(x, str) or not x or any(c in x for c in '\r\n\x00') for x in values.values()):
        raise ValueError('Runtime values must be nonempty single-line strings.')
    if values['DB_USER'].lower() in {'root', 'admin', 'pipeline_admin'} or values['DB_NAME'] != 'soccer_db':
        raise ValueError('Use the approved least-privileged soccer_db account.')
    if not values['DB_HOST'].endswith('.rds.amazonaws.com'):
        raise ValueError('Candidate runtime must target the approved RDS endpoint.')
    if values.get('FOOTBALL_SOURCE', 'football_data') != 'football_data' or values.get('FOOTBALL_SEASONS', '2026') != '2026':
        raise ValueError('Candidate runtime is limited to football_data season 2026.')
    destination = Path(destination).expanduser().resolve()
    repo = Path(__file__).resolve().parents[1]
    if destination.is_relative_to(repo) or not destination.parent.is_dir():
        raise ValueError('Choose an existing private directory outside the repository.')
    from cryptography.fernet import Fernet
    Fernet(values['FERNET_KEY'].encode())
    if values['FERNET_KEY'] == values['AIRFLOW__API_AUTH__JWT_SECRET'] or len(values['AIRFLOW__API_AUTH__JWT_SECRET']) < 32:
        raise ValueError('Independent valid Airflow secrets are required.')
    values = {**values, 'FOOTBALL_SOURCE': 'football_data', 'FOOTBALL_SEASONS': '2026'}
    # JSON avoids the incompatible quoting/interpolation rules of dotenv and Compose.
    content = json.dumps(values, indent=2) + '\n'
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        # Remove only the new partial file created by this invocation.
        destination.unlink(missing_ok=True)
        raise
    return destination


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--secret-id', required=True)
    p.add_argument('--region', required=True)
    p.add_argument('--output', required=True)
    args = p.parse_args()
    import boto3
    raw = boto3.client('secretsmanager', region_name=args.region).get_secret_value(SecretId=args.secret_id)
    write_private_environment(json.loads(raw['SecretString']), args.output)
    print('Private runtime file created; no services started. Existing files are never overwritten.')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Private runtime preparation stopped ({type(exc).__name__}); secret details withheld.', file=sys.stderr)
        raise SystemExit(1) from None
