"""CLI commands for Agent Skills v1.0 (markdown instructions surfaced via ``SkillsManager``)."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from typing import Any

import click

from leagent.cli.utils import (
    console,
    create_table,
    print_dim,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    status_badge,
)
from leagent.config.constants import LEAGENT_HOME


SKILLS_DIR = LEAGENT_HOME / "skills"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_skill_config_path() -> Path:
    return LEAGENT_HOME / "skills.yaml"


def _load_skill_config() -> dict[str, Any]:
    import yaml

    config_path = _get_skill_config_path()
    if not config_path.exists():
        return {"enabled": [], "disabled": [], "settings": {}}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {"enabled": [], "disabled": [], "settings": {}}


def _save_skill_config(config: dict[str, Any]) -> None:
    import yaml

    config_path = _get_skill_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)


def _iter_installed_skills() -> list[dict[str, Any]]:
    """Enumerate every installed skill via the manager (SKILL.md only)."""
    from leagent.skills.manager import SkillsManager

    manager = SkillsManager(
        skills_dir=SKILLS_DIR,
        load_builtin=True,
        enable_hot_reload=False,
    )
    asyncio.run(manager.load_all())

    rows: list[dict[str, Any]] = []
    for skill in manager.all_skills:
        origin = manager.origin_of(skill.name)
        rows.append(
            {
                "name": skill.name,
                "version": skill.version,
                "description": skill.description,
                "source": skill.source.value,
                "scope": origin.scope if origin else skill.source.value,
                "origin": origin.origin if origin else "leagent",
                "path": str(skill.path) if skill.path else "",
                "resources": len(skill.manifest.resources),
                "scripts": len(skill.manifest.scripts),
                "category": skill.manifest.category,
                "tags": skill.manifest.tags,
                "license": skill.manifest.license or "",
                "compatibility": skill.manifest.compatibility or "",
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Click group
# ---------------------------------------------------------------------------


@click.group(name="skills")
def skills_group() -> None:
    """Agent Skills v1 bundles (``SKILL.md``) discovered like the web agent (builtin + home + project)."""


@skills_group.command(name="list")
@click.option("--all", "-a", "show_all", is_flag=True, help="Show all skills including disabled.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def list_skills(show_all: bool, as_json: bool) -> None:
    """List installed skills from every configured source."""
    skills = _iter_installed_skills()
    config = _load_skill_config()
    disabled = set(config.get("disabled", []))

    if as_json:
        console.print_json(data=skills)
        return

    if not skills:
        print_info("No skills installed.")
        print_dim("Install skills with: leagent skills install <name>")
        print_dim("Create a skill with: leagent skills init <name>")
        return

    console.print()
    console.rule("[bold cyan]Skills[/]")
    console.print()

    table = create_table(columns=[
        ("Name", {"style": "cyan"}),
        ("Version", {}),
        ("Origin", {}),
        ("Scope", {}),
        ("R/S", {}),
        ("Description", {}),
        ("Status", {}),
    ])

    for skill in sorted(skills, key=lambda s: s.get("name", "")):
        name = skill.get("name", "unknown")
        is_disabled = name in disabled
        if not show_all and is_disabled:
            continue
        badge = status_badge("disabled" if is_disabled else "enabled")
        origin = skill.get("origin", "-")
        scope = skill.get("scope", "-")
        rs = f"{skill.get('resources', 0)}/{skill.get('scripts', 0)}"
        table.add_row(
            name,
            skill.get("version", "-"),
            origin,
            scope,
            rs,
            (skill.get("description") or "")[:40],
            badge,
        )

    console.print(table)
    console.print()
    print_dim(f"User skills directory: {SKILLS_DIR}")
    console.print()


@skills_group.command(name="init")
@click.argument("name", default="my-skill")
@click.option("--output", "-o", default=None, help="Output directory (default: ~/.leagent/skills/).")
def init_skill(name: str, output: str | None) -> None:
    """Scaffold a new skill directory with a v1.0-compliant SKILL.md."""
    import re

    if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
        print_error("Name must match ^[a-z0-9]+(-[a-z0-9]+)*$ (lowercase letters, digits, hyphens).")
        raise click.Abort()

    target_dir = Path(output) / name if output else SKILLS_DIR / name

    if target_dir.exists():
        print_warning(f"Skill directory already exists: {target_dir}")
        if not prompt_confirm("Overwrite?"):
            return
        shutil.rmtree(target_dir)

    target_dir.mkdir(parents=True, exist_ok=True)
    skill_md = target_dir / "SKILL.md"
    display = name.replace("-", " ").title()
    skill_md.write_text(
        "---\n"
        f"name: {name}\n"
        "description: TODO - describe what this skill does AND when to use it (<=1024 chars).\n"
        "license: MIT\n"
        "metadata:\n"
        "  version: 1.0.0\n"
        "  category: general\n"
        "  tags: []\n"
        "---\n\n"
        f"# {display}\n\n"
        "Write instructions for the agent here in imperative form.\n\n"
        "## When to use\n"
        "Describe the scenarios this skill is meant for.\n\n"
        "## Steps\n"
        "1. Step one\n"
        "2. Step two\n",
        encoding="utf-8",
    )

    print_success(f"Skill scaffolded at: {target_dir}")
    print_dim(f"  Edit {skill_md} to add your skill instructions.")


@skills_group.command(name="show")
@click.argument("name")
def show_skill(name: str) -> None:
    """Show detailed information about a skill."""
    from leagent.skills.markdown_loader import parse_skill_markdown
    from rich.markdown import Markdown

    skills = _iter_installed_skills()
    info = next((s for s in skills if s.get("name") == name), None)
    if not info:
        print_error(f"Skill '{name}' not found.")
        raise click.Abort()

    skill_path = Path(info["path"]) if info.get("path") else None
    console.print()
    console.rule(f"[bold cyan]Skill: {info['name']}[/]")
    console.print()
    console.print(f"  [bold]Version:[/]        {info.get('version', '-')}")
    console.print(f"  [bold]Origin:[/]         {info.get('origin', '-')} ({info.get('scope', '-')})")
    console.print(f"  [bold]Path:[/]           {skill_path or '-'}")
    if info.get("description"):
        console.print(f"  [bold]Description:[/]    {info['description']}")
    if info.get("license"):
        console.print(f"  [bold]License:[/]        {info['license']}")
    if info.get("compatibility"):
        console.print(f"  [bold]Compatibility:[/]  {info['compatibility']}")
    if info.get("tags"):
        console.print(f"  [bold]Tags:[/]           {', '.join(info['tags'])}")
    console.print(f"  [bold]Resources:[/]      {info.get('resources', 0)}")
    console.print(f"  [bold]Scripts:[/]        {info.get('scripts', 0)}")

    if skill_path and (skill_path / "SKILL.md").exists():
        content = (skill_path / "SKILL.md").read_text(encoding="utf-8")
        _meta, body = parse_skill_markdown(content)
        console.print()
        console.print("[bold]Content:[/]")
        console.print(Markdown(body[:3000]))
    console.print()


@skills_group.command(name="validate")
@click.argument("path", type=click.Path(exists=True))
def validate_skill(path: str) -> None:
    """Validate a skill directory against the v1.0 spec."""
    from leagent.skills.loader import SkillLoadError, SkillLoader, SkillValidationError
    from leagent.skills.base import SkillSource

    skill_path = Path(path)
    if not skill_path.is_dir():
        print_error("Path must be a directory.")
        raise click.Abort()

    loader = SkillLoader(skill_path.parent, source=SkillSource.LOCAL)

    async def _run() -> None:
        try:
            await loader.load_skill(skill_path)
        except SkillValidationError as exc:
            print_warning(f"Validation found {len(exc.errors)} issue(s):")
            for err in exc.errors:
                console.print(f"  [yellow]•[/] {err}")
            raise click.Abort()
        except SkillLoadError as exc:
            print_error(str(exc))
            raise click.Abort()

    asyncio.run(_run())
    print_success(f"Skill at '{skill_path}' is valid.")


@skills_group.command(name="package")
@click.argument("skill_dir", type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.option(
    "--output",
    "-o",
    "output_path",
    default=None,
    help="Output .zip path (default: <skill_dir>.zip in the current directory).",
)
def package_skill_cmd(skill_dir: str, output_path: str | None) -> None:
    """Build a v1.0–compliant .zip of a skill directory (single top-level folder in archive)."""
    from leagent.skills.packaging import SkillPackageError, build_skill_zip

    src = Path(skill_dir).resolve()
    if not src.is_dir():
        print_error("Path must be a directory.")
        raise click.Abort()

    out = Path(output_path).resolve() if output_path else Path.cwd() / f"{src.name}.zip"
    if out.suffix.lower() != ".zip":
        out = out.with_suffix(".zip")

    try:
        data = build_skill_zip(src)
    except SkillPackageError as exc:
        print_error(str(exc))
        raise click.Abort()

    out.write_bytes(data)
    print_success(f"Wrote {out} ({len(data)} bytes)")


@skills_group.command(name="lint")
def lint_skills() -> None:
    """Validate every installed skill and summarise violations."""
    from leagent.skills.base import SkillSource
    from leagent.skills.discovery import collect_discovery_roots
    from leagent.skills.loader import SkillLoader

    from leagent.skills.bundled import BUILTIN_DIR

    try:
        from leagent.cli.config_cmd import find_project_dir
        project_dir = find_project_dir()
        project_root = project_dir.parent if project_dir else None
    except Exception:  # noqa: BLE001
        project_root = None

    roots = collect_discovery_roots(
        leagent_home=LEAGENT_HOME,
        project_dir=project_root,
        builtin_dir=BUILTIN_DIR,
    )

    issues: list[tuple[str, Path, str]] = []
    successes = 0

    async def _run() -> None:
        nonlocal successes
        for root in roots:
            loader = SkillLoader(root.path, source=root.source)
            for subdir in sorted(root.path.iterdir()):
                if not subdir.is_dir() or subdir.name.startswith((".", "_")):
                    continue
                if not (subdir / "SKILL.md").exists():
                    continue
                try:
                    await loader.load_skill(subdir)
                    successes += 1
                except Exception as exc:  # noqa: BLE001
                    issues.append((subdir.name, subdir, str(exc)))

    asyncio.run(_run())

    console.print()
    console.rule("[bold cyan]Skill Lint Report[/]")
    console.print(f"  Valid: {successes}   Failing: {len(issues)}")
    console.print()

    if issues:
        table = create_table(columns=[
            ("Name", {"style": "cyan"}),
            ("Path", {}),
            ("Issue", {"style": "yellow"}),
        ])
        for name, path, reason in issues:
            table.add_row(name, str(path), reason)
        console.print(table)
        console.print()
        raise click.Abort()


@skills_group.command(name="migrate")
@click.argument("path", type=click.Path(exists=True, file_okay=False), required=False)
@click.option("--apply", is_flag=True, help="Write SKILL.md files (without this flag only prints).")
def migrate_legacy(path: str | None, apply: bool) -> None:
    """Convert legacy skill.yaml manifests to SKILL.md (v1.0)."""
    import yaml

    root = Path(path) if path else SKILLS_DIR
    if not root.exists():
        print_info(f"No skills directory at {root}.")
        return

    converted = 0
    skipped = 0
    for skill_dir in sorted(root.iterdir()):
        if not skill_dir.is_dir():
            continue
        if (skill_dir / "SKILL.md").exists():
            skipped += 1
            continue
        legacy_yaml = None
        for fname in ("skill.yaml", "skill.yml", "manifest.yaml", "manifest.yml"):
            if (skill_dir / fname).exists():
                legacy_yaml = skill_dir / fname
                break
        if not legacy_yaml:
            continue

        try:
            data = yaml.safe_load(legacy_yaml.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            print_warning(f"{skill_dir.name}: could not parse YAML ({exc})")
            continue

        if not isinstance(data, dict):
            print_warning(f"{skill_dir.name}: YAML root must be a mapping")
            continue

        name = data.get("name") or skill_dir.name
        description = data.get("description") or "TODO - describe this skill."
        metadata: dict[str, Any] = {}
        for key in ("version", "author", "category", "tags"):
            if key in data:
                metadata[key] = data[key]
        allowed = data.get("allowed_tools") or data.get("allowed-tools") or []
        if isinstance(allowed, list):
            allowed_str = " ".join(str(t) for t in allowed)
        else:
            allowed_str = str(allowed)

        body = data.get("instructions") or f"# {name}\n\nMigrated from {legacy_yaml.name}.\n"

        lines: list[str] = ["---", f"name: {name}", f"description: {description}"]
        if data.get("license"):
            lines.append(f"license: {data['license']}")
        if allowed_str:
            lines.append(f"allowed-tools: {allowed_str}")
        if metadata:
            lines.append("metadata:")
            for k, v in metadata.items():
                lines.append(f"  {k}: {v!r}")
        lines.append("---\n")
        lines.append(body if isinstance(body, str) else str(body))
        rendered = "\n".join(lines)

        print_info(f"{skill_dir.name}: prepared migration ({len(rendered)} chars)")
        if apply:
            (skill_dir / "SKILL.md").write_text(rendered, encoding="utf-8")
            archive = skill_dir / (legacy_yaml.name + ".legacy")
            legacy_yaml.rename(archive)
            converted += 1

    if apply:
        print_success(f"Migration complete: {converted} converted, {skipped} already SKILL.md.")
    else:
        print_dim("Dry-run. Re-run with --apply to write SKILL.md files.")


@skills_group.command(name="install")
@click.argument("name")
@click.option("--source", "-s", default=None, help="Install from local path or git URL.")
@click.option("--force", "-f", is_flag=True, help="Force reinstall if already exists.")
def install_skill(name: str, source: str | None, force: bool) -> None:
    """Install a skill from the registry or a custom source."""
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_dir = SKILLS_DIR / name

    if skill_dir.exists() and not force:
        print_warning(f"Skill '{name}' is already installed.")
        if not prompt_confirm("Reinstall?"):
            return
        shutil.rmtree(skill_dir)

    console.print(f"Installing skill [cyan]{name}[/]...")
    try:
        if source and source.startswith(("http://", "https://", "git@")) and not source.endswith((".tar.gz", ".zip", ".tgz")):
            _install_from_git(source, skill_dir)
        elif source:
            _install_from_local(source, skill_dir)
        else:
            _install_from_registry(name, skill_dir)

        _run_post_install_validation(name, skill_dir)

        config = _load_skill_config()
        if name in config.get("disabled", []):
            config["disabled"].remove(name)
        if name not in config.get("enabled", []):
            config.setdefault("enabled", []).append(name)
        _save_skill_config(config)

        print_success(f"Skill '{name}' installed successfully.")

    except Exception as exc:
        if skill_dir.exists():
            shutil.rmtree(skill_dir)
        print_error(f"Failed to install skill: {exc}")
        raise click.Abort()


def _install_from_registry(name: str, skill_dir: Path) -> None:
    from leagent.skills.manager import SkillsManager

    manager = SkillsManager(skills_dir=SKILLS_DIR, load_builtin=False, enable_hot_reload=False)

    async def _run() -> Any:
        return await manager.install_from_hub(name)

    skill = asyncio.run(_run())
    if skill is None:
        raise RuntimeError(
            "Registry not configured or skill unavailable. Set LEAGENT_SKILLS_REGISTRY_URL "
            "or install from a --source."
        )


def _install_from_git(git_url: str, skill_dir: Path) -> None:
    import subprocess

    print_dim(f"Cloning from {git_url}...")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", git_url, str(skill_dir)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Git clone failed: {result.stderr}")


def _install_from_local(source_path: str, skill_dir: Path) -> None:
    source = Path(source_path)
    if not source.exists():
        raise RuntimeError(f"Source path does not exist: {source}")
    if not source.is_dir():
        raise RuntimeError(f"Source must be a directory: {source}")
    print_dim(f"Copying from {source}...")
    shutil.copytree(source, skill_dir)


def _run_post_install_validation(name: str, skill_dir: Path) -> None:
    from leagent.skills.base import SkillSource
    from leagent.skills.loader import SkillLoader

    loader = SkillLoader(skill_dir.parent, source=SkillSource.LOCAL)

    async def _run() -> None:
        await loader.load_skill(skill_dir)

    asyncio.run(_run())


@skills_group.command(name="uninstall")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def uninstall_skill(name: str, yes: bool) -> None:
    """Uninstall a user-installed skill."""
    skill_dir = SKILLS_DIR / name
    if not skill_dir.exists():
        print_error(f"Skill '{name}' is not installed.")
        raise click.Abort()

    if not yes and not prompt_confirm(f"Uninstall skill '{name}'?"):
        print_info("Cancelled.")
        return

    console.print(f"Uninstalling skill [cyan]{name}[/]...")
    try:
        shutil.rmtree(skill_dir)
        config = _load_skill_config()
        for key in ("enabled", "disabled"):
            if name in config.get(key, []):
                config[key].remove(name)
        if name in config.get("settings", {}):
            del config["settings"][name]
        _save_skill_config(config)
        print_success(f"Skill '{name}' uninstalled.")
    except Exception as exc:
        print_error(f"Failed to uninstall skill: {exc}")
        raise click.Abort()


@skills_group.command(name="enable")
@click.argument("name")
def enable_skill(name: str) -> None:
    config = _load_skill_config()
    if name in config.get("disabled", []):
        config["disabled"].remove(name)
    if name not in config.get("enabled", []):
        config.setdefault("enabled", []).append(name)
    _save_skill_config(config)
    print_success(f"Skill '{name}' enabled.")


@skills_group.command(name="disable")
@click.argument("name")
def disable_skill(name: str) -> None:
    config = _load_skill_config()
    if name in config.get("enabled", []):
        config["enabled"].remove(name)
    if name not in config.get("disabled", []):
        config.setdefault("disabled", []).append(name)
    _save_skill_config(config)
    print_success(f"Skill '{name}' disabled.")


@skills_group.command(name="search")
@click.argument("query", required=False)
@click.option("--category", "-c", default=None, help="Filter by category.")
def search_skills(query: str | None, category: str | None) -> None:
    """Search the configured skills registry."""
    from leagent.skills.manager import SkillsManager

    manager = SkillsManager(skills_dir=SKILLS_DIR, load_builtin=False, enable_hot_reload=False)

    async def _run() -> list[Any]:
        return await manager.search_hub(query=query or "", category=category, page=1, limit=100)

    entries = asyncio.run(_run())
    if not entries:
        print_info("No registry configured or no results.")
        print_dim("Configure with LEAGENT_SKILLS_REGISTRY_URL or skills.registry.url.")
        return

    installed = {row["name"] for row in _iter_installed_skills()}

    console.print()
    console.rule("[bold cyan]Available Skills[/]")
    console.print()

    table = create_table(columns=[
        ("Name", {"style": "cyan"}),
        ("Version", {}),
        ("Category", {}),
        ("Description", {}),
        ("Installed", {}),
    ])
    for entry in sorted(entries, key=lambda e: e.name):
        table.add_row(
            entry.name,
            entry.version,
            entry.category,
            (entry.description or "")[:40],
            "[green]\u2713[/]" if entry.name in installed else "",
        )
    console.print(table)
    console.print()
    print_dim(f"Found {len(entries)} skill(s)")
    console.print()


@skills_group.command(name="info")
@click.argument("name")
@click.pass_context
def skill_info(ctx: click.Context, name: str) -> None:
    """Alias for `skills show`."""
    ctx.invoke(show_skill, name=name)
