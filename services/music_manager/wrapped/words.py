"""The words the "word of the year" card skips: articles, joiners and release-name filler."""

import re

STOP_WORDS = frozenset(
    {
        'the',
        'and',
        'feat',
        'ft',
        'vs',
        'with',
        'you',
        'for',
        'het',
        'een',
        'van',
        'original',
        'mix',
        'version',
        'edit',
        'remix',
        'extended',
        'radio',
        'official',
        'video',
        'audio',
        'live',
        'set',
        'from',
        'this',
        'that',
        'are',
        'not',
        'all',
        'your',
        'our',
        'der',
        'die',
        'das',
        'les',
    }
)

_SPLIT = re.compile(r'[^\w]+|[\d_]+', re.UNICODE)


def title_words(title: str | None) -> list[str]:
    """The countable words of a title: lower case, three letters or more, no stop words."""
    if not title:
        return []
    words = []
    for word in _SPLIT.split(title.lower()):
        if len(word) >= 3 and word not in STOP_WORDS:
            words.append(word)
    return words
