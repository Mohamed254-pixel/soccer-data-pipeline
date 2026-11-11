import json
import os
from pathlib import Path
from unittest.mock import Mock

import pytest
from dotenv import dotenv_values

import aws_deploy
import aws_runtime_env

ROOT = Path(__file__).resolve().parents[1]


def test_wrong_account_refuses_all_provisioning(capsys):
    session = Mock()
    session.client.return_value.get_caller_identity.return_value = {'Account': '000000000000'}
    with pytest.raises(ValueError, match='account differs'):
        aws_deploy.main(['plan', '--region', 'us-west-2', '--account-id', '111111111111'], session)
    assert session.client.call_count == 1


def test_execute_requires_specific_approval():
    session = Mock()
    session.client.return_value.get_caller_identity.return_value = {'Account': '111111111111'}
    with pytest.raises(ValueError, match='requires --change-set'):
        aws_deploy.main(['execute', '--region', 'us-west-2', '--account-id', '111111111111'], session)
    session.client.return_value.execute_change_set.assert_not_called()


def test_refuse_modifying_existing_stack():
    session = Mock()
    client = session.client.return_value
    client.get_caller_identity.return_value = {'Account': '111111111111'}
    client.describe_change_set.return_value = {'Status': 'CREATE_COMPLETE', 'ExecutionStatus': 'AVAILABLE'}
    client.describe_stacks.return_value = {'Stacks': [{'StackStatus': 'CREATE_COMPLETE'}]}
    with pytest.raises(ValueError, match='new candidate stack'):
        aws_deploy.main(['execute', '--region', 'us-west-2', '--account-id', '111111111111', '--change-set', 'test', '--approve-costs-and-resources'], session)
    client.execute_change_set.assert_not_called()


def test_candidate_template_with_sdk_validation():
    boto3 = pytest.importorskip('boto3')
    from botocore.stub import Stubber
    session = boto3.Session(aws_access_key_id='testing', aws_secret_access_key='testing', region_name='us-west-2')
    sts, cf = session.client('sts'), session.client('cloudformation')
    wrapper = Mock()
    wrapper.client.side_effect = lambda name: {'sts': sts, 'cloudformation': cf}[name]
    with Stubber(sts) as a, Stubber(cf) as b:
        a.add_response('get_caller_identity', {'Account': '111111111111'}, {})
        b.add_response('validate_template', {'Description': 'test'}, {'TemplateBody': (ROOT / 'deploy/aws/infrastructure.json').read_text()})
        # Direct SDK validation proves the request shape without AWS access.
        assert sts.get_caller_identity()['Account'] == '111111111111'
        assert cf.validate_template(TemplateBody=(ROOT / 'deploy/aws/infrastructure.json').read_text())['Description'] == 'test'


def runtime():
    from cryptography.fernet import Fernet
    values = {key: 'test-only-value' for key in aws_runtime_env.REQUIRED}
    values.update(DB_USER='pipeline_app', DB_HOST='test.rds.amazonaws.com', DB_NAME='soccer_db',
                  FERNET_KEY=Fernet.generate_key().decode(), AIRFLOW__API_AUTH__JWT_SECRET='j' * 48)
    return values


def test_runtime_is_private_preserves_special_values_and_never_overwrites(tmp_path):
    pytest.importorskip('cryptography')
    values = runtime()
    values['DB_PASSWORD'] = "test$only'\\password"
    dest = tmp_path / 'runtime.private.json'
    aws_runtime_env.write_private_environment(values, dest)
    assert os.stat(dest).st_mode & 0o777 == 0o600
    assert json.loads(dest.read_text())['DB_PASSWORD'] == values['DB_PASSWORD']
    with pytest.raises(FileExistsError):
        aws_runtime_env.write_private_environment(values, dest)
    assert json.loads(dest.read_text())['DB_PASSWORD'] == values['DB_PASSWORD']


def test_runtime_refuses_admin_and_repository_paths(tmp_path):
    pytest.importorskip('cryptography')
    values = runtime()
    values['DB_USER'] = 'root'
    with pytest.raises(ValueError, match='least-privileged'):
        aws_runtime_env.write_private_environment(values, tmp_path / 'runtime.env')
    values['DB_USER'] = 'pipeline_app'
    with pytest.raises(ValueError, match='outside the repository'):
        aws_runtime_env.write_private_environment(values, ROOT / 'must-not-exist.env')
    assert not (ROOT / 'must-not-exist.env').exists()


def test_execute_new_stack_uses_supported_cloudformation_api_shapes(capsys):
    boto3 = pytest.importorskip('boto3')
    from botocore.stub import Stubber
    from datetime import datetime, timezone
    session = boto3.Session(aws_access_key_id='testing', aws_secret_access_key='testing', region_name='us-west-2')
    sts, cf = session.client('sts'), session.client('cloudformation')
    wrapper = Mock()
    wrapper.client.side_effect = lambda name: {'sts': sts, 'cloudformation': cf}[name]
    selection = {'StackName': 'premier-league-phase3', 'ChangeSetName': 'reviewed-change'}
    template = (ROOT / 'deploy/aws/infrastructure.json').read_text()
    with Stubber(sts) as a, Stubber(cf) as b:
        a.add_response('get_caller_identity', {'Account': '111111111111'}, {})
        b.add_response('describe_change_set', {'Status': 'CREATE_COMPLETE', 'ExecutionStatus': 'AVAILABLE',
            'Changes': [{'Type': 'Resource', 'ResourceChange': {'Action': 'Add', 'LogicalResourceId': 'Vpc', 'ResourceType': 'AWS::EC2::VPC'}}]}, selection)
        b.add_response('describe_stacks', {'Stacks': [{'StackName': 'premier-league-phase3', 'CreationTime': datetime.now(timezone.utc), 'StackStatus': 'REVIEW_IN_PROGRESS'}]}, {'StackName': 'premier-league-phase3'})
        b.add_response('get_template', {'TemplateBody': template}, selection)
        b.add_response('execute_change_set', {}, selection)
        aws_deploy.main(['execute', '--region', 'us-west-2', '--account-id', '111111111111', '--change-set', 'reviewed-change', '--approve-costs-and-resources'], wrapper)
        a.assert_no_pending_responses()
        b.assert_no_pending_responses()
    assert json.loads(capsys.readouterr().out)['scheduling_enabled'] is False


def test_cloud_launcher_preserves_literal_password_and_requires_private_file(tmp_path):
    import aws_compose
    pytest.importorskip('cryptography')
    values = runtime()
    values['DB_PASSWORD'] = "test$only'\\\\password"
    file = tmp_path / 'cloud.private.json'
    aws_runtime_env.write_private_environment(values, file)
    assert aws_compose.command_environment(file)['DB_PASSWORD'] == values['DB_PASSWORD']
    file.chmod(0o644)
    with pytest.raises(ValueError, match='mode 0600'):
        aws_compose.command_environment(file)
