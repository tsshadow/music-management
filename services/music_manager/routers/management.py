import json
import logging
import os
from typing import Any

import markdown
from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, field_validator

import docker
from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.FilterTableHelper import resolve_redirect_chains
from services.common.Helpers.GenreNameAnalyzer import KINDS as PROPOSAL_KINDS
from services.common.Helpers.GenreRulesHelper import BLACK, VALID_STATES, WHITE
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.PodcastHelper import normalize as normalize_show_name
from services.common.Helpers.ProcessedFilesHelper import ProcessedFilesHelper
from services.common.Helpers.ReleaseFolder import MOVED, move_release_folder
from services.common.Helpers.RescanInvalidator import invalidate_quietly, rescan_invalidator
from services.common.version_helper import get_changelog, get_release_notes, get_version
from services.music_manager import curation_rules
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.deprecation import DEPRECATED_CALL
from services.music_manager.rbac import has_permission, require_admin, require_permission

# Re-exported: news, radio and events import it from here. It is the canonical
# users.verify_api_key -- this module used to carry its own copy, which accepted any
# enabled account for every route below, including the ones that change rules, move
# folders on disk and read container logs. See docs/bug-reports/037-management-routes-open-to-every-user.md.
from services.music_manager.routers.users import verify_api_key

router = APIRouter(tags=['management'])


class ArtistGenreRule(BaseModel):
    artist_name: str
    genre_id: int


class GenreDecisionRequest(BaseModel):
    """A curation decision, optionally rewriting the genre to one or more others.

    `canonical_id` is the single-target form kept for existing callers;
    `canonical_ids` is the general one, needed for contractions like 'Upterror'
    becoming 'Uptempo Hardcore' plus 'Terror'. Whichever is given ends up in
    `rules_genre_expansions`.
    """

    state: str
    canonical_id: int | None = None
    canonical_ids: list[int] | None = None

    def targets(self) -> list[int]:
        """The rewrite targets, de-duplicated, order preserved."""
        raw = (
            self.canonical_ids
            if self.canonical_ids is not None
            else ([self.canonical_id] if self.canonical_id is not None else [])
        )
        return list(dict.fromkeys(target for target in raw if target is not None))


class LabelGenreRule(BaseModel):
    label_name: str
    genre_id: int


class ArtistRedirect(BaseModel):
    """A name the tagger should rewrite, or ignore when there is no correction."""

    name: str
    corrected_name: str | None = None


class PodcastDecisionRequest(BaseModel):
    """A curation decision on a radio show or podcast series.

    `merge_into_podcast_id` folds this row into another show, which is how the
    detected spellings "Isaac's Hardstyle Sessions", "DJ ISAAC - HARDSTYLE
    SESSIONS" and "Q-Dance: Isaac's Hardstyle Sessions" become one show. `host`
    and `station` are descriptive and optional.
    """

    state: str
    merge_into_podcast_id: int | None = None
    host: str | None = None
    station: str | None = None


class PodcastRenameRequest(BaseModel):
    """The show name as it should appear on a file and in the browse list.

    `tools/detect_podcasts.py` files the raw filename fragment it grouped on, so a
    detected row is usually named after the uploader ('KELTEK Presents | Pure
    Hardstyle |') rather than after the show.
    """

    name: str


class PodcastAliasRequest(BaseModel):
    """One spelling a show occurs under in the library."""

    alias: str


# Changes rules the tagger applies to every file, or moves releases on disk.
require_rules_manage = require_permission('rules.manage')
# Operating the installation itself: container logs, downloader sources.
require_admin_role = require_admin()


