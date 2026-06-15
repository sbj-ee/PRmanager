# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-06-14

First stable release. The CLI, command names, and on-disk SQLite schema are now
considered stable and will follow semantic versioning. No functional changes
since 0.9.0; this release marks the feature set built up across 0.1–0.9:

- Track repos and **incrementally sync** their PRs into local SQLite.
- Rich **filtering** (author/label/assignee/reviewer/tag/review status, `--mine`,
  `--needs-review`) and a maintainer **triage** queue with **CI status**.
- **Review-requested detection** (`--requested` / `--reviewer`).
- Local **review status, notes, and tags**; **write-back** reviews to GitHub.
- **Desktop notifications** that prioritize review-requested PRs.
- An interactive **REPL**, shell **completion**, and an offline test suite.

## [0.9.0] - 2026-06-14

### Changed
- **`prm notify` prioritizes review-requested PRs.** PRs where review is
  requested from you are announced first and at higher (critical) urgency, with
  a distinct "🔔 Review requested from you" title; the rest follow at normal
  urgency. New `--requested-only` flag notifies about just the review-requested
  ones. Notification urgency is now passed through to notify-send/gdbus.

## [0.8.0] - 2026-06-14

### Added
- **Review-requested detection.** Sync now stores each PR's requested
  reviewers. New `--requested` flag (on `prm list` and `prm triage`) narrows to
  PRs where review is requested from *you*; `prm list --reviewer <login>`
  filters by a specific requested reviewer. `prm show` lists requested
  reviewers. Run `prm sync --full` once to backfill existing data.

## [0.7.0] - 2026-06-14

### Added
- **`prm notify`** — sends a desktop notification for PRs that have newly
  entered the review queue (open, non-draft, unreviewed, not authored by you).
  Each PR is announced once (tracked via a `notified_at` column); `--seed`
  baselines the current queue silently. Uses `notify-send`, falling back to
  `gdbus` over D-Bus.

## [0.6.0] - 2026-06-14

### Added
- **Multi-label filtering.** `--label` is now repeatable on `prm list` and
  `prm triage`; passing it multiple times requires a PR to have *all* the given
  labels (AND), e.g. `prm list --label bug --label ready-for-review`.

## [0.5.0] - 2026-06-14

### Added
- **Labels and assignees.** Sync now stores each PR's GitHub labels and
  assignees. Labels render inline in `list`/`triage`, and `show` lists both.
  Filter with `prm list --label <name>` / `--assignee <login>` and
  `prm triage --label <name>` (case-insensitive, exact-token match). Run
  `prm sync --full` once to backfill existing data.

## [0.4.0] - 2026-06-14

### Added
- **`prm triage --checks`** — fetches each queued PR's **CI checks rollup** from
  GitHub (combining commit statuses and check runs) and shows it as a column
  (✓ pass / ✗ fail / ● running / — none). Results are cached per head commit, so
  a plain `prm triage` shows the last-known CI without API calls; the cache is
  invalidated when a PR's head commit changes. Sync now stores each PR's head
  SHA (run `prm sync --full` once to backfill existing data).

## [0.3.0] - 2026-06-14

### Added
- **`prm triage`** — a maintainer review queue showing open, non-draft,
  unreviewed PRs across tracked repos, oldest first, with a PR-age column. Your
  own PRs are excluded by default (`--include-mine` to include them);
  `--repo` scopes to one repo.
- **`prm list --needs-review`** — filters to open, non-draft PRs you haven't
  reviewed yet (review status pending).

## [0.2.0] - 2026-06-14

### Added
- **Incremental sync.** Each repo records a watermark (the newest PR
  `updated_at` ingested, plus the `--state` it used); subsequent syncs fetch
  only PRs updated since then and stop paginating early. Use `prm sync --full`
  to force a complete re-fetch. `prm repos` now shows the last-synced time.

## [0.1.3] - 2026-06-14

### Documentation
- README feature list now documents case-insensitive fuzzy author matching and
  `--mine`. No functional changes since 0.1.2.

## [0.1.2] - 2026-06-14

### Added
- Case-insensitive **substring (fuzzy) matching** for `--author`, so
  `--author dependabot` matches `dependabot[bot]`. `--mine` keeps an exact
  match on your own login.

## [0.1.1] - 2026-06-14

### Fixed
- Crash (`MarkupError`) when rendering PR content containing `[...]` that Rich
  parsed as console markup — e.g. a dependabot body `Bumps [pkg](url)...` or the
  author `dependabot[bot]`. PR titles, authors, bodies, tags, and notes are now
  escaped before rendering in `list` and `show`.

## [0.1.0] - 2026-06-14

### Added
- Initial release of **prmanager** (`prm`), a CLI to manage GitHub pull requests
  backed by local SQLite.
- Track repositories and **sync** their PRs into SQLite for fast, offline
  browsing.
- **List/filter** PRs by repo, state, author, tag, review status, and `--mine`.
- Local-only workflow state: per-PR **review status**, **notes**, and **tags**.
- **Write-back**: submit reviews to GitHub (`approve` / `request-changes` /
  `comment`) with a confirmation prompt.
- Interactive **REPL** with `/`-prefixed commands (bare `prm`).
- Shell **completion** for bash/zsh/fish.
- Authentication via `GITHUB_TOKEN`/`GH_TOKEN`, a saved config token, or the
  `gh` CLI.
- Offline **pytest** suite and **GitHub Actions CI** across Python 3.10–3.13.
- MIT license.

[Unreleased]: https://github.com/sbj-ee/PRmanager/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/sbj-ee/PRmanager/compare/v0.9.0...v1.0.0
[0.9.0]: https://github.com/sbj-ee/PRmanager/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/sbj-ee/PRmanager/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/sbj-ee/PRmanager/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/sbj-ee/PRmanager/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/sbj-ee/PRmanager/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/sbj-ee/PRmanager/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/sbj-ee/PRmanager/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/sbj-ee/PRmanager/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/sbj-ee/PRmanager/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/sbj-ee/PRmanager/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/sbj-ee/PRmanager/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/sbj-ee/PRmanager/releases/tag/v0.1.0
