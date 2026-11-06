"""The subgenre graph, and the one rule that uses it.

Uptempo is a subgenre of hardcore, so an uptempo track carries both tags. Counted
naively every uptempo listen also feeds hardcore, the parent wins by construction,
and a profile of someone who never chose a plain hardcore track says they mostly
play hardcore. `deepest()` is what prevents that: a tag whose own child is present
contributes nothing.

`rules_subgenre_hierarchy` is a graph rather than a tree -- Upterror is Uptempo
Hardcore *plus* Terror -- so a genre can have several parents. The genre edit page
refuses a parent that would close a cycle (`PUT /api/curation/genres/{name}/parents`
answers 409), but a row entered before that check existed, or by hand in SQL, can
still close one. So every walker here stops at a node it has already seen, never
counts a genre as its own ancestor, and the loaders call `warn_cycles()` once per
load so the bad rows show up in the event log instead of silently skewing a feed.
"""

import logging

logger = logging.getLogger('music-manager.feeds.hierarchy')

#: How far any walker climbs. Real chains are three or four levels deep; the bound
#: only exists so that no data, however wrong, can make a walk unbounded.
MAX_DEPTH = 64


def ancestors(genre: str, parents: dict[str, set[str]], max_depth: int = MAX_DEPTH) -> set[str]:
    """Every genre above `genre` in the subgenre graph, up to `max_depth` levels.

    Never contains `genre` itself, even when a cycle leads back to it: a genre that
    is its own ancestor is a data error, not information about the genre.
    """
    seen: set[str] = {genre}
    frontier = {genre}
    for _ in range(max_depth):
        frontier = {p for child in frontier for p in parents.get(child, set())} - seen
        if not frontier:
            break
        seen |= frontier
    return seen - {genre}


def deepest(genres: set[str], parents: dict[str, set[str]]) -> set[str]:
    """The genres in `genres` that are not an ancestor of another one in the set.

    A cycle (A under B and B under A) makes each an ancestor of the other; dropping
    both would lose the tag entirely. Genres that sit in a cycle together are treated
    as one, and the alphabetically first of them is kept, so the choice is the same on
    every call.
    """
    above = {genre: ancestors(genre, parents) for genre in genres}
    kept: set[str] = set()
    for genre in genres:
        below = [other for other in genres if other != genre and genre in above[other]]
        if any(other not in above[genre] for other in below):
            continue  # a genre strictly below this one is present
        if any(other < genre for other in below):
            continue  # a cycle mate that sorts first speaks for the cycle
        kept.add(genre)
    return kept


def nearest_ancestor(
    genre: str, parents: dict[str, set[str]], candidates: set[str], max_depth: int = MAX_DEPTH
) -> str | None:
    """The closest of `candidates` above `genre`, or None if none qualify.

    Upterror means a genre can have two parents at different distances from a
    given candidate, so "nearest" has to be resolved level by level rather than
    by picking anything out of the flat set `ancestors()` returns. Ties within a
    level break alphabetically so the result is deterministic. A cycle back to
    `genre` itself never makes it its own nearest ancestor.
    """
    seen: set[str] = {genre}
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


def find_cycles(parents: dict[str, set[str]]) -> list[list[str]]:
    """Every cycle in the graph, as sorted lists of the genres that form it.

    A cycle here is a strongly connected component of more than one genre, or a genre
    listed as its own parent. Iterative Tarjan, so a long chain cannot hit Python's
    recursion limit. Sorted, so the report (and the log line) is stable.
    """
    nodes = set(parents) | {p for ps in parents.values() for p in ps}
    index: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    cycles: list[list[str]] = []
    counter = 0

    for root in sorted(nodes):
        if root in index:
            continue
        work: list[tuple[str, list[str]]] = [(root, sorted(parents.get(root, set())))]
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        while work:
            node, pending = work[-1]
            if pending:
                nxt = pending.pop()
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, sorted(parents.get(nxt, set()))))
                elif nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
                continue
            work.pop()
            if work:
                low[work[-1][0]] = min(low[work[-1][0]], low[node])
            if low[node] == index[node]:
                component = []
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    component.append(member)
                    if member == node:
                        break
                if len(component) > 1 or node in parents.get(node, set()):
                    cycles.append(sorted(component))
    return sorted(cycles)


def warn_cycles(parents: dict[str, set[str]], where: str) -> list[list[str]]:
    """Log each cycle in a freshly loaded hierarchy once, at WARNING, and return them.

    Called by the code that loads the table, never by the walkers: a feed build calls
    `deepest()` thousands of times, and one line per load is the signal, not noise.
    """
    cycles = find_cycles(parents)
    if cycles:
        logger.warning(
            'Genre hierarchy has %d cycle(s) (seen by %s): %s -- fix the parents in Management',
            len(cycles),
            where,
            '; '.join(' <-> '.join(cycle) for cycle in cycles),
        )
    return cycles
