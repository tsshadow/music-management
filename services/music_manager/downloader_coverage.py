"""How complete each followed channel is, from the counts the deep sweep leaves behind.

The deep sweep stores one snapshot per account in `downloads_account_checks` (see
`services.downloader.account_snapshot.AccountSnapshot` and docs/designs/channel-coverage). This
turns those rows, the configured account list and the archive timestamps into the shape the
Volledigheid page renders. Pure over its inputs; the router does the queries.

The list is built from the configured accounts, not from the check rows: a check row
without a configured account belongs to a channel that was deleted, and a configured
account without a check row is exactly the "nog niet geteld" case the page exists to show.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from services.common.channels import channel_from_path, normalize_channel_name
from services.downloader.account_schedule import AccountCheck

SOURCES = ('soundcloud', 'youtube')

# What the downloaders can write off a track for, in the order the page lists them.
# Anything else the ledger holds is appended after these.
WRITE_OFF_REASONS = ('too_short', 'too_long', '403', 'failing', 'failed')


@dataclass(frozen=True)
class ConfiguredAccount:
    """One followed channel. `key` is what the schedule and the ledger file it under."""

    name: str
    key: str
    download_type: str | None = None
    # What the download archive files the account under, when that differs from `key`: the
    # SoundCloud archive keys every row on the numeric `soundcloud_id`, not on the slug.
    archive_key: str | None = None

    @property
    def archive(self) -> str:
        """The key to look the account up by in the archive."""
        return self.archive_key or self.key


def youtube_key(name: str, download_type: str | None) -> str:
    """The schedule key of a YouTube channel; mirrors `YoutubeAccount.schedule_key`."""
    return f'{name}#video' if download_type == 'video' else name


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def channel_entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """The `channel` object of a coverage row, from a channels row joined to its links."""
    return {
        'id': row['id'],
        'name': row['name'],
        'label': {'id': row['label_id'], 'name': row['label_name']} if row.get('label_id') else None,
        'artist': {'id': row['artist_id'], 'name': row['artist_name']} if row.get('artist_id') else None,
        'open_proposals': int(row.get('open_proposals') or 0),
    }


def channel_for(path: str | None, channels: Mapping[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The channel a file the account wrote lies under, or None.

    The configured account (a SoundCloud slug like `brainimpact`) and the channel (the folder
    the downloader wrote to, `BRAIN IMPACT`) cannot be derived from each other, so one path
    from the archive is the bridge. `channels` is keyed by `normalize_channel_name`.
    """
    found = channel_from_path(path or '')
    if not found:
        return None
    return channels.get(normalize_channel_name(found[1]))


def account_row(
    account: ConfiguredAccount,
    check: AccountCheck | None,
    last_download_at: datetime | None,
    channel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One table row. Every snapshot field is None until a deep pass has counted the account."""
    snapshot = check.snapshot if check else None
    return {
        'account': account.name,
        'key': account.key,
        'download_type': account.download_type,
        'listed': snapshot.listed if snapshot else None,
        'held': snapshot.held if snapshot else None,
        'excluded': snapshot.excluded if snapshot else None,
        'remaining': snapshot.remaining if snapshot else None,
        'coverage': snapshot.coverage if snapshot else None,
        'state': snapshot.state if snapshot else None,
        'snapshot_at': _iso(snapshot.taken_at) if snapshot else None,
        'last_checked_at': _iso(check.last_checked_at) if check else None,
        'last_deep_sweep_at': _iso(check.last_deep_sweep_at) if check else None,
        'last_download_at': _iso(last_download_at),
        'channel': channel,
    }


def totals(rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    """The tiles. complete + with_backlog + never_counted always equals configured."""
    counts = {
        'configured': 0,
        'counted': 0,
        'complete': 0,
        'with_backlog': 0,
        'never_counted': 0,
        'listed': 0,
        'held': 0,
        'excluded': 0,
        'remaining': 0,
    }
    for row in rows:
        counts['configured'] += 1
        if row['listed'] is None:
            counts['never_counted'] += 1
            continue
        counts['counted'] += 1
        for field in ('listed', 'held', 'excluded', 'remaining'):
            counts[field] += int(row[field] or 0)
        if int(row['remaining'] or 0) > 0:
            counts['with_backlog'] += 1
        else:
            counts['complete'] += 1
    return counts


def write_off_rows(counts: Mapping[str, int]) -> list[dict[str, Any]]:
    """Every reason with its count, known reasons first and in a fixed order, zeroes included."""
    rows = [{'reason': reason, 'count': int(counts.get(reason, 0))} for reason in WRITE_OFF_REASONS]
    rows.extend(
        {'reason': reason, 'count': int(count)}
        for reason, count in sorted(counts.items())
        if reason not in WRITE_OFF_REASONS
    )
    return rows


def build_coverage(
    source: str,
    configured: Iterable[ConfiguredAccount],
    checks: Mapping[str, AccountCheck],
    last_downloads: Mapping[str, datetime],
    downloads_7d: int,
    downloads_30d: int,
    write_offs: Mapping[str, int],
    rate_state: dict[str, Any] | None,
    now: datetime,
    channels: Mapping[str, dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    """The full response body for one source.

    `last_downloads` and `channels` are keyed by the account's archive key (see
    `ConfiguredAccount.archive`); `channels` maps it to the channel row it writes into.
    """
    channels = channels or {}
    rows = [
        account_row(
            account,
            checks.get(account.key),
            last_downloads.get(account.archive),
            channels.get(account.archive),
        )
        for account in configured
    ]
    rows.sort(key=lambda row: (-(row['remaining'] or 0), row['account'].lower()))
    summary = totals(rows)
    summary['downloads_7d'] = int(downloads_7d)
    summary['downloads_30d'] = int(downloads_30d)
    return {
        'source': source,
        'generated_at': now.isoformat(),
        'totals': {**summary, 'write_offs': write_off_rows(write_offs), 'rate_state': rate_state},
        'accounts': rows,
    }
