---
name: adv
description: Pairs a stronger advisor model with a faster executor ("do-er") model using Claude's advisor tool. "/adv fable opus" means advisor = latest Claude Fable, executor = latest Claude Opus. Use when the user types /adv, asks to set up, change or check an advisor/executor pairing, asks which models can advise which, wants Claude to consult a stronger model mid-task, or wants Messages API, SDK or Managed Agents code that uses the advisor tool (advisor_20260301, beta advisor-tool-2026-03-01).
license: MIT
metadata:
  author: Charles Russella
  homepage: https://github.com/crussella0129/adv
  version: 0.1.0
---

# /adv: advisor + executor pairing

Arguments: $ARGUMENTS

If the line above is empty or still shows an unreplaced placeholder, take the arguments from the
user's message. Tokens are case-insensitive: `/adv Fable Opus` = `/adv fable opus`.

The **executor** is the model doing the work (in Claude Code, the main model). The **advisor** is
a stronger model the executor consults mid-task. It sees the whole transcript and returns a plan
or course correction. Everything runs server-side inside one Messages API request.

## 1. Parse the request

| Form | Meaning |
|---|---|
| `/adv <advisor> <executor>` | Pair them. `/adv fable opus` |
| `/adv <advisor> <executor> <task…>` | Pair them, then do the task on the new pairing |
| `/adv <advisor>` | Change only the advisor; keep the current executor |
| `/adv <advisor> -- <task…>` | `--` ends the model tokens |
| `/adv off` · `/adv status` (or bare `/adv`) | Turn the advisor off · show the pairing |
| `/adv api <advisor> <executor>` | Write API code for that pairing (section 4) |
| anything else | Answer it as a question about the advisor tool |

A model token is a family (`fable`, `opus`, `sonnet`, `haiku`, `mythos`), optionally versioned
(`opus-4.8`, `opus4.8`, `claude-opus-4-8`, `sonnet-5`). A family alone means **the latest model of
that family**. `[1m]` after the executor (`opus[1m]`) is Claude Code's 1M-context suffix.

## 2. Resolve and check the pair

Latest per family (from `assets/models.json`, as of 2026-10-25; prefer that file if it is newer than
this table):

| Alias | Resolves to | Rank | Advice |
|---|---|---|---|
| `fable` | `claude-fable-5-1` (Claude Fable 5.1) | 9 | encrypted |
| `mythos` | `claude-mythos-5-1` (Project Glasswing only) | 9 | encrypted |
| `opus` | `claude-opus-5-5` (Claude Opus 5.5) | 7 | encrypted |
| `sonnet` | `claude-sonnet-5-5` (Claude Sonnet 5.5) | 6 | encrypted |
| `haiku` | `claude-haiku-5-5` (Claude Haiku 5.5) | 4 | encrypted |

Other ranks: fable-5 / mythos-5 / opus-5 = 7 (Claude Code ranks fable-5 and mythos-5 at 8),
opus-4-8 / opus-4-7 = 5 (plaintext), sonnet-5 = 4 (plaintext), opus-4-6 = 3 (plaintext),
sonnet-4-6 = 2 (plaintext), haiku-4-5 = 1 (executor only). Older models can't take part.

**Rule:** the advisor's rank must be at least 2, and at least the executor's rank. Equal ranks
are fine.
- Valid: `/adv fable opus`, `/adv opus sonnet`, `/adv sonnet haiku`, `/adv opus opus`.
- Invalid: `/adv opus fable`. A Fable 5.1 executor accepts only Fable 5.1 or Mythos 5.1. Say why,
  suggest the swapped order, and stop. Don't change anything.
- Encrypted advice means the executor reads the advice but nobody else sees its text. Say so when
  it matters. For readable advice you need an Opus 4.8/4.7/4.6, Sonnet 5 or Sonnet 4.6 advisor
  paired with an executor that accepts it.
- Full tables, accepted spellings and worked examples: `references/models.md`.

For a deterministic answer, run the resolver. In Claude Code the folder is `${CLAUDE_SKILL_DIR}`;
elsewhere use the `scripts/` folder next to this file. Try `python3`, then `python`, then `py -3`.

```
python3 "${CLAUDE_SKILL_DIR}/scripts/resolve.py" fable opus --format text
```

It exits 2 for an invalid pair or an unknown model. `--ranks claude-code` applies Claude Code's
stricter ranks, and `--live` checks the Models API for newer releases (needs the `anthropic`
package and a key). Never paste user input into a `!` shell line: arguments are not escaped there.

## 3. Act for the environment you are in

