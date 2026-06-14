"""Command-line interface for prmanager."""

from __future__ import annotations

import webbrowser
from datetime import datetime, timezone
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from prm import __version__, config, db
from prm.github import GitHubClient, GitHubError

app = typer.Typer(
    help="Manage GitHub pull requests from the command line, backed by SQLite.",
)
console = Console()
err = Console(stderr=True)

REVIEW_STATES = ("pending", "approved", "changes", "commented")
STATE_STYLE = {"open": "green", "closed": "red"}
REVIEW_STYLE = {
    "pending": "dim",
    "approved": "green",
    "changes": "red",
    "commented": "yellow",
}


def _fail(msg: str) -> None:
    err.print(f"[bold red]error:[/] {msg}")
    raise typer.Exit(1)


def _age(iso: Optional[str]) -> str:
    """Compact human age of an ISO-8601 UTC timestamp, e.g. '3d', '5h', '2w'."""
    if not iso:
        return ""
    try:
        ts = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    delta = datetime.now(timezone.utc) - ts
    secs = int(delta.total_seconds())
    if secs < 3600:
        return f"{secs // 60}m"
    if secs < 86400:
        return f"{secs // 3600}h"
    days = secs // 86400
    if days < 14:
        return f"{days}d"
    return f"{days // 7}w"


def _split_repo(full: str) -> tuple[str, str]:
    if full.count("/") != 1 or not all(full.split("/")):
        _fail(f"repo must be in 'owner/name' form, got: {full!r}")
    owner, name = full.split("/")
    return owner, name


def _resolve_login() -> str:
    """Return the authenticated user's login, caching it in config."""
    login = config.cached_login()
    if login:
        return login
    token = config.resolve_token()
    if not token:
        _fail("--mine needs authentication. Set a token with 'prm auth --token'.")
    try:
        login = GitHubClient(token).current_user()
    except GitHubError as e:
        _fail(str(e))
    config.set_login(login)
    return login


def _resolve_pull(conn, number: int, repo: Optional[str]):
    """Return a single PR row or exit with a helpful message."""
    rows = db.find_pull(conn, number, repo)
    if not rows:
        scope = f" in {repo}" if repo else ""
        _fail(f"no PR #{number} found{scope}. Have you run 'prm sync'?")
    if len(rows) > 1:
        repos = ", ".join(r["repo"] for r in rows)
        _fail(
            f"PR #{number} exists in multiple repos ({repos}). "
            f"Disambiguate with --repo."
        )
    return rows[0]


@app.callback(invoke_without_command=True)
def _main(ctx: typer.Context) -> None:
    """Initialize the database; with no subcommand, drop into the REPL."""
    db.init_db()
    if ctx.invoked_subcommand is None:
        from prm import repl

        repl.run(app)


@app.command()
def version() -> None:
    """Show the prmanager version."""
    console.print(f"prmanager {__version__}")


@app.command()
def shell() -> None:
    """Start an interactive REPL where commands are entered with a leading '/'."""
    from prm import repl

    repl.run(app)


@app.command()
def auth(
    token: Optional[str] = typer.Option(
        None, "--token", "-t", help="Store a GitHub token in the config file."
    ),
) -> None:
    """Configure or check GitHub authentication."""
    if token:
        config.set_token(token)
        console.print(f"[green]Token saved to[/] {config.CONFIG_FILE}")
        return

    resolved = config.resolve_token()
    if resolved:
        masked = resolved[:4] + "…" + resolved[-4:] if len(resolved) > 8 else "****"
        console.print(f"[green]Authenticated.[/] Using token [dim]{masked}[/]")
    else:
        console.print(
            "[yellow]No token found.[/] Set GITHUB_TOKEN, run 'prm auth --token <T>', "
            "or log in with 'gh auth login'."
        )


@app.command()
def track(repo: str = typer.Argument(..., help="Repository as owner/name.")) -> None:
    """Start tracking a repository."""
    owner, name = _split_repo(repo)
    with db.connect() as conn:
        db.add_repo(conn, owner, name)
    console.print(f"[green]Tracking[/] {owner}/{name}. Run 'prm sync {owner}/{name}'.")


