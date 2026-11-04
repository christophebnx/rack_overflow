"""Errors of the ops layer."""


class OpsError(Exception):
    """A host operation (supervise, update) was refused or failed."""


class SupervisorRunningError(OpsError):
    """Another process holds the supervisor lock of the data folder (`rack supervise` runs)."""
