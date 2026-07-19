# Troubleshooting

## Read source health before interpreting totals

`agent-usage doctor` and `agent-usage collect` report source health separately from token totals:

- `available_with_activity` means the source was readable and produced activity.
- `available_with_zero_activity` means the source was readable for the requested window and produced no activity.
- `source_unavailable` means the source could not be read or did not contain the required source shape. It is not zero activity.

Do not estimate unavailable usage. In particular, Claude Code history without readable project transcripts is `source_unavailable`; do not estimate Claude Code tokens from history alone.

## Initial backfill and repeat runs

On an agent's first collection, the only backfill window is the half-open UTC interval from `2026-07-04T00:00:00Z` through `2026-07-18T00:00:00Z`. The start is included and the `2026-07-18T00:00:00Z` end is excluded. The collector does not scan earlier history on a first run.

Later runs begin at the saved checkpoint. Deduplication uses opaque fingerprints, so repeat runs do not double-count the same normalized records.

## Codex accounting

Codex rollout `token_count` events are cumulative snapshots. The collector converts them to monotonic per-session deltas rather than summing snapshots. Counter resets are treated as a new delta from zero, and malformed lines are skipped without inventing tokens.

## Publishing

`agent-usage publish` requires a configured profile repository and a working GitHub CLI login. Start with:

```sh
gh auth status
agent-usage init --repo OWNER/PROFILE-REPO
```

Publishing is limited to this device's sanitized partition. It fetches and rebases before push, retries a non-fast-forward race a bounded number of times, and never force-pushes. If a push fails, resolve the reported Git/GitHub problem and rerun publish; do not manually stage another device's partition.

## Scheduler

Scheduling is opt-in and macOS-only:

```sh
agent-usage schedule install --daily-at 09:00
agent-usage schedule status
agent-usage schedule remove
```

The scheduled `launchd` job runs `collect` and only then `publish`; it writes local scheduler logs. If installation or removal fails, the command preserves the prior configuration state rather than claiming success. Do not configure the scheduler until you are ready for the local machine to publish its own sanitized daily aggregates.

## Privacy questions

If a local preview or public record appears to contain sensitive data, stop publishing and inspect the privacy policy and local overrides. Never paste prompts, transcripts, credentials, raw session IDs, source paths, or raw tool arguments into an issue or fixture. See [privacy.md](privacy.md) for the public boundary and [multi-device.md](multi-device.md) for partition rules.
