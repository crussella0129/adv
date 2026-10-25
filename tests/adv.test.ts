// Tests for the /adv mod. Run with `claude plugin test .` from the repo root.
// The hooks registered here sit beneath the plugin and stand for Claude Code:
// they record which built-in commands the mod ran and answer them.

import { expect, mock, test } from 'claude-code/testing'
import type { CommandInfo, CommandRunInput, On, SessionMessage } from 'claude-code'

type WorldOptions = {
  advisor?: string
  model?: string
  hasAdvisorCommand?: boolean
  advisorText?: (args: string) => string
  advisorRefuses?: boolean
  advisorSilent?: boolean
  messages?: SessionMessage[]
}

function world(on: On, options: WorldOptions = {}) {
  const ran: string[] = []
  const prompts: string[] = []
  const logs: string[] = []
  const state = { advisor: options.advisor, model: options.model ?? 'claude-opus-5-5' }
  const clock = mock.clock(on)

  const commands: CommandInfo[] = [{ name: 'model', description: 'model', source: 'builtin' }]
  if (options.hasAdvisorCommand !== false) {
    commands.push({ name: 'advisor', description: 'advisor', source: 'builtin' })
  }

  on('command.list', () => ({ value: commands }))
  on('session.model', () => ({ value: state.model }))
  on('session.messages', () => ({ value: options.messages ?? [] }))
  on('settings.read', () => ({
    value: state.advisor === undefined ? {} : { advisorModel: state.advisor },
  }))
  on('ui.log', (_$, e) => {
    logs.push(e.text)
    return { value: undefined }
  })
  on('prompt.submit', (_$, e) => {
    prompts.push(e.text)
    return { text: e.text }
  })
  on('command.run', (_$, e) => {
    ran.push(`/${e.command} ${e.args}`.trim())
    if (e.command === 'advisor') {
      if (options.advisorRefuses) return { text: 'Fable 5.1 as the advisor bills to usage credits.' }
      state.advisor = e.args === 'off' ? undefined : e.args
      if (options.advisorSilent) return {}
      return { text: options.advisorText?.(e.args) ?? `Advisor set to ${e.args}` }
    }
    if (e.command === 'model') {
      state.model = e.args
      return { text: `Set model to ${e.args}` }
    }
    return { text: 'the skill ran' }
  })

  return { ran, prompts, logs, state, clock }
}

// A typed `/<command> <args>` as Claude Code raises it from the prompt box.
function typed(args: string, command = 'adv:adv'): CommandRunInput {
  return {
    command,
    args,
    origin: { kind: 'composer' },
    presentation: { isFullscreen: false, columns: 100 },
  }
}

const ASSISTANT_TURN: SessionMessage = { role: 'assistant', text: 'hi', toolUses: [] }

test('/adv Fable Opus sets the executor, then the advisor, by alias', async ($, on) => {
  const w = world(on)

  const { text } = await $.command.run(typed('Fable Opus'))
  await w.clock.settle()

  expect(text).toContain('Executor → opus (latest: Claude Opus 5.5)')
  expect(text).toContain('advisor → fable (latest: Claude Fable 5.1)')
  expect(w.ran).toEqual(['/model opus', '/advisor fable'])
  expect(w.prompts).toEqual([])
})

test('a task after the pair starts once the advisor is in place', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('fable opus  fix the flaky\ntest'))
  await w.clock.settle()

  expect(w.ran).toEqual(['/model opus', '/advisor fable'])
  expect(w.prompts).toEqual(['fix the flaky\ntest'])
})

test('one model token sets only the advisor and the rest is the task', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('opus review this diff'))
  await w.clock.settle()

  expect(w.ran).toEqual(['/advisor opus'])
  expect(w.prompts).toEqual(['review this diff'])
})

test('-- ends the model tokens', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('fable -- opus is the word here'))
  await w.clock.settle()

  expect(w.ran).toEqual(['/advisor fable'])
  expect(w.prompts).toEqual(['opus is the word here'])
})

test('an advisor weaker than the executor is refused with a hint', async ($, on) => {
  const w = world(on)

  const { text } = await $.command.run(typed('opus fable'))
  await w.clock.settle()

  expect(text).toContain("Claude Opus 5.5 can't advise Claude Fable 5.1")
  expect(text).toContain('Did you mean /adv fable opus?')
  expect(w.ran).toEqual([])
})

