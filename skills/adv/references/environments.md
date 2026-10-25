# What /adv does in each environment

`/adv` behaves differently by environment, because only Claude Code has an advisor that can be
switched from inside a session. Covered: each environment, what is saved, requirements,
troubleshooting, installation. Pairing rules: [models.md](models.md). API code: [api.md](api.md).

## Contents

1. [At a glance](#at-a-glance)
2. [Claude Code CLI and desktop Code tab (mod on)](#claude-code-cli-and-desktop-code-tab-mod-on)
3. [Requirements for /advisor](#requirements-for-advisor)
4. [New sessions: flags and settings](#new-sessions-flags-and-settings)
5. [Agent SDK and claude -p](#agent-sdk-and-claude--p)
6. [Claude Code with mods disabled](#claude-code-with-mods-disabled)
7. [claude.ai chat](#claudeai-chat)
8. [Cowork](#cowork)
9. [API and Managed Agents](#api-and-managed-agents)
10. [Troubleshooting](#troubleshooting)
11. [Installation](#installation)

## At a glance

| Environment | What `/adv fable opus [task]` does | Model tokens |
|---|---|---|
| Claude Code CLI, desktop Code tab, VS Code (mods on) | The mod runs `/model opus`, then `/advisor fable`, then submits the task | Zero for the switch |
| Claude Code, mods blocked by policy | The skill validates and tells you the two commands to type | A short skill reply |
| claude.ai chat (web, desktop, mobile) | Explains; no advisor exists there. Offers the Claude Code one-liner and API code | A skill reply |
| Cowork | Explains; points to the Code tab | A skill reply |
| API / Managed Agents | `/adv api fable opus` writes the tool definition, SDK, curl or agent config | A skill reply |

## Claude Code CLI and desktop Code tab (mod on)

The plugin's mod (`hooks/hooks.json` -> `hooks/register.ts`) answers the `/adv` command before
any prompt is sent:

1. Parses `<advisor> [executor] [task...]` (`--` ends the model tokens; `off`/`none` and `status`
   are keywords). Anything else (`api ...`, `help`, free text) goes on to the skill.
2. Checks that this session has an `/advisor` command at all (see
   [Requirements](#requirements-for-advisor)). If not, it changes nothing and lists the requirements.
3. Validates the pair with Claude Code's ranks. Invalid pairs change nothing; if swapping would
   work it suggests the swap (`/adv opus fable` -> "Did you mean /adv fable opus?").
4. Runs `/model <executor>` (if given), then `/advisor <advisor>`, exactly as if you typed them.
   Aliases (`fable`, `opus`, `sonnet` for the advisor; plus `haiku` for the model) are passed as
   aliases so they keep tracking the latest model; versioned specs, a Haiku advisor and Mythos are
   passed as full IDs.
5. If a task was given, submits it as your next prompt, but only once the advisor is really set.

`/adv status` (or bare `/adv`) shows executor and advisor; `/adv off` turns only the advisor off.

**What is saved.** The same as typing the commands yourself:

| Command | Interactive CLI | `-p`, Agent SDK, desktop Code tab | Remote Control |
|---|---|---|---|
| `/advisor X` | Saved as `advisorModel` in `~/.claude/settings.json` (default for new sessions) | Saved the same way | This session only |
| `/model X` | Saved as `model` in `~/.claude/settings.json` | This session only | This session only |

Editing `advisorModel` in a settings file by hand does not change a running interactive session;
use `/advisor` (or `/adv`).

**Deferred advisor changes.** Turning the advisor on or off applies immediately. Changing an advisor
this conversation already uses is held until `/clear` or `/compact` (Claude Code keeps the tool it
already declared); the mod then does not start your task: run `/clear`, then send it.

**Fable consent.** On some Claude plans a Fable advisor bills to usage credits and needs a one-time
consent. Until then `/advisor fable` saves nothing. Run `/model fable` once in an interactive
session to review and enable it, then repeat `/adv`.

**Subagents** inherit the advisor. Pairing is checked against each subagent's own model, so a Haiku
or Sonnet subagent can still use an advisor that is too weak for the main model.

**Desktop Code tab.** It is Claude Code (its own bundled copy; check with `/status`) running in
headless mode. Its model picker under the prompt box owns the main model, and `/model` there is
session-only. If the picker still shows the old model after `/adv`, pick the executor there as well
(not yet verified whether the picker re-applies its choice). Plugins work in local and SSH
sessions, not in cloud or WSL sessions.

**Mod requirements.** Mods are on by default (terminal v2.1.287+, desktop v2.1.286+); `/advisor` in
`-p`, SDK, desktop and Remote Control needs v2.1.260+. Managed settings `allowManagedModsOnly`,
`allowManagedHooksOnly` or `disableAllHooks` block the mod; see
[mods disabled](#claude-code-with-mods-disabled).

## Requirements for /advisor

The `/advisor` command only exists when all of these hold:

- **Provider**: the Anthropic API, Claude Platform on AWS (Claude Code 2.1.300+; the Claude Code
  advisor docs page may still say otherwise) or Claude on Google Cloud, Anthropic-managed. Not
  Bedrock, Vertex AI, Foundry or an LLM gateway.
- **Feature flag**: on the Anthropic API the advisor is a server-side rollout per account; it
  defaults on for the AWS and Google Cloud Anthropic-managed providers. Feature flags are fetched
  with telemetry, so `DISABLE_TELEMETRY` keeps the advisor off.
- `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` is unset (setting it turns the advisor off).
- `CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS` is unset, and the org is not a HIPAA org (both disable
  experimental betas, the advisor included).

The main model does not need an advisor rank for `/advisor` to exist: with an unranked main model
(Opus 4.5, Sonnet 4.5 and older) `/advisor` still works and saves the choice, but the advisor does
not activate until you switch to a supported model (`/model opus`).

`CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1` force-enables the advisor even without the feature
flag. It **also bypasses Claude Code's own rank checks**, so an invalid pair is sent to the API and
fails there. The `/adv` mod still validates pairs itself.

## New sessions: flags and settings

Start a session with the pair already set:

```bash
claude --model opus --advisor fable
claude --model opus --advisor fable "refactor the payment module"
claude --settings '{"model":"opus","advisorModel":"fable"}'
```

- `--advisor` is a hidden flag (not in `--help`). It takes an alias or a full ID, applies to this
  session only and is ignored if the advisor feature is unavailable.
- At launch it exits with `Error: The model "X" does not support the advisor tool.` (main model has
  no rank) or `Error: The model "X" cannot be used as an advisor.`; it warns
  (`"X" cannot advise "Y" ...`) if the advisor is weaker than the main model.
- `--settings` loads a session-only settings layer that outranks your settings files. In
  PowerShell, quote the JSON with single quotes or escape the inner double quotes.
- Windows Git Bash rewrites a leading `/` in arguments: use `MSYS_NO_PATHCONV=1 claude -p "/adv ..."`
  or PowerShell.

## Agent SDK and claude -p

- **Documented**: send `/advisor fable` as a prompt (Claude Code v2.1.260+), and set the executor
  with the SDK's `model` option (`model: "opus"`). With the plugin loaded, `/adv fable opus` works
  as a prompt too, and in a long-lived session (SDK or stream-json) `/adv fable opus <task>`
  also starts the task.
- **One-shot `claude -p "/adv fable opus <task>"`** sets the pairing but cannot start the task,
  because no session is bound for the plugin to submit to. Use the flags instead:
  `claude -p --model opus --advisor fable "<task>"`.
- **Unverified**: TypeScript `settings: { advisorModel: "fable" }` (Python: a JSON string), or
  `extraArgs: { advisor: "fable" }` / Python `extra_args={"advisor": "fable"}`, which passes the
  hidden `--advisor` flag. Neither SDK documents an advisor option.
- SDK apps do not show the Fable consent prompt; if consent is pending, `--advisor fable` exits.

## Claude Code with mods disabled

When managed policy blocks mods, `/adv` reaches the skill instead. A skill cannot run built-in
commands (Claude Code refuses with "... is a UI/built-in CLI command, not a skill"), and a skill's
`model:` field lasts one turn only. So the skill validates the pair and tells you to type:

```text
/model opus
/advisor fable
```

or to relaunch with `claude --model opus --advisor fable`.

## claude.ai chat

Only the skill loads in chat (hooks, mods and `!` command lines are ignored; `${CLAUDE_SKILL_DIR}`
is not substituted; arguments are read from your message). There is **no advisor in claude.ai chat**,
and a skill cannot change the chat's model. `/adv` there:

- says so plainly and never pretends an advisor is running;
- suggests choosing the executor in the model menu next to the send button;
- gives the Claude Code one-liner (`claude --model opus --advisor fable`) and an API snippet.

Optional: `scripts/run.py` runs one task through the Messages API with the advisor, using the
official `anthropic` SDK. It needs network egress from the sandbox (Free/Pro/Max on by default,
Team package managers only, Enterprise off by default; `api.anthropic.com` must be allowed) and an
Anthropic Console API key that you provide. Pasting a key into a chat leaves it in the transcript:
use a short-lived key and revoke it afterwards. API usage bills to the Console account, not your
Claude subscription. Current-generation advisors return encrypted advice, so you will see only the
executor's output.

## Cowork

Cowork loads the plugin's skill from your claude.ai account (`!` lines are replaced with a
placeholder). Whether `/advisor` exists in Cowork is not documented, so `/adv` explains the pairing
and points you to the desktop app's Code tab, where the advisor works.

## API and Managed Agents

`/adv api <advisor> <executor>` (or a plain request such as "write the Python for fable advising
opus") produces the `advisor_20260301` tool definition with the `advisor-tool-2026-03-01` beta
header, SDK or curl code, or a Managed Agents `multiagent` config, using API ranks (not Claude
Code's). `scripts/resolve.py` prints the same resolution from the command line. Details: [api.md](api.md).

## Troubleshooting

Messages are quoted as Claude Code and the mod print them (`X`, `Y` stand for model names).

| You see | Cause | Fix |
|---|---|---|
| `This session has no /advisor command, so nothing changed. Claude Code's advisor needs:` | Advisor feature not enabled here | Check [Requirements](#requirements-for-advisor); try `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1` |
| `The advisor is not available` | Same, from `/advisor` in `-p`/SDK/desktop | Same |
| `X can't advise Y: the advisor must be at least as capable as the executor. Did you mean /adv Y X?` | Pair invalid (advisor weaker); the hint appears only when the swapped pair is valid | Swap the order or pick a stronger advisor ([models.md](models.md)) |
| `X can't be an advisor: the advisor has to be Claude Sonnet 4.6 or more capable.` | Advisor below Sonnet 4.6 (Haiku 4.5) | Choose another advisor |
| `The advisor was not set (see the /advisor output above), so the task was not started.` | `/advisor` refused the choice (e.g. Fable consent pending, invalid or disallowed model) | Read the `/advisor` output just above it and fix that, then run `/adv` again |
| `X cannot be used as an advisor. Valid options: fable, opus, sonnet, off` | Not an advisor-eligible model or alias | Use one of the aliases or a full ID of a valid advisor |
| `Invalid advisor model: ...` | Unknown or disallowed model name | Check spelling; `availableModels` policy may exclude it |
| `... as the advisor bills to usage credits ... Run /model fable to review and enable.` | Fable usage-credit consent pending | Run `/model fable` in an interactive session, then `/adv` again |
| `Advisor will not activate on the main model (advisor is less capable); subagents may still use it ...` | Main model outranks the advisor | Stronger advisor or smaller main model |
| `Note: X is less capable than the current main model (Y), so the advisor will not activate.` | Same, reported by `/advisor` | Same |
| `The current main model (X) does not support the advisor.` | Main model has no advisor rank | Switch to a current model (`/model opus`) |
| `Warning: Advisor disabled — base model 'X' has no advisor rank in the model catalog.` | Custom or unknown main model ID | Use a public alias (opus, sonnet, fable) |
| `The current conversation keeps X as its advisor model until /clear or /compact ...` | Advisor change deferred | Run `/clear` (or `/compact`), then send the task |
| `This conversation keeps its previous advisor until /clear or /compact, so the task was not started. Run /clear, then send the task.` | Same, mod held the task | `/clear`, then send the task |
| `The API refused the advisor for the current conversation ...` | Server rejected the advisor mid-conversation | Continues without one until `/clear` or `/compact` |
| `... The configured advisor model is not compatible with this request model` | Saved `advisorModel` or `--advisor` invalid for this model | `/advisor` to change or `/advisor off` |
| `The advisor can't be changed from this client ...` | View-only or no control channel (Remote Control) | Change it from the terminal |
| `Advisor unavailable (<code>)` | A consult failed (e.g. `overloaded`, `too_many_requests`) | Transient; the executor continues without advice |
| `$.command.run: no command named /advisor in this session` (debug log) | Feature gated off while the mod ran | As the first row |
| `/adv` is an unknown command | Plugin not installed/enabled, or another command owns `/adv` | `/plugin` to check; `/adv:adv` always works |

## Installation

- **Claude Code, one step**: `/plugin install adv --marketplace crussella0129/adv`, or in a shell
  `claude plugin install adv --marketplace crussella0129/adv`.
- **Claude Code, two steps**: `/plugin marketplace add crussella0129/adv`, then
  `/plugin install adv@adv`.
- **Desktop app Code tab**: `+` > Add plugins (local and SSH sessions), or install from the CLI;
  the CLI, the Code tab and VS Code share the same user settings.
- **claude.ai (chat, Cowork, and synced to Claude Code)**: Customize > Plugins > Add marketplace,
  enter `crussella0129/adv`, then install `adv`.
- **Skill only** (claude.ai "Upload a skill"): build `dist/adv-skill.zip` with
  `python tools/package_skill.py`, then Customize > Skills > `+` > Create skill > Upload a skill.
  Code execution and file creation must be enabled (Settings > Capabilities; on Team/Enterprise,
  Organization settings > Capabilities).
- **Teams**: in the project's `.claude/settings.json` add
  `"extraKnownMarketplaces": {"adv": {"source": {"source": "github", "repo": "crussella0129/adv"}}}`
  and `"enabledPlugins": {"adv@adv": true}`; it applies after the workspace-trust prompt.
- **Development**: `claude --plugin-dir .` loads a checkout; `claude plugin validate .` checks it.
