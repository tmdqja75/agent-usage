# agent-usage

`agent-usage` is a macOS-first Python CLI for collecting privacy-conscious
summaries of local agent usage.

## Privacy boundary

The project is designed to process only data a user explicitly makes available
on their own machine. It does not transmit session content, identifiers,
credentials, or other personal data by default.

## Development

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv run pytest -q
uv run ruff check .
```
