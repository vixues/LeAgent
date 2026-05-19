---
name: skill-packager
description: Authors Agent Skills v1.0 packages (SKILL.md plus references/scripts), runs package_skill to produce a standards-compliant zip, and uses install_skill to add skills from HTTPS, registry, workspace, or an uploaded archive. Use when the user wants to turn documentation, workflows, or code into a portable skill, export a skill zip, or install a skill from a link or file without leaving the chat.
license: Apache-2.0
metadata:
  version: 1.0.0
  category: platform
  tags: [skills, skill, zip, pack, install, export, cursor, agentskills]
---

# Skill packager

Help the user create, package, and install [Agent Skills v1.0](https://agentskills.my/specification) bundles.

## When to use

- User finished a doc, workflow, or code and wants it **reusable as a skill**.
- User pastes an **https://** link to a `.zip` / `.tar.gz` skill bundle to **install**.
- User wants a **.zip** to import into Cursor (`~/.cursor/skills/` or `.cursor/skills/`) or another agent.

## Authoring layout

- One directory per skill: directory name **must** equal the `name` field in `SKILL.md` frontmatter (kebab-case).
- Put long prose in `references/` or `assets/`; keep `SKILL.md` concise with links to those files.
- Optional `scripts/` for helpers; script execution may require server env flags—document that.

## Tools (LeAgent)

| Goal | Tool |
|------|------|
| Validate + zip a folder | `package_skill` with `skill_directory` (optional `output_path`) |
| Install from URL | `install_skill` with `source_type: url`, `url`, optional `sha256` |
| Install from registry | `install_skill` with `source_type: registry`, `registry_skill_name` |
| Install from project folder | `install_skill` with `source_type: workspace`, `workspace_path`, `target_skill_name` |
| Install from uploaded archive | `install_skill` with `source_type: uploaded_archive`, `file_id` |

After installation, use `load_skill` with the returned skill name to pull instructions.

## Cursor / desktop import (manual)

If the user only needs Cursor (not LeAgent runtime): give them the zip from `package_skill` and instruct them to extract so one top-level folder `skill-name/` contains `SKILL.md`, then copy that folder into `%USERPROFILE%\.cursor\skills\` or the project’s `.cursor/skills/`. Do **not** place skills in `~/.cursor/skills-cursor/` (reserved for built-ins).

## Quality checklist

- [ ] `description` in frontmatter states **what** the skill does and **when** to use it (third person).
- [ ] Directory name matches `name` in `SKILL.md`.
- [ ] Run `package_skill` before sharing the zip; fix validation errors if any.
