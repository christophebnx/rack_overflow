"""The users of V1 (D-017): one user. Read when creating a device and by `rack migrate` for the
catalog seed (D-057); once paired, the user id comes from the device row, so V2 multi-user
changes these two places only."""

SINGLE_USER_ID = 1
