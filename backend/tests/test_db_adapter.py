from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import insert, select
from analyzer.matching.normalizer import normalize_text
from analyzer.matching.uid import make_track_uid

from backend.app.core.startup import init_database
from backend.app.db.sqlite_test import create_sqlite_memory_adapter
from backend.app.models import (
    albums,
    artists,
    genres,
    metadata,
    track_artists,
    track_genres,
    tracks,
)


async def add_artist(adapter, name: str, mbid: str | None = None) -> int:
    normalized = normalize_text(name)
    async with adapter.session_factory() as session:
        res = await session.execute(
            insert(artists).values(
                name=name,
                name_normalized=normalized,
                sort_name=normalized,
                mbid=mbid,
            )
        )
        await session.commit()
        return int(res.inserted_primary_key[0])


async def add_genre(adapter, name: str) -> int:
    normalized = normalize_text(name)
    async with adapter.session_factory() as session:
        res = await session.execute(
            insert(genres).values(
                name=name,
                name_normalized=normalized,
            )
        )
        await session.commit()
        return int(res.inserted_primary_key[0])


async def add_album(
    adapter,
    title: str,
    *,
    artist_id: int,
    release_year: int | None = None,
    mbid: str | None = None,
) -> int:
    normalized = normalize_text(title)
    async with adapter.session_factory() as session:
        res = await session.execute(
            insert(albums).values(
                artist_id=artist_id,
                title=title,
                title_normalized=normalized,
                year=release_year,
                mbid=mbid,
            )
        )
        await session.commit()
        return int(res.inserted_primary_key[0])


async def add_track(
    adapter,
    *,
    title: str,
    album_id: int | None,
    primary_artist_id: int | None,
    duration_secs: int | None,
    disc_no: int | None,
    track_no: int | None,
    mbid: str | None = None,
    isrc: str | None = None,
    acoustid: str | None = None,
    track_uid: str | None = None,
) -> int:
    normalized = normalize_text(title)
    async with adapter.session_factory() as session:
        uid = track_uid
        if uid is None:
            artist_name = None
            if primary_artist_id is not None:
                artist_row = await session.execute(
                    select(artists.c.name).where(artists.c.id == primary_artist_id)
                )
                artist_name = artist_row.scalar_one_or_none()
            album_title = None
            if album_id is not None:
                album_row = await session.execute(
                    select(albums.c.title).where(albums.c.id == album_id)
                )
                album_title = album_row.scalar_one_or_none()
            uid = make_track_uid(artist_name, title, album_title, duration_secs)
        res = await session.execute(
            insert(tracks).values(
                title=title,
                title_normalized=normalized,
                album_id=album_id,
                primary_artist_id=primary_artist_id,
                duration_secs=duration_secs,
                disc_no=disc_no,
                track_no=track_no,
                mbid=mbid,
                isrc=isrc,
                acoustid=acoustid,
                track_uid=uid,
            )
        )
        await session.commit()
        return int(res.inserted_primary_key[0])


async def link_track_artist(
    adapter,
    track_id: int,
    artists_payload,
    role: str = "primary",
) -> None:
    async with adapter.session_factory() as session:
        if isinstance(artists_payload, list):
            pairs = artists_payload
        else:
            pairs = [(artists_payload, role)]
        for artist_id, artist_role in pairs:
            await session.execute(
                insert(track_artists).values(
                    track_id=track_id, artist_id=artist_id, role=artist_role
                )
            )
        await session.commit()


async def link_track_genre(adapter, track_id: int, genres_payload) -> None:
    async with adapter.session_factory() as session:
        if isinstance(genres_payload, list):
            genre_ids = genres_payload
        else:
            genre_ids = [genres_payload]
        for genre_id in genre_ids:
            await session.execute(
                insert(track_genres).values(track_id=track_id, genre_id=genre_id)
            )
        await session.commit()


