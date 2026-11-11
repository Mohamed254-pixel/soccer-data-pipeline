import hashlib
import io
import json
from unittest.mock import Mock

import pytest
import raw_storage


@pytest.fixture
def cloud(monkeypatch):
    monkeypatch.setenv('PIPELINE_RAW_S3_BUCKET', 'test-only-archive')
    monkeypatch.setenv('PIPELINE_S3_EXPECTED_OWNER', '123456789012')
    monkeypatch.setenv('PIPELINE_RUN_ID', 'test-run')
    client = Mock()
    monkeypatch.setattr(raw_storage, '_client', lambda: client)
    return client


def test_disabled_archive_never_constructs_aws_client(monkeypatch):
    client = Mock(side_effect=AssertionError('Unexpected AWS request'))
    monkeypatch.setattr(raw_storage, '_client', client)
    assert raw_storage.archive_response('football_data', 'invalid', {}, {}) is None
    client.assert_not_called()


def test_immutable_content_address_and_response_only(cloud):
    first = raw_storage.archive_response('football_data', 'competitions/PL/matches', {'season': 2026}, {'matches': []})
    assert raw_storage.archive_response('football_data', 'competitions/PL/matches', {'season': 2026}, {'matches': []}) == first
    request = cloud.put_object.call_args.kwargs
    assert request['IfNoneMatch'] == '*' and request['ExpectedBucketOwner'] == '123456789012'
    assert request['ServerSideEncryption'] == 'AES256'
    assert hashlib.sha256(request['Body']).hexdigest() in first
    assert 'test-run' not in first and json.loads(request['Body'])['response'] == {'matches': []}
    changed = raw_storage.archive_response('football_data', 'competitions/PL/matches', {'season': 2026}, {'matches': [{'id': 1}]})
    assert first != changed


def test_duplicate_upload_verifies_existing_content(cloud):
    class Exists(Exception):
        response = {'Error': {'Code': 'PreconditionFailed'}}
    raw_storage.archive_response('api_football', 'teams', {'season': 2026}, {'response': []})
    body = cloud.put_object.call_args.kwargs['Body']
    cloud.put_object.side_effect = Exists()
    cloud.get_object.return_value = {'Body': io.BytesIO(body)}
    assert raw_storage.archive_response('api_football', 'teams', {'season': 2026}, {'response': []})
    cloud.get_object.return_value = {'Body': io.BytesIO(b'corrupt')}
    with pytest.raises(RuntimeError, match='archival failed'):
        raw_storage.archive_response('api_football', 'teams', {'season': 2026}, {'response': []})


def test_archive_failure_is_sanitized_and_propagated(cloud):
    cloud.put_object.side_effect = RuntimeError('private-provider-value')
    with pytest.raises(RuntimeError, match='archival failed') as err:
        raw_storage.archive_response('football_data', 'matches/1', {}, {})
    assert 'private-provider-value' not in str(err.value)


@pytest.mark.parametrize('endpoint,params', [('https://example.com', {}), ('competitions/OTHER/matches', {}), ('matches/1', {'token': 'secret'})])
def test_reject_unapproved_metadata(cloud, endpoint, params):
    with pytest.raises(ValueError):
        raw_storage.archive_response('football_data', endpoint, params, {})
    cloud.put_object.assert_not_called()


def test_no_credential_echo_saved(cloud, monkeypatch):
    monkeypatch.setenv('FOOTBALL_DATA_API_KEY', 'test-only-private-value')
    with pytest.raises(ValueError, match='Credential-like'):
        raw_storage.archive_response('football_data', 'matches/1', {}, {'message': 'test-only-private-value'})
    cloud.put_object.assert_not_called()


def test_owner_required_before_upload(cloud, monkeypatch):
    monkeypatch.delenv('PIPELINE_S3_EXPECTED_OWNER')
    with pytest.raises(ValueError, match='12-digit'):
        raw_storage.archive_response('football_data', 'matches/1', {}, {})
    cloud.put_object.assert_not_called()


def test_real_sdk_accepts_checksum_and_conditional_request(monkeypatch):
    boto3 = pytest.importorskip('boto3')
    from botocore.stub import Stubber, ANY
    client = boto3.client('s3', region_name='us-west-2', aws_access_key_id='testing', aws_secret_access_key='testing')
    monkeypatch.setattr(raw_storage, '_client', lambda: client)
    monkeypatch.setenv('PIPELINE_RAW_S3_BUCKET', 'test-only-archive')
    monkeypatch.setenv('PIPELINE_S3_EXPECTED_OWNER', '123456789012')
    monkeypatch.setenv('PIPELINE_RUN_ID', 'test-run')
    with Stubber(client) as stub:
        stub.add_response('put_object', {}, {'Bucket': 'test-only-archive', 'Key': ANY, 'Body': ANY,
            'ContentType': 'application/json', 'ServerSideEncryption': 'AES256', 'ChecksumSHA256': ANY,
            'IfNoneMatch': '*', 'ExpectedBucketOwner': '123456789012'})
        assert raw_storage.archive_response('football_data', 'matches/1', {}, {'id': 1})
        stub.assert_no_pending_responses()


@pytest.mark.parametrize('provider', ['football_data', 'api_football'])
def test_api_response_archive_failure_is_not_silently_ignored(monkeypatch, provider):
    import football_data
    import incremental
    payload = {'matches': []} if provider == 'football_data' else {'response': []}
    response = Mock(status_code=200, headers={})
    response.json.return_value = payload
    monkeypatch.setenv('FOOTBALL_DATA_API_KEY', 'test-only-key')
    monkeypatch.setenv('API_KEY', 'test-only-key')
    monkeypatch.setattr(incremental.requests, 'get', Mock(return_value=response))
    monkeypatch.setattr(football_data, 'sleep', lambda _: None)
    archive = Mock(side_effect=RuntimeError('S3 archival failed'))
    monkeypatch.setattr(raw_storage, 'archive_response', archive)
    with pytest.raises(RuntimeError, match='S3 archival failed'):
        if provider == 'football_data':
            football_data.Client().request('competitions/PL/matches', {'season': 2026})
        else:
            incremental.request_payload('fixtures', {'season': 2026})
    archive.assert_called_once_with(provider, 'competitions/PL/matches' if provider == 'football_data' else 'fixtures', {'season': 2026}, payload)
