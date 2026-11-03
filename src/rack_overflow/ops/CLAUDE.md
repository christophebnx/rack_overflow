# ops/ — rules

- Host process management: supervision of `rack serve` and self-update of a deployed clone (D-038, D-051). Neither a business operation (`services/`) nor HTTP (`web/`).
- Imports allowed: the standard library, `domain` and `storage` (`tests/unit/test_layering.py`). Never `web`, `services`, `cli` or `config`: paths, commands and settings values are passed in.
- POSIX only (`fcntl`, signals): the NAS and the Jelastic Linux node.
- Tests never run real git, uv or network, and never sleep for real delays: commands, the clock and the wait between restarts are injected; child processes are the fake server `tests/fixtures/fake_server.py`.
- State files (the PID file) go through `storage/files.atomic_write`. Append-only logs are not state files (D-051): they use the stdlib `RotatingFileHandler`.
- Errors derive from `errors.OpsError`; the CLI maps them to exit code 1.

## Modules

| Module | Owns |
|---|---|
| `errors.py` | `OpsError` |
| `logs.py` | `LOG_FORMAT`, `LOG_DATE_FORMAT`, `utc_formatter()`: the one log line format of the server (`cli.configure_logging`) and the supervisor |
| `supervise.py` | `Supervisor(command, log_path, policy, *, monotonic, wait, max_bytes, backup_count, kill_after_s).run(stop)`: child with output copied line by line to `<data_dir>/logs/rack.log` (1 MiB × 5), restart delay from `domain/supervision`, stop = SIGTERM then SIGKILL after 10 s; `log_path(data_dir)`, `acquire_lock(data_dir)` (`flock` on `supervise.lock`), `write_pid` / `remove_pid` (`supervise.pid`), `running_supervisor_pid(data_dir)` |
| `update.py` | `update(repo, config_path, data_dir, tools)`: preconditions (clone on `main`, `git status --porcelain` empty, `uv` found), `git pull --ff-only` (HEAD unchanged → `already up to date`), `uv sync --frozen`, `rack migrate` in a new process, SIGHUP to `running_supervisor_pid`; a failing step echoes its output and raises `OpsError` (no restart). `UpdateTools` (injected runner, supervisor lookup, signal sender, output, python, uv), `run_command` (the real runner) |
