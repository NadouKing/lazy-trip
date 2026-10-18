# lazy-trip

Read `skills/daytrip-planner/SKILL.md` for travel planning and `docs/architecture.md` before changing integration boundaries.

## Ownership and layers

- Python 3.14 standard GIL build, uv, src layout, hatchling. Keep the project language Python; a platform library may execute JavaScript inside Chrome.
- CLI parses arguments and writes JSON. Research calls `xiaohongshu_tools.XiaohongshuClient` and `dazhongdianping_tools.DianpingClient` directly; never shell out to their CLIs.
- Platform libraries own browsers, profiles and page parsing. This repository owns requirements, provenance, official MCP handoff, scheduling and reporting. Platform packages do not import lazy-trip.
- Official Amap MCP already covers maps and weather. Only generate tasks and consume real receipts here; no alternate driver, credential lookup or Key extraction.
- Current AI reads evidence, extracts candidates and calls official MCP. Do not present the CLI as an autonomous LLM host.

## Changes and verification

- Use `uv sync --locked` and `uv run pytest`; run `uv run ruff check .` before a code commit. See `docs/environment.md` for directory-outside wheel acceptance.
- Test return legs, budget for the whole group, venue walking, source identity, selected branches, units, stale/date-specific weather and unknown fields after planner changes.
- Never invent absent routes, coordinates, opening hours, comments or prices to complete a report. Mark uncertainty and partial-source failure explicitly.
- Maintain public error codes and JSON envelopes. stdout is JSON, progress is stderr. Avoid raw HTTP exceptions in public output.
- An installation must work without this machine's absolute paths or sibling checkouts. Release dependency sources are immutable Git SHAs in pyproject/lock.

## Local state

- Preserve existing logins. Dedicated platform profiles must not be shared concurrently; close clients with async context managers.
- Never commit/package cookies, browser profiles, signed URLs, tokens, raw request headers, private config or user research data. Examples here are explicitly synthetic.
- Read-only collection: no posts, likes, comments, orders, bookings or payments. Verification gates require the account owner's browser interaction; no CAPTCHA bypass.
- Live checks are needed for platform/integration behavior changes, not for documentation alone. Label saved-data replays as historical; refresh weather before a real trip.
- Update README and docs for changed behavior. Roadmap follows run → simplify setup → share resources → improve recommendations.