@router.get('/rules')
def get_genre_rules(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            # Approved genres only: this list feeds the tagger page's artist and
            # label links and the playlist filters, and linking an artist to a
            # genre that is rejected or still in the curation queue is never right.
            cursor.execute("SELECT id, name, corrected_genre FROM rules_genres WHERE state = 'white' ORDER BY name")
            genres = cursor.fetchall()
            cursor.execute("SHOW TABLES LIKE 'rules_ignored_genres'")
            ignored = []
            if cursor.fetchone():
                cursor.execute('SELECT name FROM rules_ignored_genres ORDER BY name')
                ignored = [{'name': r['name']} for r in cursor.fetchall()]
            return {'genres': genres, 'ignored_genres': ignored}
    finally:
        conn.close()


@router.get('/artists')
def search_artists(q: str = '', _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_artists WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/labels')
def search_labels(q: str = '', _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM library_labels WHERE name LIKE %s LIMIT 50', (f'%{q}%',))
            return cursor.fetchall()
    finally:
        conn.close()


class LabelDecisionRequest(BaseModel):
    """The label a curator files a proposal under: one folder name directly under the EPs root."""

    label: str

    @field_validator('label')
    @classmethod
    def one_folder_name(cls, value: str) -> str:
        """Refuse a value that is not a single folder name.

        The label becomes a path segment of the move target and a rule the importer acts on
        later; `../x` or an absolute path would move the release out of the EPs root.
        """
        if not value.strip() or value.strip() in ('.', '..') or any(c in value for c in ('/', '\\', '\x00')):
            raise ValueError('a label is one folder name, without "/" or ".."')
        return value


def folder_exists(path: str) -> bool:
    """Named so a test can replace it without patching os.path.isdir for the whole process."""
    return os.path.isdir(path)


@router.get('/label-proposals')
def get_label_proposals(status: str = 'new', _auth: dict = Depends(verify_api_key)):
    """
    Releases the importer could not place.

    Ordered by proposed label so the caller can group them: one label usually covers
    many releases, and confirming a group is one decision instead of fifteen. The
    proposals nothing could be read from sort last, because they are the ones that
    genuinely need a human to go looking.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, folder, catid, proposed_label, source, confidence, status, '
                'alternative_label, label_choice_key '
                'FROM rules_label_proposals WHERE status = %s '
                'ORDER BY proposed_label IS NULL, proposed_label, confidence DESC',
                (status,),
            )
            # get_db_connection hands out a DictCursor, so these rows are already the
            # objects the caller wants.
            return cursor.fetchall()
    finally:
        conn.close()


@router.get('/import-conflicts')
def get_import_conflicts(_auth: dict = Depends(verify_api_key)):
    """
    What the importer left in place for a human: folder pairs and single files.

    Written by the importer's renamer and mover (services/importer/conflict_store.py,
    bug report 091), which warn about each pair once and then only count it, and by its
    extractor (bug report 119), which files a single file it will not import -- not an
    archive, or an archive no backend can extract -- with `reason` set and `target`
    holding a detail instead of a second folder. Read-only: resolving one means removing,
    renaming or replacing the folder or file by hand, after which the importer forgets it
    on its next cycle. Oldest first, because those are the ones that have waited longest.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT step, source, target, reason, first_seen, last_seen FROM importer_conflicts '
                'ORDER BY first_seen, target'
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/label-proposals/{proposal_id}/confirm')
def confirm_label_proposal(
    proposal_id: int, decision: LabelDecisionRequest = Body(...), _auth: dict = Depends(require_rules_manage)
):
    """
    Accept a proposal.

    With a catalogue number this writes the rule and stops: the importer already
    knows how to move a release whose CAT ID resolves, and it will do so on its next
    cycle, so there is no second move implementation here. Without one there is
    nothing to learn -- no key to hang a rule on -- so this places that single folder.

    A proposal that offered two folders -- the one the release's .nfo label names and the one
    the curator filed such releases in (`label_choice_key` set, #164) -- also records the
    answer in `rules_label_name_choices`, so every later release with that .nfo label is placed
    there without asking again.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    settings = Settings()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, folder, catid, proposed_label, label_choice_key FROM rules_label_proposals WHERE id = %s',
                (proposal_id,),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404)
            folder, catid = row['folder'], row['catid']
            if not catid:
                src = os.path.join(settings.import_folder_path, folder)
                if not folder_exists(src):
                    # Another import cycle moved it, or it was cleaned up by hand. Not an
                    # error: the row is simply out of date, and saying so beats a stack trace.
                    cursor.execute(
                        "UPDATE rules_label_proposals SET status = 'stale', decided_at = NOW() WHERE id = %s",
                        (proposal_id,),
                    )
                    conn.commit()
                    return {'status': 'stale', 'folder': folder}
                dst = os.path.join(settings.eps_folder_path, decision.label, folder)
                # The label is one folder name (LabelDecisionRequest); the folder comes from the
                # importer's own row. Checked once more on the result, so neither can move a
                # release out of the EPs root.
                eps_root = os.path.realpath(settings.eps_folder_path)
                if not os.path.realpath(dst).startswith(eps_root.rstrip(os.sep) + os.sep):
                    raise HTTPException(status_code=400, detail=f'{dst} is not inside the EPs folder')
                # Never a bare shutil.move: it does not fail on an existing destination
                # directory, it moves into it, and the release ends up one level inside the
                # folder it collided with. The proposal stays open when that happens --
                # marking it confirmed while nothing moved would leave the folder sitting in
                # import with nothing left pointing at it.
                outcome = move_release_folder(src, dst)
                if outcome != MOVED:
                    logging.warning('Not moving %s: %s already holds a release (%s)', src, dst, outcome)
                    conn.commit()
                    return {'status': outcome, 'folder': folder, 'destination': dst}
                # Both paths: the new one so LMS reads the files, the old one so the rows
                # underneath a folder that is now gone get removed.
                lms_scan_trigger.notify([src, dst])
            # The rule and the verdict land together (bug report 115). A rule written
            # without the verdict left the proposal open while the importer already
            # acted on the rule -- and a later reject of that proposal left the rule in
            # force. No folder move happens in here: it cannot be rolled back.
            with transaction(conn):
                if catid:
                    cursor.execute(
                        'INSERT INTO rules_catid_label (catid, label) VALUES (%s, %s) '
                        'ON DUPLICATE KEY UPDATE label = VALUES(label)',
                        (catid, decision.label),
                    )
                cursor.execute(
                    "UPDATE rules_label_proposals SET status = 'confirmed', decided_label = %s, decided_at = NOW() "
                    'WHERE id = %s',
                    (decision.label, proposal_id),
                )
                if row.get('label_choice_key'):
                    cursor.execute(
                        'UPDATE rules_label_name_choices SET chosen_folder = %s, decided_at = NOW() '
                        'WHERE nfo_label_key = %s',
                        (decision.label, row['label_choice_key']),
                    )
        return {'status': 'confirmed', 'folder': folder, 'label': decision.label}
    finally:
        conn.close()


@router.post('/label-proposals/{proposal_id}/reject')
def reject_label_proposal(proposal_id: int, _auth: dict = Depends(require_rules_manage)):
    """A rejected proposal never returns to the list, however often the importer meets the folder again."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "UPDATE rules_label_proposals SET status = 'rejected', decided_at = NOW() WHERE id = %s", (proposal_id,)
            )
        conn.commit()
        return {'status': 'rejected'}
    finally:
        conn.close()


@router.get('/config')
def get_config(auth: dict = Depends(verify_api_key)):
    """The version for every account; where the database lives only for `config.manage`.

    Beheer calls this as its sign-in check, so every account still gets an answer.
    """
    version = '1.3.0'
    try:
        with open(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'VERSION'), encoding='utf-8') as f:
            version = f.read().strip()
    except Exception:
        pass
    if not has_permission(auth, 'config.manage'):
        return {'VERSION': version}
    return {
        'DB_HOST': os.getenv('DB_HOST'),
        'DB_NAME': os.getenv('DB_DB'),
        'VERSION': version,
        'PHPMYADMIN_URL': os.getenv('PHPMYADMIN_URL', ''),
    }


