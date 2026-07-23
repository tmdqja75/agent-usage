# Dashboard UI

React + Vite + visx source for the interactive localhost dashboard served by
`agent-usage dashboard`.

**You normally never build this by hand.** The `agent-usage dashboard` command
builds it on demand (via `dashboard/ui_build.py`), caching `dist/` and rebuilding
only when this source changes. `node_modules/` and `dist/` are gitignored.

## Develop

```bash
pnpm install
pnpm dev      # live dev server against a running dashboard backend
pnpm build    # emits dist/index.html (what the CLI serves)
```

## Data contract

The app fetches `data.json` on load. Keys:

- `window {start, end}`
- `tokens [{date, input, output, reasoning}]`
- `agents [{agent, tokens}]`
- `skills [{name, count}]`
- `mcp [{name, count}]`
- `heatmap [{date, tokens}]`

## Theme constraints

Page background is `#090A0B`; each chart block is `#0E0F13`. Backgrounds and
blocks must be flat hex fills — **no gradients** on any page/block element.
