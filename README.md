# adv

`adv` is a Claude Code plugin that sets up an advisor pairing in one command. Claude's server-side
[advisor tool](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool) lets a
faster **executor** model do the work while a stronger **advisor** model reviews the conversation
and offers guidance when the executor asks for it. Normally you set this up with two commands
(`/model` for the executor, `/advisor` for the advisor) and have to know which pairings are
allowed. With `adv` you type one command with short family names. It resolves each name to the
latest model in that family, checks the pairing rule, and applies both settings.

```text
/adv Fable Opus
```

resolves to advisor `claude-fable-5-1` (Claude Fable 5.1) and executor `claude-opus-5-5`
(Claude Opus 5.5). In Claude Code this is the same as typing `/model opus` and then
`/advisor fable`.

## Quick start

```text
/plugin install adv --marketplace crussella0129/adv
/adv fable opus
/adv fable opus refactor the parser and add tests
/adv status
/adv off
```

## Install

Pick whichever route fits where you use Claude.

| Where | How |
| --- | --- |
| Claude Code, one step | `/plugin install adv --marketplace crussella0129/adv` |
| Claude Code, two steps | `/plugin marketplace add crussella0129/adv`, then `/plugin install adv@adv` |
| Shell | `claude plugin install adv --marketplace crussella0129/adv` |
| Desktop app (Code tab) | **+** next to the prompt box > **Plugins** > **Add marketplace** > `crussella0129/adv`, then install `adv` |
| claude.ai (chat, Cowork, synced to Claude Code) | **Customize** > **Plugins** > **Add marketplace** > `crussella0129/adv`, then install `adv` |
| claude.ai "Upload a skill" | Download `adv-skill.zip` from [Releases](https://github.com/crussella0129/adv/releases) and upload it under **Customize** > **Skills** > **+** > **Create skill** > **Upload a skill** (code execution and file creation must be enabled) |

The one-step `--marketplace` forms need a recent Claude Code; on older versions use the two-step
route.

### Enable it for a whole team

Commit this to your project's `.claude/settings.json`. After a teammate trusts the workspace,
Claude Code adds the marketplace and turns the plugin on:

```json
{
  "extraKnownMarketplaces": {
    "adv": { "source": { "source": "github", "repo": "crussella0129/adv" } }
  },
  "enabledPlugins": { "adv@adv": true }
}
```

## Usage

Tokens are case-insensitive and separated by spaces.

| Command | What it does |
| --- | --- |
| `/adv` or `/adv status` | Show the current executor (main model) and advisor. |
| `/adv off` | Turn the advisor off. The main model stays as it is. |
| `/adv <advisor>` | Set only the advisor and keep the current executor. |
| `/adv <advisor> <executor>` | Set both. |
| `/adv <advisor> <executor> <task...>` | Set both, then send the task as a new prompt on the new pairing. |
| `/adv <advisor> -- <task...>` | `--` ends the model tokens, so the task's first word is never read as an executor. |
| `/adv api <advisor> <executor>` | Have Claude write Messages API, SDK or Managed Agents code for that pairing. |
| `/adv help` | Explain the command. |

Without `--`, the second token counts as the executor only if it parses as a model spec. Anything
whose first token is neither a model spec nor a keyword goes to the skill, which answers in prose.

### Model specs

A model spec is one token: an optional `claude-` prefix, a family (`fable`, `mythos`, `opus`,
`sonnet`, `haiku`), and an optional version such as `5.5`, `-5.5`, `-5-5` or `4.8`. A family on
its own means the latest model of that family. A versioned spec must exist in the catalog. The
executor may carry Claude Code's `[1m]` context-window suffix; it is dropped for advisors and for
the API.

| Alias | Resolves to |
| --- | --- |
| `fable` | `claude-fable-5-1` |
| `mythos` | `claude-mythos-5-1` |
| `opus` | `claude-opus-5-5` |
| `sonnet` | `claude-sonnet-5-5` |
| `haiku` | `claude-haiku-5-5` |

### Pairing rule

The advisor has to be Claude Sonnet 4.6 or more capable, and at least as capable as the executor.
Models of equal capability can advise each other. Some consequences:

- `/adv fable opus` is valid.
- `/adv opus fable` is not: a Fable 5.1 executor accepts only a Fable 5.1 or Mythos 5.1 advisor.
  `adv` explains this and suggests `/adv fable opus`.
- Claude Haiku 4.5 can be an executor but never an advisor.
- Claude Code ranks Fable 5 and Mythos 5 one step above Opus 5.5, so inside Claude Code an Opus
  advisor cannot advise a Fable 5 main model, even though the API allows it.

The full ranks, the pairing table, prices, and which advisors return readable advice are in
[skills/adv/references/models.md](skills/adv/references/models.md). The data behind them lives in
[skills/adv/assets/models.json](skills/adv/assets/models.json).

## How it works

What `/adv` can do depends on where you run it. Details and troubleshooting are in
[skills/adv/references/environments.md](skills/adv/references/environments.md).

- **Claude Code CLI and the desktop app's Code tab.** The plugin ships a mod (a hooks module) that
  handles `/adv` without spending model tokens. It validates the pair, runs `/model <executor>`
  and `/advisor <advisor>` for you, and then submits the task if you gave one and the advisor was
  set. Family names are passed as Claude Code aliases so they keep tracking the latest model.
- **Claude Code with mods turned off** (for example by managed policy). The skill runs instead. A
  skill cannot call built-in commands, so it checks the pair and tells you exactly what to type.
- **claude.ai chat.** Only the skill loads. Chat cannot attach an advisor and a skill cannot switch
  the chat model, so `adv` says so plainly, suggests picking the executor in the model menu, and
  gives you the Claude Code command and an API snippet. It never claims an advisor is running.
- **Cowork.** The skill loads, but `/advisor` support there is undocumented, so it points you to
  the Code tab.
- **API developers.** The skill and `scripts/resolve.py` produce the tool definition, SDK code,
  curl, or a Managed Agents config for the pairing.

To start a new session already paired, use `claude --model opus --advisor fable` (a hidden flag
that accepts an alias or a full ID).

## Requirements and limits

- **Provider.** The API advisor tool is in beta on the Claude API, Claude Platform on AWS and Claude
  Models on Google Cloud (Anthropic managed). It is not available on Amazon Bedrock, Google Cloud
  (Google managed) or Microsoft Foundry. In Claude Code, `/advisor` needs a first-party Anthropic
  login, or Claude Platform on AWS / Google Cloud (Anthropic managed) in recent releases (the
  official Claude Code docs still list Anthropic API only), plus feature-flag fetching:
  `DISABLE_TELEMETRY` keeps the advisor off.
- **Rollout.** Claude Code turns the advisor on through a server-side feature flag. If your session
  has no `/advisor` command, `adv` changes nothing and tells you why. Setting
  `CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1` force-enables it, and
  `CLAUDE_CODE_DISABLE_ADVISOR_TOOL` turns it off.
- **Fable credits.** On some plans a Fable advisor bills to usage credits and needs a one-time
  consent. Run `/model fable` once to review and enable it.
- **Encrypted advice.** Current-generation advisors (Fable 5.1, Mythos 5.1, Opus 5.5, Opus 5,
  Fable 5, Mythos 5, Sonnet 5.5, Haiku 5.5) return encrypted advice. The executor reads it, but you
  cannot. Opus 4.8, 4.7 and 4.6, Sonnet 5 and Sonnet 4.6 return plain text.
- **It persists.** Like typing `/model` and `/advisor` yourself, `/adv` saves the choice as your
  default for new sessions. In headless and desktop sessions `/model` lasts only for the session.
- **Changing an active advisor** is deferred by Claude Code until `/clear` or `/compact`. Turning
  the advisor on or off applies right away.
- **claude.ai chat cannot attach an advisor.** Use Claude Code or the API for the real thing.
- **One-shot `claude -p`** applies the pairing but can't chain a task after it. Use
  `claude -p --model opus --advisor fable "<task>"` there.

## API usage

`skills/adv/scripts/resolve.py` resolves a pairing and prints the advisor tool definition and
example code. It works offline from the bundled catalog and needs only the Python standard
library (an optional live check of the model list uses the official `anthropic` SDK if it is
installed).

```bash
python skills/adv/scripts/resolve.py fable opus
python skills/adv/scripts/resolve.py --help
```

`skills/adv/scripts/run.py` sends a task through the Messages API with the advisor tool attached.
It needs the official SDK and your own API key, and usage bills to your Claude Console account:

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...   # your key; never commit it or paste it into a chat
python skills/adv/scripts/run.py --help
```

The request it builds uses the beta header `advisor-tool-2026-03-01` and a tool entry like this:

```json
{ "type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1" }
```

See [skills/adv/references/api.md](skills/adv/references/api.md) for the full parameter reference
and [skills/adv/references/prompting.md](skills/adv/references/prompting.md) for when to use an
advisor and how to keep costs down.

## Repository layout

```text
.claude-plugin/
  plugin.json            plugin manifest
  marketplace.json       this repo is also the "adv" marketplace
hooks/
  hooks.json             registers the mod
  register.ts            the /adv mod for Claude Code
  catalog.ts             generated from models.json; do not edit by hand
skills/adv/
  SKILL.md               the skill (fallback path, claude.ai, API help)
  assets/models.json     canonical model catalog, ranks and pairing table
  references/            api.md, prompting.md, models.md, environments.md
  scripts/               advmodels.py, resolve.py, run.py
tests/                   Python unit tests and the mod test (adv.test.ts)
tools/
  sync_catalog.py        regenerates hooks/catalog.ts from models.json
  package_skill.py       builds dist/adv-skill.zip for "Upload a skill"
.github/workflows/ci.yml lint, tests, catalog check, packaging, release
```

## Development

```bash
python -m unittest discover -s tests -v   # Python tests (no network)
ruff format . && ruff check .             # formatting and lint
python tools/sync_catalog.py              # regenerate hooks/catalog.ts after editing models.json
python tools/sync_catalog.py --check      # fail if catalog.ts is stale (CI runs this)
python tools/package_skill.py             # build dist/adv-skill.zip
claude plugin validate . --strict         # validate the manifest, marketplace and skill
claude plugin test .                      # run the mod tests
claude --plugin-dir .                     # try the plugin from this checkout for one session
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to update the catalog when a new model ships.

## License

[MIT](LICENSE)

This is a community plugin. It is not made, endorsed or supported by Anthropic.
