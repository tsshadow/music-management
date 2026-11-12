"""The shape every Wrapped card has, whatever it counts.

A card is `{id, status, reason, basis, data}`. Only `ok` is drawn; the others go to the
coverage card with their reason, so a reader learns why a card is missing instead of seeing
a zero (docs/designs/wrapped-page/technical.md, "Definitions shared by every card").
"""

from __future__ import annotations

from typing import Any

OK = 'ok'
EMPTY = 'empty'
BELOW_MINIMUM = 'below_minimum'
BLOCKED = 'blocked'

NO_ARRIVAL_DATE = 'no_arrival_date'
NO_REMIXER_CREDITS = 'no_remixer_credits'
SAME_AS_TOP_ARTIST = 'same_as_top_artist'


def basis(counted: int, of: int, unit: str = 'listens') -> dict[str, Any]:
    """What a card is based on: `counted` of `of` units."""
    return {'counted': int(counted), 'of': int(of), 'unit': unit}


def ok(card_id: str, data: dict[str, Any], card_basis: dict | None = None) -> dict[str, Any]:
    """A card with something to say."""
    return {'id': card_id, 'status': OK, 'reason': None, 'basis': card_basis, 'data': data}


def empty(card_id: str) -> dict[str, Any]:
    """A card with no rows at all."""
    return {'id': card_id, 'status': EMPTY, 'reason': None, 'basis': None, 'data': None}


def below(card_id: str, card_basis: dict | None = None, reason: str | None = None) -> dict[str, Any]:
    """A card whose rows do not reach its minimum."""
    return {'id': card_id, 'status': BELOW_MINIMUM, 'reason': reason, 'basis': card_basis, 'data': None}


def blocked(card_id: str, reason: str) -> dict[str, Any]:
    """A card whose source data does not exist."""
    return {'id': card_id, 'status': BLOCKED, 'reason': reason, 'basis': None, 'data': None}


def gated(card_id: str, count: int, minimum: int, build, card_basis: dict | None = None) -> dict[str, Any]:
    """`empty` without rows, `below_minimum` under the minimum, else `ok` with `build()`."""
    if count <= 0:
        return empty(card_id)
    if count < minimum:
        return below(card_id, card_basis)
    return ok(card_id, build(), card_basis)
