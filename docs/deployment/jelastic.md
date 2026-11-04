# Install and update on Infomaniak Jelastic Cloud

Target: one Infomaniak Jelastic Cloud environment holding a single **Linux / VPS node** (Ubuntu or AlmaLinux), running `rack serve` under systemd, with the database on the node's own disk and plain HTTP on a high, non-standard port (D-013, D-038, D-076). Not the Jelastic Python application server: it is built for WSGI apps, while Rack Overflow is its own ASGI server with a CLI. Design: `docs/architecture/2026-11-03-l6-operations.md`. Written for `rack 1.0.0`.

Each step ends with a **Check**: a command and the output to expect. Commands run over SSH on the node, as `root` (prompt `#`) or as the dedicated user `rack` (prompt `$`, after `sudo -iu rack`).

> **The data folder must be on the node's own disk.** Never put `data_dir` on a Jelastic Shared Storage container or any mounted network volume (NFS, GlusterFS…): SQLite's locking and its WAL need local storage (brief §7.3). A database on a network volume can be corrupted silently.

## 1. Environment and node

1. Jelastic dashboard → **New Environment** → the **VPS** (or "Custom" / "Linux") tab → a **Ubuntu** (22.04 or later) or **AlmaLinux** (9 or later) node. One node, no load balancer, no Shared Storage.
2. Resources: 1 to 2 cloudlets reserved is enough for one user; give the node a **disk** of a few GiB (the database and 30 daily snapshots stay small).
3. Network: attach a **public IPv4** to the node (recommended), or plan a TCP endpoint (step 8).
4. Open an SSH session: dashboard → node → **Web SSH**, or your own key through the Jelastic SSH gate.

**Check**: `# cat /etc/os-release | head -n 2` → Ubuntu or AlmaLinux; `# df -h /home` → a local device (e.g. `/dev/…`), not an `nfs` or `glusterfs` mount.

## 2. Dedicated user, git

```bash
# useradd --create-home --shell /bin/bash rack
# apt-get install -y git curl        # Ubuntu
# dnf install -y git curl            # AlmaLinux
```

**Check**: `# id rack` → a uid; `# git --version` → `git version 2.x`.

## 3. uv and Python (as `rack`)

```bash
# sudo -iu rack
$ curl -LsSf https://astral.sh/uv/install.sh | sh     # installs into ~/.local/bin
$ . ~/.profile                                        # or open a new session
$ uv python install 3.12
```

**Check**: `$ uv --version` → `uv 0.x`; `$ uv python find 3.12` → a path under `~/.local/share/uv/python/`.

## 4. Clone `main`

```bash
$ cd /home/rack
$ git clone --branch main <repository URL> rack_overflow
```

**Check**: `$ git -C /home/rack/rack_overflow rev-parse --abbrev-ref HEAD` → `main`.

## 5. Settings

```bash
$ cd /home/rack/rack_overflow
$ cp config.example.toml config.toml
```

Edit `config.toml` (git-ignored):

```toml
[server]
host = "0.0.0.0"              # listen on every interface of the node
port = 18765                  # high, non-standard
public_host = "203.0.113.10"  # exactly what you type in the browser: the public IP, or the endpoint's host name
https = false

[storage]
data_dir = "/home/rack/data"  # absolute, on the node's own disk (never Shared Storage)

[backup]
retention_days = 30

[calendar]
time_zone = "Europe/Brussels" # where the sessions take place
```

`public_host` must be exactly the host name typed in the browser, without the port: other `Host` headers are refused and the device cookie is bound to that name. If the NAS install is also used, keep the same `time_zone` on both (`docs/deployment/migration.md`).

**Check**: `$ grep -E '^(host|port|public_host|data_dir)' config.toml` → the four values above.

## 6. Install and create the database

```bash
$ uv sync --frozen
$ .venv/bin/rack --version
$ .venv/bin/rack migrate --config config.toml
```

When the data will come from another install (NAS), **skip the `migrate` line** and follow `docs/deployment/migration.md` from here: the restore creates the database.

**Check**: `rack 1.0.0` (or the current version), then `database /home/rack/data/rack.sqlite at revision 0004` (or the current head), then `seeded 41 exercises` and `seeded 4 templates` on the first run.

## 7. systemd unit

systemd starts the server at boot, restarts it after a crash and keeps its logs, so `rack supervise` is not used on Jelastic (D-038, D-076). The daily backup runs inside the server, as on the NAS. As `root`, create `/etc/systemd/system/rack.service`:

