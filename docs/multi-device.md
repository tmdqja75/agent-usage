# Multi-device setup

Each installation owns a random opaque device ID and a private local ledger. Devices do not exchange raw events or copy one another's ledgers.

## Shared profile repository layout

A device publishes only its own sanitized UTC-day files:

```text
data/v1/devices/<opaque-device-id>/<YYYY-MM-DD>.json
```

Do not rename another device's directory or edit another device's records. A device/day record is idempotent: unchanged content is not rewritten. The public profile repository contains sanitized aggregates only, never private SQLite data, raw session IDs, source paths, prompts, transcripts, credentials, or tool arguments.

## Device workflow

After choosing a profile repository, configure that installation locally:

```sh
agent-usage init --repo OWNER/PROFILE-REPO
agent-usage collect
agent-usage publish
```

`init` updates local configuration only. `collect` imports new local usage into the private ledger. `publish` requires an authenticated GitHub CLI session, writes this installation's device partition, fetches and rebases the configured branch, and uses bounded retries for concurrent device publishes. It never force-pushes.

Use the same `OWNER/PROFILE-REPO` target on each device. Run collection before publishing; repeat collection and publish safely as records are deduplicated locally and daily files are content-idempotent.

## Profile dashboard workflow

The profile repository's GitHub Actions workflow validates the public device/day records, merges their aggregates, and refreshes the managed README plus a screenshot of the dashboard. The template lives in this collector repository at `templates/github-workflow.yml`; copy it into the profile repository only when profile initialization has been explicitly approved.

The workflow is intentionally triggered only by direct default-branch changes under `data/v1/**`. It serializes dashboard runs and commits generated README/chart changes only when the rendered output differs. Its dashboard does not expose device IDs or raw source records.

## Adding or replacing a device

A new installation receives a new opaque device ID automatically. Point it at the existing profile repository and begin with `collect`; its records appear in a separate partition and join the aggregate dashboard after publishing.

If a device is retired, keep its existing public daily aggregates unless you have a deliberate data-retention decision. Removing its local ledger does not remove public history from the profile repository.
