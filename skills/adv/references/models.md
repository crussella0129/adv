# Models, aliases and valid pairings

Written by hand from [`assets/models.json`](../assets/models.json), which is the source of truth
(`as_of`: 2026-10-25). If the two disagree, trust `models.json`. Sources: the advisor tool's
model-compatibility table and the models overview on platform.claude.com, and Claude Code's
advisor docs.

## Contents

1. [Aliases: family to latest model](#aliases-family-to-latest-model)
2. [Accepted spellings](#accepted-spellings)
3. [Catalog](#catalog)
4. [Pairing rule](#pairing-rule)
5. [Executor to valid advisors](#executor-to-valid-advisors)
6. [Claude Code difference](#claude-code-difference)
7. [Worked examples](#worked-examples)
8. [Readable (plaintext) advice](#readable-plaintext-advice)

## Aliases: family to latest model

| Alias | Resolves to | Claude Code passes |
|---|---|---|
| `fable` | `claude-fable-5-1` (Claude Fable 5.1) | alias `fable` (advisor and model) |
| `opus` | `claude-opus-5-5` (Claude Opus 5.5) | alias `opus` (advisor and model) |
| `sonnet` | `claude-sonnet-5-5` (Claude Sonnet 5.5) | alias `sonnet` (advisor and model) |
| `haiku` | `claude-haiku-5-5` (Claude Haiku 5.5) | alias `haiku` as model; full ID as advisor (no advisor alias) |
| `mythos` | `claude-mythos-5-1` (Claude Mythos 5.1) | full ID; Project Glasswing customers only |

Inside Claude Code the aliases are handed to `/model` and `/advisor` as-is, so the saved choice
keeps following Claude Code's own "latest" as it updates (`ANTHROPIC_DEFAULT_*_MODEL` overrides
apply). Versioned specs are sent as full IDs and stay pinned.

## Accepted spellings

One token per model, case-insensitive: optional `claude-` prefix, a family (`fable`, `mythos`,
`opus`, `sonnet`, `haiku`), an optional version, and (executor only) an optional `[1m]` suffix for
Claude Code's 1M-context variant (dropped for advisors and the API).

| You type | Means |
|---|---|
| `opus`, `Opus`, `claude-opus` | latest Opus: `claude-opus-5-5` |
| `opus-4.8`, `opus4.8`, `opus-4-8`, `claude-opus-4-8` | `claude-opus-4-8` |
| `opus5`, `opus-5` | `claude-opus-5` (not 5.5) |
| `sonnet[1m]` | latest Sonnet with 1M context (executor in Claude Code) |

Write the version attached to the family: `opus 4.8` is two tokens and the `4.8` would be read as
the start of the task. A versioned spec must exist in the catalog (the Claude Code mod passes
well-formed unknown IDs through and lets Claude Code decide).

## Catalog

Rank = API capability rank used for pairing; CC rank = Claude Code's internal rank. Prices are USD
per million tokens (input / output).

| ID | Display | Rank | CC rank | Advice | $ in / out | Notes |
|---|---|---|---|---|---|---|
| `claude-fable-5-1` | Claude Fable 5.1 | 9 | 9 | encrypted | 10 / 50 | Not for zero-data-retention orgs; some Claude plans bill it to usage credits. Rejects forced `tool_choice`. |
| `claude-mythos-5-1` | Claude Mythos 5.1 | 9 | 9 | encrypted | 10 / 50 | Glasswing only. Rejects forced `tool_choice`. |
| `claude-fable-5` | Claude Fable 5 | 7 | 8 | encrypted | 10 / 50 | |
| `claude-mythos-5` | Claude Mythos 5 | 7 | 8 | encrypted | n/a | Glasswing only. |
| `claude-opus-5-5` | Claude Opus 5.5 | 7 | 7 | encrypted | 4 / 20 | Rejects forced `tool_choice`. |
| `claude-opus-5` | Claude Opus 5 | 7 | 7 | encrypted | 5 / 25 | |
| `claude-opus-4-8` | Claude Opus 4.8 | 5 | 5 | plaintext | 5 / 25 | |
| `claude-opus-4-7` | Claude Opus 4.7 | 5 | 5 | plaintext | 5 / 25 | |
| `claude-opus-4-6` | Claude Opus 4.6 | 3 | 3 | plaintext | 5 / 25 | |
| `claude-sonnet-5-5` | Claude Sonnet 5.5 | 6 | 6 | encrypted | 2 / 10 | Rejects forced `tool_choice`. |
| `claude-sonnet-5` | Claude Sonnet 5 | 4 | 4 | plaintext | 2 / 10 | |
| `claude-sonnet-4-6` | Claude Sonnet 4.6 | 2 | 2 | plaintext | 3 / 15 | Weakest allowed advisor. |
| `claude-haiku-5-5` | Claude Haiku 5.5 | 4 | 4 | encrypted | 0.10 / 0.50 | Prices for prompts up to 100K tokens. |
| `claude-haiku-4-5` | Claude Haiku 4.5 | 1 | 1 | none | 1 / 5 | Executor only; cannot advise. No adaptive thinking. |

Models older than these (Opus 4.5, Sonnet 4.5 and earlier) cannot take part in either role.
Advisor tokens bill at the advisor's price, executor tokens at the executor's.

## Pairing rule

An advisor must have **rank >= 2** (Claude Sonnet 4.6 or more capable) and the executor's rank must
be **<= the advisor's rank**. Equal ranks may advise each other. The API returns 400
`invalid_request_error` for anything else. These ranks reproduce the official table exactly.

## Executor to valid advisors

Short names drop the `claude-` prefix. Bold = plaintext (readable) advisor.

| Executor (rank) | Valid advisors |
|---|---|
| haiku-4-5 (1) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, **opus-4-6**, sonnet-5-5, **sonnet-5**, **sonnet-4-6**, haiku-5-5 |
| sonnet-4-6 (2) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, **opus-4-6**, sonnet-5-5, **sonnet-5**, **sonnet-4-6**, haiku-5-5 |
| opus-4-6 (3) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, **opus-4-6**, sonnet-5-5, **sonnet-5**, haiku-5-5 |
| sonnet-5 (4) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, sonnet-5-5, **sonnet-5**, haiku-5-5 |
| haiku-5-5 (4) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, sonnet-5-5, **sonnet-5**, haiku-5-5 |
| opus-4-7 (5) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, sonnet-5-5 |
| opus-4-8 (5) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, **opus-4-8**, **opus-4-7**, sonnet-5-5 |
| sonnet-5-5 (6) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5, sonnet-5-5 |
| opus-5 (7) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5 |
| opus-5-5 (7) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5 |
| fable-5 (7) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5 |
| mythos-5 (7) | mythos-5-1, fable-5-1, mythos-5, fable-5, opus-5-5, opus-5 |
| fable-5-1 (9) | mythos-5-1, fable-5-1 |
| mythos-5-1 (9) | mythos-5-1, fable-5-1 |

## Claude Code difference

Claude Code checks pairs with its own ranks (`claude_code_rank`), identical except **Fable 5 and
Mythos 5 are rank 8**. So with a Fable 5 or Mythos 5 main model, Claude Code accepts only Fable 5.1,
Mythos 5.1, Fable 5 or Mythos 5 advisors; an Opus 5 / Opus 5.5 advisor that the API would accept is
refused. The `/adv` mod uses the Claude Code ranks; `/adv api ...` uses the API ranks.
(`CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1` turns Claude Code's own rank checks off.)

## Worked examples

| Command | Advisor -> executor | Result |
|---|---|---|
| `/adv fable opus` | fable-5-1 (9) -> opus-5-5 (7) | Valid everywhere. Advice encrypted. Fable may need usage-credit consent in Claude Code. |
| `/adv opus fable` | opus-5-5 (7) -> fable-5-1 (9) | **Invalid**: the advisor is less capable than the executor, and a Fable 5.1 executor accepts only Fable 5.1 / Mythos 5.1. Swap to `/adv fable opus`. |
| `/adv opus sonnet` | opus-5-5 (7) -> sonnet-5-5 (6) | Valid; Claude Code's recommended setup. Encrypted. |
| `/adv sonnet haiku` | sonnet-5-5 (6) -> haiku-5-5 (4) | Valid; cheap pair. Encrypted. |
| `/adv haiku-4-5 ...` | haiku-4-5 (1) | **Invalid**: rank 1 cannot advise anyone. |
| `/adv haiku haiku-4-5` | haiku-5-5 (4) -> haiku-4-5 (1) | Valid; in Claude Code the advisor is passed as `claude-haiku-5-5`. |
| `/adv opus fable-5` | opus-5-5 (7) -> fable-5 (7 API / 8 CC) | Valid on the API, refused by Claude Code. |
| `/adv opus-4-8 sonnet-4-6` | opus-4-8 (5) -> sonnet-4-6 (2) | Valid, and the advice is readable. |

## Readable (plaintext) advice

Every current-generation advisor (Fable 5.1, Mythos 5.1, Opus 5.5, Sonnet 5.5, Haiku 5.5, and also
Opus 5, Fable 5, Mythos 5) returns **encrypted** advice: the executor reads it, you do not. To see
the advice text you need a plaintext advisor (opus-4-8, opus-4-7, opus-4-6, sonnet-5, sonnet-4-6)
paired with an executor that accepts it:

| Executor | Plaintext advisors it accepts |
|---|---|
| haiku-4-5, sonnet-4-6 | opus-4-8, opus-4-7, opus-4-6, sonnet-5, sonnet-4-6 |
| opus-4-6 | opus-4-8, opus-4-7, opus-4-6, sonnet-5 |
| sonnet-5, haiku-5-5 | opus-4-8, opus-4-7, sonnet-5 |
| opus-4-7, opus-4-8 | opus-4-8, opus-4-7 |
| sonnet-5-5, opus-5, opus-5-5, fable-5, mythos-5, fable-5-1, mythos-5-1 | none (advice is never readable) |
