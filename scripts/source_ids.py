"""Provider namespaces and transactional source identity registry (migration 004)."""

API = "api_football"
FD = "football_data"
OFFSETS = {"team": 2**31, "fixture": 2**63}


def canonical_id(provider, source_id, kind):
    if provider not in {API, FD} or kind not in OFFSETS:
        raise ValueError("Unknown source namespace.")
    offset = OFFSETS[kind]
    if type(source_id) is not int or not 0 < source_id < offset:
        raise ValueError("Source ID is outside its namespace range.")
    return source_id + (offset if provider == FD else 0)


def original_id(provider, value, kind):
    source = value - (OFFSETS[kind] if provider == FD else 0)
    if canonical_id(provider, source, kind) != value:
        raise ValueError("Canonical ID does not match its provider namespace.")
    return source


def available(cursor, provider=API):
    if provider not in {API, FD}:
        raise ValueError("Unknown source provider.")
    cursor.execute("SELECT COUNT(*) AS total FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='source_registry_state'")
    if not cursor.fetchone()["total"]:
        if provider == FD:
            raise RuntimeError("football-data.org requires reviewed migration 004 after 003.")
        return False
    cursor.execute("SELECT ready FROM source_registry_state WHERE control_id=1")
    row = cursor.fetchone()
    if not row or not row["ready"]:
        raise RuntimeError("Source migration is incomplete. Inspect/resume migration 004.")
    return True


def bind_seasons(cursor, seasons, provider, claim=False):
    registered = available(cursor, provider)
    if not registered:
        return False
    for season in seasons:
        if season == 2024 and provider != API:
            raise ValueError("Historical season is protected.")
        cursor.execute("SELECT provider FROM season_sources WHERE season=%s FOR UPDATE", (season,))
        row = cursor.fetchone()
        if row and row["provider"] != provider:
            raise ValueError("Season belongs to another provider. Explicit reconciliation is required to switch.")
        if not row:
            if not claim:
                raise ValueError("Season source was not registered by extraction.")
            cursor.execute("INSERT INTO season_sources (season,provider) VALUES (%s,%s)", (season, provider))
    return True


def remember(cursor, provider, value, kind, season=None):
    source = original_id(provider, value, kind)
    if kind == "team":
        cursor.execute("INSERT INTO team_source_ids (provider,source_id,canonical_id) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE source_id=team_source_ids.source_id", (provider, source, value))
    else:
        cursor.execute("INSERT INTO fixture_source_ids (provider,source_id,canonical_id,season) VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE source_id=fixture_source_ids.source_id", (provider, source, value, season))
