import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector

#: How many hops a redirect chain is followed before it counts as broken. Far more
#: than any real chain (one or two hops); it only has to stop a malformed table.
MAX_CHAIN_DEPTH = 32


def resolve_redirect_chains(
    corrections: dict[str, str],
) -> tuple[dict[str, str], dict[str, list[str]], list[list[str]]]:
    """Follow every correction to the end of its chain, refusing to go round in circles.

    `corrections` maps a name to the spelling it is rewritten to. When that spelling is
    itself rewritten (`Y -> X`, `X -> Z`), a one-hop lookup writes `X` -- a name that
    was rejected -- and only a second tagger pass gets to `Z`. Names are compared
    case-insensitively, the way `FilterTableHelper` matches, and a correction that only
    changes the casing of its own key (`angerfist -> Angerfist`) ends a chain rather
    than looping.

    Returns three things:

    * `resolved` -- every key mapped to its final target. A key whose chain loops, or
      runs past `MAX_CHAIN_DEPTH`, keeps its own one-hop correction: there is no right
      answer to pick, and the one-hop answer is what the tagger always did.
    * `paths` -- every key whose chain is longer than one hop, as `[key, hop, ..., end]`.
    * `cycles` -- each loop once, as its member names starting at the alphabetically
      first one (case-insensitive), so a report is the same on every call.

    @param corrections: `{name: corrected_name}`; names without a correction must not be in it.
    """
    by_lower = {name.lower(): (name, target) for name, target in corrections.items()}
    resolved: dict[str, str] = {}
    paths: dict[str, list[str]] = {}
    cycles: dict[tuple[str, ...], list[str]] = {}
    for name, first_target in corrections.items():
        path = [name]
        target = first_target
        looping = False
        while True:
            target_key = target.lower()
            if target_key == path[-1].lower():
                break  # a casing fix of the name itself: the end of the chain
            entry = by_lower.get(target_key)
            if entry is None:
                break
            lowered = [hop.lower() for hop in path]
            if target_key in lowered:
                looping = True
                members = path[lowered.index(target_key) :]
                start = min(range(len(members)), key=lambda i: members[i].lower())
                ordered = members[start:] + members[:start]
                cycles.setdefault(tuple(sorted(m.lower() for m in ordered)), ordered)
                break
            if len(path) > MAX_CHAIN_DEPTH:
                looping = True
                break
            path.append(entry[0])
            target = entry[1]
        if looping:
            resolved[name] = first_target
            continue
        resolved[name] = target
        if len(path) > 1:
            paths[name] = path + [target]
    return resolved, paths, sorted(cycles.values(), key=lambda members: [m.lower() for m in members])


class FilterTableHelper:
    """Looks a value up in a rules table, case-insensitively.

    The values arrive from outside (SoundCloud genres, uploader tags), so the
    casing is whatever someone typed. Matching on the stored spelling alone
    would reject `Uptempo` while accepting `uptempo`, so every lookup here
    normalises to lowercase and answers with the *stored* spelling -- or with
    the correction, when the table defines one. That keeps one genre from
    entering the library under three different casings.

    With `follow_chains`, a correction whose target is itself corrected is followed
    to the end (`resolve_redirect_chains`), so the answer is never a name the table
    rewrites again. Only the preloaded path does this; the uncached one answers one
    hop, as it always did.
    """

    def __init__(
        self,
        table_name: str,
        column_name: str,
        corrected_column_name: str,
        preload: bool = True,
        follow_chains: bool = False,
    ):
        self.table_name = table_name
        self.column_name = column_name
        self.corrected_column_name = corrected_column_name
        self.follow_chains = follow_chains
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload
        self._exists_cache: set[str] = set()
        self._canonical_map: dict[str, str] = {}
        self._corrected_map: dict[str, str] = {}
        if preload:
            self._preload()

    def _preload(self):
        query = f'SELECT {self.column_name}, {self.corrected_column_name} FROM {self.table_name}'
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f'[{self.table_name}] Error preloading table: {e}')
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for row in cursor.fetchall():
                    name = str(row[0]).strip()
                    corrected = str(row[1]).strip() if row[1] else ''
                    self._exists_cache.add(name)
                    self._canonical_map[name.lower()] = name
                    if corrected:
                        self._corrected_map[name.lower()] = corrected
            if self.follow_chains:
                self._corrected_map, _paths, cycles = resolve_redirect_chains(self._corrected_map)
                if cycles:
                    # INFO, not WARNING: every process that preloads this table would push
                    # the same line. The consistency endpoint is where a cycle is found.
                    logging.info(f'[{self.table_name}] Redirect cycles left at one hop: {cycles}')
        except Exception as e:
            logging.error(f'[{self.table_name}] Error preloading table: {e}')
        finally:
            connection.close()

    def reload(self):
        """Re-read the table. See LookupTableHelper.reload for why."""
        if not self.cache_enabled:
            return
        self._exists_cache = set()
        self._canonical_map = {}
        self._corrected_map = {}
        self._preload()

    def exists(self, key: str) -> bool:
        """Whether `key` is in the table, compared case-insensitively."""
        key = key.strip()
        if self.cache_enabled:
            return key.lower() in self._canonical_map
        query = f'SELECT 1 FROM {self.table_name} WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"[{self.table_name}] Error checking existence for key '{key}': {e}")
            return False
        finally:
            connection.close()

    def get_corrected(self, key: str) -> str:
        """The corrected value stored for `key`, or '' when there is none."""
        key = key.strip()
        if self.cache_enabled:
            return str(self._corrected_map.get(key.lower(), ''))
        query = f'SELECT {self.corrected_column_name} FROM {self.table_name} WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result[0].strip() if result and result[0] else ''
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected value for '{key}': {e}")
            return ''
        finally:
            connection.close()

    def get_corrected_or_exists(self, key: str) -> str | bool:
        """The correction for `key`, else its stored spelling, else False."""
        key = key.strip()
        normalized = key.lower()
        if self.cache_enabled:
            if normalized in self._corrected_map:
                return str(self._corrected_map[normalized])
            if normalized in self._canonical_map:
                return str(self._canonical_map[normalized])
            return False
        query = (
            f'SELECT {self.column_name}, {self.corrected_column_name} FROM {self.table_name} '
            f'WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1'
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                if result:
                    stored, corrected = result[0], result[1]
                    return corrected.strip() if corrected else str(stored).strip()
                return False
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected/existing for '{key}': {e}")
            return False
        finally:
            connection.close()

    def add(self, key: str, corrected: str | None = None) -> bool:
        """Insert `key`, with its correction when one is given; True when the write succeeded."""
        key = key.strip()
        values = [key]
        columns = [self.column_name]
        if self.corrected_column_name and corrected is not None:
            corrected = corrected.strip()
            columns.append(self.corrected_column_name)
            values.append(corrected)
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)
        query = f'INSERT INTO {self.table_name} ({column_names}) VALUES ({placeholders})'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"[{self.table_name}] Error inserting key '{key}': {e}")
            connection.rollback()
            return False
        finally:
            connection.close()

    def get_all(self) -> list[str]:
        """
        Returns all raw (unprocessed) values from the main column.

        Returns:
            list[str]: Sorted list of distinct values.
        """
        query = f'SELECT DISTINCT {self.column_name} FROM {self.table_name}'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                return sorted([str(row[0]).strip() for row in result if row and row[0]])
        except Exception as e:
            logging.error(f'[{self.table_name}] Error fetching all values: {e}')
            return []
        finally:
            connection.close()
