# Prompting the executor and controlling cost

When the advisor pattern pays off, how to get the executor to consult at the right moments, and
how to keep advisor spend in check. Paraphrased from Anthropic's advisor-tool page; the measured
numbers are Anthropic's internal results, so re-measure on your own workload. For the verbatim
system-prompt blocks, follow the links (we do not copy them here).
Base page: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool>

## Contents

1. [When the pattern fits](#when-the-pattern-fits)
2. [The two timings that matter](#the-two-timings-that-matter)
3. [How the executor should treat advice](#how-the-executor-should-treat-advice)
4. [Haiku executors on coding work](#haiku-executors-on-coding-work)
5. [Opus executors that under-call](#opus-executors-that-under-call)
6. [Nudging on turn 2](#nudging-on-turn-2)
7. [Trimming advisor output](#trimming-advisor-output)
8. [Effort pairing](#effort-pairing)
9. [Cost control](#cost-control)
10. [Inside Claude Code](#inside-claude-code)

## When the pattern fits

Good fits:
- Long-horizon agentic work (coding agents, computer use, multi-step research) where most turns are
  routine but the plan decides success.
- A **Sonnet** executor on hard tasks: an Opus advisor tends to keep total cost about the same or
  lower; a Fable 5.1 advisor gives the biggest quality lift.
- A **Haiku** executor that needs more judgment: an Opus or Fable advisor costs more than Haiku
  alone but less than moving the whole loop to a bigger model.

Weak fits:
- Single-turn Q&A: there is nothing to plan.
- Pass-through model pickers where users already choose their own cost/quality trade-off.
- Work where every turn needs the strongest model anyway: just run that model.

Caveats: the gain depends on the executor actually consulting. Lowering executor effort or
prompting badly can drop the consult rate to near zero, and then the pair scores below the
executor alone. Benchmark the pair against the executor at higher effort and against the stronger
model alone before committing.

## The two timings that matter

Aim for roughly 2-3 consults on a coding task:

1. **Early**: after a little orientation (finding files, reading the relevant code, fetching
   sources) but **before** substantive work: writing, choosing an interpretation, or building on an
   assumption. Orientation alone does not need a consult.
2. **Final**: on hard tasks, once the result is durable (files written, tests run and their output
   in the transcript), before declaring done.

Also consult when stuck, or when about to change approach. If the executor has planning tools (a
todo list, say), have it consult before writing the plan. Verbatim wording:
[#suggested-system-prompt-for-coding-tasks](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#suggested-system-prompt-for-coding-tasks).

## How the executor should treat advice

- Give the advice real weight and follow it by default.
- Deviate when a step actually fails, or when primary evidence (a test result, the source itself)
  contradicts a claim in the advice.
- If what it found conflicts with the advice, it should not silently switch: it should state the
  conflict and consult once more so the advisor can reconcile it.

The second block in the docs section linked above words this for a system prompt.

## Haiku executors on coding work

Haiku 4.5 follows the default guidance conservatively. Anthropic's Haiku variant adds a hard rule:
the first file write, edit, or state-changing shell command must come after a consult (read-only
commands such as `ls`, `cat`, `grep`, `find` are exempt). It gained about 7.5 points on an internal
coding benchmark, but a close variant lost about 4 points on a browsing/comprehension benchmark
(n = 1,266). Use it for write-heavy work; keep the standard blocks for lookup-heavy mixes.
Wording: [#alternative-system-prompt-for-haiku-on-coding-workloads](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#alternative-system-prompt-for-haiku-on-coding-workloads).

## Opus executors that under-call

Opus usually consults at a sensible rate. If you see it skipping consults, an extra checkpoint for
design, architecture and risk questions (plus the same write-action rule) added about 7-10 points
on the under-calling tasks, but it made Opus over-call where no planning was needed, and the net
on a mixed workload was roughly flat. Add it only after you observe under-calling, never by default.
Wording: [#increasing-advisor-calls-on-opus-executors](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#increasing-advisor-calls-on-opus-executors).

## Nudging on turn 2

The nudge is aimed at **Haiku executors that under-call**: if a Haiku executor has not consulted by
its first assistant turn (`NUDGE_TURN = 2`), send a short plain-text reminder as its own user
message after the tool results (consecutive user messages are valid). The Sonnet and Opus rows below
are measured side effects, not targets. Measured effects:

| Executor | Effect of the nudge |
|---|---|
| Haiku 4.5 | about +7 points pass rate; 98% of nudged runs consulted at turn 2 |
| Sonnet | no measurable change (74% consulted at turn 2); timing guidance matters more |
| Opus | slightly worse: do not nudge |

- Where the executor's first consult normally lands at turn 7 or later, a turn-2 nudge went with a
  3-4 point drop. Measure the baseline first-consult turn and set `NUDGE_TURN` beyond it.
- On a browsing workload that already consulted 86% of the time, the nudge raised engagement at no
  cost.
- Skip it if the system prompt already tells the executor to be sparing with consults.
- It can push simple tasks into needless consults; `NUDGE_TURN = 3` is a gentler choice, and on
  mixed workloads you can gate the nudge on a complexity signal instead.

Loop details: [#mid-conversation-nudge-for-under-calling-executors](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#mid-conversation-nudge-for-under-calling-executors).

## Trimming advisor output

- **Soft limit**: the advisor responds better to a direct request than to a third-person
  description. Start the user message with a short parenthetical addressed to the advisor asking
  for guidance under N words. Ask for about **80% of your real ceiling** because it is soft. In
  testing this led to more consults, each shorter, and lower total cost.
- **Hard limit**: set the tool's `max_tokens`. **2048** is the suggested starting point.

| Tool `max_tokens` | Mean advisor output (hard reasoning benchmark, n = 40 each) | Consults truncated |
|---|---|---|
| unset | about 4,200-5,900 | n/a |
| 2048 | about 630-840 (about 7x less) | about 0% |
| 1024 | about 370-480 (about 10x less) | about 10% |

Accuracy differences were within noise. Those tasks run longer than the typical 1,400-1,800 tokens
per consult, so read the table as ratios. Combine soft and hard limits if you like.
See [#trimming-advisor-output-length](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#trimming-advisor-output-length)
and [#capping-advisor-output](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#capping-advisor-output).

## Effort pairing

For coding tasks, a Sonnet executor at **medium** effort with an Opus advisor reached about the intelligence of
Sonnet at default effort, for less money. For maximum quality keep the executor at default effort.

## Cost control

- Count consults on the client; at your ceiling, remove the advisor tool from `tools` (keep the beta
  header and the history). `max_uses` only caps one request.
- Cap each consult with `max_tokens` (2048) and/or the soft word limit.
- Enable advisor-side `caching` only for conversations expected to make 3+ consults, and never
  toggle it mid-conversation.
- Track spend from `usage.iterations` ([api.md](api.md#usage-and-billing)), not top-level `usage`.

## Inside Claude Code

Claude Code ships its own advisor tool description and guidance for the main model, so `/adv`
needs no extra prompting there: it only selects the executor (`/model`) and the advisor
(`/advisor`). To steer a particular task, say so in the task text ("check with the advisor before
editing anything"). Claude Code shows consults in the transcript (for example "Advising ... using
<model>"), and its picker recommends Sonnet as the main model with an Opus advisor
(`/adv opus sonnet`). The guidance on this page is for API and Managed Agents builders.
