"""Build dist/adv-skill.zip for claude.ai "Upload a skill".

The zip's single top-level entry is the skill folder (adv/) holding SKILL.md,
references/, scripts/ and assets/. Before packaging, the SKILL.md frontmatter is
checked against the Agent Skills spec: only the keys name, description, license,
compatibility, metadata and allowed-tools are allowed, and name must equal the
folder name. Exits 1 if SKILL.md is missing or the frontmatter fails a check.

Usage:
    python tools/package_skill.py
    python tools/package_skill.py --skill-dir path/to/skill --out path/to/out.zip
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SKILL_DIR = REPO / "skills" / "adv"
DEFAULT_OUT = REPO / "dist" / "adv-skill.zip"

SPEC_KEYS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
SUBDIRS = ("references", "scripts", "assets")
EXCLUDED_DIRS = {"__pycache__"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
KEY_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*:(.*)$")
# Fixed timestamp so repeated builds of the same tree give the same zip.
ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def read_frontmatter(skill_md: Path) -> dict[str, str]:
    """Return the top-level keys of the YAML frontmatter mapped to their raw scalar text."""
    lines = skill_md.read_text(encoding="utf-8-sig").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("SKILL.md does not start with a '---' frontmatter block")
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration:
        raise ValueError("SKILL.md frontmatter has no closing '---'") from None
    keys: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#") or line[0] in " \t-":
            continue  # blank, comment, or nested/continuation line
        match = KEY_RE.match(line)
        if not match:
            raise ValueError(f"cannot parse frontmatter line: {line!r}")
        key, value = match.group(1), match.group(2).strip()
        if key in keys:
            raise ValueError(f"duplicate frontmatter key: {key}")
        keys[key] = value.strip("'\"")
    return keys


def check_frontmatter(skill_dir: Path) -> list[str]:
    """Return a list of problems with the skill's frontmatter (empty when it is valid)."""
    try:
        keys = read_frontmatter(skill_dir / "SKILL.md")
    except ValueError as exc:
        return [str(exc)]
    problems = []
    extra = sorted(set(keys) - SPEC_KEYS)
    if extra:
        problems.append(
            "frontmatter keys outside the Agent Skills spec: "
            + ", ".join(extra)
            + f" (allowed: {', '.join(sorted(SPEC_KEYS))})"
        )
    name = keys.get("name", "")
    if not name:
        problems.append("frontmatter has no name")
    elif name != skill_dir.name:
        problems.append(f"name {name!r} does not match the folder name {skill_dir.name!r}")
    elif not NAME_RE.match(name) or len(name) > 64:
        problems.append(f"name {name!r} must be 1-64 lowercase letters, digits and single hyphens")
    if not keys.get("description"):
        problems.append("frontmatter has no description")
    return problems


def collect_files(skill_dir: Path) -> list[Path]:
    """SKILL.md plus every file under the packaged subfolders, minus caches."""
    files = [skill_dir / "SKILL.md"]
    for sub in SUBDIRS:
        root = skill_dir / sub
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            rel_parts = path.relative_to(skill_dir).parts
            if not path.is_file() or EXCLUDED_DIRS.intersection(rel_parts):
                continue
            if path.suffix in EXCLUDED_SUFFIXES:
                continue
            files.append(path)
    return files


def build(skill_dir: Path, out: Path) -> list[str]:
    """Write the zip and return the archive names it contains."""
    out.parent.mkdir(parents=True, exist_ok=True)
    names = []
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in collect_files(skill_dir):
            arcname = f"{skill_dir.name}/{path.relative_to(skill_dir).as_posix()}"
            info = zipfile.ZipInfo(arcname, date_time=ZIP_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
            names.append(arcname)
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skill-dir", type=Path, default=DEFAULT_SKILL_DIR, help="skill folder")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output zip path")
    args = parser.parse_args(argv)

    skill_dir = args.skill_dir.resolve()
    if not (skill_dir / "SKILL.md").is_file():
        print(
            f"error: {skill_dir / 'SKILL.md'} not found; nothing to package",
            file=sys.stderr,
        )
        return 1
    problems = check_frontmatter(skill_dir)
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    names = build(skill_dir, args.out)
    print(f"wrote {args.out} ({len(names)} files, top-level folder {skill_dir.name}/)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
