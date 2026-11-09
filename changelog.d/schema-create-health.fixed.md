- A music-manager that started without being able to create its tables said nothing: the create pass stopped at the first failing statement, logged a `WARNING` and went on, and `/health` stayed `ok`. The failure is now an `ERROR` event, and `/health` has a `schema` field that is `failed` until a restart gets through the pass, which makes the endpoint answer 503. A deploy was never affected, because the schema reconcile step stops it first; a fresh or local stack was.

<!-- release notes -->

- A server that could not create its database tables at start-up now reports an error and shows as unhealthy, instead of starting as if all was well.
