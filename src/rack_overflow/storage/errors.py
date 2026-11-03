"""Errors of the storage layer."""


class StorageError(Exception):
    """A persistence operation failed. Base of every storage error."""


class MigrationError(StorageError):
    """A schema migration could not be applied; the database was left as it was."""


class BackupError(StorageError):
    """A database snapshot could not be taken."""


class CorruptDatabaseError(BackupError):
    """The database failed the integrity check: it is neither backed up nor touched."""


class DeviceNameTakenError(StorageError):
    """An active device already has this name (unique index on active names)."""
