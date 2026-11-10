"""football-data.org v4 adapter. No SQL, secrets in logs, or provider fallback."""
from datetime import timedelta
from time import monotonic, sleep

import requests

import incremental as etl
import source_ids as ids

STATUS = {'SCHEDULED': 'TBD', 'TIMED': 'NS', 'IN_PLAY': 'LIVE', 'PAUSED': 'HT',
          'EXTRA_TIME': 'ET', 'PENALTY_SHOOTOUT': 'P', 'SUSPENDED': 'SUSP',
          'POSTPONED': 'PST', 'CANCELLED': 'CANC', 'AWARDED': 'AWD'}


class Client:
    def __init__(self):
        self.next_call = monotonic() + 6.1

    def request(self, endpoint, params):
        import os
        token = os.getenv('FOOTBALL_DATA_API_KEY')
        if not token:
            raise RuntimeError('FOOTBALL_DATA_API_KEY is missing.')
        for attempt in range(3):
            wait = max(0, self.next_call - monotonic())
            if wait > 65:
                raise RuntimeError('Provider wait exceeds the local budget; retry the task later.')
            if wait:
                sleep(wait)
            self.next_call = monotonic() + 6.1  # Conservative free-plan 10/minute pacing.
            try:
                response = requests.get('https://api.football-data.org/v4/' + endpoint,
                                        headers={'X-Auth-Token': token}, params=params,
                                        timeout=30, allow_redirects=False)
                if 300 <= response.status_code < 400:
                    raise RuntimeError('Unexpected provider redirect refused.')
                response.raise_for_status()
                break
            except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as exc:
                response = getattr(exc, 'response', None)
                if isinstance(exc, requests.HTTPError) and (response is None or response.status_code not in {429,500,502,503,504}):
                    raise RuntimeError('football-data.org denied or rejected the request; check entitlement/configuration.') from None
                delay = etl.retry_delay(attempt, response)
                if response is not None and response.status_code == 429 and not response.headers.get('Retry-After'):
                    delay = reset_delay(response.headers)
                if attempt == 2 or delay is None or delay > 65:
                    raise RuntimeError('football-data.org transient failure exhausted the retry budget.') from None
                self.next_call = max(self.next_call, monotonic() + delay)
        try:
            payload = response.json()
        except ValueError:
            raise ValueError('football-data.org returned invalid JSON.') from None
        if not isinstance(payload, dict) or payload.get('errorCode') or payload.get('message'):
            raise ValueError('football-data.org returned an error or invalid response.')
        remaining = response.headers.get('X-RequestsAvailable', response.headers.get('X-Requests-Available-Minute'))
        if remaining is not None:
            try:
                exhausted = int(remaining) <= 0
            except (TypeError,ValueError):
                raise ValueError('Invalid provider rate-limit header.') from None
            if exhausted:
                self.next_call = max(self.next_call, monotonic() + reset_delay(response.headers))
        from raw_storage import archive_response
        archive_response(ids.FD, endpoint, params, payload)
        return payload


def reset_delay(headers):
    try:
        value = int(headers.get('X-RequestCounter-Reset', '60'))
        if value < 0:
            raise ValueError
        return value + 1
    except (TypeError,ValueError):
        raise ValueError('Invalid provider rate-limit reset header.') from None


def season_matches(value, season):
    try:
        start = etl.utc_datetime(value['startDate'])
        if start.year != season:
            raise ValueError('Response belongs to another season.')
    except (KeyError,TypeError):
        raise ValueError('Response season metadata is missing.') from None


def optional_text(value, maximum):
    if value is None:
        return None
    if not isinstance(value,str) or len(value.strip())>maximum:
        raise ValueError('Optional source text does not fit the canonical field.')
    return value.strip() or None


def parse_match(value, season):
    try:
        if value['competition']['code'] != 'PL' or value['competition']['id'] != 2021:
            raise ValueError('Match belongs to another competition.')
        season_matches(value['season'], season)
        source_status = value['status']
        score = value['score']
        if source_status == 'FINISHED':
            short = {'REGULAR':'FT', 'EXTRA_TIME':'AET', 'PENALTY_SHOOTOUT':'PEN'}.get(score['duration'])
        else:
            short = STATUS.get(source_status)
        if not short:
            raise ValueError('Unknown football-data.org status or score duration.')
        source_id = etl.integer(value['id'], 'source fixture ID', 1, maximum=2**63-1)
        home, away = value['homeTeam'], value['awayTeam']
        home_id = etl.integer(home['id'], 'source team ID', 1, maximum=2**31-1)
        away_id = etl.integer(away['id'], 'source team ID', 1, maximum=2**31-1)
        total = score['fullTime']
        record = etl.parse_fixture({
            'fixture': {'id':ids.canonical_id(ids.FD,source_id,'fixture'), 'date':value['utcDate'],
                        'status':{'short':short,'long':source_status,'elapsed':None}},
            'league':{'id':39,'season':season},
            'teams':{'home':{'id':ids.canonical_id(ids.FD,home_id,'team'),'name':home['name']},
                     'away':{'id':ids.canonical_id(ids.FD,away_id,'team'),'name':away['name']}},
            'goals':{'home':total['home'],'away':total['away']}}, season)
        record.update(source_fixture_id=source_id, source_home_team_id=home_id, source_away_team_id=away_id,
                      source_status=source_status, source_last_updated=value.get('lastUpdated'), source_venue=value.get('venue'))
        if record['source_last_updated'] is not None:
            record['source_last_updated'] = etl.utc_datetime(record['source_last_updated']).isoformat()
        return record
    except (KeyError,TypeError,AttributeError):
        raise ValueError('football-data.org match is missing required fields.') from None


