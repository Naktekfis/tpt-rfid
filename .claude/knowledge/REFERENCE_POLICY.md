# Reference policy

When sources disagree, the higher one wins:

1. The checked-out code, config, and lockfiles/requirements of this repo.
2. Official docs or source for the exact versions the repo pins.
3. Context7 results: resolve the library ID, prefer official/high-reputation entries, ask one concept per query, record the source, then check it against 1 and 2.
4. Blog posts, Q&A answers, and model memory: hints only, never cited as fact.

Do not adopt an API from a newer major version than the one pinned without saying so and getting the upgrade agreed.
