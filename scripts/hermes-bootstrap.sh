#!/usr/bin/env bash
# Restore the Hermes agent after a Replit container reset.
#
# Replit only persists $REPL_HOME (/home/runner/workspace). Everything else under
# /home/runner is rebuilt from a base image on every reset. The real Hermes tree
# lives at $REPL_HOME/.hermes; this script recreates the ephemeral bits that point
# at it (the canonical ~/.hermes path and the ~/.local/bin shims) so hard-coded
# paths inside the venv keep resolving.
#
# Safe to run repeatedly. Sourced from $REPL_HOME/.config/bashrc and invoked from
# the .replit run command.
set -eu

RT="${REPL_HOME:-$HOME/workspace}/.hermes"

if [ ! -d "$RT/hermes-agent" ]; then
  echo "hermes-bootstrap: $RT not found — run the full installer once:" >&2
  echo "  HERMES_HOME=$RT HERMES_INSTALL_DIR=$RT/hermes-agent \\" >&2
  echo "  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash" >&2
  exit 0
fi

# 1. Canonical ~/.hermes -> workspace copy (venv shebangs hard-code this path)
if [ ! -L "$HOME/.hermes" ] || [ "$(readlink "$HOME/.hermes")" != "$RT" ]; then
  rm -rf "$HOME/.hermes"
  ln -sfn "$RT" "$HOME/.hermes"
fi

# 2. CLI shims + bundled node on ~/.local/bin (belt-and-braces; PATH also has
#    $REPL_HOME/.hermes-bin directly via .config/bashrc and .replit [env]).
#    The hermes shims are copied as plain files, not symlinked — `hermes doctor`
#    flags a ~/.local/bin/hermes symlink that doesn't resolve to venv/bin/hermes,
#    but accepts a regular-file wrapper.
mkdir -p "$HOME/.local/bin"
for f in hermes hermes-acp hermes-agent; do
  [ -e "${REPL_HOME:-$HOME/workspace}/.hermes-bin/$f" ] \
    && cp -f "${REPL_HOME:-$HOME/workspace}/.hermes-bin/$f" "$HOME/.local/bin/$f"
done
for f in node npm npx; do
  [ -e "$RT/node/bin/$f" ] && ln -sfn "$RT/node/bin/$f" "$HOME/.local/bin/$f"
done

exit 0
