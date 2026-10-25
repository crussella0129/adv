# Advisor tool: API reference

How to use the advisor tool from the Messages API, the SDKs and Claude Managed Agents.
Source of truth: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool>
(beta). This page restates the facts in our own words; the examples are ours. Model pairings and
prices are in [models.md](models.md), prompting advice in [prompting.md](prompting.md).

## Contents

1. [What it is and how a call flows](#what-it-is-and-how-a-call-flows)
2. [Request: beta header and tool definition](#request-beta-header-and-tool-definition)
3. [Examples: curl, Python, TypeScript](#examples-curl-python-typescript)
4. [Response shapes and error codes](#response-shapes-and-error-codes)
5. [Multi-turn conversations and pause_turn](#multi-turn-conversations-and-pause_turn)
6. [Forcing a consult with tool_choice](#forcing-a-consult-with-tool_choice)
7. [Streaming](#streaming)
8. [Usage and billing](#usage-and-billing)
9. [Caching](#caching)
10. [Combining with other tools and features](#combining-with-other-tools-and-features)
11. [Cost control](#cost-control)
12. [Platform availability](#platform-availability)
13. [Claude Managed Agents](#claude-managed-agents)
14. [Model compatibility](#model-compatibility)

## What it is and how a call flows

The request's top-level `model` is the **executor**: it does the work and writes almost all the
tokens. The tool's `model` is the **advisor**: a stronger model the executor can consult mid-turn
for a plan, a second opinion or a course correction. Everything happens inside one
`POST /v1/messages` (except when the turn pauses, see below).

1. The executor decides to consult and emits a `server_tool_use` block with `name: "advisor"` and
   `input: {}`. The input is always empty; the executor cannot pass a question in it.
2. Anthropic's servers run a separate inference on the advisor model. The advisor sees the whole
   transcript so far (system prompt, tool definitions, earlier turns, tool results and the
   executor's partial output for this turn) and answers under Anthropic's own advisor prompt.
3. The advisor has no tools and no context management. Its thinking is discarded; only its advice
   text goes back to the executor.
4. An `advisor_tool_result` block is inserted, and the executor carries on in the same response.

Since the advisor reads the transcript, the way to "ask it something" is to have the executor say
what it is unsure about in its own text just before calling.

## Request: beta header and tool definition

- Header: `anthropic-beta: advisor-tool-2026-03-01`. SDKs: `client.beta.messages.create(...,
  betas=["advisor-tool-2026-03-01"])`.
- Tool type `advisor_20260301`, name `advisor`.

| Field | Type | Default | Notes |
|---|---|---|---|
| `type` | string | required | `"advisor_20260301"` |
| `name` | string | required | `"advisor"` |
| `model` | string | required | Advisor model ID, e.g. `"claude-fable-5-1"`. Billed at that model's rates. Must pair with the executor ([models.md](models.md)), else 400 `invalid_request_error`. |
| `max_uses` | integer | unlimited | Cap on advisor calls **per request** (not per conversation). Extra calls get the `max_uses_exceeded` error result. |
| `max_tokens` | integer | advisor's own output limit | Cap on advisor output (thinking + text) **per call**. Minimum 1024; above the advisor's output limit is a 400. The advisor is told its remaining budget and shapes its answer to fit. |
| `caching` | object or null | `null` (off) | `{"type": "ephemeral", "ttl": "5m"}` or `"1h"`. An on/off switch for advisor-side prompt caching, not a breakpoint; the server picks the cache boundaries. |
| `cache_control`, `allowed_callers`, `defer_loading`, `strict` | | | Generic tool-definition properties, accepted as on other tools. |

Minimal definition:

```json
{"type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1", "max_tokens": 2048}
```

## Examples: curl, Python, TypeScript

The executors below (Opus 5.5, Sonnet 4.6) are steered by the prompt, never by forced
`tool_choice` (see [Forcing a consult](#forcing-a-consult-with-tool_choice)).

curl (key from the environment, never inline):

```bash
curl https://api.anthropic.com/v1/messages \
  -H "content-type: application/json" \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "anthropic-beta: advisor-tool-2026-03-01" \
  -d '{
    "model": "claude-opus-5-5",
    "max_tokens": 16000,
    "system": "Consult the advisor once you have looked around and before you change anything, and again before you finish.",
    "tools": [{"type": "advisor_20260301", "name": "advisor", "model": "claude-fable-5-1", "max_tokens": 2048}],
    "messages": [{"role": "user", "content": "Plan a zero-downtime migration from a single Postgres node to a primary/replica pair."}]
  }'
```

Python SDK (`pip install anthropic`; the client reads `ANTHROPIC_API_KEY`):

```python
import anthropic

client = anthropic.Anthropic()

ADVISOR = {"type": "advisor_20260301", "name": "advisor",
           "model": "claude-fable-5-1", "max_tokens": 2048}

response = client.beta.messages.create(
    model="claude-opus-5-5",                 # executor
    max_tokens=16000,
    betas=["advisor-tool-2026-03-01"],
    tools=[ADVISOR],
    messages=[{"role": "user", "content": "Review this design and propose the safest rollout: ..."}],
)

for block in response.content:
    if block.type == "text":
        print(block.text)
    elif block.type == "advisor_tool_result":
        advice = block.content
        if advice.type == "advisor_result":            # plaintext advisors only
            print("[advisor]", advice.text)
        elif advice.type == "advisor_redacted_result":  # Fable 5.1 lands here
            print("[advisor] (encrypted; the executor read it)")
        elif advice.type == "advisor_tool_result_error":
            print("[advisor error]", advice.error_code)
```

TypeScript SDK (`npm install @anthropic-ai/sdk`), with a plaintext advisor so the advice is readable:

```typescript
import Anthropic from "@anthropic-ai/sdk";

const client = new Anthropic(); // reads ANTHROPIC_API_KEY

const response = await client.beta.messages.create({
  model: "claude-sonnet-4-6", // executor
  max_tokens: 16000,
  betas: ["advisor-tool-2026-03-01"],
  tools: [{ type: "advisor_20260301", name: "advisor", model: "claude-opus-4-8", max_tokens: 2048 }],
  messages: [{ role: "user", content: "Find and fix the race in worker.go; explain the fix." }],
});

for (const block of response.content) {
  if (block.type !== "advisor_tool_result") continue;
  const advice = block.content;
  if (advice.type === "advisor_result") console.log("[advisor]", advice.text);
  else if (advice.type === "advisor_tool_result_error") console.log("[advisor error]", advice.error_code);
  else console.log("[advisor] encrypted");
}
```

## Response shapes and error codes

A successful consult adds two blocks to `content`:

```json
{"type": "server_tool_use", "id": "srvtoolu_01...", "name": "advisor", "input": {}}
{"type": "advisor_tool_result", "tool_use_id": "srvtoolu_01...",
 "content": {"type": "advisor_result", "text": "Start by ...", "stop_reason": "end_turn"}}
```

The block type is always `advisor_tool_result`; switch on **`content.type`**:

| `content.type` | Fields | When |
|---|---|---|
| `advisor_result` | `text`, `stop_reason`? | Plaintext advisors: Opus 4.8, Opus 4.7, Opus 4.6, Sonnet 5, Sonnet 4.6 |
| `advisor_redacted_result` | `encrypted_content`, `stop_reason`? | Encrypted advisors: Fable 5.1, Mythos 5.1, Opus 5.5, Sonnet 5.5, Opus 5, Fable 5, Mythos 5, Haiku 5.5 |
| `advisor_tool_result_error` | `error_code` | The consult failed |

- `stop_reason` is present only when the tool sets `max_tokens`; it is usually `end_turn` or
  `max_tokens`. On truncation the API appends a note to the advice saying it was cut at the cap
  (the executor sees it; your client sees it only for plaintext advisors).
- Encrypted advice cannot be read by the client. Send it back unchanged; the server decrypts it for
  the executor. Code that reads `.text` unconditionally gets nothing from a current-generation advisor.
- Executors Sonnet 5.5, Opus 5.5, Opus 5, Fable 5, Mythos 5, Fable 5.1 and Mythos 5.1 accept only
  encrypted advisors, so their advice is never readable.

An error result does not fail the request; the executor simply continues without advice.

| `error_code` | Cause |
|---|---|
| `max_uses_exceeded` | More calls in this request than the tool's `max_uses` |
| `too_many_requests` | The advisor call was rate-limited (it shares the advisor model's normal limits). An executor rate limit fails the whole request with HTTP 429 instead. |
| `overloaded` | Advisor model at capacity |
| `prompt_too_long` | The transcript is larger than the advisor's context window |
| `execution_time_exceeded` | The advisor call timed out |
| `model_not_found` | The advisor model is not available to you |
| `unavailable` | Any other failure |

## Multi-turn conversations and pause_turn

- Append the assistant's full `content` (including `server_tool_use` and `advisor_tool_result`
  blocks) to `messages` verbatim. Do not edit or strip advisor blocks.
- You may leave the advisor tool out of `tools` on a later turn while history still holds advisor
  blocks: the request is accepted and the executor just cannot consult that turn. The beta header
  is still required, or those history blocks are rejected. (Older reference copies claimed this was
  a 400; the live page says it is accepted.)
- Changing the advisor model mid-conversation is allowed; branch on `content.type` when reading.

`pause_turn` rules:

| Situation | What you get | What to send next |
|---|---|---|
| Executor called the advisor and the turn paused before the result | `stop_reason: "pause_turn"`, a `server_tool_use` with no result | Append the assistant message as-is and resend with the **same advisor tool** and beta header. No new user message. It may pause again. |
| Resuming a paused advisor call without the advisor tool | 400 `invalid_request_error` | Keep the tool until the dangling call completes |
| Advisor call and a client tool call in the same turn | `stop_reason: "tool_use"` | Send your `tool_result` blocks as usual; the pending advisor call runs first in the next request (keep the tool) |

Loop sketch (Python) with client tools, `pause_turn`, and a per-conversation advisor cap:

```python
def run(client, task, client_tools, run_tool, cap=4):
    messages = [{"role": "user", "content": task}]
    seen, pending = set(), False                    # advisor call ids; a call awaiting its result
    while True:
        # Keep the tool while under the cap, and always while a call is still pending.
        tools = client_tools + ([ADVISOR] if len(seen) < cap or pending else [])
        resp = client.beta.messages.create(
            model="claude-opus-5-5", max_tokens=16000,
            betas=["advisor-tool-2026-03-01"],      # keep sending it even after dropping the tool
            tools=tools, messages=messages)
        messages.append({"role": "assistant", "content": resp.content})
        calls = [b for b in resp.content if b.type == "server_tool_use" and b.name == "advisor"]
        answered = {b.tool_use_id for b in resp.content if b.type == "advisor_tool_result"}
        seen |= {b.id for b in calls}
        pending = any(b.id not in answered for b in calls)
        if resp.stop_reason == "pause_turn":
            continue                                # resend unchanged
        if resp.stop_reason == "tool_use":
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id, "content": run_tool(b)}
                for b in resp.content if b.type == "tool_use"]})
            continue
        return resp                                 # end_turn, max_tokens, refusal, ...
```

On `max_tokens` either retry with a higher limit or, if the turn has no `tool_use`, continue with a
new user message; prefilling a truncated turn is rejected on Claude 4.6 and later.

## Forcing a consult with tool_choice

`tool_choice: {"type": "tool", "name": "advisor"}` forces a consult on executors that allow it.

- Executors **Opus 5.5, Sonnet 5.5, Fable 5.1 and Mythos 5.1 reject `tool_choice` types `tool` and
  `any`** (400). For them, ask for the consult in the system prompt or a user message
  ([prompting.md](prompting.md)). `forced_tool_choice` in `assets/models.json` records this per model.
- Forcing any tool cannot be combined with manual extended thinking (`thinking: {"type":
  "enabled"}`); adaptive thinking is fine.

## Streaming

- The advisor's own inference does not stream. After the executor's advisor `server_tool_use` block
  closes (`content_block_stop`) the stream goes quiet.
- During the wait you get only SSE `ping` keepalives, roughly every 30 seconds (short consults may
  have none). Set client read timeouts accordingly.
- The `advisor_tool_result` arrives whole in a single `content_block_start` event with no deltas,
  then the executor resumes streaming.
- A following `message_delta` carries updated `usage.iterations` with the advisor's token counts.

## Usage and billing

`usage.iterations` lists every inference in the request, in order:

| `type` | Billed at | Fields |
|---|---|---|
| `message` | executor rates | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` |
| `advisor_message` | advisor rates | the same, plus `model` |

- Top-level `usage` counts the **executor only** (the sum of the `message` iterations). Bill from
  `iterations`.
- Input tokens summed over iterations exceed any one prompt, because each iteration re-reads the
  growing transcript.
- Typical consult: about 400-700 advice tokens, about 1,400-1,800 including advisor thinking. Hard
  reasoning tasks run much longer unless capped.
- The request's top-level `max_tokens` does not bound the advisor; use the tool's `max_tokens`.
  A task budget set for the executor does not cover advisor tokens either.
- Priority Tier is per model: advisor calls get it only if your org also has a commitment on the
  advisor model.

Cost accounting from `iterations` (prices per MTok from [models.md](models.md); cache multipliers
are the standard ones, 0.1x for reads and 1.25x / 2x for 5-minute / 1-hour writes):

```python
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-fable-5-1": (10.0, 50.0)}

def request_cost(resp, executor="claude-opus-5-5", write_mult=1.25):
    total = {"executor": 0.0, "advisor": 0.0}
    for it in resp.usage.iterations or []:
        role = "advisor" if it.type == "advisor_message" else "executor"
        inp, out = PRICES[it.model if role == "advisor" else executor]
        total[role] += (it.input_tokens * inp
                        + (it.cache_read_input_tokens or 0) * inp * 0.1
                        + (it.cache_creation_input_tokens or 0) * inp * write_mult
                        + it.output_tokens * out) / 1_000_000
    return total
```

## Caching

- **Executor side**: `advisor_tool_result` blocks are cacheable like any block; a `cache_control`
  breakpoint after them hits on later turns. The executor always sees plaintext advice, so this
  works the same for encrypted and plaintext advisors.
- **Advisor side**: set `caching` on the tool. Each consult writes a cache entry; later consults in
  the conversation read the stable prefix and pay full price only for the new part (non-zero
  `cache_read_input_tokens` on later `advisor_message` iterations).
- Break-even is about **3 consults per conversation**; with 2 or fewer the cache writes cost more
  than they save.
- Choose once per conversation. Switching `caching` on and off mid-conversation causes misses.
- `clear_thinking` caveat: if context editing keeps fewer than all thinking turns, the advisor's view
  of the transcript shifts every turn and its cache misses (a cost issue, not a quality one). Set
  `keep: "all"` when using advisor caching. Without an explicit `clear_thinking`, Opus 4.5+,
  Sonnet 4.6+ and Haiku 5.5 already keep all turns; older Opus/Sonnet and Haiku 4.5 and earlier
  default to keeping one thinking turn.

## Combining with other tools and features

The advisor sits in the same `tools` array as server tools (for example web search) and your own
client tools.

| Feature | Interaction |
|---|---|
| Message Batches | Supported; `usage.iterations` is reported per batch item |
| Token counting | `count_tokens` returns only the executor's first-iteration input. For an advisor estimate, call it again with `model` set to the advisor |
| Context editing | `clear_tool_uses` does not fully work with advisor blocks; see the `clear_thinking` caveat above |
| `pause_turn` | See [Multi-turn conversations and pause_turn](#multi-turn-conversations-and-pause_turn) |
| Zero data retention | Fable 5.1 is not available to ZDR orgs; see Anthropic's API and data retention page for how ZDR applies to the advisor |

## Cost control

- There is no built-in per-conversation limit (`max_uses` is per request). Count consults on the
  client and drop the advisor tool from `tools` once you reach your ceiling; history blocks can stay.
- Cap each consult with the tool's `max_tokens` (2048 is a good start) and/or ask for short advice
  in the prompt ([prompting.md](prompting.md#trimming-advisor-output)).
- Turn on `caching` only when you expect 3 or more consults in the conversation.
- Cost comes from the advisor rate times its tokens: a Fable 5.1 advisor costs 2.5x an Opus 5.5
  advisor per token.

## Platform availability

| Platform | Advisor tool |
|---|---|
| Claude API (Anthropic) | Beta |
| Claude Platform on AWS | Beta |
| Claude Models on Google Cloud, Anthropic-managed | Beta |
| Amazon Bedrock | Not available |
| Google Cloud Vertex AI (Google-managed) | Not available |
| Microsoft Foundry | Not available |

Mythos models are for Project Glasswing customers only, and Mythos 5.1 is not offered on Claude
Platform on AWS. Claude Code's `/advisor` has its own gating ([environments.md](environments.md)).

## Claude Managed Agents

Managed Agents (beta header `managed-agents-2026-04-01`) configure the advisor on the **agent**,
not as a tool. On the `multiagent_20261001` block it is the `advisor` member:

```python
agent = client.beta.agents.create(
    name="Repo maintainer",
    model="claude-opus-5-5",                       # executor
    system="You maintain this repository end to end.",
    tools=[{"type": "agent_toolset_20260401"}],
    multiagent={
        "type": "multiagent_20261001",
        "advisor": {"type": "enabled", "model": "claude-fable-5-1"},
        "workflows": {"type": "disabled"},          # omitted members default to enabled
        "subagents": {"type": "disabled"},
    },
)
```

- The advisor object has exactly `type` and `model`: no `max_uses`, `max_tokens` or `caching`.
- The older `coordinator` form takes the advisor as a roster entry instead:
  `"multiagent": {"type": "coordinator", "agents": [{"type": "advisor", "model": "claude-opus-5-5"}]}`
  (at most one advisor entry).
- Pairing is validated when the agent is saved (400 if invalid) with the same table as the tool.
- Only the session's primary thread can consult it. Each consult runs as a thread named
  `anthropic.advisor`; the advice arrives as an `agent.thread_message_received` event, not as an
  `advisor_tool_result`. Encrypted advisors deliver `[{"type": "redacted"}]` to clients.
- A failed consult never fails the agent's turn.

## Model compatibility

Rule: the advisor must be Claude Sonnet 4.6 or more capable, and at least as capable as the
executor (equals may advise each other). Invalid pairs return 400 `invalid_request_error`.
The full executor-to-advisor table, ranks, prices and which pairings give readable advice are in
[models.md](models.md).
