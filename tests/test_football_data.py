from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest
import requests

import football_data as fd
import incremental as etl
import source_ids as ids

NOW = datetime(2026,11,2,6)


@pytest.fixture
def match():
    return {'id':1208021,'competition':{'id':2021,'code':'PL'},
            'season':{'startDate':'2026-08-21','endDate':'2027-05-30'},
            'utcDate':'2026-08-21T19:00:00Z','status':'FINISHED',
            'homeTeam':{'id':33,'name':'Manchester United'},'awayTeam':{'id':34,'name':'Newcastle'},
            'score':{'duration':'REGULAR','fullTime':{'home':2,'away':1}},
            'lastUpdated':'2026-08-21T21:05:00Z'}


def matches_payload(matches):
    return {'competition':{'code':'PL','id':2021},'resultSet':{'count':len(matches)},'matches':matches}


def teams_payload(season=2026):
    return {'competition':{'code':'PL','id':2021},'season':{'startDate':f'{season}-08-21'},'count':20,
            'teams':[{'id':i,'name':f'Club {i}','tla':f'T{i}', 'venue':f'Ground {i}'} for i in range(33,53)]}


def test_namespaced_ids_are_lossless_and_do_not_collide(match):
    row = fd.parse_match(match,2026)
    assert row['source_fixture_id']==match['id']
    assert row['fixture_id']==2**63+match['id']
    assert row['home_api_team_id']==2**31+33
    assert etl.match_rows([row],NOW)[0][0]==row['fixture_id']
    assert ids.original_id(ids.FD,row['fixture_id'],'fixture')==match['id']
    assert ids.canonical_id(ids.API,match['id'],'fixture')!=row['fixture_id']


@pytest.mark.parametrize('kind,raw',[('fixture',0),('fixture',2**63),('team',2**31),('team',True),('team',1.0)])
def test_invalid_or_overlapping_source_ranges(kind,raw):
    with pytest.raises(ValueError): ids.canonical_id(ids.FD,raw,kind)


@pytest.mark.parametrize('status,expected',[('SCHEDULED','TBD'),('TIMED','NS'),('IN_PLAY','LIVE'),('PAUSED','HT'),
    ('EXTRA_TIME','ET'),('PENALTY_SHOOTOUT','P'),('SUSPENDED','SUSP'),('POSTPONED','PST'),('CANCELLED','CANC'),('AWARDED','AWD')])
def test_incomplete_fixture_statuses(match,status,expected):
    match['status']=status
    match['score']['fullTime']={'home':None,'away':None}
    if status in {'SCHEDULED','POSTPONED'}:match['utcDate']=None
    row=fd.parse_match(match,2026)
    assert row['status_short']==expected and row['home_goals'] is None


@pytest.mark.parametrize('field',['id','season','homeTeam','utcDate','score','status'])
def test_missing_required_fields_fail(match,field):
    del match[field]
    with pytest.raises(ValueError): fd.parse_match(match,2026)


@pytest.mark.parametrize('change',['score','season','competition','status','team','date'])
def test_invalid_match_data_fails(match,change):
    if change=='score':match['score']['fullTime']['home']=-1
    if change=='season':match['season']['startDate']='2025-08-01'
    if change=='competition':match['competition']['code']='CL'
    if change=='status':match['status']='NEW_UNKNOWN'
    if change=='team':match['homeTeam']['id']=None
    if change=='date':match['utcDate']='invalid'
    with pytest.raises(ValueError):fd.parse_match(match,2026)


def test_completed_match_requires_both_scores(match):
    match['score']['fullTime']['away']=None
    with pytest.raises(ValueError):fd.parse_match(match,2026)


def test_reconciliation_checks_known_ids_counts_and_duplicates(match):
    row=fd.parse_match(match,2026)
    assert fd.parse_matches(matches_payload([match]),2026,known_ids=[row['fixture_id']],full=True)
    with pytest.raises(ValueError,match='omitted'):fd.parse_matches(matches_payload([match]),2026,known_ids=[2**63+999],full=True)
    with pytest.raises(ValueError,match='Duplicate'):fd.parse_matches(matches_payload([match,match]),2026)
    payload=matches_payload([match]);payload['resultSet']['count']=2
    with pytest.raises(ValueError,match='count'):fd.parse_matches(payload,2026)
    with pytest.raises(ValueError):fd.parse_matches(matches_payload([]),2026,full=True)
    assert fd.parse_matches(matches_payload([]),2026)==[]