test('Haiku 4.5 cannot be an advisor', async ($, on) => {
  const w = world(on)

  const { text } = await $.command.run(typed('haiku-4.5 haiku-4.5'))

  expect(text).toContain("Claude Haiku 4.5 can't be an advisor")
  expect(w.ran).toEqual([])
})

test('versions, haiku and [1m] map to the arguments Claude Code takes', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('opus-4.8 haiku'))
  await w.clock.settle()
  await $.command.run(typed('Claude-Sonnet-5-5 haiku-4.5'))
  await w.clock.settle()
  await $.command.run(typed('fable opus[1m]'))
  await w.clock.settle()

  expect(w.ran).toEqual([
    '/model haiku',
    '/advisor claude-opus-4-8',
    '/model claude-haiku-4-5',
    '/advisor claude-sonnet-5-5',
    '/model opus[1m]',
    '/advisor fable',
  ])
})

test('haiku as an advisor goes by its full ID', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('haiku haiku-4.5'))
  await w.clock.settle()

  expect(w.ran).toEqual(['/model claude-haiku-4-5', '/advisor claude-haiku-5-5'])
})

test('anything that is not a model goes on to the skill', async ($, on) => {
  const w = world(on)

  const api = await $.command.run(typed('api fable opus'))
  const help = await $.command.run(typed('help'))

  expect(api.text).toBe('the skill ran')
  expect(help.text).toBe('the skill ran')
  expect(w.ran).toEqual(['/adv:adv api fable opus', '/adv:adv help'])
})

test('without an /advisor command nothing changes and it says why', async ($, on) => {
  const w = world(on, { hasAdvisorCommand: false })

  const { text } = await $.command.run(typed('fable opus do it'))
  await w.clock.settle()

  expect(text).toContain('has no /advisor command')
  expect(text).toContain('CLAUDE_CODE_ENABLE_EXPERIMENTAL_ADVISOR_TOOL=1')
  expect(w.ran).toEqual([])
  expect(w.prompts).toEqual([])
})

test('the task waits when the advisor was not set', async ($, on) => {
  const w = world(on, { advisorRefuses: true })

  await $.command.run(typed('fable opus do it'))
  await w.clock.settle()

  expect(w.prompts).toEqual([])
  expect(w.logs.join('\n')).toContain('the task was not started')
})

test('a silent /advisor is confirmed through the settings', async ($, on) => {
  const w = world(on, { advisorSilent: true })

  await $.command.run(typed('fable opus do it'))
  await w.clock.settle()

  expect(w.prompts).toEqual(['do it'])
})

test('the task waits when Claude Code defers the advisor change', async ($, on) => {
  const deferred = (args: string) =>
    `Advisor set to ${args}. The current conversation keeps opus as its advisor model until /clear or /compact.`
  const w = world(on, { advisor: 'opus', advisorText: deferred, messages: [ASSISTANT_TURN] })

  await $.command.run(typed('fable opus do it'))
  await w.clock.settle()

  expect(w.prompts).toEqual([])
  expect(w.logs.join('\n')).toContain('Run /clear, then send the task')
})

test('/adv off turns the advisor off', async ($, on) => {
  const w = world(on, { advisor: 'fable' })

  const { text } = await $.command.run(typed('OFF'))
  await w.clock.settle()

  expect(text).toContain('Turning the advisor off')
  expect(w.ran).toEqual(['/advisor off'])
  expect(w.state.advisor).toBeUndefined()
})

test('/adv alone shows the current pairing', async ($, on) => {
  const w = world(on, { advisor: 'fable', model: 'claude-opus-5-5' })

  const { text } = await $.command.run(typed(''))

  expect(text).toContain('Executor (main model): claude-opus-5-5')
  expect(text).toContain('Advisor: fable (latest fable: Claude Fable 5.1')
  expect(w.ran).toEqual([])
})

test('the bare /adv alias is handled the same way', async ($, on) => {
  const w = world(on)

  await $.command.run(typed('sonnet haiku', 'adv'))
  await w.clock.settle()

  expect(w.ran).toEqual(['/model haiku', '/advisor sonnet'])
})
