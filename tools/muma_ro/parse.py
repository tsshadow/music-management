"""Turn the command string into tokens, or refuse it.

This is steps 1 to 3 of the parser in the technical design: the length and control-character
check, and a character scan that tracks single quotes. Which token may be quoted is decided
later, per argument kind, in ``verbs.py``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_COMMAND_BYTES = 4096

# Outside single quotes. Everything a shell would treat specially is absent: ; | & $ ` < > ( ) { }
# [ ] * ? ! # ~ " \ and every whitespace other than the space.
_PLAIN = re.compile(r'[A-Za-z0-9 _./:=@+,%-]')


class Refused(ValueError):
    """The command is not allowed. The message is the reason, safe to show and to log."""


@dataclass(frozen=True)
class Token:
    """One word of the command. ``quoted`` is true when any part of it was in single quotes."""

    text: str
    quoted: bool = False


def check_characters(command: str) -> None:
    """Steps 1 to 3: refuse an empty, oversized or unsafe command string."""
    if not command or not command.strip():
        raise Refused('no command')
    if len(command.encode('utf-8')) > MAX_COMMAND_BYTES:
        raise Refused(f'command longer than {MAX_COMMAND_BYTES} bytes')
    for bad, name in (('\x00', 'a NUL'), ('\r', 'a carriage return'), ('\n', 'a newline')):
        if bad in command:
            raise Refused(f'{name} in the command')
    if '"' in command:
        raise Refused('a double quote; quote a path with single quotes')
    if '\\' in command:
        raise Refused('a backslash')
    inside = False
    for char in command:
        if char == "'":
            inside = not inside
        elif inside:
            if not char.isprintable():
                raise Refused('a control character inside quotes')
        elif not _PLAIN.fullmatch(char):
            raise Refused(f'the character {char!r} outside single quotes')
    if inside:
        raise Refused('an unterminated single quote')


def tokenize(command: str) -> list[Token]:
    """Check the characters, then split on spaces outside single quotes."""
    check_characters(command)
    tokens: list[Token] = []
    current: list[str] = []
    quoted = False
    started = False
    inside = False
    for char in command:
        if char == "'":
            inside = not inside
            quoted = True
            started = True
        elif char == ' ' and not inside:
            if started:
                tokens.append(Token(''.join(current), quoted))
            current, quoted, started = [], False, False
        else:
            current.append(char)
            started = True
    if started:
        tokens.append(Token(''.join(current), quoted))
    if not tokens:
        raise Refused('no command')
    return tokens