@app.command()
def untrack(repo: str = typer.Argument(..., help="Repository as owner/name.")) -> None:
    """Stop tracking a repository and delete its cached PRs."""
    with db.connect() as conn:
        if db.remove_repo(conn, repo):
            console.print(f"[green]Untracked[/] {repo}.")
        else:
            _fail(f"{repo} is not tracked.")


@app.command()
def repos() -> None:
    """List tracked repositories."""
    with db.connect() as conn:
        rows = db.list_repos(conn)
    if not rows:
        console.print("[dim]No repositories tracked. Use 'prm track owner/name'.[/]")
        return
    table = Table(title="Tracked repositories")
    table.add_column("Repository", style="cyan")
    table.add_column("PRs", justify="right")
    table.add_column("Last synced", style="dim")
    for r in rows:
        synced = r["last_synced_at"] or "never"
        table.add_row(r["full_name"], str(r["pr_count"]), synced)
    console.print(table)


@app.command()
def sync(
    repo: Optional[str] = typer.Argument(
        None, help="Repository to sync. Omit to sync all tracked repos."
    ),
    state: str = typer.Option(
        "all", "--state", help="Which PRs to fetch: open, closed, or all."
    ),
    full: bool = typer.Option(
        False, "--full", help="Ignore the watermark and re-fetch every PR."
    ),
) -> None:
    """Fetch pull requests from GitHub into the local database.

    Syncs are incremental: only PRs updated since the last sync are fetched.
    Use --full to force a complete re-fetch.
    """
    if state not in ("open", "closed", "all"):
        _fail("--state must be one of: open, closed, all")

    client = GitHubClient(config.resolve_token())

    with db.connect() as conn:
        if repo:
            owner, name = _split_repo(repo)
            db.add_repo(conn, owner, name)
            targets = [db.get_repo(conn, f"{owner}/{name}")]
        else:
            targets = db.list_repos(conn)
            if not targets:
                _fail("no repositories tracked. Use 'prm track owner/name' first.")

        total = 0
        for r in targets:
            full_name = r["full_name"]
            # Use the watermark only when the previous sync used the same state.
            since = None
            if not full and r["last_synced_at"] and r["last_sync_state"] == state:
                since = r["last_synced_at"]

            try:
                with console.status(f"Syncing {full_name}…"):
                    pulls = client.fetch_pulls(
                        r["owner"], r["name"], state=state, since=since
                    )
            except GitHubError as e:
                _fail(str(e))

            for pr in pulls:
                db.upsert_pull(conn, r["id"], pr)

            newest = max((p["updated_at"] for p in pulls if p["updated_at"]), default=None)
            watermark = max(t for t in (r["last_synced_at"], newest) if t) if (
                r["last_synced_at"] or newest
            ) else None
            db.set_repo_sync(conn, r["id"], watermark, state)

            total += len(pulls)
            kind = "updated" if since else "PRs"
            console.print(f"  [green]{full_name}[/]: {len(pulls)} {kind}")

    console.print(f"[bold green]Synced {total} PRs.[/]")


@app.command(name="list")
def list_prs(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Filter by repo."),
    state: Optional[str] = typer.Option(
        None, "--state", "-s", help="open or closed."
    ),
    author: Optional[str] = typer.Option(
        None, "--author", "-a", help="Filter by author (case-insensitive substring)."
    ),
    mine: bool = typer.Option(
        False, "--mine", help="Only PRs you authored (the authenticated user)."
    ),
    tag: Optional[str] = typer.Option(None, "--tag", "-T"),
    review: Optional[str] = typer.Option(
        None, "--review", help=f"Review status: {', '.join(REVIEW_STATES)}."
    ),
    no_drafts: bool = typer.Option(
        False, "--no-drafts", help="Exclude draft PRs from the listing."
    ),
    needs_review: bool = typer.Option(
        False,
        "--needs-review",
        help="Open, non-draft PRs you haven't reviewed yet (review pending).",
    ),
) -> None:
    """List cached pull requests with optional filters."""
    if mine and author:
        _fail("use either --mine or --author, not both.")

    filters: dict = {
        "repo": repo,
        "state": state,
        "author": author,  # substring match
        "tag": tag,
        "review_status": review,
    }
    if needs_review:
        if state or review:
            _fail("--needs-review already implies --state open and review pending.")
        filters["state"] = "open"
        filters["review_status"] = "pending"
        filters["draft"] = False
    if mine:
        # exact match on your own login, so it can't over-match a superstring
        filters["author_exact"] = _resolve_login()
    if no_drafts:
        filters["draft"] = False

    with db.connect() as conn:
        rows = db.query_pulls(conn, filters)

    if not rows:
        console.print("[dim]No matching PRs. Try 'prm sync' first.[/]")
        return

    _render_pr_table(rows, title=f"Pull requests ({len(rows)})")


