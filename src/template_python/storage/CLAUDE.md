# storage/ — rules

- Everything that touches the disk lives here (or in a later outer layer). Business rules stay in `domain/`.
- Every write of a user or state file goes through `files.atomic_write`. Never `Path.write_text` / `open(..., "w")` on such a file.
- No partial state on failure: write the new file completely, then switch to it.
- Tests use `tmp_path` only.

## Modules

| Module | Owns |
|---|---|
| `files.py` | `atomic_write(path, data)`: temp file in the same folder, fsync, `os.replace`, folder fsync (POSIX) |