**Claude Code (terminal CLI or the desktop app's Code tab).** The advisor is Claude Code's own
`/advisor`. This plugin's mod normally answers a typed `/adv <advisor> [executor] [task]` before
you see it. It runs `/model` and then `/advisor`, then sends the task.
- If the user asked in plain words ("use Fable as my advisor"), check the pair and tell them to
  type `/adv <advisor> <executor>`, which the mod applies at once.
- If the user's message *is* such a typed `/adv` command, the mod didn't run, usually because an
  organization policy turns mods off. Built-in commands can't be run from a skill, so work through
  the steps below.

1. Check the pair (section 2).
2. Give the user the two commands to type, in this order:
   - `/model <executor>`: aliases `fable|opus|sonnet|haiku`, else the full ID; keep `[1m]`.
   - `/advisor <advisor>`: aliases `fable|opus|sonnet`; full ID for haiku, mythos and versioned
     picks.
3. Mention the new-session one-liner: `claude --model opus --advisor fable`.
4. Tell them to send the task again once both commands report success. Don't start the task on
   the wrong pairing.
5. If `/advisor` is missing or says it is unavailable, explain the requirements and fixes from
   `references/environments.md`:
   - an Anthropic API, Claude Platform on AWS or Anthropic-managed Google Cloud login (not Bedrock,
     Vertex or Foundry)
   - the feature rolled out to the account, or `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1`
   - a one-time usage-credit consent through `/model fable` before Fable can advise
   - an already-active advisor only changes after `/clear` or `/compact`

These settings save as the user's default, the same as typing `/model` and `/advisor`.

**claude.ai chat (web, desktop or mobile) and Cowork.** There is no advisor here, and a skill
can't switch the conversation's model. Say that plainly, then offer:
- choosing the executor in the model menu
- the Claude Code one-liner above, for real advisor use
- an API snippet (section 4)

Never claim an advisor is running when it isn't.

**API developers.** See section 4.

## 4. API, SDK and Managed Agents code (`/adv api …` or on request)

Read `references/api.md` first. Then write code in the user's language with the official SDK. Get
a snippet to adapt from `resolve.py <advisor> <executor> --format python|typescript|curl|managed-agents`.
Essentials:
- Beta header `advisor-tool-2026-03-01`. Tool
  `{"type": "advisor_20260301", "name": "advisor", "model": "<advisor id>"}` in `tools`. The
  executor is the request's top-level `model`.
- Use the full model IDs from section 2, not aliases.
- Optional tool fields:
  - `max_uses`: per-request cap
  - `max_tokens`: at least 1024; 2048 is a good start
  - `caching: {"type": "ephemeral", "ttl": "5m" | "1h"}`: worth it from about 3 calls per
    conversation
- Round-trip `advisor_tool_result` blocks verbatim on later turns.
- Resume `stop_reason: "pause_turn"` by re-sending with the same tool. Read advisor tokens from
  `usage.iterations` (`type: "advisor_message"`). Top-level usage counts the executor only.
- Executors `claude-opus-5-5`, `claude-sonnet-5-5`, `claude-fable-5-1` and `claude-mythos-5-1`
  reject forced `tool_choice`. Nudge advisor calls from the prompt instead (`references/prompting.md`).
- Platforms: the Claude API, Claude Platform on AWS and Anthropic-managed Google Cloud. Not
  Bedrock, Google-managed Vertex AI or Microsoft Foundry.
- Managed Agents: put
  `"multiagent": {"type": "multiagent_20261001", "advisor": {"type": "enabled", "model": "<id>"}}`
  on the agent, with beta `managed-agents-2026-04-01`. Members you leave out take their defaults,
  and `workflows` and `subagents` default to enabled. Set them to `{"type": "disabled"}` if you
  only want the advisor.

**Running a task through the API.** `scripts/run.py <advisor> <executor> "<task>"` streams the
executor's answer, then reports each advisor call and the split between executor and advisor
tokens. Use `--dry-run` to see the request without sending it.
- It needs `pip install anthropic` and an `ANTHROPIC_API_KEY` in the environment, and it bills that
  API account. Run it only when the user asks.
- Never ask anyone to paste a key into the conversation. Without a key in the environment, give
  the user the command to run themselves.

## 5. Answering questions about the advisor tool

- How a call flows, the request and response shapes, errors, streaming, billing, caching and
  platform support: `references/api.md`.
- When the pattern pays off, prompting the executor to consult at the right moments, trimming
  advisor output and cost control: `references/prompting.md`.
- Pairings, ranks, prices and which advisors return readable advice: `references/models.md`.
- What `/adv` does in each app, and troubleshooting Claude Code's advisor messages:
  `references/environments.md`.

The source of truth is Anthropic's docs:
https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool and
https://code.claude.com/docs/en/advisor. Fetch them when the user needs something these files don't
cover or that may have changed. When a model or pairing here disagrees with what Claude Code or the
API reports, trust Claude Code or the API, and tell the user the plugin's catalog may be out of date.
