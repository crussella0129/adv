# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-25

### Added

- `/adv <advisor> [executor] [task...]` command that pairs an advisor model with an executor
  model, plus `/adv status`, `/adv off`, `/adv help`, `/adv api` and the `--` task separator.
- Family aliases (`fable`, `mythos`, `opus`, `sonnet`, `haiku`) that resolve to the latest model
  of each family, and versioned specs such as `opus-4.8`.
- Pairing checks against the advisor tool's compatibility rules, with Claude Code's own ranks used
  inside Claude Code.
- Claude Code mod that runs `/model` and `/advisor` for you and optionally submits a task.
- Skill fallback for Claude Code with mods disabled, claude.ai chat, Cowork and API developers.
- Model catalog (`skills/adv/assets/models.json`) and references for the API, prompting, models
  and environments.
- `resolve.py` and `run.py` scripts for API users.
- Marketplace manifest, CI, and a packaged skill zip for claude.ai "Upload a skill".

[Unreleased]: https://github.com/crussella0129/adv/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/crussella0129/adv/releases/tag/v0.1.0
