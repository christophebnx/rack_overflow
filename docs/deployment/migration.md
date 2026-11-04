# Move the data between the NAS and Jelastic

Moving Rack Overflow from the Synology NAS to Infomaniak Jelastic Cloud, or back, is a backup on the source, a copy, and a restore on the target (D-075, D-076). The database file carries everything (catalog, sessions, settings, devices); the devices pair again because their cookie is bound to the host name. Written for `rack 1.0.0`.

Below, **source** is the install that holds the data today and **target** the new one. Paths: NAS `/volume1/rack/…` (`docs/deployment/nas.md`), Jelastic `/home/rack/…` (`docs/deployment/jelastic.md`). Each step ends with a **Check**.

## 1. Prepare the target

Install the target from its guide **up to the settings**, then `uv sync --frozen`, **without** `rack migrate` (no database there yet; a restore creates it):

- Same `[calendar] time_zone` as the source: local dates and times of the sessions depend on it.
- Code at the **same version as the source, or newer**: a snapshot from a newer version is refused (`… unknown to this version …; update the code first`). An older snapshot is migrated by the restore.
- Do not start the server on the target yet (NAS: do not click **Run**; Jelastic: do not `systemctl enable --now` yet, or `systemctl stop rack`).

**Check**: on the target, `.venv/bin/rack --version` prints a version equal to or newer than the source's; `ls <target data_dir>` → no `rack.sqlite`.

## 2. Stop the source and take a backup

Stop the source so that nothing is written after the backup:

- NAS: `kill $(cat /volume1/rack/data/supervise.pid)`.
- Jelastic: `systemctl stop rack`.

Then, on the source:

```bash
.venv/bin/rack backup --config config.toml
```

It prints the snapshot path, e.g. `/volume1/rack/data/backups/rack-20261103T184200Z.sqlite`.

**Check**: the printed file exists; `ls -l` shows a size of a few hundred KiB or more.

## 3. Copy the snapshot to the target

Create the target's backups folder and copy the printed file into it, e.g. NAS → Jelastic:

```bash
ssh rack@<jelastic node> mkdir -p /home/rack/data/backups
scp /volume1/rack/data/backups/rack-20261103T184200Z.sqlite rack@<jelastic node>:/home/rack/data/backups/
```

Jelastic → NAS: the same with the paths swapped (`/volume1/rack/data/backups/` on the NAS).

**Check**: `sha256sum` of the file gives the same value on both hosts.

## 4. Restore on the target

```bash
.venv/bin/rack restore rack-20261103T184200Z.sqlite --config config.toml
```

The bare name is looked up in the target's backups folder. The output ends with `restored … as <target data_dir>/rack.sqlite at revision …` (then `database … at revision …` when the target's code is newer and migrates it). Refusals change nothing (`docs/deployment/nas.md` section 13).

**Check**: `ls <target data_dir>` → `rack.sqlite`.

## 5. Start the target

- NAS: DSM → Task Scheduler → task `rack` → **Run** (and make sure the task is enabled for boot).
- Jelastic: `systemctl enable --now rack`.

**Check**: `curl -s -o /dev/null -w '%{http_code}\n' http://<target public_host>:<port>/appairage` → `200`.

## 6. Pair the devices again

The device cookie is bound to the host name typed in the browser, and the target has a different one: each browser must pair again. On the target, for each device listed by `rack device list`:

```bash
.venv/bin/rack device revoke iPhone --config config.toml
.venv/bin/rack device add iPhone --config config.toml
```

Open the printed URL on that device (on Jelastic with an endpoint, use the endpoint's public port), type the code. Update the bookmarks and the iPhone home-screen icon to the new address.

**Check**: `.venv/bin/rack device list --config config.toml` → each device `paired` with a fresh `LAST SEEN`; « Historique » on the iPhone shows the latest session logged on the source.

## 7. Keep the source stopped, then retire it

Keep the source stopped, and keep its data, until the target has been used for a while:

- NAS: DSM → Task Scheduler → task `rack` → disable it (so a reboot does not start it).
- Jelastic: `systemctl disable --now rack`.

Running both would split new sessions between two databases. Once the target is confirmed, the source's data folder can be archived; nothing on the target depends on it.

**Check**: on the source, `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:<port>/appairage` → `000` (nothing answers), also after a reboot.
