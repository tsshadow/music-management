from __future__ import annotations
import pytest
from backend.tests.fixtures import seed_dataset

@pytest.mark.asyncio
async def test_stats_endpoints(client):
    await seed_dataset(client)
    library_artists = await client.get('/api/v1/stats/library_artists', params={'period': 'year', 'value': '2023'})
    assert library_artists.status_code == 200
    artist_payload = library_artists.json()
    artist_names = [row['artist'] for row in artist_payload['items']]
    assert 'Artist A' in artist_names
    artists_all_time = await client.get('/api/v1/stats/library_artists', params={'period': 'all'})
    assert artists_all_time.status_code == 200
    assert any((row['artist'] == 'Artist A' for row in artists_all_time.json()['items']))
    albums = await client.get('/api/v1/stats/albums', params={'period': 'year', 'value': '2023'})
    assert albums.status_code == 200
    album_titles = [row['album'] for row in albums.json()['items']]
    assert 'Sunrise' in album_titles
    library_tracks = await client.get('/api/v1/stats/library_tracks', params={'period': 'all'})
    assert library_tracks.status_code == 200
    track_payload = library_tracks.json()
    track_titles = [row['track'] for row in track_payload['items']]
    assert 'Afternoon Groove' in track_titles
    groove_row = next((row for row in track_payload['items'] if row['track'] == 'Afternoon Groove'))
    assert groove_row['artist'] == 'Artist A'
    assert groove_row['album'] == 'Groove'
    assert groove_row['count'] == 1
    rules_genres = await client.get('/api/v1/stats/rules_genres', params={'period': 'year', 'value': '2023'})
    assert rules_genres.status_code == 200
    genre_names = [row['genre'] for row in rules_genres.json()['items']]
    assert 'Chill' in genre_names
    month_genres = await client.get('/api/v1/stats/rules_genres', params={'period': 'month', 'value': '2023-11'})
    assert month_genres.status_code == 200
    month_payload = month_genres.json()
    assert month_payload['items'] and month_payload['items'][0]['genre'] == 'Chill'
    day_artists = await client.get('/api/v1/stats/library_artists', params={'period': 'day', 'value': '2023-05-20'})
    assert day_artists.status_code == 200
    assert any((row['artist'] == 'Artist A' for row in day_artists.json()['items']))
    top_artist = await client.get('/api/v1/stats/top-artist-by-genre', params={'year': 2023})
    assert top_artist.status_code == 200
    data = top_artist.json()
    assert any((item['genre'] == 'Chill' for item in data))
    time_of_day = await client.get('/api/v1/stats/time-of-day', params={'year': 2023, 'period': 'evening'})
    assert time_of_day.status_code == 200
