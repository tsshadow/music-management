"""The subgenre graph, and the one rule that uses it.

Uptempo is a subgenre of hardcore, so an uptempo track carries both tags. Counted
naively every uptempo listen also feeds hardcore, the parent wins by construction,
and a profile of someone who never chose a plain hardcore track says they mostly
play hardcore. `deepest()` is what prevents that: a tag whose own child is present
contributes nothing.

`rules_subgenre_hierarchy` is a graph rather than a tree -- Upterror is Uptempo
Hardcore *plus* Terror -- so a genre can have several parents, and a hand-entered
row can close a cycle. Hence the depth guard: a wrong row must not hang a feed.
"""


def ancestors(genre: str, parents: dict[str, set[str]], max_depth: int = 8) -> set[str]:
    seen: set[str] = set()
    frontier = {genre}
    for _ in range(max_depth):
        frontier = {p for child in frontier for p in parents.get(child, set())} - seen
        if not frontier:
            break
        seen |= frontier
    return seen


def deepest(genres: set[str], parents: dict[str, set[str]]) -> set[str]:
    covered: set[str] = set()
    for genre in genres:
        covered |= ancestors(genre, parents)
    return {g for g in genres if g not in covered}


def nearest_ancestor(genre: str, parents: dict[str, set[str]], candidates: set[str], max_depth: int = 8) -> str | None:
    """The closest of `candidates` above `genre`, or None if none qualify.

    Upterror means a genre can have two parents at different distances from a
    given candidate, so "nearest" has to be resolved level by level rather than
    by picking anything out of the flat set `ancestors()` returns. Ties within a
    level break alphabetically so the result is deterministic.
    """
    seen: set[str] = set()
    frontier = {genre}
    for _ in range(max_depth):
        frontier = {p for child in frontier for p in parents.get(child, set())} - seen
        if not frontier:
            break
        seen |= frontier
        found = frontier & candidates
        if found:
            return min(found)
    return None
