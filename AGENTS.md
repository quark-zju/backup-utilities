## FORMAT CODE

This environment cannot run `black` reliably.

Use `ruff` for formatting and lint checks instead:

- `ruff format`
- `ruff check`

## RUNNING TOOLS

Run `pytest` and any `keyring`-related commands via `uv run`.

- Use `uv run pytest -q` for tests.
- Use `uv run python ...` (or equivalent `uv run` command) for keyring behavior checks.