def test_team_venue_text_has_no_invented_resource_ids():
    batch=fd.team_batch(teams_payload(),2026)
    assert len(batch['teams'])==20 and batch['venues']==[]
    assert batch['teams'][0]['venue_id'] is None
    assert batch['teams'][0]['stadium']=='Ground 33'
    bad=teams_payload();bad['teams'][-1]=bad['teams'][0]
    with pytest.raises(ValueError,match='Duplicate'):fd.team_batch(bad,2026)


def test_incremental_pending_lookup_uses_raw_ids_outside_window(match,tmp_path):
    config={'seasons':[2026],'league':39,'run_id':'fd-run','path':tmp_path/'batch.json','provider':ids.FD,'overlap_days':14,'reconcile_days':28}
    state={2026:{'last_success_at':NOW-timedelta(days=7),'last_full_sync_at':NOW-timedelta(days=7)}}
    client=Mock();client.request.side_effect=[matches_payload([]),match]
    manifest=fd.extract_batch(config,state,[{'season':2026,'fixture_id':2**63+match['id']}],NOW,client)
    assert client.request.call_args.args==('matches/'+str(match['id']),{})
    assert client.request.call_args_list[0].args[1]['dateFrom']=='2026-10-12'
    assert not manifest['plans']['2026']['full']
    etl.save_manifest(config,manifest)
    assert etl.read_manifest(config)['provider']==ids.FD
    config['provider']=ids.API
    with pytest.raises(ValueError,match='provider'):etl.read_manifest(config)


def test_staging_rejects_changed_source_identity(match,tmp_path):
    config={'run_id':'fd','league':39,'seasons':[2026],'provider':ids.FD,'path':tmp_path/'batch.json'}
    row=fd.parse_match(match,2026);row['source_fixture_id']+=1
    etl.save_manifest(config,{'version':2,**{k:v for k,v in config.items() if k!='path'},'matches':[row]})
    with pytest.raises(ValueError,match='mapping'):etl.read_manifest(config)


def response(status=200,headers=None,payload=None):
    value=Mock(status_code=status,headers=headers or {})
    value.json.return_value=payload if payload is not None else {'ok':True}
    if status>=400:value.raise_for_status.side_effect=requests.HTTPError(response=value)
    return value


@pytest.fixture
def http(monkeypatch):
    monkeypatch.setenv('FOOTBALL_DATA_API_KEY','test-only-token')
    monkeypatch.setattr(fd,'monotonic',lambda:100)
    wait=Mock();monkeypatch.setattr(fd,'sleep',wait)
    get=Mock();monkeypatch.setattr(fd.requests,'get',get)
    return get,wait


def test_authentication_and_successful_quota_headers(http):
    get,wait=http
    get.return_value=response(headers={'X-RequestsAvailable':'0','X-RequestCounter-Reset':'20'})
    client=fd.Client();client.request('competitions/PL/matches',{'season':2026})
    assert get.call_args.kwargs['headers']=={'X-Auth-Token':'test-only-token'}
    assert get.call_args.kwargs['allow_redirects'] is False
    assert client.next_call==121
    assert wait.call_args.args[0]==pytest.approx(6.1)


@pytest.mark.parametrize('headers,delay',[({'Retry-After':'12'},12),({'X-RequestCounter-Reset':'20'},21)])
def test_rate_limit_retry_respects_wait(http,headers,delay):
    get,wait=http;get.side_effect=[response(429,headers),response()]
    fd.Client().request('competitions/PL/matches',{'season':2026})
    assert get.call_count==2 and wait.call_args.args[0]==delay


@pytest.mark.parametrize('failure',[requests.Timeout(),response(503)])
def test_transient_failures_retry(http,failure):
    get,_=http;get.side_effect=[failure,response()]
    assert fd.Client().request('competitions/PL/matches',{})=={'ok':True}
    assert get.call_count==2


