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
    artist_names = [row["artist"] for row in artists.json()]
    assert "Artist A" in artist_names

    genres = await client.get(
        "/api/v1/stats/genres", params={"period": "year", "value": "2023"}
    )
    assert genres.status_code == 200
    genre_names = [row["genre"] for row in genres.json()]
    assert "Chill" in genre_names

    month_genres = await client.get(
        "/api/v1/stats/genres", params={"period": "month", "value": "2023-11"}
    )
    assert month_genres.status_code == 200
    month_payload = month_genres.json()
    assert month_payload and month_payload[0]["genre"] == "Chill"

    day_artists = await client.get(
        "/api/v1/stats/artists", params={"period": "day", "value": "2023-05-20"}
    )
    assert day_artists.status_code == 200
    assert any(row["artist"] == "Artist A" for row in day_artists.json())

    top_artist = await client.get("/api/v1/stats/top-artist-by-genre", params={"year": 2023})
    assert top_artist.status_code == 200
    data = top_artist.json()
    assert any(item["genre"] == "Chill" for item in data)

    time_of_day = await client.get(
        "/api/v1/stats/time-of-day",
        params={"year": 2023, "period": "evening"},
    )
    assert time_of_day.status_code == 200
