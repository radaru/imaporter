# AGENTS.md — IMAPorter

## Project Overview

IMAPorter is a single-file Python 3 daemon that fetches emails from an external IMAP
account via IMAP IDLE, optionally filters them through SpamAssassin (`spamc`), and
delivers them into a Gmail account via IMAP APPEND. It runs as a systemd service
or as a **Home Assistant app** (HAOS).

The entire application logic lives in **one file**: `imaporter/imaporter.py` (≈415 lines).
There is no package structure, but the code is structured in an Object-Oriented Programming (OOP) model.
No async code, but uses standard library `threading` to run concurrent workers for multiple source accounts.
A symlink at `imaporter.py` (repo root) points to `imaporter/imaporter.py` for
backward compatibility with the bare-metal deployment path.

## Tech Stack

- **Language**: Python 3 (no minimum version pinned; uses f-strings, so ≥3.6)
- **Dependencies**: `imapclient>=3.0.1` (sole third-party dependency, in `requirements.txt`)
- **External tools**: `spamc` (SpamAssassin client), `systemd`
- **Config format**: INI (`configparser`)

## Key Files

| File | Purpose |
|---|---|
| `imaporter/imaporter.py` | Entire application — fetch, filter, deliver loop |
| `imaporter.py` | Symlink → `imaporter/imaporter.py` (backward compat) |
| `config.ini` | Runtime configuration (IMAP hosts, ports, SpamAssassin toggles) |
| `requirements.txt` | Python dependencies (`imapclient`) |
| `Makefile` | Install/uninstall/update/service management targets |
| `install.sh` | System installer (creates user, venv, deploys to `/opt/imaporter/`) |
| `imaporter.service` | Systemd unit file (uses `LoadCredential` for secrets) |
| `plan.md` | Architecture design doc with Mermaid diagram |
| `README.md` | User-facing documentation and setup instructions |
| `repository.yaml` | HA app repository manifest (enables GitHub-based install) |
| `imaporter/config.yaml` | HA app manifest (options, schema, architecture) |
| `imaporter/Dockerfile` | HA app Docker image (Alpine + Python3 + SpamAssassin) |
| `imaporter/rootfs/` | S6 overlay service scripts for HA app |
| `imaporter/DOCS.md` | HA app user documentation |
| `imaporter/CHANGELOG.md` | HA app changelog |
| `imaporter/translations/en.yaml` | English labels for HA app config UI |

## Build & Run Commands

There is no build step. This is an interpreted Python script.

### Makefile Targets

```bash
make install      # Full system install: creates user, venv, deploys to /opt/imaporter/
make uninstall    # Stops service, removes systemd unit and /opt/imaporter/
make update       # Hot-swap imaporter.py into /opt/imaporter/ and restart service
make run-logs     # Tail the journald logs (journalctl -u imaporter.service -f)
make enable       # Enable and start the systemd service
make disable      # Disable and stop the systemd service
```

### Manual / Development Run

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python3 imaporter.py                # Reads config.ini from cwd
```

### Dependency Installation

```bash
pip install -r requirements.txt     # Only installs imapclient
```

## Testing

**No test infrastructure exists.** There are no test files, no test framework, no
test configuration, and no `test` target in the Makefile. The `requirements.txt`
contains no test dependencies.

If tests are added in the future, note that the key testable components are:
`ConfigManager`, `SpamFilter`, `IMAPConnection`, `RelayWorker`.

## Code Style

### Formatting

No formatter (black, autopep8, yapf) or linter (ruff, flake8, pylint) is configured.
No `.editorconfig`. Code is manually formatted. No CI/CD pipeline enforces style.

### Imports (imaporter.py:1-13)

- One import per line.
- Stdlib imports first (`argparse`, `configparser`, `logging`, `os`, `signal`, etc.),
  then third-party (`imapclient`). Grouping is not enforced by tooling; no blank line
  separates groups.
- `from` imports used for specific symbols: `from imapclient import IMAPClient`.
- `import socket` appears after third-party imports (line 13), breaking strict ordering.
  Not a convention to follow — just current state.

### Naming Conventions

| Element | Convention | Examples |
|---|---|---|
| Files | `snake_case` | `imaporter.py`, `install.sh`, `config.ini` |
| Functions | `snake_case` | `load_config`, `connect_imap`, `check_spam`, `run_loop` |
| Variables | `snake_case` | `src_client`, `dst_client`, `ham_folder`, `raw_msg`, `scored_msg` |
| Unused args | Leading underscore | `_signo`, `_stack_frame` (line 229) |
| Module-level objects | Lowercase | `logger` (line 15) |
| Constants | None promoted to `UPPER_CASE` | `spam_folder = '[Gmail]/Spam'` is a local var |
| Classes | `PascalCase` | `ConfigManager`, `SpamFilter`, `IMAPConnection`, `RelayWorker`, `RelayDaemon` |

### Type Annotations

Basic type hints are used for function and method signatures (e.g. arguments and return values).
The file imports `List`, `Tuple`, and `Optional` from the standard library `typing` module.

### Functions

- Methods and functions use `def` declarations — no lambdas or closures.
- Uses standard library decorators (specifically, `@dataclass`).
- No async/await — the daemon uses blocking I/O with IMAP IDLE.
- Methods are short and focused.
- Default parameter values used: `config_path='config.ini'`, `section_name=None`.

### Comments and Docstrings

- Inline `#` comments explain *why* or clarify non-obvious behavior.
- Only one docstring exists: `check_spam()` (lines 58-61), describing input/output.
- No TODO/FIXME/HACK markers in the codebase.

