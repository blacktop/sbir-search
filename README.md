# sbir-search

Nightly SBIR opportunity crawler focused on AI-powered reverse engineering tools.

## Quick Start

```bash
uv venv
uv pip install -e .[dev]
uv run sbir-search --config config.toml --dry-run
```

## Configuration

Edit `config.toml`:

| Setting | Description |
|---------|-------------|
| `keywords` | Terms to match (case-insensitive) |
| `min_score` | Minimum keyword hits to trigger a match |
| `agencies` | Optional filter (e.g., `["DOD", "NSF"]`) |
| `open_only` | Only open solicitations |
| `state_path` | Where to store seen IDs between runs |

## Data Sources

| Source | Config Section | API Key | Default |
|--------|----------------|---------|---------|
| SBIR.gov | `[match]` | No | Primary |
| SAM.gov | `[sam]` | Yes (`SAM_API_KEY`) | Fallback |
| DARPA Topics | `[dod]` | No | Fallback |
| NSF Seed Fund | `[nsf]` | No | Fallback |
| NIH Guide | `[nih]` | No | Fallback |
| Grants.gov RSS | `[rss]` | No | Fallback |

Set `fallback_only = false` to always run a source regardless of SBIR.gov status.

### SAM.gov API Key

```bash
export SAM_API_KEY="your-key"
```

Get a free key at https://sam.gov → Account Details → Request Public API Key.

## Discord Notifications

**Webhook (simplest):**

```bash
export DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

**Bot token:**

```bash
export DISCORD_TOKEN="your-bot-token"
export DISCORD_CHANNEL_ID="your-channel-id"
```

**Test without crawling:**

```bash
uv run sbir-search --config config.toml --test-discord
```

## CLI Options

```bash
sbir-search --config config.toml              # Run crawler
sbir-search --config config.toml --dry-run    # Print matches, don't notify
sbir-search --config config.toml --explain    # Show match/skip decisions
sbir-search --config config.toml --test-discord "message"  # Test Discord
```

## GitHub Actions

The workflow in `.github/workflows/sbir-crawl.yml` runs nightly (UTC) using `DISCORD_WEBHOOK_URL` from repo secrets. State is cached to avoid duplicate notifications.

## License

MIT Copyright (c) 2025 **blacktop**
