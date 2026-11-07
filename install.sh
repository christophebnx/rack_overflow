#!/usr/bin/env bash
# Install Rack Overflow on a Mac or a Linux machine (Synology NAS included): uv, the clone on
# `main`, the dependencies, a settings file and the database. Safe to run again: it never
# overwrites an existing settings file and never touches existing data.
#
#   ./install.sh                     # from a clone: install in place
#   bash install.sh                  # from anywhere: clone into $RACK_DIR (default ~/rack_overflow)
#
# Environment:
#   RACK_DIR       where to clone when not run from a clone   (default: ~/rack_overflow)
#   RACK_DATA_DIR  data folder written into a new settings file (default: ~/RackOverflow)
#   RACK_REPO      repository URL                               (default: the GitHub repository)
#
# Guides: docs/deployment/mac.md, docs/deployment/nas.md.

set -euo pipefail

REPO_URL="${RACK_REPO:-https://github.com/christophebnx/rack_overflow.git}"
TARGET_DIR="${RACK_DIR:-$HOME/rack_overflow}"
DATA_DIR="${RACK_DATA_DIR:-$HOME/RackOverflow}"
SETTINGS="config.toml"

say() { printf '==> %s\n' "$*"; }
fail() { printf 'install.sh: error: %s\n' "$*" >&2; exit 1; }

case "$(uname -s)" in
  Darwin | Linux) ;;
  *) fail "unsupported system $(uname -s): use macOS or Linux" ;;
esac

# 1. git
if ! command -v git >/dev/null 2>&1; then
  if [ "$(uname -s)" = Darwin ]; then
    fail "git is missing: run 'xcode-select --install', then run this script again"
  fi
  fail "git is missing: install it with your package manager (on DSM: Package Center, Git Server)"
fi

# 2. uv
export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  say "installing uv into ~/.local/bin"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  command -v uv >/dev/null 2>&1 || fail "uv was installed but is not on the PATH; open a new terminal and run this script again"
fi

# 3. the clone
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-.}")" && pwd)" # "." when piped from curl
if [ -f "$script_dir/pyproject.toml" ] && grep -q '^name = "rack-overflow"' "$script_dir/pyproject.toml"; then
  app_dir="$script_dir"
  say "using the clone in $app_dir"
elif [ -d "$TARGET_DIR/.git" ]; then
  app_dir="$TARGET_DIR"
  say "using the existing clone in $app_dir"
else
  [ -e "$TARGET_DIR" ] && fail "$TARGET_DIR exists and is not a clone; set RACK_DIR to another folder"
  say "cloning $REPO_URL into $TARGET_DIR"
  git clone --branch main "$REPO_URL" "$TARGET_DIR"
  app_dir="$TARGET_DIR"
fi
cd "$app_dir"

# 4. dependencies (uv also installs Python 3.12 if needed)
say "installing the dependencies"
uv sync --frozen

# 5. settings file, created once from the example
if [ -e "$SETTINGS" ]; then
  say "keeping the existing $SETTINGS"
else
  case "$DATA_DIR" in
    /*) ;;
    *) fail "RACK_DATA_DIR must be an absolute path, got '$DATA_DIR'" ;;
  esac
  say "creating $SETTINGS (data folder: $DATA_DIR)"
  tmp="$(mktemp "$SETTINGS.XXXXXX")"
  sed "s|^data_dir = .*|data_dir = \"$DATA_DIR\"|" config.example.toml >"$tmp"
  mv "$tmp" "$SETTINGS"
fi

# 6. database: create or upgrade, seed the catalog and the templates
say "creating or upgrading the database"
uv run rack migrate --config "$SETTINGS"

cat <<EOF

Rack Overflow is installed in $app_dir.

Next steps:
  cd "$app_dir"
  uv run rack serve                  # http://localhost:8765 (Ctrl-C to stop)
  uv run rack device add Mac         # in another terminal: one-time code for /appairage

To use it from the iPhone on the same Wi-Fi, set host and public_host in $SETTINGS
(see docs/deployment/mac.md, section 6). Start at login: section 7 of the same guide.
EOF