### Logging

- Uses stdlib `logging` with a single logger: `logging.getLogger('imaporter')`.
- `logging.basicConfig()` is called in `__main__` after arg parsing, so log level
  is configurable via `--log-level` CLI arg or `IMAPORTER_LOG_LEVEL` env var.
- Output goes to stdout; systemd/S6 captures it via journald/container logs.
- Format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`.
- All log messages use f-strings.
- Levels used: `debug` (credential loading), `info` (connections, processing),
  `warning` (size limits), `error` (failures), `fatal` (config load failure).

### Error Handling Patterns

Several distinct patterns are used throughout:

1. **Return sentinel on failure** — `IMAPConnection.connect()` returns `False` on retry exhaustion.

2. **Nested try/except with fallback then re-raise** — `IMAPConnection.ensure_folder()` tries to
   select, falls back to create, re-raises if both fail.

3. **Tiered exception handling in the worker loop** — `RelayWorker.run()` catches
   `ConnectionError` and `socket.error`/`socket.timeout`/`IMAPClientError` for fast retry (30s)
   and generic `Exception` for slow retry (60s).

4. **Bare `except: pass` for cleanup** — used only when logging out dead IMAP
   connections inside `IMAPConnection.disconnect()`.

5. **Fail-open for external tools** — if `spamc` fails, the message is treated as
   ham (not spam) and delivered normally.

6. **Guaranteed Cleanup via try...finally** — `RelayWorker.process_unseen()` wraps critical
   delivery and post-delivery cleanup (deleting/marking read) in a `try...finally` block.
   Source deletion is only triggered if the `delivered` boolean flag is successfully set.

### String Formatting

f-strings exclusively. No `.format()`, no `%` formatting.

## Architecture Notes

- **Daemon loop** (`RelayWorker.run()`): connects clients, processes unseen emails, enters IMAP IDLE,
  checks for IDLE events or shutdown events, and repeats. Re-IDLEs every 29 minutes per RFC recommendation.
- **Connection management**: Wrapped in `IMAPConnection` instances. Clients are set to `None` on
  disconnection and reconnected dynamically on error.
- **SIGTERM handling**: graceful shutdown via `signal.signal` + `sys.exit(0)` (line 234).
- **Credential injection**: passwords can come from `config.ini` or from systemd
  `LoadCredential` files in `$CREDENTIALS_DIRECTORY` (lines 30-37).
- **Gmail label trick**: APPEND to ham folder, then COPY to label folder. If APPENDUID
  response is available, uses it for efficient COPY; otherwise double-APPENDs (lines 132-153).
- **Concurrency**: Multi-threaded. `RelayDaemon` spawns a separate `RelayWorker` thread for each
  configured source account in `config.ini`, enabling concurrent processing of multiple accounts.

## Home Assistant App Architecture

The HA app runs as a Docker container managed by the HA Supervisor. It uses
the HA base image with S6-Overlay V3 for process supervision.

### Deployment model

- **Repository-based install**: users add the GitHub repo URL in HA's app store.
  The `repository.yaml` at the repo root identifies it as an HA app repository.
  The `imaporter/` directory (matching the `slug` in `config.yaml`) contains the app.
- **Locally built**: the Supervisor builds the Docker image on the user's device from
  the `imaporter/Dockerfile`. No pre-built images are published yet.

### Container structure

- **S6 services**: long-running services under `/etc/services.d/`:
  - `spamd/run`: SpamAssassin daemon (or `sleep infinity` if disabled); configures persistent Bayes DB at `/data/spamassassin/bayes`
  - `cron/run`: System cron daemon (`crond`) for background maintenance tasks
  - `imaporter/run`: generates `config.ini` from HA options, then `exec`s `imaporter.py`
- **Periodic tasks**: `/etc/periodic/daily/sa-update`: Daily background rule updater (triggers `sa-update` and reloads `spamd` via `SIGHUP` every 24h)
- **Config bridging**: HA options (`/data/options.json`) are translated to `config.ini`
  format at `/data/config.ini` by the `imaporter/run` S6 script using bashio.
- **No `CMD`/`ENTRYPOINT`**: S6 overlay's `/init` is the entrypoint (requires `init: false`
  in `config.yaml` for V3 compatibility).

### Key files

| File | Purpose |
|---|---|
| `imaporter/config.yaml` | App manifest: options schema, arch, startup order |
| `imaporter/Dockerfile` | Alpine base + Python3 + SpamAssassin + imapclient |
| `imaporter/rootfs/etc/services.d/spamd/run` | S6 service: SpamAssassin daemon |
| `imaporter/rootfs/etc/services.d/imaporter/run` | S6 service: config bridge + imaporter |
| `imaporter/translations/en.yaml` | Config UI labels |
| `imaporter/DOCS.md` | In-app documentation |
| `repository.yaml` | Repo-level manifest for HA app store |

## "Self-healing" document

It there are any significant changes in code update this file ie. AGENTS.md to stay up to date.
