"""Explicit AWS change-set workflow. Never migrates data, starts Airflow or changes scheduling."""
import argparse
import json
import shlex
from pathlib import Path
import sys
import uuid


def main(argv=None, session=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['identity', 'plan', 'execute'])
    p.add_argument('--profile')
    p.add_argument('--region', required=True)
    p.add_argument('--account-id', required=True)
    p.add_argument('--stack', default='premier-league-phase3')
    p.add_argument('--mysql-version')
    p.add_argument('--change-set')
    p.add_argument('--approve-costs-and-resources', action='store_true')
    args = p.parse_args(argv)
    if session is None:
        import boto3
        session = boto3.Session(profile_name=args.profile, region_name=args.region)
    identity = session.client('sts').get_caller_identity()
    if identity['Account'] != args.account_id:
        raise ValueError('AWS account differs from the explicitly selected deployment account.')
    if args.action == 'identity':
        print(json.dumps({'account': identity['Account'], 'region': args.region, 'resources_created': False}))
        return
    cf = session.client('cloudformation')
    if args.action == 'plan':
        if not args.mysql_version:
            raise ValueError('--mysql-version must select a supported MySQL 8.4 patch.')
        import re
        if not re.fullmatch(r'8\.4\.[0-9]+', args.mysql_version):
            raise ValueError('Only reviewed MySQL 8.4 patch releases are accepted.')
        versions = session.client('rds').describe_db_engine_versions(Engine='mysql', EngineVersion=args.mysql_version)['DBEngineVersions']
        if not versions or any(v['DBParameterGroupFamily'] != 'mysql8.4' for v in versions):
            raise ValueError('Selected MySQL patch is not supported in this region.')
        template = (Path(__file__).resolve().parents[1] / 'deploy/aws/infrastructure.json').read_text()
        cf.validate_template(TemplateBody=template)
        name = 'phase3-review-' + uuid.uuid4().hex[:12]
        result = cf.create_change_set(StackName=args.stack, ChangeSetName=name, ChangeSetType='CREATE',
                                      TemplateBody=template, Capabilities=['CAPABILITY_IAM'],
                                      Parameters=[{'ParameterKey': 'MySQLEngineVersion', 'ParameterValue': args.mysql_version}],
                                      Description='Review paid Phase 3 resources; execution is a separate approval gate')
        review = ['aws', 'cloudformation', 'describe-change-set', '--region', args.region,
                  '--change-set-name', name, '--stack-name', args.stack]
        if args.profile:
            review += ['--profile', args.profile]
        print(json.dumps({'change_set': result['Id'], 'stack': args.stack, 'executed': False,
                          'review_command': shlex.join(review)}))
        return
    if not args.approve_costs_and_resources or not args.change_set:
        raise ValueError('Execution requires --change-set and --approve-costs-and-resources after reviewing cost and resource changes.')
    plan = cf.describe_change_set(StackName=args.stack, ChangeSetName=args.change_set)
    if plan['Status'] != 'CREATE_COMPLETE' or plan['ExecutionStatus'] != 'AVAILABLE':
        raise ValueError('Change set is not available for execution.')
    stack = cf.describe_stacks(StackName=args.stack)['Stacks'][0]
    if stack['StackStatus'] != 'REVIEW_IN_PROGRESS':
        raise ValueError('Only a new candidate stack is supported; existing infrastructure updates require a separate review.')
    template = json.loads((Path(__file__).resolve().parents[1] / 'deploy/aws/infrastructure.json').read_text())
    actual = cf.get_template(StackName=args.stack, ChangeSetName=args.change_set)['TemplateBody']
    actual = json.loads(actual) if isinstance(actual, str) else actual
    if actual != template or plan.get('NextToken'):
        raise ValueError('Changed or incomplete infrastructure plan; execution refused.')
    changes = plan.get('Changes', [])
    if not changes or any(x.get('ResourceChange', {}).get('Action') != 'Add' for x in changes):
        raise ValueError('Unexpected replacement, removal or modification in change set; execution refused.')
    cf.execute_change_set(StackName=args.stack, ChangeSetName=args.change_set)
    print(json.dumps({'creation_requested': True, 'stack': args.stack, 'airflow_started': False,
                      'database_imported': False, 'scheduling_enabled': False}))


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'AWS operation stopped ({type(exc).__name__}); inspect account/access/configuration privately.', file=sys.stderr)
        raise SystemExit(1) from None