@router.get('/about', response_class=HTMLResponse, deprecated=True, dependencies=[DEPRECATED_CALL])
def get_about(_auth: dict = Depends(verify_api_key)):
    readme_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'README.md')
    content = '# Music Manager\nDocumentation not found.'
    if os.path.exists(readme_path):
        with open(readme_path, encoding='utf-8') as f:
            content = f.read()
    html = markdown.markdown(content, extensions=['fenced_code', 'tables'])
    return html


@router.get('/stats')
def get_stats_proxy(_auth: dict = Depends(verify_api_key)):
    from services.music_manager.routers.stats import get_stats

    return get_stats(_auth)


# The containers this installation owns. /system/containers lists only these, and
# /system/logs/{name} serves only these: the Docker socket reaches every container on
# the host, and a log is where a service prints its connection strings.
CONTAINER_NAME_MARKERS = ('muma', 'music-management', 'music-manager', 'db', 'lms')


def is_listed_container(name: str) -> bool:
    """Whether a container name belongs to this installation, by the list endpoint's rule."""
    return any(marker in name for marker in CONTAINER_NAME_MARKERS)


@router.get('/system/containers')
def get_containers(_auth: dict = Depends(require_admin_role)):
    """The installation's containers and their state. Admin only."""
    try:
        # The repo's own docker/ folder shadows the SDK package for mypy.
        client = docker.from_env()  # type: ignore[attr-defined]
        containers = []
        for container in client.containers.list(all=True):
            if is_listed_container(container.name):
                containers.append(
                    {
                        'id': container.short_id,
                        'name': container.name,
                        'status': container.status,
                        'image': container.image.tags[0] if container.image.tags else 'unknown',
                    }
                )
        return sorted(containers, key=lambda x: x['name'])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get('/system/logs/{name}')
def get_logs(name: str, tail: int = 200, _auth: dict = Depends(require_admin_role)):
    """The tail of one listed container's log. Admin only.

    `name` must be a container name the list endpoint would return. Docker also
    resolves ids and id prefixes, so the resolved container's own name is checked
    too, rather than trusting what was asked for.
    """
    if not is_listed_container(name):
        raise HTTPException(status_code=404, detail='Unknown container')
    try:
        # The repo's own docker/ folder shadows the SDK package for mypy.
        client = docker.from_env()  # type: ignore[attr-defined]
        container = client.containers.get(name)
        if container.name != name:
            raise HTTPException(status_code=404, detail='Unknown container')
        logs = container.logs(tail=tail).decode('utf-8')
        return {'logs': logs}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get('/system/activity')
def get_activity(limit: int = 20, _auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                SELECT t.title, a.name as artist, CAST(t.created_at AS CHAR) as timestamp\n                FROM library_tracks t\n                JOIN library_artists a ON t.primary_artist_id = a.id\n                ORDER BY t.created_at DESC\n                LIMIT %s\n            ',
                (limit,),
            )
            recent_added = cursor.fetchall()
            cursor.execute(
                '\n                SELECT t.title, a.name as artist, CAST(ml.updated_at AS CHAR) as timestamp\n                FROM library_track_ml_labels ml\n                JOIN library_tracks t ON ml.track_id = t.track_uid\n                LEFT JOIN library_artists a ON t.primary_artist_id = a.id\n                WHERE ml.ml_genre IS NOT NULL\n                ORDER BY ml.updated_at DESC\n                LIMIT %s\n            ',
                (limit,),
            )
            recent_tagged = cursor.fetchall()
            return {'recent_added': recent_added, 'recent_tagged': recent_tagged}
    finally:
        conn.close()


@router.get('/notes')
def get_notes(_auth: dict = Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}


@router.get('/all-notes')
def get_all_notes(_auth: dict = Depends(verify_api_key)):
    return {'release_notes': get_release_notes(), 'changelog': get_changelog()}


@router.get('/versions')
def get_versions(_auth: dict = Depends(verify_api_key)):
    version = get_version()
    return {
        'music-manager': version,
        'muma-tagger': version,
        'muma-scanner': version,
        'muma-downloader': version,
        'muma-importer': version,
        'ultrasonic': 'unknown',
    }


