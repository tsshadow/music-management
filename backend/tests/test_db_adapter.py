from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.core.startup import init_database
from backend.app.db.sqlite_test import create_sqlite_memory_adapter
from backend.app.models import metadata


@pytest.mark.asyncio
async def test_adapter_upserts():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    assert user_id == await adapter.upsert_user("alice")

    artist_id = await adapter.upsert_artist("Artist")
    genre_id = await adapter.upsert_genre("Genre")
    album_id = await adapter.upsert_album("Album", release_year=2024)
    track_id = await adapter.upsert_track(
        title="Song",
        album_id=album_id,
        duration_secs=200,
        disc_no=None,
        track_no=1,
        mbid=None,
        isrc=None,
    )
    await adapter.link_track_artists(track_id, [(artist_id, "primary")])
    await adapter.link_track_genres(track_id, [genre_id])

    listened_at = datetime.now(timezone.utc)
    listen_id, created = await adapter.insert_listen(
        user_id=user_id,
        track_id=track_id,
        listened_at=listened_at,
        source="test",
        source_track_id="1",
        position_secs=10,
        duration_secs=200,
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )
    assert listen_id > 0
    assert created is True
    assert await adapter.count_listens() == 1

    # Deduped listen
    listen_id2, created2 = await adapter.insert_listen(
        user_id=user_id,
        track_id=track_id,
        listened_at=listened_at,
        source="test",
        source_track_id="1",
        position_secs=10,
        duration_secs=200,
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )
    assert listen_id == listen_id2
    assert created2 is False

    rows = await adapter.fetch_listens_for_export(user="alice", limit=10)
    assert len(rows) == 1
    export_row = rows[0]
    assert export_row["username"] == "alice"
    assert export_row["track"]["title"] == "Song"
    assert export_row["artists"] == [{"name": "Artist", "role": "primary"}]
    assert export_row["genres"] == ["Genre"]
    assert export_row["listen_artists"] == ["Artist"]

    future_rows = await adapter.fetch_listens_for_export(
        user="alice",
        since=listened_at + timedelta(seconds=1),
    )
    assert future_rows == []

    await adapter.delete_all_listens()
    assert await adapter.count_listens() == 0

    await adapter.close()