def _render_pr_table(rows, title: str, show_age: bool = False) -> None:
    """Render PR rows as a Rich table. Untrusted fields are markup-escaped."""
    table = Table(title=title)
    table.add_column("#", justify="right", style="bold")
    table.add_column("Repo", style="cyan")
    table.add_column("Title")
    table.add_column("Author", style="magenta")
    if show_age:
        table.add_column("Age", justify="right", style="yellow")
    else:
        table.add_column("State")
    table.add_column("Review")
    table.add_column("Tags", style="blue")

    for r in rows:
        # PR titles/authors/tags are untrusted; escape Rich markup in them.
        title_cell = escape(r["title"] or "")
        if r["draft"]:
            title_cell = f"[dim](draft)[/] {title_cell}"
        if r["note_count"]:
            title_cell += f" [dim]📝{r['note_count']}[/]"
        review_status = r["review_status"] or "pending"
        if show_age:
            mid_cell = _age(r["created_at"])
        else:
            state_label = "merged" if r["merged"] else r["state"]
            state_style = "blue" if r["merged"] else STATE_STYLE.get(r["state"], "white")
            mid_cell = f"[{state_style}]{state_label}[/]"
        table.add_row(
            str(r["number"]),
            r["repo"],
            title_cell,
            escape(r["author"] or ""),
            mid_cell,
            f"[{REVIEW_STYLE.get(review_status, 'white')}]{review_status}[/]",
            escape(r["tags"] or ""),
        )
    console.print(table)


@app.command()
def triage(
    repo: Optional[str] = typer.Option(None, "--repo", "-r", help="Filter by repo."),
    include_mine: bool = typer.Option(
        False, "--include-mine", help="Include PRs you authored (excluded by default)."
    ),
) -> None:
    """Show the review queue: open, non-draft, unreviewed PRs, oldest first.

    This is the maintainer's "what needs me" view across tracked repos.
    """
    filters: dict = {
        "repo": repo,
        "state": "open",
        "review_status": "pending",
        "draft": False,
    }
    with db.connect() as conn:
        rows = db.query_pulls(conn, filters, order="created-asc")

    if not include_mine:
        mine = config.cached_login()
        if mine:
            rows = [r for r in rows if (r["author"] or "") != mine]

    if not rows:
        console.print("[green]Triage queue is empty — nothing awaiting review.[/]")
        return

    _render_pr_table(rows, title=f"Triage queue ({len(rows)}) — oldest first", show_age=True)


