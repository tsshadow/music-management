"""The `params` JSON of a dynamic playlist: what a client may store, and how the track query reads it.

Two spellings share the column (services/frontend/src/lib/presets.js says why): the phone's
`TileInfo` (`genre`, `sortMethod`, `ratingMin`, `size`, ...) and the management tab's (`genres`,
`rating_range`, `sort_method`, `song_type`, `rules`, `size`). Only the keys the track query reads
are checked; any other key is the client's own business and passes through untouched.
"""

import json
from typing import Any

#: The track query's LIMIT when a playlist names no size; the phone and the web default to it too.
DEFAULT_SIZE = 500
#: The most tracks one playlist may ask for. The UIs never offer more than the default; this
#: keeps a typo or a hand-made request from turning into an unbounded scan.
MAX_SIZE = 2000

_DEFAULT_RATING_RANGE = [0, 100]


def validate_params(text: str) -> str:
    """Return `text` unchanged when it is a playlist definition the track query can run.

    Raises ValueError, which the request model turns into a 422, when it is not a JSON object,
    when `size` is not a whole number from 1 to MAX_SIZE, or when `genres`, `rating_range` or
    `rules` have the wrong shape. A null or empty `size` means "the default", as the web's empty
    number field sends it.
    """
    try:
        params = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f'params is not valid JSON: {exc.msg}') from exc
    if not isinstance(params, dict):
        raise ValueError('params must be a JSON object')
    if params.get('size') not in (None, ''):
        size = _whole_number(params['size'])
        if size is None:
            raise ValueError('size must be a whole number')
        if not 1 <= size <= MAX_SIZE:
            raise ValueError(f'size must be from 1 to {MAX_SIZE}')
    genres = params.get('genres')
    if genres is not None and not (isinstance(genres, list) and all(isinstance(g, str) for g in genres)):
        raise ValueError('genres must be a list of names')
    rating_range = params.get('rating_range')
    if rating_range is not None and _rating_range(rating_range) is None:
        raise ValueError('rating_range must be two numbers')
    rules = params.get('rules')
    if rules is not None and not (isinstance(rules, list) and all(isinstance(r, dict) for r in rules)):
        raise ValueError('rules must be a list of objects')
    return text


def read_params(text: str | None) -> dict[str, Any]:
    """What the track query needs from a stored definition, with a default for every bad value.

    Rows written before validation existed, and rows the LMS sync copies in as they are, may hold
    anything; the query must not fail on them. A value that is not JSON is read as the old
    `key=value&key=value` form.
    """
    params: Any
    try:
        params = json.loads(text or '')
    except json.JSONDecodeError:
        params = dict(part.split('=', 1) for part in (text or '').split('&') if '=' in part)
    if not isinstance(params, dict):
        params = {}
    size = _whole_number(params.get('size'))
    genres = params.get('genres')
    rules = params.get('rules')
    return {
        'genres': [g for g in genres if isinstance(g, str)] if isinstance(genres, list) else [],
        'rating_range': _rating_range(params.get('rating_range')) or list(_DEFAULT_RATING_RANGE),
        'size': min(max(size, 1), MAX_SIZE) if size is not None else DEFAULT_SIZE,
        'sort_method': params.get('sort_method', 'newest'),
        'song_type': params.get('song_type', 'both'),
        'rules': [r for r in rules if isinstance(r, dict)] if isinstance(rules, list) else [],
    }


def _whole_number(value: Any) -> int | None:
    """`value` as an int when it is a whole number or a string of one, else None (bool is not one)."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().lstrip('-').isdigit():
        return int(value)
    return None


def _rating_range(value: Any) -> list[float] | None:
    """`value` when it is a list of two numbers, else None."""
    if not isinstance(value, list) or len(value) != 2:
        return None
    if not all(isinstance(v, int | float) and not isinstance(v, bool) for v in value):
        return None
    return list(value)