def parse_matches(payload, season, expected_ids=None, known_ids=(), full=False):
    if (not isinstance(payload,dict) or not isinstance(payload.get('competition'),dict)
            or not isinstance(payload.get('resultSet'),dict)):
        raise ValueError('Invalid competition response metadata.')
    values = payload.get('matches')
    if not isinstance(values,list) or payload.get('competition',{}).get('code') != 'PL':
        raise ValueError('Invalid competition match response.')
    if type(payload['resultSet'].get('count')) is not int or payload['resultSet']['count'] != len(values):
        raise ValueError('Provider match count does not match response completeness metadata.')
    parsed = [parse_match(value,season) for value in values]
    canonical = [row['fixture_id'] for row in parsed]
    if len(set(canonical)) != len(canonical):
        raise ValueError('Duplicate source fixture IDs.')
    if full and (not parsed or set(known_ids).difference(canonical)):
        raise ValueError('Empty/incomplete season reconciliation omitted known fixtures.')
    if expected_ids is not None and {r['source_fixture_id'] for r in parsed} != set(expected_ids):
        raise ValueError('Pending fixture lookup omitted or added IDs.')
    return parsed


def extract_batch(config, states, pending, now, client):
    plans, records = {}, {}
    for season in config['seasons']:
        state = states[season]
        full = not state or not state['last_full_sync_at'] or now-state['last_full_sync_at'] >= timedelta(days=config['reconcile_days'])
        params = {'season':season}
        if not full:
            start = min(state['last_success_at'],now)-timedelta(days=config['overlap_days'])
            params.update(dateFrom=start.date().isoformat(), dateTo=(now+timedelta(days=14)).date().isoformat())
        payload = client.request('competitions/PL/matches',params)
        parsed = parse_matches(payload,season,known_ids=(state or {}).get('known_fixture_ids',()),full=full)
        if not full:
            unresolved = [ids.original_id(ids.FD,r['fixture_id'],'fixture') for r in pending if r['season']==season]
            seen = {r['source_fixture_id'] for r in parsed}
            for source_id in sorted(set(unresolved)-seen):
                # A single match endpoint is documented for v4; never send API-FOOTBALL IDs.
                entry = client.request('matches/'+str(source_id),{})
                row = parse_match(entry,season)
                if row['source_fixture_id'] != source_id:
                    raise ValueError('Pending fixture lookup returned another identity.')
                parsed.append(row)
        plans[str(season)] = {'full':full,'requests':[params]}
        for row in parsed:
            old = records.get(row['fixture_id'])
            if old and old['season'] != season:
                raise ValueError('Source fixture ID was reused across seasons.')
            records[row['fixture_id']] = row
    return {'version':2,'provider':ids.FD,'run_id':config['run_id'],'league':39,'seasons':config['seasons'],
            'started_at':now.isoformat(),'plans':plans,'matches':sorted(records.values(),key=lambda r:r['fixture_id']),
            'stage':'extract_matches'}


def team_batch(payload, season):
    try:
        if payload['competition']['code'] != 'PL':
            raise ValueError('Team response belongs to another competition.')
        season_matches(payload['season'],season)
        values = payload['teams']
        if not isinstance(values,list) or payload['count'] != len(values) or len(values)!=20:
            raise ValueError('Expected exactly 20 season teams and matching count metadata.')
        teams = []
        for team in values:
            source_id = etl.integer(team['id'],'source team ID',1,maximum=2**31-1)
            name = team['name']
            if not isinstance(name,str) or not name.strip() or len(name.strip())>100:
                raise ValueError('Invalid source team name.')
            teams.append({'api_team_id':ids.canonical_id(ids.FD,source_id,'team'),'source_team_id':source_id,
                          'team_name':name.strip(),'team_code':optional_text(team.get('tla'),20),
                          'country':optional_text((team.get('area') or {}).get('name'),100),
                          'league':'Premier League','stadium':optional_text(team.get('venue'),150),
                          'founded':etl.integer(team.get('founded'),'founding year',nullable=True,maximum=65535),
                          'is_national':0,'logo_url':optional_text(team.get('crest'),500),'venue_id':None})
        if len({t['api_team_id'] for t in teams}) != 20:
            raise ValueError('Duplicate source team IDs.')
        return {'season':season,'teams':teams,'venues':[]}
    except (KeyError,TypeError,AttributeError):
        raise ValueError('football-data.org team response is missing required fields.') from None


def validate_manifest(manifest):
    for batch in manifest.get('team_batches',[]):
        for team in batch['teams']:
            if ids.canonical_id(ids.FD,team['source_team_id'],'team') != team['api_team_id']:
                raise ValueError('Staged team source mapping does not match its namespace.')
    for row in manifest['matches']:
        for raw,canonical,kind in [('source_fixture_id','fixture_id','fixture'),
                                   ('source_home_team_id','home_api_team_id','team'),
                                   ('source_away_team_id','away_api_team_id','team')]:
            if ids.canonical_id(ids.FD,row[raw],kind) != row[canonical]:
                raise ValueError('Staged source ID mapping does not match its canonical namespace.')
