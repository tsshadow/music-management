"""MuMa Wrapped: a year (or a range) of listening, per account and for the whole server.

docs/designs/wrapped-page/ holds the cards and their definitions. `data.py` reads a period's
listens and what the cards need about their tracks in a few bulk queries; `listening_cards.py`
and `collection_cards.py` turn that into cards; `payload.py` puts a tab together; and
`snapshots.py` keeps the result, so a second visit is one key lookup.
"""
