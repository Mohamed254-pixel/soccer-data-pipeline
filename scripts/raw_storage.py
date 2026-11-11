"""Optional immutable S3 copies of provider responses; local POSIX staging stays authoritative."""
import base64
import hashlib
import json
import os
import re


def _client():
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise RuntimeError('S3 archival requires requirements-aws.txt.') from None
    return boto3.client('s3', config=Config(connect_timeout=10, read_timeout=30,
                                          retries={'mode': 'standard', 'total_max_attempts': 3}))


def archive_response(provider, endpoint, params, payload):
    """Fail closed when enabled. Headers/tokens are never accepted or serialized."""
    bucket = os.getenv('PIPELINE_RAW_S3_BUCKET')
    if not bucket:
        return None
    if provider not in {'api_football', 'football_data'}:
        raise ValueError('Unknown archive provider.')
    allowed = (r'(competitions/PL/(matches|teams)|matches/[1-9][0-9]*)' if provider == 'football_data'
               else r'(fixtures|teams)')
    if not isinstance(endpoint, str) or not re.fullmatch(allowed, endpoint):
        raise ValueError('Unapproved archive endpoint.')
    if not isinstance(params, dict) or set(params) - {'league', 'season', 'timezone', 'from', 'to', 'ids', 'dateFrom', 'dateTo'}:
        raise ValueError('Unapproved archive request parameters.')
    run_id = os.getenv('PIPELINE_RUN_ID')
    if not run_id or len(run_id) > 250:
        raise ValueError('A valid PIPELINE_RUN_ID is required for S3 archival.')
    prefix = os.getenv('PIPELINE_RAW_S3_PREFIX', 'raw').strip('/')
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9/_-]{0,199}', prefix) or '..' in prefix:
        raise ValueError('Invalid S3 archive prefix.')
    owner = os.getenv('PIPELINE_S3_EXPECTED_OWNER', '')
    if not re.fullmatch(r'[0-9]{12}', owner):
        raise ValueError('PIPELINE_S3_EXPECTED_OWNER must be the 12-digit bucket account.')
    body = json.dumps({'provider': provider, 'endpoint': endpoint, 'params': params,
                       'response': payload}, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    for name in ('API_KEY', 'FOOTBALL_DATA_API_KEY', 'DB_PASSWORD'):
        secret = os.getenv(name)
        if secret and len(secret) >= 8 and secret.encode() in body:
            raise ValueError('Credential-like value refused in archive content.')
    digest = hashlib.sha256(body).digest()
    key = f'{prefix}/{provider}/{hashlib.sha256(run_id.encode()).hexdigest()}/{digest.hex()}.json'
    try:
        client = _client()
        client.put_object(Bucket=bucket, Key=key, Body=body, ContentType='application/json',
                          ServerSideEncryption='AES256', ChecksumSHA256=base64.b64encode(digest).decode(),
                          IfNoneMatch='*', ExpectedBucketOwner=owner)
    except Exception as exc:
        # 412 means this exact content-addressed object already exists. Check its
        # body checksum metadata before accepting a retry as successful.
        code = getattr(exc, 'response', {}).get('Error', {}).get('Code')
        if code in {'PreconditionFailed', '412'}:
            try:
                existing = client.get_object(Bucket=bucket, Key=key, ExpectedBucketOwner=owner)
                stream = existing['Body']
                try:
                    actual = hashlib.sha256(stream.read()).digest()
                finally:
                    stream.close()
                if actual == digest:
                    return key
            except Exception:
                pass
        raise RuntimeError('S3 response archival failed; no successful extraction is claimed.') from None
    return key
