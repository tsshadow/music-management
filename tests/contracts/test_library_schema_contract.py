"""Every library and analytics query, run against a real schema.

The defect this guards against: /api/library/advanced selected five columns that
did not exist, so every request returned 500 -- and no unit test caught it,
because mocked cursors accept any column name. These endpoints are therefore
exercised against a database built by services/common/db_init.py.

Assumes docker/compose.test.yml is already running; see scripts/test/contracts.sh.
"""
import os

import pytest
import requests
from test_lms_subsonic_contract import MUSIC_MANAGER_URL  # noqa: F401 (reused config)

MUMA_API_KEY = os.getenv("API_KEY", "test-api-key")
HEADERS = {"x-api-key": MUMA_API_KEY}

# MUSIC_MANAGER_URL already ends in /api, so these are relative to that.
# Each entry pairs an endpoint with a filter combination, so the filter branches
# are executed too and not just the unfiltered query.
ENDPOINTS = [
    "/library/advanced",
    "/library/advanced?q=test",
    "/library/advanced?q=150",
    "/library/advanced?genre=Hardcore&label=Footworxx",
    "/library/advanced?artist=Angerfist&bpm_min=140&bpm_max=200",
    "/library/advanced?year_min=2020&year_max=2026&analyzed=true",
    "/library/advanced?analyzed=false",
    "/library/advanced?page=2&limit=10",
    "/library/genres",
    "/analytics/summary",
    "/analytics/summary?genre=Hardcore&analyzed=true",
    "/analytics/genre-distribution",
    "/analytics/genre-distribution?artist=Angerfist",
    "/analytics/bpm-histogram",
    "/analytics/bpm-histogram?bucket=10&genre=Frenchcore",
    "/analytics/year-histogram",
    "/analytics/year-histogram?label=Footworxx",
    "/analytics/top-artists",
    "/analytics/top-artists?limit=5&bpm_min=190",
    "/analytics/top-labels",
    "/analytics/top-labels?year_min=2024",
    "/analytics/artist-search?q=an",
    "/stats/",
]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoint_runs_against_a_real_schema(path):
    response = requests.get(f"{MUSIC_MANAGER_URL}{path}", headers=HEADERS, timeout=30)
    assert response.status_code == 200, (
        f"{path} returned {response.status_code}: {response.text[:400]}"
    )


@pytest.mark.parametrize("path", ENDPOINTS)
def test_endpoint_requires_an_api_key(path):
    response = requests.get(f"{MUSIC_MANAGER_URL}{path}", timeout=30)
    assert response.status_code == 401, f"{path} returned {response.status_code}"


def test_empty_filter_result_is_not_an_error():
    """A filter matching nothing is a 200 with empty content, never a 4xx or 5xx."""
    response = requests.get(
        f"{MUSIC_MANAGER_URL}/library/advanced?genre=DefinitelyNotAGenre",
        headers=HEADERS, timeout=30)
    assert response.status_code == 200
    assert response.json()["tracks"] == []
    assert response.json()["total"] == 0

    response = requests.get(
        f"{MUSIC_MANAGER_URL}/analytics/genre-distribution?genre=DefinitelyNotAGenre",
        headers=HEADERS, timeout=30)
    assert response.status_code == 200
    assert response.json() == []


def test_advanced_response_carries_no_phantom_column():
    """The five columns that never existed must not reappear in the response."""
    response = requests.get(f"{MUSIC_MANAGER_URL}/library/advanced?limit=1",
                            headers=HEADERS, timeout=30)
    assert response.status_code == 200
    for track in response.json()["tracks"]:
        for column in ("musical_key", "energy", "danceability", "valence", "popularity"):
            assert column not in track, f"{column} does not exist in the database"


def test_summary_track_count_matches_the_advanced_total():
    """Both must interpret the same filter identically -- they share build_filter."""
    query = "genre=Hardcore&bpm_min=180"
    summary = requests.get(f"{MUSIC_MANAGER_URL}/analytics/summary?{query}",
                           headers=HEADERS, timeout=30).json()
    advanced = requests.get(f"{MUSIC_MANAGER_URL}/library/advanced?{query}&limit=1",
                            headers=HEADERS, timeout=30).json()
    assert summary["tracks"] == advanced["total"]


def test_bpm_histogram_rejects_an_out_of_range_bucket():
    response = requests.get(f"{MUSIC_MANAGER_URL}/analytics/bpm-histogram?bucket=99",
                            headers=HEADERS, timeout=30)
    assert response.status_code == 422


def test_artist_search_rejects_a_one_character_query():
    response = requests.get(f"{MUSIC_MANAGER_URL}/analytics/artist-search?q=a",
                            headers=HEADERS, timeout=30)
    assert response.status_code == 422
