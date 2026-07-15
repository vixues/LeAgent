"""CLI auth recovery helpers (force password reset without knowing the old one)."""

from __future__ import annotations

import click

from leagent.cli.utils import (
    print_error,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
)


def _resolve_password(password: str | None) -> str | None:
    """Return a validated password from flag or interactive prompt."""
    if password is not None:
        pwd = password
    else:
        pwd = prompt_text("New password", password=True)
        confirm = prompt_text("Confirm password", password=True)
        if pwd != confirm:
            print_error("Passwords do not match.")
            return None

    if len(pwd) < 6:
        print_error("Password must be at least 6 characters.")
        return None
    return pwd


def force_reset_password(*, username: str | None, password: str) -> str:
    """Force-set a password without verifying the current one.

    Args:
        username: When set, reset that named user in the database. When
            ``None``, reset the instance access password in ``security.json``
            and sync the local admin account.
        password: New password (min 6 characters).

    Returns:
        Short human-readable summary of what was updated.

    Raises:
        LookupError: Named user not found.
        ValueError: Invalid password / role constraints from the store.
        RuntimeError: Database unavailable for a named-user reset.
    """
    if username:
        from leagent.services.auth.users import list_users, set_user_password

        uname = username.strip().lower()
        match = next((u for u in list_users() if u.username.lower() == uname), None)
        if match is None:
            raise LookupError(f"User not found: {username}")
        set_user_password(match.user_id, password)
        return f"Password reset for user '{match.username}'"

    from leagent.services.auth.store import get_security_store
    from leagent.services.auth.users import seed_admin_from_access_password

    store = get_security_store()
    require_unlock = store.load().require_unlock_on_desktop
    store.set_access_password(password, require_unlock_on_desktop=require_unlock)
    try:
        seed_admin_from_access_password(password)
    except Exception:  # noqa: BLE001 - access gate still works without DB seed
        pass
    return "Instance access password reset (local admin synced when DB is available)"


@click.command(name="reset-password")
@click.option(
    "--username",
    "-u",
    default=None,
    help="Named user to reset. Omit to force-reset the instance access password.",
)
@click.option(
    "--password",
    "-p",
    default=None,
    help="New password (min 6 chars). If omitted, you will be prompted.",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def reset_password_cmd(username: str | None, password: str | None, yes: bool) -> None:
    """Force-reset a password without knowing the current one.

    Intended for operators with shell access to the machine (e.g. forgotten
    admin / access password). Requires filesystem access to ``LEAGENT_HOME``
    and, for ``--username``, the configured database.

    \b
    Examples:
      leagent reset-password
      leagent reset-password -u alice
      leagent reset-password -p 'new-secret' -y
      leagent reset-password -u bob -p 'new-secret' -y
    """
    target = f"user '{username.strip()}'" if username else "the instance access password"
    print_warning(
        f"This forcibly resets {target} without verifying the current password."
    )
    if not yes and not prompt_confirm("Continue?", default=False):
        print_error("Aborted.")
        raise SystemExit(1)

    pwd = _resolve_password(password)
    if pwd is None:
        raise SystemExit(1)

    try:
        summary = force_reset_password(username=username, password=pwd)
    except LookupError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc
    except ValueError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc
    except RuntimeError as exc:
        print_error(str(exc))
        raise SystemExit(1) from exc

    print_success(summary)
