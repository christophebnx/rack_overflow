# Install and update on the Synology NAS (LAN only)

Target: Synology DS224+ on DSM 7.2, the app reachable from the home network only (D-013, D-024). No Docker, no reverse proxy, no certificate, no router port forward. Design: `docs/architecture/2026-11-03-l1b-auth-and-deployment.md`; decisions D-038, D-049, D-051.

Each step ends with a **Check**: a command and the output to expect. Commands run over SSH as the dedicated user unless stated otherwise. Paths below assume the volume `/volume1`; adapt if yours differs.

## 1. Dedicated user and SSH

1. DSM → Control Panel → User & Group → Create: user `rack`, member of `users` only (not `administrators`), with a home folder (Control Panel → User & Group → Advanced → "Enable user home service").
2. DSM → Control Panel → Terminal & SNMP → enable the SSH service. Allow `rack` to log in over SSH (on DSM 7 only administrators may by default; either add the user to the SSH-allowed list of your DSM version, or run the install steps from an admin account with `sudo -u rack -i`).
3. Create the folder of the app as an administrator: `sudo mkdir -p /volume1/rack && sudo chown rack:users /volume1/rack`.

**Check**: `ssh rack@<nas>` then `whoami && ls -ld /volume1/rack` → `rack` and a folder owned by `rack`.

## 2. Git

DSM → Package Center → install **Git Server** (it provides the `git` command).

**Check**: `git --version` → `git version 2.x`.

## 3. uv (and Python)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # installs into ~/.local/bin
. ~/.profile                                        # or open a new SSH session
uv python install 3.12
```

**Check**: `uv --version` → `uv 0.x`; `uv python find 3.12` → a path under `~/.local/share/uv/python/`.

## 4. Clone `main`

```bash
cd /volume1/rack
git clone --branch main <repository URL> rack_overflow
```

The clone lives on the local volume. The data folder must be on a local volume too, **never a mounted network share** (SQLite locking).

**Check**: `git -C /volume1/rack/rack_overflow rev-parse --abbrev-ref HEAD` → `main`.

## 5. Settings

```bash
cd /volume1/rack/rack_overflow
cp config.example.toml config.toml
```

Edit `config.toml` (git-ignored):

```toml
[server]
host = "0.0.0.0"          # listen on the LAN
port = 8765
public_host = "192.168.1.20"   # the LAN IP or name you type in the browser, without port
https = false

[storage]
data_dir = "/volume1/rack/data"   # absolute, on a local volume

[backup]
retention_days = 30
```

`public_host` must be exactly the host name typed in the browser: other `Host` headers are refused, and the device cookie is bound to that name.

**Check**: `grep -E '^(host|public_host|data_dir)' config.toml` → the three values above.

## 6. Install and create the database

```bash
uv sync --frozen
.venv/bin/rack --version
.venv/bin/rack migrate --config config.toml
```

**Check**: `rack 0.1.0` (or the current version), then `database /volume1/rack/data/rack.sqlite at revision 0002` (or the current head).

## 7. Start at boot

DSM → Control Panel → Task Scheduler → Create → Triggered Task → User-defined script:

- General: task name `rack`, user **`rack`**, event **Boot-up**, enabled.
- Task Settings → Run command:

  ```bash
  cd /volume1/rack/rack_overflow && .venv/bin/rack supervise --config config.toml
  ```

Then select the task and click **Run** once, so you do not have to reboot now.

`rack supervise` runs `rack serve`, restarts it after a crash (1, 2, 4… seconds, at most 5 minutes), writes the logs to `/volume1/rack/data/logs/rack.log` (rotated, 5 × 1 MiB), and refuses to start twice on the same data folder.

**Check**: `cat /volume1/rack/data/supervise.pid` → a number; `tail -n 3 /volume1/rack/data/logs/rack.log` → a line ending in `Uvicorn running on http://0.0.0.0:8765 (Press CTRL+C to quit)`; from the NAS, `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8765/appairage` → `200`.

## 8. Firewall (LAN only)

DSM → Control Panel → Security → Firewall → enable, edit the rules of the active profile:

1. Allow: port 8765 (TCP), source IP = your LAN subnet (e.g. `192.168.1.0/255.255.255.0`).
2. Keep SSH and DSM allowed from the LAN.
3. Last rule: deny all.

Do **not** add any port forward on the router: the app is not exposed to the Internet during development (D-013).

**Check**: from a computer on the LAN, `curl -s -o /dev/null -w '%{http_code}\n' http://<public_host>:8765/appairage` → `200`; from a phone on mobile data (Wi-Fi off), the same URL does not load.

## 9. Pair the iPhone

On the NAS:

```bash
cd /volume1/rack/rack_overflow
.venv/bin/rack device add iPhone --config config.toml
```

It prints `device "iPhone" added; pairing code 1234 5678, valid until …Z (10 minutes)` and `open http://<public_host>:8765/appairage on the device and type the code`. In Safari on the iPhone, open that URL, type the 8 digits, tap « Appairer ». The browser lands on the home page and stays paired as long as it is used at least once every 400 days.

The code works once, for 10 minutes, and five wrong attempts block it. To get a new one: `rack device revoke iPhone --config config.toml`, then `rack device add iPhone` again. Do the same for the desktop browser with another name.

**Check**: `.venv/bin/rack device list --config config.toml` → a row `iPhone  paired  …`.

## 10. Day-to-day

- Logs: `tail -f /volume1/rack/data/logs/rack.log`.
- Stop: `kill $(cat /volume1/rack/data/supervise.pid)` (the server stops, then the supervisor; the PID file is removed). Start again with the task's **Run** button.
- Revoke a lost device: `.venv/bin/rack device revoke <name> --config config.toml` (works while the server runs).
- Manual backup: `.venv/bin/rack backup --config config.toml` (the server also takes one every day).

**Check**: after `kill`, `cat /volume1/rack/data/supervise.pid` → `No such file or directory`.

## 11. Update

When you are **not logging a session** (during the few seconds between the migration and the restart the old server runs on the new files):

```bash
cd /volume1/rack/rack_overflow
.venv/bin/rack update --config config.toml
```

It refuses to run unless the clone is on `main` with no local changes (`config.toml` and the data folder do not count), then pulls, runs `uv sync --frozen`, migrates the database (after a backup), and asks the supervisor to restart on the new code. When nothing changed it prints `already up to date`. If a step fails, it prints the step and its output, exits with code 1, and does not restart: the running server keeps its code.

**Check**: the last line is `restart requested (supervisor pid N)` or `already up to date`; `grep 'supervisor started' /volume1/rack/data/logs/rack.log | tail -n 1` shows a fresh timestamp after an update.

## 12. Reboot check

Reboot the NAS (DSM → Restart). After it is back:

**Check**: `cat /volume1/rack/data/supervise.pid` → a number; the iPhone opens the app directly, without pairing again.

## Later: exposure through the DDNS (not V1 development)

Exposing the app on the Internet is a router change made by the user: forward a high, non-standard external port to `<NAS>:8765`. `public_host` then becomes the DDNS name. The device cookie is bound to the host name typed in the browser, so each device pairs again under the new name. HTTPS and a reverse proxy are V2 (D-013). Jelastic deployment is milestone L6.
