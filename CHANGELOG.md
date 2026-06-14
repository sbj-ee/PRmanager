# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/sbj-ee/PRmanager/compare/v0.1.3...HEAD
[0.1.3]: https://github.com/sbj-ee/PRmanager/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/sbj-ee/PRmanager/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/sbj-ee/PRmanager/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/sbj-ee/PRmanager/releases/tag/v0.1.0