@pytest.mark.parametrize('status,headers',[(401,{}),(403,{}),(302,{}),(429,{'Retry-After':'120'})])
def test_permanent_errors_redirects_and_long_waits_fail_without_retry(http,status,headers):
    get,_=http;get.return_value=response(status,headers)
    with pytest.raises(RuntimeError):fd.Client().request('competitions/PL/matches',{})
    assert get.call_count==1


def test_missing_token_and_payload_errors_are_safe(http,monkeypatch):
    get,_=http
    monkeypatch.delenv('FOOTBALL_DATA_API_KEY')
    with pytest.raises(RuntimeError,match='missing'):fd.Client().request('x',{})
    get.assert_not_called()
    monkeypatch.setenv('FOOTBALL_DATA_API_KEY','test-only-token')
    get.return_value=response(payload={'errorCode':403,'message':'private-provider-text'})
    with pytest.raises(ValueError) as exc:fd.Client().request('x',{})
    assert 'private-provider-text' not in str(exc.value)


def test_source_setting_is_explicit_and_validated(monkeypatch):
    monkeypatch.setenv('PIPELINE_RUN_ID','fd-test')
    monkeypatch.setenv('FOOTBALL_SOURCE',ids.FD)
    assert etl.settings()['provider']==ids.FD
    monkeypatch.setenv('FOOTBALL_SOURCE','unknown')
    with pytest.raises(ValueError):etl.settings()


def test_periodic_reconciliation_catches_old_corrections(match,tmp_path):
    config={'seasons':[2026],'league':39,'run_id':'late','provider':ids.FD,'overlap_days':14,'reconcile_days':28}
    state={2026:{'last_success_at':NOW-timedelta(days=7),'last_full_sync_at':NOW-timedelta(days=29),
                 'known_fixture_ids':[2**63+match['id']]}}
    match['score']['fullTime']['home']=3
    client=Mock();client.request.return_value=matches_payload([match])
    manifest=fd.extract_batch(config,state,[],NOW,client)
    assert client.request.call_args.args[1]=={'season':2026}
    assert manifest['plans']['2026']['full'] and manifest['matches'][0]['home_goals']==3


def test_same_source_fixture_cannot_be_reassigned_across_seasons(match):
    other=deepcopy(match);other['season']['startDate']='2025-08-01'
    client=Mock();client.request.side_effect=[matches_payload([other]),matches_payload([match])]
    config={'seasons':[2025,2026],'league':39,'run_id':'cross','overlap_days':14,'reconcile_days':28}
    with pytest.raises(ValueError,match='reused across seasons'):
        fd.extract_batch(config,{2025:None,2026:None},[],NOW,client)


def test_transport_retry_budget_is_bounded(http):
    get,_=http;get.side_effect=requests.Timeout()
    with pytest.raises(RuntimeError,match='exhausted'):fd.Client().request('competitions/PL/matches',{})
    assert get.call_count==3


@pytest.mark.parametrize('payload',[None,[],{}, {'competition':None,'resultSet':{}}])
def test_malformed_list_metadata_fails_safely(payload):
    with pytest.raises(ValueError):fd.parse_matches(payload,2026)


def test_fd_readiness_uses_no_database_writes(monkeypatch,match):
    import check_readiness
    request=Mock(side_effect=[matches_payload([match]),teams_payload()])
    monkeypatch.setattr(fd.Client,'request',request)
    monkeypatch.setattr(etl.store,'extraction_state',Mock(side_effect=AssertionError('Must not claim a run')))
    assert check_readiness.check_football_data([2026])=={'provider':ids.FD,'verified_seasons':[2026]}
    assert request.call_args_list[0].args[1]=={'season':2026,'matchday':1}
    assert not check_readiness.source_configuration_ready({'source_registry_ready':False},ids.FD,[2026])
    assert not check_readiness.source_configuration_ready({'source_registry_ready':True,'season_sources':{'2026':ids.API}},ids.FD,[2026])
    assert check_readiness.source_configuration_ready({'source_registry_ready':True,'season_sources':{'2026':ids.FD}},ids.FD,[2026])


@pytest.mark.parametrize('field,value',[('venue','x'*151),('tla','x'*21),('crest',{}),('founded',-1)])
def test_team_metadata_cannot_be_silently_truncated_or_coerced(field,value):
    payload=teams_payload();payload['teams'][0][field]=value
    with pytest.raises(ValueError):fd.team_batch(payload,2026)