@pytest.mark.asyncio
async def test_adapter_upserts():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    assert user_id == await adapter.upsert_user("alice")

    artist_id = await add_artist(adapter, "Artist")
    genre_id = await add_genre(adapter, "Genre")
    album_id = await add_album(adapter, "Album", artist_id=artist_id, release_year=2024)
    track_uid = make_track_uid("Artist", "Song", "Album", 200)
    track_id = await add_track(
        adapter,
        title="Song",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=200,
        disc_no=None,
        track_no=1,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=track_uid,
    )
    await link_track_artist(adapter, track_id, artist_id, "primary")
    await link_track_genre(adapter, track_id, genre_id)

    assert await adapter.lookup_artist_id("Artist") == artist_id
    assert (
        await adapter.lookup_album_id(
            title="Album", artist_id=artist_id, release_year=2024
        )
        == album_id
    )
    assert await adapter.lookup_track_id_by_uid(track_uid) == track_id
    assert await adapter.lookup_track_artist_ids(track_id) == [artist_id]
    assert await adapter.lookup_track_genre_ids(track_id) == [genre_id]

    listened_at = datetime.now(timezone.utc)
    listen_id, created = await adapter.insert_listen(
        user_id=user_id,
        track_id=track_id,
        listened_at=listened_at,
        source="test",
        source_track_id="1",
        position_secs=10,
        duration_secs=200,
        artist_name_raw="Artist",
        track_title_raw="Song",
        album_title_raw="Album",
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
        artist_name_raw="Artist",
        track_title_raw="Song",
        album_title_raw="Album",
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


@pytest.mark.asyncio
async def test_fetch_recent_listens_prefers_clean_listen_artists():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    artist_good1 = await add_artist(adapter, "Jur Terreur")
    artist_good2 = await add_artist(adapter, "Brainkick")
    artist_bad1 = await add_artist(adapter, ",Jur Terreur")
    artist_bad2 = await add_artist(adapter, " Brainkick ,")
    track_id = await add_track(adapter, 
        title="Ready To Move",
        album_id=None,
        primary_artist_id=None,
        duration_secs=None,
        disc_no=None,
        track_no=None,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )

    await link_track_artist(adapter, 
        track_id,
        [
            (artist_good1, "primary"),
            (artist_good2, "primary"),
        ],
    )

    async with adapter.session_factory() as session:
        await session.execute(
            insert(track_artists).values(track_id=track_id, artist_id=artist_bad1, role="primary")
        )
        await session.execute(
            insert(track_artists).values(track_id=track_id, artist_id=artist_bad2, role="primary")
        )
        await session.commit()

    listened_at = datetime.now(timezone.utc)
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_id,
        listened_at=listened_at,
        source="listenbrainz",
        source_track_id="1",
        position_secs=None,
        duration_secs=None,
        artist_name_raw=None,
        track_title_raw=None,
        album_title_raw=None,
        artist_ids=[artist_good1, artist_good2],
        genre_ids=[],
    )

    rows = await adapter.fetch_recent_listens(limit=5)
    assert len(rows) == 1
    assert rows[0]["artist_names"] == "Jur Terreur, Brainkick"
    assert [artist["name"] for artist in rows[0]["artists"]] == [
        "Jur Terreur",
        "Brainkick",
    ]

    await adapter.close()