@router.get('/soundcloud')
def get_soundcloud_accounts(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name, soundcloud_id FROM downloads_soundcloud_accounts')
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/soundcloud')
def add_soundcloud_account(req: dict[str, Any] = Body(...), _auth: dict = Depends(require_admin_role)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                INSERT INTO downloads_soundcloud_accounts (name, soundcloud_id)\n                VALUES (%s, %s)\n                ON DUPLICATE KEY UPDATE soundcloud_id = VALUES(soundcloud_id)\n            ',
                (req.get('name'), req.get('soundcloud_id')),
            )
            conn.commit()
            return {'status': 'ok', 'message': 'SoundCloud account toegevoegd'}
    finally:
        conn.close()


@router.delete('/soundcloud/{name}')
def delete_soundcloud_account(name: str, _auth: dict = Depends(require_admin_role)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('DELETE FROM downloads_soundcloud_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


@router.get('/youtube')
def get_youtube_accounts(_auth: dict = Depends(verify_api_key)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT name, channel_id, download_type, active, min_duration FROM downloads_youtube_accounts'
            )
            return cursor.fetchall()
    finally:
        conn.close()


# A channel can be an audio source, a video source, or both: the table's key is
# (name, download_type).
YOUTUBE_DOWNLOAD_TYPES = ('audio', 'video')

# Video rows are event channels, where the floor keeps trailers and teasers out.
YOUTUBE_DEFAULT_MIN_DURATION = {'audio': 60, 'video': 1200}


@router.post('/youtube')
def add_youtube_account(req: dict[str, Any] = Body(...), _auth: dict = Depends(require_admin_role)):
    download_type = req.get('download_type') or 'audio'
    if download_type not in YOUTUBE_DOWNLOAD_TYPES:
        raise HTTPException(status_code=400, detail=f'download_type must be one of {YOUTUBE_DOWNLOAD_TYPES}')
    min_duration = req.get('min_duration') or YOUTUBE_DEFAULT_MIN_DURATION[download_type]
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '\n                INSERT INTO downloads_youtube_accounts (name, download_type, min_duration)\n                VALUES (%s, %s, %s)\n                ON DUPLICATE KEY UPDATE name = name\n            ',
                (req.get('name'), download_type, min_duration),
            )
            conn.commit()
            return {'status': 'ok', 'message': 'YouTube account toegevoegd'}
    finally:
        conn.close()


@router.delete('/youtube/{name}')
def delete_youtube_account(name: str, download_type: str = '', _auth: dict = Depends(require_admin_role)):
    """Delete one channel row, or every row for the channel when no type is given."""
    if download_type and download_type not in YOUTUBE_DOWNLOAD_TYPES:
        raise HTTPException(status_code=400, detail=f'download_type must be one of {YOUTUBE_DOWNLOAD_TYPES}')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if download_type:
                cursor.execute(
                    'DELETE FROM downloads_youtube_accounts WHERE name = %s AND download_type = %s',
                    (name, download_type),
                )
            else:
                cursor.execute('DELETE FROM downloads_youtube_accounts WHERE name = %s', (name,))
            conn.commit()
            return {'status': 'ok'}
    finally:
        conn.close()


def _parse_proposal(row: dict) -> dict:
    """Fold the joined proposal columns into one `proposal` object, or None without a run."""
    row = dict(row)
    kind = row.pop('proposal_kind', None)
    targets_raw = row.pop('proposal_targets', None)
    evidence_raw = row.pop('proposal_evidence', None)
    confidence = row.pop('proposal_confidence', None)
    if not kind:
        row['proposal'] = None
        return row
    try:
        targets = json.loads(targets_raw) if targets_raw else []
    except (TypeError, ValueError):
        targets = []
    try:
        evidence = json.loads(evidence_raw) if evidence_raw else []
    except (TypeError, ValueError):
        evidence = [str(evidence_raw)]
    row['proposal'] = {'kind': kind, 'targets': targets, 'evidence': evidence, 'confidence': int(confidence or 0)}
    return row


@router.get('/rules/genres')
def get_genre_curation_queue(
    state: str | None = None, proposal: str | None = None, limit: int = 200, _auth: dict = Depends(verify_api_key)
):
    """Genres by curation state, most frequently seen first.

    Called without a state this returns the whole table; `state=unknown` is the
    curation queue, ordered so the genres that touch most tracks come first.
    Every row carries what the last analysis run proposed for it (`proposal`,
    null before the first run), and `proposal=<kind>` narrows the list to one
    kind of advice so a curator can work through a class at a time.
    """
    if state is not None and state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state, expected one of {', '.join(VALID_STATES)}")
    if proposal is not None and proposal not in PROPOSAL_KINDS:
        raise HTTPException(status_code=400, detail=f"Invalid proposal, expected one of {', '.join(PROPOSAL_KINDS)}")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT g.id, g.name, g.state, g.occurrences,
                       CAST(g.detected_at AS CHAR) AS detected_at,
                       CAST(g.decided_at AS CHAR) AS decided_at, g.decided_by,
                       p.kind AS proposal_kind, p.targets AS proposal_targets,
                       p.evidence AS proposal_evidence, p.confidence AS proposal_confidence
                FROM rules_genres g
                LEFT JOIN rules_genre_proposals p ON p.genre_id = g.id
            """
            where = []
            params: list = []
            if state:
                where.append('g.state = %s')
                params.append(state)
            if proposal:
                where.append('p.kind = %s')
                params.append(proposal)
            if where:
                query += ' WHERE ' + ' AND '.join(where)
            query += ' ORDER BY g.occurrences DESC, g.name LIMIT %s'
            params.append(limit)
            cursor.execute(query, params)
            rows = [_parse_proposal(row) for row in cursor.fetchall()]
            # Targets come from a second query rather than a join: a genre can now
            # expand into several, so joining would multiply the rows the page shows.
            ids = [row['id'] for row in rows]
            if ids:
                placeholders = ', '.join(['%s'] * len(ids))
                cursor.execute(
                    f'\n                    SELECT e.genre_id, t.id AS target_id, t.name AS target_name\n                    FROM rules_genre_expansions e\n                    JOIN rules_genres t ON t.id = e.target_id\n                    WHERE e.genre_id IN ({placeholders})\n                    ORDER BY e.genre_id, e.position, t.name\n                ',
                    ids,
                )
                targets: dict = {}
                for target in cursor.fetchall():
                    targets.setdefault(target['genre_id'], []).append(
                        {'id': target['target_id'], 'name': target['target_name']}
                    )
                for row in rows:
                    row['canonical_targets'] = targets.get(row['id'], [])
            return rows
    finally:
        conn.close()


@router.post('/rules/genres/{genre_id}/decide')
def decide_genre(genre_id: int, decision: GenreDecisionRequest, auth: dict = Depends(require_rules_manage)):
    """Move a genre to white or black, optionally rewriting it to other genres.

    A decision made here is recorded as `decided_by`, so the tagger never
    overwrites it later. More than one target is allowed, which is how a
    contraction is expressed: 'Upterror' becomes 'Uptempo Hardcore' + 'Terror'.
    """
    if decision.state not in (WHITE, BLACK):
        raise HTTPException(status_code=400, detail=f'Invalid state, expected {WHITE} or {BLACK}')
    targets = decision.targets()
    if genre_id in targets:
        raise HTTPException(status_code=400, detail='A genre cannot be its own correction')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id, name FROM rules_genres WHERE id = %s', (genre_id,))
            genre_row = cursor.fetchone()
            if not genre_row:
                raise HTTPException(status_code=404, detail='Unknown genre')
            for target in targets:
                cursor.execute('SELECT id FROM rules_genres WHERE id = %s', (target,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=400, detail='Unknown correction target')
            decided_by = (
                (auth.get('user') or {}).get('username')
                if isinstance(auth.get('user'), dict)
                else auth.get('type', 'human')
            )
            cursor.execute(
                '\n                UPDATE rules_genres\n                SET state = %s, canonical_id = %s, decided_at = NOW(), decided_by = %s\n                WHERE id = %s\n            ',
                (decision.state, targets[0] if targets else None, decided_by or 'human', genre_id),
            )
            # Replace rather than merge: the request carries the whole target list,
            # so clearing a correction is just an empty one.
            cursor.execute('DELETE FROM rules_genre_expansions WHERE genre_id = %s', (genre_id,))
            for position, target in enumerate(targets):
                cursor.execute(
                    'INSERT INTO rules_genre_expansions (genre_id, target_id, position) VALUES (%s, %s, %s)',
                    (genre_id, target, position),
                )
        # After the commit: the retag has to see the decision it was queued for.
        try:
            rescan_invalidator.invalidate_by_genre_id(genre_id, genre_row.get('name') or '', 'genre_decision')
        except Exception as e:
            logging.warning('Genre decision saved but marking files for retag failed: %s', e)
    finally:
        conn.close()
    # Outside the connection: the decision has to reach the running tagger, which holds a
    # preloaded GenreRulesHelper and would otherwise keep resolving the genre the old way
    # until a restart. The files were just marked for a retag *because* of this decision;
    # without the refresh that retag would rewrite them with the decision it was meant to
    # apply still missing.
    curation_rules.refresh(curation_rules.GENRE_RULES_HELPER)
    return {'status': 'ok'}


#: Shortest normalised show name or spelling that may be stored.
#
# `PodcastHelper` matches a spelling as a substring of `title + path`, so a two-letter
# one hits half the library. Four is what `tools/detect_podcasts.py` already treats as
# too short to be a name of its own (`len(normalize(raw)) < 4`), so both agree on when
# a fragment says nothing.
MINIMUM_SHOW_KEY_LENGTH = 4


def show_key(value: str | None, what: str) -> str:
    """The normalised matching key for a show name or spelling, or a 400.

    Same normalisation `PodcastHelper` and `tools/detect_podcasts.py` use, so what the
    page stores is exactly what the tagger will match on.
    """
    key = normalize_show_name(value or '')
    if not key:
        raise HTTPException(status_code=400, detail=f'{what} cannot be empty')
    if len(key) < MINIMUM_SHOW_KEY_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f'{what} needs at least {MINIMUM_SHOW_KEY_LENGTH} letters or digits: '
            'a shorter one matches unrelated files',
        )
    return key


def load_podcast(cursor, podcast_id: int) -> dict:
    cursor.execute('SELECT id, name FROM rules_podcasts WHERE id = %s', (podcast_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail='Unknown podcast')
    return row


def keep_as_alias(cursor, podcast_id: int, name: str) -> None:
    """Record a show's own name as one of its spellings.

    `PodcastHelper._load` seeds every show with its name as an alias, so a name that
    is dropped -- by a rename, or by the row being merged away -- stops matching
    unless it survives here. IGNORE rather than an upsert: when the spelling already
    belongs to another show, that show's claim on it is the older decision and wins.
    """
    cursor.execute(
        'INSERT IGNORE INTO rules_podcast_aliases (podcast_id, alias, normalized_alias, occurrences) '
        'VALUES (%s, %s, %s, 0)',
        (podcast_id, name, normalize_show_name(name)),
    )


@router.get('/rules/podcasts')
def get_podcast_curation_queue(state: str | None = None, limit: int = 200, _auth: dict = Depends(verify_api_key)):
    """Radio shows and podcast series by curation state, most episodes first.

    `state=unknown` is the queue `tools/detect_podcasts.py` fills; only the shows
    moved to white are ever written to a file by the tagger.
    """
    if state is not None and state not in VALID_STATES:
        raise HTTPException(status_code=400, detail=f"Invalid state, expected one of {', '.join(VALID_STATES)}")
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            query = '\n                SELECT p.id, p.name, p.state, p.occurrences, p.host, p.station,\n                       CAST(p.detected_at AS CHAR) AS detected_at,\n                       CAST(p.decided_at AS CHAR) AS decided_at, p.decided_by\n                FROM rules_podcasts p\n            '
            params: list = []
            if state:
                query += ' WHERE p.state = %s'
                params.append(state)
            query += ' ORDER BY p.occurrences DESC, p.name LIMIT %s'
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            # Aliases come from a second query for the same reason the genre targets
            # do: a show has several spellings, and joining would multiply the rows.
            ids = [row['id'] for row in rows]
            if ids:
                placeholders = ', '.join(['%s'] * len(ids))
                cursor.execute(
                    f'\n                    SELECT podcast_id, alias\n                    FROM rules_podcast_aliases\n                    WHERE podcast_id IN ({placeholders})\n                    ORDER BY occurrences DESC, alias\n                ',
                    ids,
                )
                aliases: dict = {}
                for row in cursor.fetchall():
                    aliases.setdefault(row['podcast_id'], []).append(row['alias'])
                for row in rows:
                    row['aliases'] = aliases.get(row['id'], [])
            return rows
    finally:
        conn.close()


@router.post('/rules/podcasts/{podcast_id}/decide')
def decide_podcast(podcast_id: int, decision: PodcastDecisionRequest, auth: dict = Depends(require_rules_manage)):
    """Move a show to white or black, optionally merging it into another show.

    Merging is how the three spellings of Isaac's Hardstyle Sessions become one
    show: the aliases move to the target and this row goes away, so the tagger
    matches every spelling and writes one name.
    """
    if decision.state not in (WHITE, BLACK):
        raise HTTPException(status_code=400, detail=f'Invalid state, expected {WHITE} or {BLACK}')
    if decision.merge_into_podcast_id == podcast_id:
        raise HTTPException(status_code=400, detail='A show cannot be merged into itself')
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            row = load_podcast(cursor, podcast_id)
            target_id = decision.merge_into_podcast_id
            if target_id is not None:
                cursor.execute('SELECT id FROM rules_podcasts WHERE id = %s', (target_id,))
                if not cursor.fetchone():
                    raise HTTPException(status_code=400, detail='Unknown merge target')
                # One transaction: the kept name, the moved spellings and the dropped row
                # land together. Under autocommit a failed DELETE left the show in the
                # queue with its spellings already handed to the target
                # (docs/bug-reports/113-parent-child-deletes-without-transaction.md).
                with transaction(conn):
                    # The name this row was known by has to survive as an alias of the
                    # target, or every file that spells the show that way stops matching.
                    # The alias rows carry the detected spellings; the name itself is only
                    # an implicit one, and after a rename it is in neither place.
                    keep_as_alias(cursor, target_id, row['name'])
                    cursor.execute(
                        'UPDATE rules_podcast_aliases SET podcast_id = %s WHERE podcast_id = %s',
                        (target_id, podcast_id),
                    )
                    cursor.execute('DELETE FROM rules_podcasts WHERE id = %s', (podcast_id,))
                curation_rules.refresh(curation_rules.PODCAST_HELPER)
                return {'status': 'ok', 'merged_into': target_id}
            decided_by = (
                (auth.get('user') or {}).get('username')
                if isinstance(auth.get('user'), dict)
                else auth.get('type', 'human')
            )
            cursor.execute(
                '\n                UPDATE rules_podcasts\n                SET state = %s, host = COALESCE(%s, host), station = COALESCE(%s, station),\n                    decided_at = NOW(), decided_by = %s\n                WHERE id = %s\n            ',
                (decision.state, decision.host, decision.station, decided_by or 'human', podcast_id),
            )
            conn.commit()
    finally:
        conn.close()
    # Outside the connection: approving a show has to reach the running tagger, which
    # holds a preloaded PodcastHelper and would otherwise not see it until a restart.
    curation_rules.refresh(curation_rules.PODCAST_HELPER)
    return {'status': 'ok'}


@router.post('/rules/podcasts/{podcast_id}/rename')
def rename_podcast(podcast_id: int, request: PodcastRenameRequest, _auth: dict = Depends(require_rules_manage)):
    """Give a show the name it should be tagged and browsed under.

    The name is what `PodcastHelper.get` writes into the PODCAST tag, so a detected
    row named after its uploader labels every episode that way. Renaming also changes
    what the show matches on -- the name doubles as a spelling -- which is why the old
    one is kept as an alias rather than dropped.
    """
    name = (request.name or '').strip()
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        # One transaction (bug report 115): a rename whose alias INSERT failed dropped the
        # old spelling for good, since a retry keeps the name the row already carries.
        with transaction(conn), conn.cursor() as cursor:
            row = load_podcast(cursor, podcast_id)
            key = show_key(name, 'A show name')
            cursor.execute('SELECT id, name FROM rules_podcasts WHERE normalized_name = %s', (key,))
            clash = cursor.fetchone()
            if clash and int(clash['id']) != podcast_id:
                raise HTTPException(
                    status_code=409, detail=f"'{clash['name']}' already uses that name -- merge the two shows instead"
                )
            cursor.execute(
                'UPDATE rules_podcasts SET name = %s, normalized_name = %s WHERE id = %s', (name, key, podcast_id)
            )
            keep_as_alias(cursor, podcast_id, row['name'])
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.PODCAST_HELPER)
    return {'status': 'ok', 'name': name}


@router.post('/rules/podcasts/{podcast_id}/aliases')
def add_podcast_alias(podcast_id: int, request: PodcastAliasRequest, _auth: dict = Depends(require_rules_manage)):
    """Record another spelling this show occurs under.

    The detector only proposes fragments that carried an episode marker, so the
    spelling that catches the rest of a series -- 'KELTEK | Pure Hardstyle |' next to
    'KELTEK Presents | Pure Hardstyle |' -- usually has to be added by hand. Matching
    is a substring test on `title + path`, so the shortest distinctive fragment covers
    the most files.
    """
    alias = (request.alias or '').strip()
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            load_podcast(cursor, podcast_id)
            key = show_key(alias, 'A spelling')
            cursor.execute(
                '\n                SELECT a.podcast_id, p.name\n                FROM rules_podcast_aliases a\n                JOIN rules_podcasts p ON p.id = a.podcast_id\n                WHERE a.normalized_alias = %s\n            ',
                (key,),
            )
            owner = cursor.fetchone()
            if owner and int(owner['podcast_id']) == podcast_id:
                # Already this show's: saying so again is not a mistake worth an error.
                return {'status': 'ok', 'alias': alias}
            if owner:
                raise HTTPException(status_code=409, detail=f"'{owner['name']}' already claims that spelling")
            cursor.execute(
                'INSERT INTO rules_podcast_aliases (podcast_id, alias, normalized_alias, occurrences) '
                'VALUES (%s, %s, %s, 0)',
                (podcast_id, alias, key),
            )
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.PODCAST_HELPER)
    return {'status': 'ok', 'alias': alias}


@router.delete('/rules/podcasts/{podcast_id}/aliases')
def delete_podcast_alias(podcast_id: int, alias: str, _auth: dict = Depends(require_rules_manage)):
    """Drop a spelling that matches files this show does not own.

    There is no floor on how many spellings may go: a show with none still matches its
    own name, which `PodcastHelper._load` always adds.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            load_podcast(cursor, podcast_id)
            cursor.execute(
                'SELECT id FROM rules_podcast_aliases WHERE podcast_id = %s AND normalized_alias = %s',
                (podcast_id, normalize_show_name(alias)),
            )
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='This show has no such spelling')
            cursor.execute('DELETE FROM rules_podcast_aliases WHERE id = %s', (row['id'],))
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.PODCAST_HELPER)
    return {'status': 'ok'}


