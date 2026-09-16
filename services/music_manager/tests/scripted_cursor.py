"""A cursor stand-in for router tests that walk a sequence of statements.

Not a test module itself: the name deliberately falls outside pytest's
``test_*`` discovery pattern.
"""


def normalize(sql):
    return ' '.join(sql.split())


class ScriptedCursor:
    """A cursor that answers fetchone/fetchall from a rule table.

    Each rule is ``(sql_fragment, params_or_None, result)``. The first rule whose
    fragment appears in the executed statement -- and whose params match, when it
    pins them down -- supplies the result: a list is served by fetchall, a mapping
    by fetchone. Anything unmatched reads as an empty table, which is what a
    router should treat as "there is no such row".
    """

    def __init__(self, rules=(), lastrowid=None, rowcount=1):
        self.rules = list(rules)
        self.lastrowid = lastrowid
        # What a statement reports having affected. One by default, because that is
        # what a write against a matching row does; set it to 0 to play a write whose
        # WHERE clause found nothing.
        self.rowcount = rowcount
        self.executed = []
        self._result = None

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def execute(self, sql, params=None):
        statement = normalize(sql)
        self.executed.append((statement, params))
        self._result = None
        for fragment, expected_params, result in self.rules:
            if fragment in statement and (expected_params is None or expected_params == params):
                self._result = result
                break

    def executemany(self, sql, seq_of_params):
        """A batch write: recorded as one statement carrying the whole parameter list."""
        statement = normalize(sql)
        self.executed.append((statement, list(seq_of_params)))
        self._result = None

    def fetchone(self):
        if isinstance(self._result, list):
            return self._result[0] if self._result else None
        return self._result

    def fetchall(self):
        if isinstance(self._result, list):
            return self._result
        return [self._result] if self._result else []

    def statements_matching(self, fragment):
        return [(sql, params) for sql, params in self.executed if fragment in sql]
