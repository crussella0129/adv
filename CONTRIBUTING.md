# Contributing

Issues and pull requests are welcome at https://github.com/crussella0129/adv.

## When Anthropic ships a new model

`skills/adv/assets/models.json` is the single source of truth. Everything else is derived from it.

1. Edit `skills/adv/assets/models.json`: add the model entry (`rank`, `claude_code_rank`, `advice`,
   prices), update `latest` if the family has a new newest model, update `pairing_table`, and bump
   `as_of`. Take the facts from the
   [advisor tool docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/advisor-tool#model-compatibility)
   and the [models overview](https://platform.claude.com/docs/en/about-claude/models/overview).
2. Regenerate the mod's catalog: `python tools/sync_catalog.py`.
3. Update the human tables in `skills/adv/references/models.md` if they changed.
4. Run the tests (below).
5. Bump `version` in `.claude-plugin/plugin.json` (it is the only place the version lives) and add
   an entry to `CHANGELOG.md`.

## Tests and checks

```bash
python -m unittest discover -s tests -v
python tools/sync_catalog.py --check
python tools/package_skill.py
claude plugin validate . --strict
claude plugin test .
```

## Style

- Python: `ruff format .` and `ruff check .` (configuration in `pyproject.toml`). The scripts under
  `skills/adv/scripts/` use only the standard library, except for the optional `anthropic` SDK.
- Keep `skills/adv/SKILL.md` frontmatter to the Agent Skills spec keys so the folder can be
  uploaded to claude.ai as-is; `tools/package_skill.py` enforces this.
- Paraphrase Anthropic's documentation rather than copying it, and link to the source for prompt
  text. Never commit API keys.