@pytest.mark.asyncio
async def test_fetch_listens_supports_period_filters_and_pagination():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    artist_id = await add_artist(adapter, "Artist")
    genre_id = await add_genre(adapter, "Hardcore")
    album_id = await add_album(adapter, "Album", artist_id=artist_id, release_year=2023)

    track1 = await add_track(adapter, 
        title="Track One",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=210,
        disc_no=1,
        track_no=1,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )
    track2 = await add_track(adapter, 
        title="Track Two",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=200,
        disc_no=1,
        track_no=2,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )

    await link_track_artist(adapter, track1, [(artist_id, "primary")])
    await link_track_artist(adapter, track2, [(artist_id, "primary")])
    await link_track_genre(adapter, track1, [genre_id])
    await link_track_genre(adapter, track2, [genre_id])

    listen_day = datetime(2025, 10, 9, 7, 14, tzinfo=timezone.utc)
    previous_day = listen_day - timedelta(days=1)

    await adapter.insert_listen(
        user_id=user_id,
        track_id=track1,
        listened_at=listen_day,
        source="listenbrainz",
        source_track_id="1",
        position_secs=30,
        duration_secs=210,
        artist_name_raw="Artist",
        track_title_raw="Track One",
        album_title_raw="Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track2,
        listened_at=previous_day,
        source="listenbrainz",
        source_track_id="2",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Artist",
        track_title_raw="Track Two",
        album_title_raw="Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )

    rows, total = await adapter.fetch_listens(
        period="day",
        value="2025-10-09",
        limit=100,
        offset=0,
    )
    assert total == 1
    assert len(rows) == 1
    listen = rows[0]
    assert listen["track_title"] == "Track One"
    assert listen["album_id"] == album_id
    assert listen["artist_names"] == "Artist"
    assert listen["genre_names"] == "Hardcore"

    rows_all, total_all = await adapter.fetch_listens(
        period="all",
        value=None,
        limit=1,
        offset=0,
    )
    assert total_all == 2
    assert len(rows_all) == 1
    assert rows_all[0]["track_title"] == "Track One"
    rows_next, _ = await adapter.fetch_listens(period="all", value=None, limit=1, offset=1)
    assert len(rows_next) == 1
    assert rows_next[0]["track_title"] == "Track Two"

    await adapter.close()


@pytest.mark.asyncio
async def test_fetch_listen_detail_returns_enriched_metadata():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    artist_id = await add_artist(adapter, "Detail Artist")
    genre_id = await add_genre(adapter, "Industrial")
    album_id = await add_album(adapter, "Detail Album", artist_id=artist_id, release_year=2024)
    track_id = await add_track(adapter, 
        title="Detail Track",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=250,
        disc_no=1,
        track_no=5,
        mbid="track-mbid",
        isrc="ISRC12345678",
        acoustid=None,
        track_uid=None,
    )

    await link_track_artist(adapter, track_id, [(artist_id, "primary")])
    await link_track_genre(adapter, track_id, [genre_id])

    listened_at = datetime.now(timezone.utc)
    listen_id, _ = await adapter.insert_listen(
        user_id=user_id,
        track_id=track_id,
        listened_at=listened_at,
        source="listenbrainz",
        source_track_id="SRC",
        position_secs=40,
        duration_secs=250,
        artist_name_raw="Detail Artist",
        track_title_raw="Detail Track",
        album_title_raw="Detail Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )

    detail = await adapter.fetch_listen_detail(listen_id)
    assert detail is not None
    assert detail["track_id"] == track_id
    assert detail["album_id"] == album_id
    assert detail["artists"][0]["name"] == "Detail Artist"
    assert detail["genres"][0]["name"] == "Industrial"
    assert detail["track_duration_secs"] == 250
    assert detail["disc_no"] == 1
    assert detail["track_no"] == 5
    assert detail["source_track_id"] == "SRC"

    await adapter.close()


@pytest.mark.asyncio
async def test_artist_insights_aggregates_listens():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    artist_id = await add_artist(adapter, "Insight Artist")
    other_artist = await add_artist(adapter, "Guest")
    genre_id = await add_genre(adapter, "Hardcore")
    album_id = await add_album(adapter, "Insight Album", artist_id=artist_id, release_year=2022)

    track_main = await add_track(adapter, 
        title="Main Track",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=200,
        disc_no=1,
        track_no=1,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )
    track_guest = await add_track(adapter, 
        title="Guest Track",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=180,
        disc_no=1,
        track_no=2,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )

    await link_track_artist(adapter, track_main, [(artist_id, "primary")])
    await link_track_artist(adapter, track_guest, [(artist_id, "primary"), (other_artist, "featured")])
    await link_track_genre(adapter, track_main, [genre_id])
    await link_track_genre(adapter, track_guest, [genre_id])

    base_time = datetime(2025, 1, 1, tzinfo=timezone.utc)
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_main,
        listened_at=base_time,
        source="listenbrainz",
        source_track_id="A",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Insight Artist",
        track_title_raw="Main Track",
        album_title_raw="Insight Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_guest,
        listened_at=base_time + timedelta(days=1),
        source="listenbrainz",
        source_track_id="B",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Insight Artist",
        track_title_raw="Guest Track",
        album_title_raw="Insight Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )

    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_guest,
        listened_at=base_time - timedelta(days=40),
        source="listenbrainz",
        source_track_id="C",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Insight Artist",
        track_title_raw="Guest Track",
        album_title_raw="Insight Album",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )

    insights = await adapter.artist_insights(artist_id)
    assert insights is not None
    assert insights["listen_count"] == 3
    assert insights["artist_id"] == artist_id
    assert len(insights["top_tracks"]) == 2
    assert insights["top_tracks"][0]["count"] >= insights["top_tracks"][1]["count"]
    assert insights["top_albums"][0]["album_id"] == album_id
    assert insights["top_genres"][0]["genre"] == "Hardcore"
    history = insights["listen_history"]
    assert len(history) == 2
    assert history[-1]["period"] == base_time.strftime("%Y-%m")
    assert history[-1]["count"] == 2

    await adapter.close()


@pytest.mark.asyncio
async def test_album_insights_aggregates_metadata():
    adapter = create_sqlite_memory_adapter()
    await init_database(adapter.engine, metadata)  # type: ignore[attr-defined]
    await adapter.connect()

    user_id = await adapter.upsert_user("alice")
    artist_id = await add_artist(adapter, "Album Artist")
    genre_id = await add_genre(adapter, "Industrial")
    album_id = await add_album(adapter, "Album Insight", artist_id=artist_id, release_year=2021)

    track_one = await add_track(adapter, 
        title="Song One",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=210,
        disc_no=1,
        track_no=1,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )
    track_two = await add_track(adapter, 
        title="Song Two",
        album_id=album_id,
        primary_artist_id=artist_id,
        duration_secs=205,
        disc_no=1,
        track_no=2,
        mbid=None,
        isrc=None,
        acoustid=None,
        track_uid=None,
    )

    await link_track_artist(adapter, track_one, [(artist_id, "primary")])
    await link_track_artist(adapter, track_two, [(artist_id, "primary")])
    await link_track_genre(adapter, track_one, [genre_id])
    await link_track_genre(adapter, track_two, [genre_id])

    now = datetime.now(timezone.utc)
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_one,
        listened_at=now,
        source="listenbrainz",
        source_track_id="1",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Album Artist",
        track_title_raw="Song One",
        album_title_raw="Album Insight",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )
    await adapter.insert_listen(
        user_id=user_id,
        track_id=track_two,
        listened_at=now + timedelta(minutes=5),
        source="listenbrainz",
        source_track_id="2",
        position_secs=None,
        duration_secs=None,
        artist_name_raw="Album Artist",
        track_title_raw="Song Two",
        album_title_raw="Album Insight",
        artist_ids=[artist_id],
        genre_ids=[genre_id],
    )

    insights = await adapter.album_insights(album_id)
    assert insights is not None
    assert insights["listen_count"] == 2
    assert insights["album_id"] == album_id
    assert len(insights["tracks"]) == 2
    assert insights["artists"][0]["artist_id"] == artist_id
    assert insights["artists"][0]["listen_count"] == 2
    assert insights["genres"][0]["genre"] == "Industrial"

    await adapter.close()
