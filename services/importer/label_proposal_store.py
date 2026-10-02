import hashlib
import logging
from dataclasses import dataclass, field

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.importer.label_resolver import LabelProposal

# A row a human already decided must survive the next scan untouched. The importer
# meets the same folder on every cycle until it is moved, so without the status guards
# a rejected release would be handed straight back to the review list, and a confirmed
# one would lose the label that was chosen for it.
#
# `resolved_fingerprint` is the exception: it is the importer's own bookkeeping, not
# part of the proposal, and records what the folder looked like when its tags were last
# read -- whatever the status. See `fingerprint`.
RECORD_QUERY = """
    INSERT INTO rules_label_proposals
        (folder, catid, proposed_label, source, confidence, resolved_fingerprint, alternative_label, label_choice_key)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        catid = IF(status = 'new', VALUES(catid), catid),
        proposed_label = IF(status = 'new', VALUES(proposed_label), proposed_label),
        source = IF(status = 'new', VALUES(source), source),
        confidence = IF(status = 'new', VALUES(confidence), confidence),
        alternative_label = IF(status = 'new', VALUES(alternative_label), alternative_label),
        label_choice_key = IF(status = 'new', VALUES(label_choice_key), label_choice_key),
        resolved_fingerprint = VALUES(resolved_fingerprint)
"""

# The catalogue-number rules, reduced to one comparable value. The table has no
# timestamp to take a MAX over, and an edited label keeps the row count, so the value
# folds every (catid, label) pair in. A few thousand short rows: one cheap scan a cycle.
RULES_VERSION_QUERY = """
    SELECT COUNT(*), COALESCE(SUM(CRC32(CONCAT(catid, CHAR(9), label))), 0)
    FROM rules_catid_label
"""

KNOWN_QUERY = 'SELECT folder, status, decided_at, resolved_fingerprint, created_at FROM rules_label_proposals'


@dataclass(frozen=True)
class KnownProposal:
    """The part of a proposal row that decides whether its folder must be read again."""

    status: str
    decided_at: object
    fingerprint: str | None
    #: When the importer first gave up on the folder: the day the release had arrived by.
    created_at: object = None


#: What `record` leaves behind for a folder that had no row yet.
NEW_ROW = KnownProposal('new', None, None)


@dataclass(frozen=True)
class ProposalSnapshot:
    """Everything the mover compares against in one cycle, read with two queries up front."""

    rules_version: str
    rows: dict[str, KnownProposal] = field(default_factory=dict)


def fingerprint(signature: str, rules_version: str, row: KnownProposal) -> str:
    """The key a folder's last resolution is filed under.

    Changes when the folder changes on disk (`signature`), when any catalogue-number rule
    changes (`rules_version`), or when a human decides the folder's own proposal (`row`'s
    status and decision time). Any of those means the folder is read again, once.
    """
    parts = (signature, rules_version, row.status, str(row.decided_at))
    return hashlib.sha256('\x1f'.join(parts).encode('utf-8')).hexdigest()


class LabelProposalStore:
    """Writes the importer's give-up decisions somewhere a human can review them."""

    def __init__(self):
        self.db_connector = DatabaseConnector()

    def snapshot(self) -> ProposalSnapshot | None:
        """
        The rules version and every proposal row, for one import cycle.

        None when the database cannot be read: the mover then has nothing durable to
        compare against and falls back to what it remembers from earlier in the process.
        """
        try:
            with self.db_connector.connection() as connection, connection.cursor() as cursor:
                cursor.execute(RULES_VERSION_QUERY)
                count, checksum = cursor.fetchone()
                cursor.execute(KNOWN_QUERY)
                rows = {
                    str(folder): KnownProposal(str(status), decided_at, fp, created_at)
                    for folder, status, decided_at, fp, created_at in cursor.fetchall()
                }
            return ProposalSnapshot(f'{count}:{checksum}', rows)
        except Exception as e:  # noqa: BLE001 - a missing cache is never a reason to fail the import
            logging.warning(f'Could not read the label proposals to skip unchanged folders: {e}')
            return None

    def record(self, folder: str, proposal: LabelProposal, resolved_fingerprint: str | None = None) -> None:
        """
        Record one unplaceable release, and the fingerprint it was resolved under.

        Failures are logged and swallowed on purpose: a proposal is a convenience laid
        on top of the import, and a database that is briefly unreachable must not turn
        a working import run into a failing one.
        """
        try:
            with self.db_connector.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        RECORD_QUERY,
                        (
                            folder,
                            proposal.catid,
                            proposal.label,
                            proposal.source,
                            proposal.confidence,
                            resolved_fingerprint,
                            proposal.alternative,
                            proposal.choice_key,
                        ),
                    )
                connection.commit()
        except Exception as e:  # noqa: BLE001 - a proposal is never a reason to fail the import
            logging.error(f'Could not record a label proposal for {folder}: {e}')
