// The /adv mod: makes `/adv <advisor> [executor] [task…]` take effect in
// Claude Code by running the built-in /model and /advisor commands for you.
//
// The skill (skills/adv/SKILL.md) owns the /adv name; this module answers its
// command before the skill's prompt is sent, so configuring a pairing costs no
// model tokens. Anything it does not handle (`/adv api …`, `/adv help`, plain
// language) goes on to the skill. Surfaces without mods (claude.ai chat) get
// the skill alone.

import type { EngineInterface, Hook, Register } from 'claude-code'

import { CATALOG } from './catalog'
import {
  accessNote,
  adviceNote,
  checkPair,
  parseArgs,
  resolve,
  unknownNote,
  type Resolved,
} from './pairing'

const HINT ='<advisor> [executor] [task…]  |  off  |  status  |  api <advisor> <executor>'
const USAGE =
  'Usage: /adv <advisor> [executor] [task…]  e.g. /adv fable opus\n' +
  '       /adv off  ·  /adv status  ·  /adv api <advisor> <executor> (API code)'

type Step = { command: 'model' | 'advisor'; args: string }

// The skill's command is `adv:adv`; `/adv` is its bare alias, which the engine
// folds into `adv:adv`. Both are matched in case a build reports the alias.
export const register: Register = on => {
  on('command.describe', { command: 'adv:adv' }, describeAdv)
  on('command.describe', { command: 'adv' }, describeAdv)

  // A failing hook falls through to the skill rather than losing the command.
  on('command.run', { command: 'adv:adv' }, runAdv).catch(($, e, next) => next(e))
  on('command.run', { command: 'adv' }, runAdv).catch(($, e, next) => next(e))
}

const describeAdv: Hook<'command.describe'> = async ($, e, next) => ({
  ...(await next(e)),
  argumentHint: HINT,
})

const runAdv: Hook<'command.run'> = async ($, e, next) => {
  const parsed = parseArgs(e.args)
  if (parsed.kind === 'skill') return next(e)
  if (parsed.kind === 'status') return { text: await status($) }

  if (!(await hasCommand($, 'advisor'))) return { text: unavailable() }

  if (parsed.kind === 'off') {
    $.clock.after(0, () => void apply($, [{ command: 'advisor', args: 'off' }], ''))
    return { text: 'Turning the advisor off.' }
  }

  const advisor = resolve(parsed.advisor, 'advisor')
  const executor = parsed.executor && resolve(parsed.executor, 'executor')
  const problem = checkPair(advisor, executor)
  if (problem) return { text: `${problem} Nothing changed.\n${USAGE}` }

  const steps: Step[] = []
  if (executor) steps.push({ command: 'model', args: executor.arg })
  steps.push({ command: 'advisor', args: advisor.arg })
  $.clock.after(0, () => void apply($, steps, parsed.task))

  return { text: announce(advisor, executor, parsed.task) }
}

async function hasCommand($: EngineInterface, name: string): Promise<boolean> {
  const commands = await $.command.list()
  return commands.some(c => c.name === name)
}

// Runs the built-in commands in order, once the session is idle, and starts the
// task only when the advisor is really in place for it.
async function apply($: EngineInterface, steps: Step[], task: string): Promise<void> {
  const before = await advisorSetting($)
  let advisorSaid = ''

  for (const step of steps) {
    try {
      const { text = '' } = await $.command.run(step)
      if (step.command === 'advisor') advisorSaid = text
    } catch (err) {
      $.ui.log(`/${step.command} ${step.args} did not run: ${messageOf(err)}`)
      return
    }
  }
  if (!task) return

  const wanted = steps.find(s => s.command === 'advisor')?.args
  if (!(await advisorTookEffect($, advisorSaid, wanted))) {
    $.ui.log('The advisor was not set (see the /advisor output above), so the task was not started.')
    return
  }

  // Claude Code keeps an advisor the conversation has already used until
  // /clear or /compact; turning one on in a fresh conversation applies at once.
  const messages = await $.session.messages()
  const hasModelTurns = Array.isArray(messages) && messages.some(m => m.role === 'assistant')
  const isDeferred = /until \/clear or \/compact/.test(advisorSaid)
  if (isDeferred || (before !== undefined && before !== wanted && hasModelTurns)) {
    $.ui.log(
      'This conversation keeps its previous advisor until /clear or /compact, ' +
        'so the task was not started. Run /clear, then send the task.',
    )
    return
  }

  try {
    await $.prompt.submit({ text: task, asUser: true })
  } catch (err) {
    // `claude -p` runs one prompt and binds no session a plugin can submit to.
    $.ui.log(`The pairing is set, but the task could not be started here (${messageOf(err)}). Send it yourself.`)
  }
}

// /advisor prints "Advisor set to <model>" when it took the choice. Where a
// build prints nothing, the settings are the witness; they can lag a moment
// behind the command, so a mismatch there errs on the side of not starting.
async function advisorTookEffect(
  $: EngineInterface,
  said: string,
  wanted: string | undefined,
): Promise<boolean> {
  if (/^Advisor set to /m.test(said)) return true
  if (said.trim() !== '') return false
  return wanted !== undefined && (await advisorSetting($)) === wanted
}

// The advisor as the merged settings hold it: /advisor writes it to the user
// settings and to the session's own layer, which outranks the files.
async function advisorSetting($: EngineInterface): Promise<string | undefined> {
  const settings: Record<string, unknown> = await $.settings.read()
  const value = settings.advisorModel
  return typeof value === 'string' && value !== '' && value !== 'off' ? value : undefined
}

async function status($: EngineInterface): Promise<string> {
  const model = await $.session.model()
  const advisor = await advisorSetting($)
  const lines = [`Executor (main model): ${model}`, `Advisor: ${advisor ? describe(advisor) : 'off'}`]
  if (!(await hasCommand($, 'advisor'))) lines.push(unavailable())
  lines.push(USAGE)
  return lines.join('\n')
}

function describe(arg: string): string {
  const family = arg as keyof typeof CATALOG.latest
  const latest = CATALOG.latest[family]
  if (!latest) return arg
  const display = CATALOG.models.find(m => m.id === latest)?.display ?? latest
  return `${arg} (latest ${family}: ${display} as of ${CATALOG.as_of})`
}

function announce(advisor: Resolved, executor: Resolved | undefined, task: string): string {
  const head = executor
    ? `Executor → ${executor.label}, advisor → ${advisor.label}.`
    : `Advisor → ${advisor.label}; the executor stays your current model.`
  const notes = [
    executor && unknownNote(executor),
    unknownNote(advisor),
    executor && accessNote(executor),
    accessNote(advisor),
    adviceNote(advisor),
    task ? 'The task starts once the pairing is in place.' : undefined,
  ].filter((n): n is string => Boolean(n))
  return [head, ...notes.map(n => `  · ${n}`)].join('\n')
}

function unavailable(): string {
  return [
    "This session has no /advisor command, so nothing changed. Claude Code's advisor needs:",
    '  · the Anthropic API, Claude Platform on AWS, or Claude on Google Cloud (Anthropic-managed);',
    '    not Bedrock, Vertex AI or Foundry',
    '  · the feature turned on for your account (rolling out), or',
    '    CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1 in your environment',
    '  · CLAUDE_CODE_DISABLE_ADVISOR_TOOL and CLAUDE_CODE_DISABLE_EXPERIMENTAL_BETAS unset',
    'For the API instead, try: /adv api <advisor> <executor>',
  ].join('\n')
}

function messageOf(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}
