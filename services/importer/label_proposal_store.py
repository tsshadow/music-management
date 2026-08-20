import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.importer.label_resolver import LabelProposal

# A row a human already decided must survive the next scan untouched. The importer
# meets the same folder on every cycle until it is moved, so without the status guards
# a rejected release would be handed straight back to the review list, and a confirmed
# one would lose the label that was chosen for it.
RECORD_QUERY = """
    INSERT INTO rules_label_proposals (folder, catid, proposed_label, source, confidence)
    VALUES (%s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        catid = IF(status = 'new', VALUES(catid), catid),
        proposed_label = IF(status = 'new', VALUES(proposed_label), proposed_label),
        source = IF(status = 'new', VALUES(source), source),
        confidence = IF(status = 'new', VALUES(confidence), confidence)
"""


class LabelProposalStore:
    """Writes the importer's give-up decisions somewhere a human can review them."""

    def __init__(self):
        self.db_connector = DatabaseConnector()

    def record(self, folder: str, proposal: LabelProposal) -> None:
        """
        Record one unplaceable release.

        Failures are logged and swallowed on purpose: a proposal is a convenience laid
        on top of the import, and a database that is briefly unreachable must not turn
        a working import run into a failing one.
        """
        try:
            with self.db_connector.connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(RECORD_QUERY, (folder, proposal.catid, proposal.label, proposal.source, proposal.confidence))
                connection.commit()
        except Exception as e:  # noqa: BLE001 - a proposal is never a reason to fail the import
            logging.error(f'Could not record a label proposal for {folder}: {e}')
