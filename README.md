# agent-usage

`agent-usage` is a macOS-first Python CLI for collecting privacy-conscious
summaries of local agent usage.

## Privacy boundary

The project is designed to process only data a user explicitly makes available
on their own machine. It does not transmit session content, raw identifiers,
credentials, or other sensitive personal data. Opt-in publishing writes only
sanitized device/day aggregates.

The collector's public boundary, per-device publishing model, and operational
diagnostics are documented in [docs/privacy.md](docs/privacy.md),
[docs/multi-device.md](docs/multi-device.md), and
[docs/troubleshooting.md](docs/troubleshooting.md).

The local collector is macOS-first. Profile-dashboard rendering happens in a
separate GitHub Actions workflow from sanitized device/day aggregates only.

## Development

Requires Python 3.11 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv run pytest -q
uv run ruff check .
uv build
uv run agent-usage --help
```
