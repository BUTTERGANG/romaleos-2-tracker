# Keeping the Hermes agent alive across Replit resets

Replit only persists **`$REPL_HOME`** (`/home/runner/workspace`). Everything else
under `/home/runner` — `~/.hermes`, `~/.local/bin`, `~/.bashrc` — is rebuilt from a
base image whenever the container recycles. The stock Hermes installer puts the
whole install in that throwaway zone, so every reset forced a full reinstall +
`hermes setup`.

## How it's wired now

| Piece | Location | Persists |
|---|---|---|
| Hermes tree (code, venv, bundled Node, `config.yaml` / `.env` / `state.db`) | `$REPL_HOME/.hermes` | ✅ real dir in the workspace |
| `~/.hermes` | symlink → `$REPL_HOME/.hermes`, recreated each boot | ✅ via bootstrap |
| CLI shims (`hermes`, `hermes-acp`, `hermes-agent`) | `$REPL_HOME/.hermes-bin/` | ✅ call the workspace venv directly |
| `PATH` + `HERMES_HOME` | `$REPL_HOME/.config/bashrc` (interactive) and `.replit` `[env]` (agent/workflow/deploy) | ✅ both files live in the workspace |
| Self-heal | `$REPL_HOME/scripts/hermes-bootstrap.sh` | ✅ |

`$REPL_HOME/.config/bashrc` is auto-sourced by Replit's stock bashrc for
interactive shells; `.replit` `[env]` covers the shells that don't source it.
The bootstrap script is idempotent — it just re-points `~/.hermes` and refreshes
`~/.local/bin`.

## After a reset

Nothing to do. Open a shell (or run the app) and `hermes` works. Verify with:

```bash
hermes --version   # Install directory: /home/runner/workspace/.hermes/hermes-agent
hermes doctor
```

## If `$REPL_HOME/.hermes` itself is ever lost

Reinstall once, pointed at the persistent path:

```bash
HERMES_HOME="$REPL_HOME/.hermes" HERMES_INSTALL_DIR="$REPL_HOME/.hermes/hermes-agent" \
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
```

## Updating Hermes

`hermes update` (or `hermes doctor --fix`) operates on the workspace copy in
place, so updates persist automatically.
