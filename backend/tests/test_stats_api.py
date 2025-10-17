from __future__ import annotations

import pytest

from backend.tests.fixtures import seed_dataset


@pytest.mark.asyncio
async def test_stats_endpoints(client):
    await seed_dataset(client)

    artists = await client.get(
        "/api/v1/stats/artists", params={"period": "year", "value": "2023"}
    )
    assert artists.status_code == 200
    artist_payload = artists.json()
    artist_names = [row["artist"] for row in artist_payload["items"]]
    assert "Artist A" in artist_names

    artists_all_time = await client.get("/api/v1/stats/artists", params={"period": "all"})
    assert artists_all_time.status_code == 200
    assert any(
        row["artist"] == "Artist A" for row in artists_all_time.json()["items"]
    )

    albums = await client.get(
        "/api/v1/stats/albums", params={"period": "year", "value": "2023"}
    )
    assert albums.status_code == 200
    album_titles = [row["album"] for row in albums.json()["items"]]
    assert "Sunrise" in album_titles

    tracks = await client.get(
        "/api/v1/stats/tracks", params={"period": "all"}
    )
    assert tracks.status_code == 200
    track_payload = tracks.json()
    track_titles = [row["track"] for row in track_payload["items"]]
    assert "Afternoon Groove" in track_titles
    groove_row = next(row for row in track_payload["items"] if row["track"] == "Afternoon Groove")
    assert groove_row["artist"] == "Artist A"
    assert groove_row["album"] == "Groove"
    assert groove_row["count"] == 1

    genres = await client.get(
        "/api/v1/stats/genres", params={"period": "year", "value": "2023"}
    )
    assert genres.status_code == 200
    genre_names = [row["genre"] for row in genres.json()["items"]]
    assert "Chill" in genre_names

    month_genres = await client.get(
        "/api/v1/stats/genres", params={"period": "month", "value": "2023-11"}
    )
    assert month_genres.status_code == 200
    month_payload = month_genres.json()
    assert month_payload["items"] and month_payload["items"][0]["genre"] == "Chill"

    day_artists = await client.get(
        "/api/v1/stats/artists", params={"period": "day", "value": "2023-05-20"}
    )
    assert day_artists.status_code == 200
    assert any(row["artist"] == "Artist A" for row in day_artists.json()["items"])

    top_artist = await client.get("/api/v1/stats/top-artist-by-genre", params={"year": 2023})
    assert top_artist.status_code == 200
    data = top_artist.json()
    assert any(item["genre"] == "Chill" for item in data)

    time_of_day = await client.get(
        "/api/v1/stats/time-of-day",
        params={"year": 2023, "period": "evening"},
    )
    assert time_of_day.status_code == 200
