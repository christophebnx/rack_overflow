# Install on a Mac

Run Rack Overflow on a Mac: alone (use it from the Mac's browser) or as the server for the iPhone on the same Wi-Fi. Same native deployment as the NAS (D-024): a git clone on `main`, uv, `rack migrate`, `rack serve` or `rack supervise`. Plain HTTP, local network only (D-013). The server stops while the Mac sleeps.

## 1. Prerequisites (once)

```bash
xcode-select --install                               # git
curl -LsSf https://astral.sh/uv/install.sh | sh      # uv, installed into ~/.local/bin
```

Open a new Terminal window afterwards so `uv` is on the `PATH`.

## 2. Get the app

```bash
git clone --branch main https://github.com/christophebnx/rack_overflow.git ~/rack_overflow
cd ~/rack_overflow
uv sync --frozen                                     # Python 3.12 and the dependencies, in .venv
```

## 3. Settings

```bash
cp config.example.toml config.toml
open -e config.toml                                  # TextEdit
```

Change:

- `[storage] data_dir`: a folder for your real data outside the clone, e.g. `"~/RackOverflow"`. Never a synced folder (iCloud Drive, Dropbox, OneDrive): syncing a live SQLite file can corrupt it.
- Keep `[calendar] time_zone = "Europe/Brussels"` unless you train elsewhere.
- For the Mac alone, keep `host = "127.0.0.1"` and `public_host = "localhost"`. For the iPhone, see section 6.

Without `--config`, every `rack` command reads `config.toml` in the current folder; run them from `~/rack_overflow`.

## 4. Create the database and start

```bash
uv run rack migrate          # creates the database, seeds 41 exercises and 4 session templates
uv run rack serve            # http://localhost:8765 — Ctrl-C to stop
```

## 5. Pair the Mac's browser

In a second Terminal tab:

```bash
cd ~/rack_overflow
uv run rack device add Mac   # prints a one-time code, valid 10 minutes
```

Open http://localhost:8765/appairage and type the code. `uv run rack device list` shows the paired devices; `uv run rack device revoke NAME` removes one.

## 6. Use it from the iPhone (same Wi-Fi)

1. Find the Mac's address: `ipconfig getifaddr en0` (Wi-Fi; try `en1` if empty), e.g. `192.168.1.20`. Give the Mac a fixed address in the router (DHCP reservation) so it does not change.
2. In `config.toml`: `host = "0.0.0.0"` (accept the local network) and `public_host = "192.168.1.20"` (the address the iPhone types; any other host name is refused).
3. Restart `rack serve` and allow incoming connections when the macOS firewall asks.
4. `uv run rack device add iPhone`, then open `http://192.168.1.20:8765/appairage` in Safari on the iPhone and type the code. Add the page to the home screen if you like (Share → Sur l'écran d'accueil).

Do not forward this port on the router: the app has no HTTPS in V1 (D-013).

## 7. Start automatically at login (optional)

`rack supervise` runs the server and restarts it after a crash (D-051); launchd starts the supervisor at login. Create `~/Library/LaunchAgents/dev.rack-overflow.plist`, replacing `YOU` with your user name (`whoami`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>dev.rack-overflow</string>
  <key>WorkingDirectory</key><string>/Users/YOU/rack_overflow</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOU/.local/bin/uv</string>
    <string>run</string>
    <string>rack</string>
    <string>supervise</string>
    <string>--config</string>
    <string>/Users/YOU/rack_overflow/config.toml</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/Users/YOU/RackOverflow/launchd.log</string>
</dict>
</plist>
```

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.rack-overflow.plist   # start now and at each login
launchctl bootout gui/$(id -u)/dev.rack-overflow                                  # stop and disable
```

The server logs are in `<data_dir>/logs/`. Stop the launchd job before running `rack serve` by hand: two servers on one port cannot both start.

## 8. Update

```bash
cd ~/rack_overflow
uv run rack update           # with rack supervise running: pull main, sync, migrate, restart (D-052)
```

Without the supervisor: `git pull --ff-only && uv sync --frozen && uv run rack migrate`, then restart `rack serve`. Each migration takes a snapshot first. Never edit files in this clone: `rack update` refuses a clone with local changes.

## 9. Backups, export, restore

- A snapshot is taken every day the server runs, in `<data_dir>/backups/` (30 days kept). Also `uv run rack backup`.
- Copy `<data_dir>/backups/` to another disk now and then (Time Machine covers it if `data_dir` is in your home folder).
- Export: « Réglages » → « Données », or `uv run rack export ~/Desktop/rack.json`.
- Restore: stop the server (section 7), then `uv run rack restore <snapshot name>`; the current database is kept aside. Details in [`nas.md`](nas.md) section 13; the steps are the same on the Mac.

## 10. Browser tests on WebKit (pending V1 check)

The Mac can run the WebKit browser tests the build environment could not:

```bash
uv run playwright install webkit chromium
RACK_REQUIRE_BROWSER=1 uv run pytest -q tests/e2e
```

## Moving to the NAS later

Follow [`migration.md`](migration.md): take a snapshot on the Mac, copy it to the NAS, `rack restore` it there.
