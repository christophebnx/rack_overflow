# Install and update on the Synology NAS (LAN only)

Target: Synology DS224+ on DSM 7.2, the app reachable from the home network only (D-013, D-024). No Docker, no reverse proxy, no certificate, no router port forward. Design: `docs/architecture/2026-11-03-l1b-auth-and-deployment.md` and `docs/architecture/2026-11-03-l6-operations.md`; decisions D-038, D-049, D-051, D-052, D-074, D-075. Written for `rack 1.0.0`.

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

[calendar]
time_zone = "Europe/Brussels"   # where the sessions take place (optional, this is the default)
```

`public_host` must be exactly the host name typed in the browser: other `Host` headers are refused, and the device cookie is bound to that name. `time_zone` gives each session its local date and the times shown on its pages; it does not depend on the NAS's own zone (D-065).

**Check**: `grep -E '^(host|public_host|data_dir)' config.toml` → the three values above.

## 6. Install and create the database

```bash
uv sync --frozen
.venv/bin/rack --version
.venv/bin/rack migrate --config config.toml
```

**Check**: `rack 1.0.0` (or the current version), then `database /volume1/rack/data/rack.sqlite at revision 0004` (or the current head), then `seeded 41 exercises` and `seeded 4 templates` on the first run (the exercise catalog and the session templates, D-057, D-060; later runs add nothing).

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

It refuses to run unless the clone is on `main` with no local changes (`config.toml` and the data folder do not count), then pulls, runs `uv sync --frozen`, migrates the database (after a backup when a revision is pending), and asks the supervisor to restart on the new code. When the pull brings nothing new it prints `already up to date; checking dependencies and database` and still runs the sync, the migration and the restart (D-052). If a step fails, it prints the step and its output, exits with code 1, and does not restart: the running server keeps its code. **Fix the cause and run `rack update` again**: the rerun completes the sync and the migration even though the code is already pulled, then restarts the server.

**Check**: the last line is `restart requested (supervisor pid N)`; `grep 'supervisor started' /volume1/rack/data/logs/rack.log | tail -n 1` shows a fresh timestamp after an update.

## 12. Export the data

A complete copy of every stored fact (archived and deleted items included), to keep or to open in another tool. It is not a backup: the app cannot be restored from it (section 13 restores a backup).

- From a browser: « Réglages » (linked from « Progression ») → « Données » → « Exporter en JSON » (one lossless file) or « Exporter en CSV » (a zip with one table per kind of data, for Excel, Numbers or LibreOffice). Safari on the iPhone asks where to save the file (Files).
- From the NAS, while the server runs:

  ```bash
  cd /volume1/rack/rack_overflow
  .venv/bin/rack export /volume1/rack/export-$(date +%Y%m%d).json --config config.toml
  .venv/bin/rack export /volume1/rack/export-$(date +%Y%m%d).zip --format csv --config config.toml
  ```

  The file must not exist yet (an existing file is never replaced) and its folder must exist.

Values are in stored units: weights in grams (`weight_g`), durations in seconds, distances in metres; enum values by key, with their labels in the `variable` table. The device and pairing-code hashes are not exported (D-072). CSV files are UTF-8 with a BOM and `;` as separator; an empty cell means "no value" (the JSON tells an empty text from no value, the CSV cannot).

**Check**: the command prints `exported N rows to /volume1/rack/export-….json`; `head -c 200 /volume1/rack/export-….json` shows `"format": "rack-overflow-export"`.

## 13. Restore a backup

Restore replaces the database by one of the daily snapshots in `/volume1/rack/data/backups/` (or any snapshot file). **Stop the server first**: `rack restore` refuses while `rack supervise` holds its lock or while anything answers on the configured port, and then changes nothing.

1. Stop: `kill $(cat /volume1/rack/data/supervise.pid)`. Do not start the server again (task **Run**, a reboot) until step 4: `rack restore` holds the supervise lock while it runs, so `rack supervise` cannot start meanwhile, but it probes the port only once, at its start, so a plain `rack serve` started during the restore would not be caught.
2. Choose the snapshot: `ls /volume1/rack/data/backups` → `rack-20261103T020000Z.sqlite` … (UTC times, newest last).
3. Restore (a bare name is looked up in the backups folder; a path works too):

   ```bash
   cd /volume1/rack/rack_overflow
   .venv/bin/rack restore rack-20261103T020000Z.sqlite --config config.toml
   ```

   It copies the snapshot (with its `-wal` / `-journal` files when present) into a scratch folder beside the database, writes one checked single-file copy of it (latest writes included), checks its schema revision, then moves the current database aside, **never deleting it**: `kept /volume1/rack/data/rack.sqlite.before-restore-<UTC time>` (with its `-wal` / `-shm` files when present, so the copy opens with its latest writes), then `restored … as /volume1/rack/data/rack.sqlite at revision 0004`. A snapshot taken by an older version is then migrated as `rack migrate` does (`database … at revision …`). The snapshot file itself is only read.
4. Start again with the task's **Run** button (DSM → Control Panel → Task Scheduler → `rack`).

Refusals print `rack: error: …`, exit with code 1 and leave the current database as it was: a corrupt or truncated snapshot (`snapshot failed the integrity check`), a file that is not a Rack Overflow database, a snapshot from a newer version (`… unknown to this version …; update the code first`: run `rack update` first), the database itself, a running server (`… stop it first`).

If the restore is interrupted between moving the current database aside and the final rename (power cut, disk error), `rack.sqlite` is missing and the server refuses to start (`database is not up to date; run rack migrate`): **run the same `rack restore` command again**; it completes (nothing is left to move aside). Keep the `.before-restore-*` files until you are sure you do not need them: they are not snapshots and are never pruned. The restore needs free space for about two copies of the snapshot while it runs; the scratch folder is removed at the end.

To **undo a restore**, restore the set kept aside, by its full path (a bare name is looked up in the backups folder): stop the server, then

```bash
.venv/bin/rack restore /volume1/rack/data/rack.sqlite.before-restore-<UTC time> --config config.toml
```

It reads the file and the `-wal` / `-journal` beside it without changing them (a `-shm` is ignored), keeps every row (those still in the `-wal` included), and moves the database it replaces aside in its turn (`….before-restore-<new time>`).

**Check**: `ls /volume1/rack/data` → `rack.sqlite` and `rack.sqlite.before-restore-…`; after **Run**, « Historique » ends at the snapshot's date. The snapshot holds the devices as they were then: a device paired, or whose cookie was renewed, after the snapshot is sent to « Appairage »; pair it again with `rack device revoke <name>` then `rack device add <name>`.

## 14. Reboot check

Reboot the NAS (DSM → Restart). After it is back:

**Check**: `cat /volume1/rack/data/supervise.pid` → a number; the iPhone opens the app directly, without pairing again.

## Later: exposure through the DDNS (not V1 development)

Exposing the app on the Internet is a router change made by the user: forward a high, non-standard external port to `<NAS>:8765`. `public_host` then becomes the DDNS name. The device cookie is bound to the host name typed in the browser, so each device pairs again under the new name. HTTPS and a reverse proxy are V2 (D-013).

## Other hosts

- Infomaniak Jelastic Cloud: `docs/deployment/jelastic.md`.
- Moving the data between the NAS and Jelastic, in either direction: `docs/deployment/migration.md`.