@router.get('/rules/artist-genres')
def get_artist_genre_rules(_auth: dict = Depends(verify_api_key)):
    """Every artist -> genre rule, with what it touches and who made it.

    `artist_id` and `track_count` come from the library row of the same name, so the
    page can open the artist and show how many tracks a rule reaches; both are
    null/zero for a rule whose artist has since left the library, which is worth
    seeing rather than hiding.
    """
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                SELECT r.id, r.artist_name, g.name AS genre_name, r.genre_id,
                       a.id AS artist_id, COALESCE(tc.track_count, 0) AS track_count,
                       CAST(r.created_at AS CHAR) AS created_at, r.created_by
                FROM rules_artist_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                LEFT JOIN library_artists a ON a.name = r.artist_name
                LEFT JOIN (
                    SELECT artist_id, COUNT(DISTINCT track_id) AS track_count
                    FROM library_track_artists GROUP BY artist_id
                ) tc ON tc.artist_id = a.id
                ORDER BY r.artist_name, g.name
                '''
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/rules/artist-genres')
def add_artist_genre_rule(rule: ArtistGenreRule, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            curation_rules.add_artist_genre_rule(
                cursor, rule.artist_name, rule.genre_id, curation_rules.actor_name(_auth)
            )
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.ARTIST_GENRE_HELPER)
    invalidate_quietly(rule.artist_name, 'artist_genre_rule')
    return {'status': 'ok'}


@router.delete('/rules/artist-genres/{rule_id}')
def delete_artist_genre_rule(rule_id: int, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            # The name has to come out before the DELETE; afterwards there is nothing
            # left to match on.
            cursor.execute('SELECT artist_name FROM rules_artist_genres WHERE id = %s', (rule_id,))
            row = cursor.fetchone()
            cursor.execute('DELETE FROM rules_artist_genres WHERE id = %s', (rule_id,))
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.ARTIST_GENRE_HELPER)
    if row:
        invalidate_quietly(row['artist_name'], 'artist_genre_rule')
    return {'status': 'ok'}


@router.get('/rules/label-genres')
def get_label_genre_rules(_auth: dict = Depends(verify_api_key)):
    """Every label -> genre rule, with its track count and provenance (see the artist twin)."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                SELECT r.id, r.label_name, g.name AS genre_name, r.genre_id,
                       l.id AS label_id, COALESCE(tc.track_count, 0) AS track_count,
                       CAST(r.created_at AS CHAR) AS created_at, r.created_by
                FROM rules_label_genres r
                JOIN rules_genres g ON r.genre_id = g.id
                LEFT JOIN library_labels l ON l.name = r.label_name
                LEFT JOIN (
                    SELECT label_id, COUNT(DISTINCT track_id) AS track_count
                    FROM library_track_labels GROUP BY label_id
                ) tc ON tc.label_id = l.id
                ORDER BY r.label_name, g.name
                '''
            )
            return cursor.fetchall()
    finally:
        conn.close()


