# prmanager (`prm`)

A command-line manager for **GitHub pull requests**, backed by a local **SQLite**
database. Track repositories, sync their PRs offline, and layer on your own
review status, notes, and tags.

## Features

- Track any number of GitHub repos and sync their PRs into local SQLite.
- List and filter PRs by repo, state, author, tag, or review status.
- Local-only workflow state that GitHub doesn't give you: a per-PR **review
  status**, free-form **notes**, and **tags** — all stored locally.
- Open any PR in your browser straight from the terminal.
- Works offline once synced; the database is the source of truth for browsing.

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
prm sync                           # sync PRs for all tracked repos
prm sync octocat/Hello-World       # ...or just one
prm repos                          # list tracked repos

prm list                           # list all cached PRs
prm list --repo octocat/Hello-World --state open
prm list --author octocat --tag urgent --review pending

prm show 42                        # full details + notes + tags
prm note 42 "needs a test for the edge case"
prm tag 42 urgent
prm tag 42 urgent --remove
prm review 42 approved             # pending | approved | changes | commented
prm open 42                        # open in browser
```

When a PR number exists in more than one tracked repo, disambiguate with
`--repo owner/name`.

## Data locations

- Database: `~/.local/share/prmanager/prm.db` (override with `PRM_DB`)
- Config:   `~/.config/prmanager/config.json`

## Development

```bash
pip install -e .
python -m prm --help
```