```ini
[Unit]
Description=Rack Overflow
After=network-online.target
Wants=network-online.target

[Service]
User=rack
WorkingDirectory=/home/rack/rack_overflow
ExecStart=/home/rack/rack_overflow/.venv/bin/rack serve --config config.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
# systemctl daemon-reload
# systemctl enable --now rack
```

**Check**: `# systemctl is-active rack` → `active`; `# journalctl -u rack -n 5` → a line ending in `Uvicorn running on http://0.0.0.0:18765 (Press CTRL+C to quit)`; `# curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18765/appairage` → `200`.

## 8. Exposure (plain HTTP) and firewall

V1 serves plain HTTP on the configured port; no Jelastic SSL, no load balancer, no reverse proxy (D-013: HTTPS is V2).

- **Public IP** (recommended): browse `http://<public IP>:18765/`; `public_host` is the IP (or a DNS name you point at it).
- **TCP endpoint** (no public IP): dashboard → environment **Settings** → **Endpoints** → add a TCP endpoint to private port `18765`. Jelastic gives a host name and a public port: set `public_host` to that host name and type the **public** port in the browser. The pairing URL printed by `rack device add` shows the private port: replace it by the public one.

Firewall: dashboard → environment **Settings** → **Firewall** (or the node's own firewall) → inbound rule allowing TCP `18765` only, plus SSH; everything else denied.

**Check**: from your computer, `curl -s -o /dev/null -w '%{http_code}\n' http://<public_host>:<port>/appairage` → `200`; only that port and SSH are open (e.g. `nc -z -w 3 <public_host> 8080` fails).

## 9. Pair the devices

```bash
$ cd /home/rack/rack_overflow
$ .venv/bin/rack device add iPhone --config config.toml
```

Open the printed URL in Safari on the iPhone (with the public port when using an endpoint), type the 8 digits, tap « Appairer ». Same for the desktop browser with another name.

**Check**: `$ .venv/bin/rack device list --config config.toml` → a row `iPhone  paired  …`.

## 10. Day-to-day

- Logs: `# journalctl -u rack -f`.
- Stop / start / restart: `# systemctl stop rack`, `# systemctl start rack`, `# systemctl restart rack`.
- Manual backup: `$ .venv/bin/rack backup --config config.toml` (the server also takes one every day into `/home/rack/data/backups/`).
- Export: `$ .venv/bin/rack export /home/rack/export-$(date +%Y%m%d).json --config config.toml` (or `--format csv`), or « Réglages » → « Données » in the browser.
- Revoke a lost device: `$ .venv/bin/rack device revoke <name> --config config.toml`.

**Check**: `$ ls /home/rack/data/backups` → `rack-<UTC time>.sqlite` files, the newest less than a day old.

## 11. Update

When you are not logging a session:

```bash
$ cd /home/rack/rack_overflow
$ .venv/bin/rack update --config config.toml
# systemctl restart rack
```

`rack update` refuses unless the clone is on `main` with no local changes, then pulls, runs `uv sync --frozen` and migrates the database (after a backup when a revision is pending), as on the NAS (D-052). It ends with `no rack supervise running; restart the server yourself`: systemd runs the server here, so restart it with `systemctl restart rack`. If a step fails, fix the cause and run `rack update` again before restarting.

**Check**: `# journalctl -u rack -n 20` shows a fresh `Uvicorn running on …` line; `$ .venv/bin/rack --version` → the new version.

## 12. Restore a backup

```bash
# systemctl stop rack
$ cd /home/rack/rack_overflow
$ ls /home/rack/data/backups
$ .venv/bin/rack restore rack-20261103T020000Z.sqlite --config config.toml
# systemctl start rack
```

`rack restore` refuses while a server answers on the configured port (`a server answers on 127.0.0.1:18765; stop it first`). It probes the port once, at its start, and systemd is not covered by the supervise lock: stop the unit with `systemctl stop rack` (never by killing the process: `Restart=on-failure` would start it again within 5 s, possibly after the probe and in the middle of the restore), and start it only once the restore has printed its last line. It keeps the current database aside as `rack.sqlite.before-restore-<UTC time>` (never deleted), restores the snapshot and migrates it when it comes from an older version; details, refusals and an interrupted restore (rerun the command) as in `docs/deployment/nas.md` section 13.

**Check**: the output ends with `restored … at revision …` (and `database … at revision …` after a migration); `# systemctl is-active rack` → `active` after the start.

## 13. Reboot check

Dashboard → node → **Restart node**.

**Check**: `# systemctl is-active rack` → `active`; the iPhone opens the app without pairing again.