@router.post('/rules/label-genres')
def add_label_genre_rule(rule: LabelGenreRule, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            curation_rules.add_label_genre_rule(
                cursor, rule.label_name, rule.genre_id, curation_rules.actor_name(_auth)
            )
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.LABEL_GENRE_HELPER)
    invalidate_quietly(rule.label_name, 'label_genre_rule')
    return {'status': 'ok'}


@router.delete('/rules/label-genres/{rule_id}')
def delete_label_genre_rule(rule_id: int, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT label_name FROM rules_label_genres WHERE id = %s', (rule_id,))
            row = cursor.fetchone()
            cursor.execute('DELETE FROM rules_label_genres WHERE id = %s', (rule_id,))
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.LABEL_GENRE_HELPER)
    if row:
        invalidate_quietly(row['label_name'], 'label_genre_rule')
    return {'status': 'ok'}


@router.get('/rules/artist-redirects', deprecated=True, dependencies=[DEPRECATED_CALL])
def get_artist_redirects(_auth: dict = Depends(verify_api_key)):
    """Names the tagger should rewrite, or ignore when there is no correction."""
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT id, name, corrected_name FROM rules_ignored_artists ORDER BY name')
            return cursor.fetchall()
    finally:
        conn.close()


def _refuse_bad_redirect_target(cursor, name: str, corrected: str) -> None:
    """400 for a redirect that would end at a rejected artist or close a loop.

    The same rule the artist curation page applies (routers/artist_curation.py): a
    correction must never rewrite one problem into another. A correction that only
    changes the casing of the name itself is fine -- that is not a loop.
    """
    cursor.execute('SELECT state FROM rules_artists WHERE name = %s', (corrected,))
    decision = cursor.fetchone()
    if decision and decision.get('state') == BLACK:
        raise HTTPException(status_code=400, detail=f"'{corrected}' is rejected; pick an approved name")
    if corrected.lower() == name.lower():
        return
    cursor.execute('SELECT name, corrected_name FROM rules_ignored_artists WHERE corrected_name IS NOT NULL')
    corrections = {
        row['name']: row['corrected_name']
        for row in cursor.fetchall()
        if row['corrected_name'] and row['name'].lower() != name.lower()
    }
    corrections[name] = corrected
    _resolved, _paths, cycles = resolve_redirect_chains(corrections)
    for cycle in cycles:
        if name.lower() in {member.lower() for member in cycle}:
            raise HTTPException(
                status_code=400, detail=f"'{name}' -> '{corrected}' closes a loop: {' -> '.join(cycle)}"
            )


