"""Statement validation for ``prod_query``.

This is the *second* line of defence and is written as such. The real boundary is
the database account (``SELECT, SHOW VIEW`` on one database, no ``FILE``): a
``DELETE`` that gets past everything here still dies on a privilege. What this
module buys is a clear refusal instead of a driver error, and a guarantee that a
looping agent cannot hand the production database something expensive.

Two details are worth stating because the obvious implementations are wrong:

- **Comments are stripped before the keyword is inspected**, so ``/* x */ DELETE``
  cannot present itself as a comment. The stripped text is then what actually
  executes -- not the original -- because MariaDB *executes* the contents of a
  ``/*! ... */`` executable comment, which a validator working on the original
  string would have skipped right over.
- **String bodies are masked before anything is matched by regex**, so a literal
  containing ``;`` or the word ``OUTFILE`` is not mistaken for syntax.
"""

from __future__ import annotations

import re

ALLOWED_KEYWORDS = frozenset({'SELECT', 'WITH', 'SHOW', 'DESCRIBE', 'DESC', 'EXPLAIN'})

# INTO OUTFILE/DUMPFILE writes a file. The account holds no FILE privilege, so
# this cannot succeed anyway; it is refused here so the answer is "not allowed"
# rather than a privilege error that reads like a misconfiguration.
_INTO_FILE = re.compile(r'\bINTO\s+(?:OUTFILE|DUMPFILE)\b', re.IGNORECASE)
_LEADING_KEYWORD = re.compile(r'^[\s(]*([A-Za-z_]+)')

_QUOTES = ("'", '"', '`')


class QueryRejected(ValueError):
    """The statement is not something this server will run."""


def _scan(sql: str) -> tuple[str, str]:
    """Return ``(stripped, masked)``.

    ``stripped`` is the statement with comments removed -- the text that will be
    executed. ``masked`` is that same text with the *contents* of every string and
    identifier literal replaced by ``x``, so structural matching cannot be fooled
    by data. Both have the same meaning; only ``masked`` is safe to regex.
    """
    stripped: list[str] = []
    masked: list[str] = []
    index = 0
    length = len(sql)

    while index < length:
        char = sql[index]

        if char in _QUOTES:
            quote = char
            stripped.append(char)
            masked.append(char)
            index += 1
            while index < length:
                current = sql[index]
                # Backslash escapes apply inside '' and "" but not inside backticks.
                if current == '\\' and quote != '`' and index + 1 < length:
                    stripped.append(sql[index : index + 2])
                    masked.append('xx')
                    index += 2
                    continue
                if current == quote:
                    # A doubled quote is an escaped quote, not the end of the literal.
                    if index + 1 < length and sql[index + 1] == quote:
                        stripped.append(quote * 2)
                        masked.append('xx')
                        index += 2
                        continue
                    stripped.append(current)
                    masked.append(current)
                    index += 1
                    break
                stripped.append(current)
                masked.append('x')
                index += 1
            continue

        # `--` only starts a comment when followed by whitespace or end of input;
        # `a--b` is two minus signs.
        if sql.startswith('--', index) and (index + 2 >= length or sql[index + 2] in ' \t\r\n'):
            while index < length and sql[index] != '\n':
                index += 1
            stripped.append(' ')
            masked.append(' ')
            continue

        if char == '#':
            while index < length and sql[index] != '\n':
                index += 1
            stripped.append(' ')
            masked.append(' ')
            continue

        if sql.startswith('/*', index):
            end = sql.find('*/', index + 2)
            index = length if end == -1 else end + 2
            stripped.append(' ')
            masked.append(' ')
            continue

        stripped.append(char)
        masked.append(char)
        index += 1

    return ''.join(stripped), ''.join(masked)


def check(sql: str) -> str:
    """Validate ``sql`` and return the exact text to execute.

    Raises ``QueryRejected`` with a reason a human (or an agent) can act on.
    """
    if not sql or not sql.strip():
        raise QueryRejected('lege query')

    stripped, masked = _scan(sql)

    if not stripped.strip():
        raise QueryRejected('de query bestaat alleen uit commentaar')

    head, _, tail = masked.partition(';')
    if tail.strip():
        raise QueryRejected(
            'meerdere statements in één query. Stuur er één per aanroep; '
            'alleen een afsluitende puntkomma is toegestaan.'
        )
    if not head.strip():
        raise QueryRejected('lege query')

    match = _LEADING_KEYWORD.match(masked)
    if not match:
        raise QueryRejected('geen herkenbaar sleutelwoord aan het begin van de query')

    keyword = match.group(1).upper()
    if keyword not in ALLOWED_KEYWORDS:
        allowed = ', '.join(sorted(ALLOWED_KEYWORDS))
        raise QueryRejected(f'{keyword} is niet toegestaan. Alleen: {allowed}.')

    if _INTO_FILE.search(masked):
        raise QueryRejected('INTO OUTFILE/DUMPFILE schrijft naar schijf en is niet toegestaan')

    # The trailing semicolon goes: the driver runs one statement and a stray
    # separator is only a way to trip it.
    return stripped.strip().rstrip(';').strip()
