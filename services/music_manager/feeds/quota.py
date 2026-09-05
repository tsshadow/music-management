"""Dividing a fixed number of places over the profile's shares.

Sorting by score and taking the top N is the obvious implementation and the wrong
one: it fills every place with the dominant genre, and a taste that is 10% hard
techno is never once visible. Largest remainder is what makes a small share show
up at all.
"""


def allocate(shares: dict[str, float], places: int) -> dict[str, int]:
    if not shares or places <= 0:
        return dict.fromkeys(shares, 0)
    exact = {name: share * places for name, share in shares.items()}
    allocation = {name: int(value) for name, value in exact.items()}
    remaining = places - sum(allocation.values())
    order = sorted(exact, key=lambda n: (-(exact[n] - allocation[n]), -shares[n], n))
    for name in order[:remaining]:
        allocation[name] += 1
    return allocation


def redistribute(allocation: dict[str, int], available: dict[str, int]) -> dict[str, int]:
    """Hand unfillable places to the shares that can still fill them.

    A share with nothing released this week must not leave a hole, and must not be
    filled with a track from another genre wearing its label.
    """
    result = {name: min(count, available.get(name, 0)) for name, count in allocation.items()}
    spare = sum(allocation.values()) - sum(result.values())
    while spare > 0:
        takers = [n for n in result if available.get(n, 0) > result[n]]
        if not takers:
            break
        takers.sort(key=lambda n: (-allocation.get(n, 0), n))
        for name in takers:
            if spare == 0:
                break
            result[name] += 1
            spare -= 1
    return result