@router.post('/rules/artist-redirects', deprecated=True, dependencies=[DEPRECATED_CALL])
def save_artist_redirect(redirect: ArtistRedirect, _auth: dict = Depends(require_rules_manage)):
    """Add a redirect, or change the correction on one that already exists."""
    name = redirect.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail='A redirect needs a name')
    corrected = (redirect.corrected_name or '').strip() or None
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            if corrected:
                _refuse_bad_redirect_target(cursor, name, corrected)
            cursor.execute('SELECT id FROM rules_ignored_artists WHERE LOWER(name) = LOWER(%s)', (name,))
            if cursor.fetchone():
                cursor.execute(
                    'UPDATE rules_ignored_artists SET corrected_name = %s WHERE LOWER(name) = LOWER(%s)',
                    (corrected, name),
                )
            else:
                cursor.execute(
                    'INSERT INTO rules_ignored_artists (name, corrected_name) VALUES (%s, %s)', (name, corrected)
                )
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    # The old spelling is what sits in the files today, so that is the term to search
    # for -- not the corrected name, which nothing carries yet.
    invalidate_quietly(name, 'artist_redirect')
    return {'status': 'ok'}


@router.delete('/rules/artist-redirects/{rule_id}', deprecated=True, dependencies=[DEPRECATED_CALL])
def delete_artist_redirect(rule_id: int, _auth: dict = Depends(require_rules_manage)):
    conn = get_db_connection()
    if not conn:
        raise HTTPException(status_code=500)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT name FROM rules_ignored_artists WHERE id = %s', (rule_id,))
            row = cursor.fetchone()
            cursor.execute('DELETE FROM rules_ignored_artists WHERE id = %s', (rule_id,))
            conn.commit()
    finally:
        conn.close()
    curation_rules.refresh(curation_rules.ARTIST_REDIRECT_HELPER)
    if row:
        invalidate_quietly(row['name'], 'artist_redirect')
    return {'status': 'ok'}


