"""Command-line interface for agent-usage."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import typer

from agent_usage.commands import collect as collect_command
from agent_usage.commands import doctor as doctor_command
from agent_usage.commands import init as init_command
from agent_usage.commands import publish as publish_command
from agent_usage.commands import render as render_command
from agent_usage.commands import schedule as schedule_command
from agent_usage.commands.collect import (
    DEFAULT_CLAUDE_CODE_PROJECTS_DIR,
    DEFAULT_CODEX_SESSIONS_DIR,
    DEFAULT_HERMES_STATE_DB,
)
from agent_usage.commands.publish import GhAuthError
from agent_usage.config import config_file_path, data_dir, ledger_file_path, load_config
from agent_usage.privacy import PrivacyPolicy
from agent_usage.publish.git import GitCommandError
from agent_usage.schedule.launchd import LaunchctlError

app = typer.Typer(
    help="Collect privacy-conscious local agent usage summaries.",
    no_args_is_help=True,
)
schedule_app = typer.Typer(help="Manage the opt-in local macOS daily scheduler.", no_args_is_help=True)
app.add_typer(schedule_app, name="schedule")


@app.callback()
def command_group() -> None:
    """Commands for collecting and reviewing agent usage."""


@app.command()
def init(
    repo: str = typer.Option(..., "--repo", help="GitHub profile repo in OWNER/REPO form."),
) -> None:
    """Set the target GitHub profile repository for this install (local only, no network)."""
    config = init_command.init(repo, config_path=config_file_path(), ledger_path=ledger_file_path())
    typer.echo(f"agent-usage: repo target set to {config.repo_target}")


@app.command()
def doctor() -> None:
    """Show local configuration and per-agent source health."""
    now = datetime.now(timezone.utc)
    report = doctor_command.run_doctor(
        config_path=config_file_path(),
        ledger_path=ledger_file_path(),
        hermes_db=DEFAULT_HERMES_STATE_DB,
        claude_projects_dir=DEFAULT_CLAUDE_CODE_PROJECTS_DIR,
        codex_sessions_dir=DEFAULT_CODEX_SESSIONS_DIR,
        now=now,
    )
    typer.echo(f"device id: {report.device_id}")
    typer.echo(f"repo target: {report.repo_target or '(not set)'}")
    typer.echo(f"display timezone: {report.display_timezone}")
    for source in report.sources:
        status = source.status.value if source.status is not None else "up to date"
        typer.echo(f"  {source.agent.value}: {status}")


@app.command()
def collect(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview what would be collected without writing to the ledger."
    ),
) -> None:
    """Pull new local agent usage into the private ledger."""
    now = datetime.now(timezone.utc)
    results = collect_command.collect_all(
        ledger_path=ledger_file_path(),
        hermes_db=DEFAULT_HERMES_STATE_DB,
        claude_projects_dir=DEFAULT_CLAUDE_CODE_PROJECTS_DIR,
        codex_sessions_dir=DEFAULT_CODEX_SESSIONS_DIR,
        now=now,
        dry_run=dry_run,
    )
    for result in results:
        status = result.status.value if result.status is not None else "up to date"
        typer.echo(
            f"  {result.agent.value}: {status} "
            f"(observed {result.records_observed}, inserted {result.records_inserted})"
        )
    if dry_run:
        typer.echo("agent-usage: dry run, nothing written")


@app.command()
def render(
    output_dir: Path | None = typer.Option(
        None, "--output-dir", help="Where to write the local dashboard preview."
    ),
    pie_top_n: int = typer.Option(
        6,
        "--pie-top-n",
        help="Max Skills/MCP pie slices to show before bucketing the rest into 'Other'.",
    ),
) -> None:
    """Render a local preview of the dashboard from this device's own collected data."""
    if pie_top_n < 1:
        raise typer.BadParameter("--pie-top-n must be at least 1")
    now = datetime.now(timezone.utc)
    config = load_config(config_file_path())
    resolved_output_dir = output_dir or (ledger_file_path().parent / "preview")
    result = render_command.render(
        ledger_path=ledger_file_path(),
        output_dir=resolved_output_dir,
        privacy_policy=PrivacyPolicy.from_config(config),
        today=now.date(),
        generated_at=now.strftime("%Y-%m-%d %H:%M UTC"),
        pie_top_n=pie_top_n,
    )
    typer.echo(f"agent-usage: preview written to {result.readme_path}")
    typer.echo(
        "agent-usage: dashboard changed" if result.changed else "agent-usage: dashboard unchanged"
    )


@app.command()
def publish(
    branch: str = typer.Option("main", "--branch", help="Target branch on the profile repo."),
    clone_dir: Path | None = typer.Option(
        None, "--clone-dir", help="Local working copy of the profile repository to use."
    ),
) -> None:
    """Publish this device's own sanitized daily aggregates to the profile repository."""
    config = load_config(config_file_path())
    if config.repo_target is None:
        typer.echo(
            "agent-usage: no repo target set — run `agent-usage init --repo OWNER/REPO` first"
        )
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc)
    resolved_clone_dir = clone_dir or (ledger_file_path().parent / "profile-repo")
    repo_url = f"https://github.com/{config.repo_target}.git"

    try:
        summary = publish_command.publish(
            ledger_path=ledger_file_path(),
            repo_url=repo_url,
            clone_dir=resolved_clone_dir,
            branch=branch,
            privacy_policy=PrivacyPolicy.from_config(config),
            today=now.date(),
        )
    except GhAuthError as error:
        typer.echo(f"agent-usage: gh auth check failed: {error}")
        raise typer.Exit(code=1) from error
    except GitCommandError as error:
        typer.echo(f"agent-usage: publish failed: {error}")
        raise typer.Exit(code=1) from error

    typer.echo(
        f"agent-usage: {summary.days_staged} day(s) of local history for device "
        f"{summary.device_id}"
    )
    if summary.result.pushed:
        typer.echo(f"agent-usage: published (commit {summary.result.commit_sha})")
    else:
        typer.echo("agent-usage: nothing new to publish")


@schedule_app.command("install")
def schedule_install(
    daily_at: str = typer.Option(..., "--daily-at", help="Local 24-hour time in HH:MM form."),
) -> None:
    """Install a daily local job that runs collect, then publish."""
    try:
        result = schedule_command.install(
            config_path=config_file_path(),
            daily_at=daily_at,
            executable=str(Path(sys.argv[0]).resolve()),
            log_dir=data_dir() / "logs",
        )
    except (LaunchctlError, ValueError) as error:
        typer.echo(f"agent-usage: schedule install failed: {error}")
        raise typer.Exit(code=1) from error

    typer.echo(f"agent-usage: daily schedule installed for {result.daily_at}")


@schedule_app.command("status")
def schedule_status() -> None:
    """Show whether the local daily job is installed and loaded."""
    result = schedule_command.status()
    if not result.installed:
        typer.echo("agent-usage: daily schedule is not installed")
        return

    load_state = "loaded" if result.loaded else "not loaded"
    typer.echo(f"agent-usage: daily schedule installed for {result.daily_at} ({load_state})")


@schedule_app.command("remove")
def schedule_remove() -> None:
    """Unload and remove the local daily job."""
    try:
        removed = schedule_command.remove(config_path=config_file_path())
    except LaunchctlError as error:
        typer.echo(f"agent-usage: schedule removal failed: {error}")
        raise typer.Exit(code=1) from error

    if removed:
        typer.echo("agent-usage: daily schedule removed")
    else:
        typer.echo("agent-usage: daily schedule is not installed")


def main() -> None:
    """Run the command-line application."""
    app()
