# prmanager (`prm`)

[![CI](https://github.com/sbj-ee/PRmanager/actions/workflows/ci.yml/badge.svg)](https://github.com/sbj-ee/PRmanager/actions/workflows/ci.yml)

A command-line **GitHub pull-request manager**, backed by a local **SQLite**
database. Track your repos, sync their PRs offline, triage what needs your
review, post reviews back to GitHub, and layer on local-only notes and tags —
all from the terminal or an interactive shell.

## Quick start

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

prm track octocat/Hello-World   # track a repo (or several)
prm sync                        # pull its PRs into local SQLite
prm triage                      # see what needs review
prm                             # ...or drop into the interactive shell
```

## Features

- Track any number of GitHub repos and **incrementally sync** their PRs into
  local SQLite — after the first sync, only updated PRs are fetched.
- Rich filtering on `prm list`: by repo, state, **author** (case-insensitive
  substring — `--author dependabot` matches `dependabot[bot]`), **label**
  (repeatable, ANDed), **assignee**, **requested reviewer**, tag, or review
  status, plus `--mine` and `--needs-review`.
- **Maintainer triage** (`prm triage`): the review queue — open, non-draft,
  unreviewed PRs, oldest first — with optional **CI status** (`--checks`:
  ✓ pass / ✗ fail / ● running / — none, cached), and `--requested` to narrow to
  PRs where review was actually requested from you.
- Local-only workflow state GitHub doesn't give you: per-PR **review status**,
  free-form **notes**, and **tags**.
- **Write-back**: post real reviews to GitHub (approve / request changes /
  comment) with a confirmation prompt.
- **Desktop notifications** (`prm notify`) when a new PR enters your review
  queue — announced once each, with review-requested PRs prioritized (first, at
  higher urgency). Uses `notify-send`, falling back to `gdbus`.
- **Interactive REPL** — run `prm` with no arguments for a `/`-command shell.
- Labels, assignees, and requested reviewers are synced from GitHub and shown
  inline; works fully offline once synced.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs the `prm` command.

## Authentication

`prm` needs a GitHub token to sync (public repos work unauthenticated but get
tighter rate limits). It looks for a token in this order:

1. `GITHUB_TOKEN` / `GH_TOKEN` environment variables
2. `prm auth --token <TOKEN>` (saved to `~/.config/prmanager/config.json`)
3. The `gh` CLI (`gh auth token`), if you're logged in

```bash
prm auth                       # show current auth status
prm auth --token ghp_xxx       # store a token
```

## Usage

```bash
prm track octocat/Hello-World      # start tracking a repo
prm sync                           # sync PRs for all tracked repos (incremental)
prm sync octocat/Hello-World       # ...or just one
prm sync octocat/Hello-World --full  # ignore the watermark, re-fetch everything
prm repos                          # list tracked repos (+ last-synced time)

prm list                           # list all cached PRs
prm list --repo octocat/Hello-World --state open
prm list --author octocat --tag urgent --review pending
prm list --label bug --assignee octocat   # filter by GitHub label / assignee
prm list --label bug --label ready         # repeat --label to require ALL (AND)
prm list --requested               # PRs where review is requested from you
prm list --reviewer octocat        # ...or from a specific person
prm list --mine                    # only PRs you authored
prm list --needs-review            # open, non-draft, not yet reviewed

prm triage                         # maintainer review queue, oldest first
prm triage --checks                # ...with CI status per PR (fetched + cached)
prm triage --label bug             # ...only PRs with a given label
prm triage --requested             # ...only PRs where review is requested from you
prm triage --repo owner/name       # ...scoped to one repo
prm triage --include-mine          # include your own PRs (excluded by default)

prm notify                         # desktop-notify about newly-arrived review PRs
prm notify --requested-only        # only PRs where review is requested from you
prm notify --seed                  # mark the current queue seen, without notifying

prm show 42                        # full details + labels + assignees + notes
prm note 42 "needs a test for the edge case"
prm tag 42 urgent
prm tag 42 urgent --remove
prm review 42 approved             # set LOCAL status: pending|approved|changes|commented
prm open 42                        # open in browser

# Write-back: post a real review to GitHub (asks to confirm; -y to skip)
prm submit 42 approve
prm submit 42 request-changes --body "needs a test for the edge case"
prm submit 42 comment -b "looks reasonable" --yes
```

When a PR number exists in more than one tracked repo, disambiguate with
`--repo owner/name`.

## Interactive shell

Run `prm` with no arguments (or `prm shell`) to enter a REPL where every command
is the same, entered with a leading `/`:

```
prm> /triage --requested
prm> /show 42
prm> /submit 42 approve
prm> /help
prm> /quit
```

Add `--help` to any command for its options (e.g. `/list --help`).

## Automating sync

Keep the local database fresh — and get notified about new review PRs —
with a cron job. Because the DB and your `gh` auth are local, the schedule must
run on your own machine. A small wrapper gives cron a usable `PATH` and a
desktop session for notifications:

```bash
#!/usr/bin/env bash
# ~/.local/share/prmanager/sync.sh
export PATH="/usr/bin:/bin:/usr/local/bin:$PATH"
export DISPLAY="${DISPLAY:-:0}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u)/bus}"

prm sync --state all          # pull new/changed PRs
prm triage --checks           # warm the CI-status cache
prm notify                    # desktop-notify new review PRs (requested ones first)
```

```cron
# crontab -e — run hourly at :17
17 * * * * /home/you/.local/share/prmanager/sync.sh >> ~/.local/share/prmanager/sync.log 2>&1
```

Run `prm notify --seed` once first to baseline the current queue so you only get
notified about genuinely new PRs.

## Shell completion

`prm` ships tab-completion for bash, zsh, and fish (via Typer/Click).

```bash
prm --install-completion        # install for your current shell, then restart it
prm --show-completion zsh       # or print the script to add it yourself
```

Once installed, `prm <TAB>` completes commands and `prm submit <TAB>` etc.
complete options.

## Data locations

- Database: `~/.local/share/prmanager/prm.db` (override with `PRM_DB`)
- Config:   `~/.config/prmanager/config.json`

## Development

```bash
pip install -e ".[dev]"
python -m prm --help
pytest                 # run the test suite
```

Tests run fully offline: the network and the `gh` fallback are mocked, and
each test gets its own temp SQLite DB and config (see `tests/conftest.py`).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

[MIT](LICENSE) © Stephen B. Johnson
