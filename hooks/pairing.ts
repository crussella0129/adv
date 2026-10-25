// Pure /adv logic: parse the arguments, resolve model specs against the
// catalog, check the advisor/executor pairing, and decide what to run.
// No engine calls here, so the rules are easy to read and to test.

import { CATALOG } from './catalog'

export type Family = keyof typeof CATALOG.latest
export type Role = 'advisor' | 'executor'
export type CatalogModel = (typeof CATALOG.models)[number]

export type Spec = {
  raw: string
  family: Family
  major?: number
  minor?: number
  // Claude Code's 1M-context suffix, `opus[1m]`: kept for the main model only.
  oneM: boolean
}

export type Resolved = {
  spec: Spec
  id: string
  model?: CatalogModel
  // What Claude Code is given: an alias where one exists, so the choice keeps
  // tracking the newest model of the family; a full ID otherwise.
  arg: string
  label: string
}

export type Parsed =
  | { kind: 'status' }
  | { kind: 'off' }
  | { kind: 'skill' }
  | { kind: 'pair'; advisor: Spec; executor?: Spec; task: string }

const SPEC = /^(?:claude-)?(fable|mythos|opus|sonnet|haiku)(?:[-_.]?(\d+)(?:[-_.](\d+))?)?(\[1m\])?$/i

const ADVISOR_ALIASES: readonly string[] = CATALOG.rules.claude_code_advisor_aliases
const MODEL_ALIASES: readonly string[] = CATALOG.rules.claude_code_model_aliases

export function parseSpec(token: string): Spec | undefined {
  const [, family, major, minor, oneM] = SPEC.exec(token.trim()) ?? []
  if (family === undefined) return undefined
  return {
    raw: token,
    family: family.toLowerCase() as Family,
    major: major === undefined ? undefined : Number(major),
    minor: minor === undefined ? undefined : Number(minor),
    oneM: oneM !== undefined,
  }
}

// Splits off one whitespace-delimited token, keeping the rest of the text as
// typed so a multi-line task survives intact.
function shift(text: string): [string | undefined, string] {
  const m = /^\s*(\S+)/.exec(text)
  if (!m) return [undefined, '']
  return [m[1], text.slice(m[0].length)]
}

export function parseArgs(args: string): Parsed {
  const [first, afterFirst] = shift(args)
  if (first === undefined) return { kind: 'status' }

  const word = first.toLowerCase()
  const isAlone = afterFirst.trim() === ''
  if (isAlone && word === 'status') return { kind: 'status' }
  if (isAlone && (word === 'off' || word === 'none')) return { kind: 'off' }

  const advisor = parseSpec(first)
  if (!advisor) return { kind: 'skill' }

  const [second, afterSecond] = shift(afterFirst)
  if (second === undefined) return { kind: 'pair', advisor, task: '' }
  if (second === '--') return { kind: 'pair', advisor, task: afterSecond.trim() }

  const executor = parseSpec(second)
  if (!executor) return { kind: 'pair', advisor, task: afterFirst.trim() }

  const [third, afterThird] = shift(afterSecond)
  const task = third === '--' ? afterThird : afterSecond
  return { kind: 'pair', advisor, executor, task: task.trim() }
}

export function modelById(id: string): CatalogModel | undefined {
  return CATALOG.models.find(m => m.id === id)
}

export function resolve(spec: Spec, role: Role): Resolved {
  const isFamilyOnly = spec.major === undefined
  const id = isFamilyOnly
    ? CATALOG.latest[spec.family]
    : `claude-${spec.family}-${spec.major}${spec.minor === undefined ? '' : `-${spec.minor}`}`
  const model = modelById(id)

  const aliases = role === 'advisor' ? ADVISOR_ALIASES : MODEL_ALIASES
  const base = isFamilyOnly && aliases.includes(spec.family) ? spec.family : id
  const arg = role === 'executor' && spec.oneM ? `${base}[1m]` : base

  const name = model?.display ?? id
  const label = isFamilyOnly ? `${spec.family} (latest: ${name})` : name
  return { spec, id, model, arg, label }
}

// Inside Claude Code the main model is checked with Claude Code's own ranks,
// which are stricter than the API's for Fable 5 and Mythos 5.
export function checkPair(advisor: Resolved, executor: Resolved | undefined): string | undefined {
  const min = CATALOG.rules.advisor_min_rank
  if (!advisor.model) return undefined
  if (advisor.model.claude_code_rank < min) {
    return `${advisor.model.display} can't be an advisor: the advisor has to be Claude Sonnet 4.6 or more capable.`
  }
  if (!executor?.model) return undefined
  if (executor.model.claude_code_rank > advisor.model.claude_code_rank) {
    const canSwap = isValid(executor.model, advisor.model)
    const hint = canSwap ? ` Did you mean /adv ${executor.spec.raw} ${advisor.spec.raw}?` : ''
    return (
      `${advisor.model.display} can't advise ${executor.model.display}: ` +
      `the advisor must be at least as capable as the executor.${hint}`
    )
  }
  return undefined
}

function isValid(advisor: CatalogModel, executor: CatalogModel): boolean {
  return (
    advisor.claude_code_rank >= CATALOG.rules.advisor_min_rank &&
    executor.claude_code_rank <= advisor.claude_code_rank
  )
}

export function unknownNote(r: Resolved): string | undefined {
  if (r.model) return undefined
  return `${r.id} isn't in this plugin's catalog (as of ${CATALOG.as_of}); Claude Code will check it.`
}

export function adviceNote(advisor: Resolved): string | undefined {
  if (advisor.model?.advice !== 'encrypted') return undefined
  return `${advisor.model.display} returns its advice encrypted: the executor reads it, you won't see the text.`
}

// Access caveats worth repeating at the moment someone picks the model.
export function accessNote(r: Resolved): string | undefined {
  if (r.spec.family !== 'fable' && r.spec.family !== 'mythos') return undefined
  return r.model?.note ?? undefined
}