@app.command()
def show(
    number: int = typer.Argument(..., help="PR number."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
) -> None:
    """Show full details, notes, and tags for a pull request."""
    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
        notes = db.list_notes(conn, pr["id"])
        tags = db.list_tags(conn, pr["id"])

    state_label = "merged" if pr["merged"] else pr["state"]
    # Escape untrusted PR fields so Rich doesn't parse '[...]' as markup.
    header = f"[bold]#{pr['number']}[/] {escape(pr['title'] or '')}"
    meta = (
        f"[cyan]{escape(pr['repo'])}[/]  ·  by [magenta]{escape(pr['author'] or '')}[/]  ·  "
        f"{state_label}  ·  review: {pr['review_status']}\n"
        f"[dim]{pr['url']}[/]\n"
        f"[dim]created {pr['created_at']} · updated {pr['updated_at']}[/]"
    )
    if tags:
        meta += f"\ntags: [blue]{escape(', '.join(tags))}[/]"
    console.print(Panel(meta, title=header, expand=False))

    if pr["body"]:
        console.print(Panel(escape(pr["body"]), title="Description", expand=False))

    if notes:
        note_table = Table(title="Notes", show_header=True)
        note_table.add_column("When", style="dim")
        note_table.add_column("Note")
        for n in notes:
            note_table.add_row(n["created_at"], escape(n["body"]))
        console.print(note_table)


@app.command()
def note(
    number: int = typer.Argument(...),
    text: str = typer.Argument(..., help="Note body."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
) -> None:
    """Attach a local note to a pull request."""
    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
        db.add_note(conn, pr["id"], text)
    console.print(f"[green]Note added to[/] {pr['repo']}#{number}.")


@app.command()
def tag(
    number: int = typer.Argument(...),
    tag: str = typer.Argument(..., help="Tag to add."),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    remove: bool = typer.Option(False, "--remove", "-d", help="Remove the tag."),
) -> None:
    """Add or remove a local tag on a pull request."""
    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
        if remove:
            if db.remove_tag(conn, pr["id"], tag):
                console.print(f"[green]Removed tag[/] '{tag}' from {pr['repo']}#{number}.")
            else:
                _fail(f"{pr['repo']}#{number} has no tag '{tag}'.")
        else:
            db.add_tag(conn, pr["id"], tag)
            console.print(f"[green]Tagged[/] {pr['repo']}#{number} with '{tag}'.")


@app.command()
def review(
    number: int = typer.Argument(...),
    status: str = typer.Argument(
        ..., help=f"One of: {', '.join(REVIEW_STATES)}."
    ),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
) -> None:
    """Set the local review status of a pull request."""
    if status not in REVIEW_STATES:
        _fail(f"status must be one of: {', '.join(REVIEW_STATES)}")
    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
        db.set_review_status(conn, pr["id"], status)
    console.print(f"[green]{pr['repo']}#{number}[/] review status → {status}")


# Maps the user-facing event name to (GitHub API event, local review status).
SUBMIT_EVENTS = {
    "approve": ("APPROVE", "approved"),
    "request-changes": ("REQUEST_CHANGES", "changes"),
    "comment": ("COMMENT", "commented"),
}


@app.command()
def submit(
    number: int = typer.Argument(...),
    event: str = typer.Argument(
        ..., help=f"One of: {', '.join(SUBMIT_EVENTS)}."
    ),
    body: Optional[str] = typer.Option(
        None, "--body", "-b", help="Review comment body."
    ),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the confirmation prompt."
    ),
) -> None:
    """Post a review to GitHub (approve, request changes, or comment)."""
    event = event.lower()
    if event not in SUBMIT_EVENTS:
        _fail(f"event must be one of: {', '.join(SUBMIT_EVENTS)}")
    api_event, local_status = SUBMIT_EVENTS[event]

    if event in ("request-changes", "comment") and not body:
        _fail(f"--body is required when event is '{event}'.")

    token = config.resolve_token()
    if not token:
        _fail("posting a review needs authentication. Run 'prm auth --token <T>'.")

    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
        owner, name = _split_repo(pr["repo"])
        pull_id = pr["id"]

    console.print(
        Panel(
            f"[bold]{pr['repo']}#{number}[/]  {pr['title']}\n"
            f"event: [bold]{api_event}[/]\n"
            f"body: {body or '[dim](none)[/]'}",
            title="About to post this review to GitHub",
            expand=False,
        )
    )
    if not yes and not typer.confirm("Post this review?"):
        console.print("[dim]aborted — nothing posted[/]")
        raise typer.Exit(0)

    client = GitHubClient(token)
    try:
        review = client.submit_review(owner, name, number, api_event, body or "")
    except GitHubError as e:
        _fail(str(e))

    with db.connect() as conn:
        db.set_review_status(conn, pull_id, local_status)

    url = review.get("html_url", pr["url"])
    console.print(f"[green]Review posted[/] to {pr['repo']}#{number} → {url}")


@app.command(name="open")
def open_pr(
    number: int = typer.Argument(...),
    repo: Optional[str] = typer.Option(None, "--repo", "-r"),
) -> None:
    """Open a pull request in your web browser."""
    with db.connect() as conn:
        pr = _resolve_pull(conn, number, repo)
    if not pr["url"]:
        _fail("this PR has no URL on record.")
    console.print(f"Opening {pr['url']}")
    webbrowser.open(pr["url"])


if __name__ == "__main__":
    app()