@router.get('/scrobble/import/latest')
def get_latest_scrobble_imports_proxy(auth: dict = Depends(verify_api_key)):
    """The same list as GET /api/scrobble/import/latest, with the same admin-or-own scope (issue #38).

    The scrobbler router is mounted first and answers this path itself; this copy only answers
    where that router is not mounted, and must never be the wider of the two.
    """
    from services.music_manager.routers.scrobbler import get_latest_imports

    return get_latest_imports(auth)


@router.post('/scrobble/import/listenbrainz')
def trigger_lb_import_proxy(
    background_tasks: BackgroundTasks, req: dict[str, Any] = Body(...), auth: dict = Depends(verify_api_key)
):
    """The same import as POST /api/scrobble/import/listenbrainz, with the same self-or-admin check."""
    from services.music_manager.routers.scrobbler import ImportRequest, trigger_lb_import

    return trigger_lb_import(ImportRequest(**req), background_tasks, auth)


@router.post('/tagger/rescan')
def trigger_tagger_rescan(_auth: dict = Depends(require_rules_manage)):
    helper = ProcessedFilesHelper()
    # With its reason: this is bulk, and the queue serves every decision before it.
    helper.mark_for_rescan(reason='rescan_all')
    return {'status': 'ok', 'message': 'All files marked for rescan'}


@router.post('/tagger/rescan/file', deprecated=True, dependencies=[DEPRECATED_CALL])
def trigger_file_rescan(filepath: str = Body(..., embed=True), _auth: dict = Depends(require_rules_manage)):
    helper = ProcessedFilesHelper()
    helper.mark_for_rescan(filepath, reason='manual')
    return {'status': 'ok', 'message': f"File '{filepath}' marked for rescan"}
