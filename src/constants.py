"""Constants used throughout the Bees ticket system."""

SCHEMA_VERSION = "0.1"

# Lowercase-only charset (34 chars)
# Excluded for visual ambiguity: 0 (zero), O, I, l
# Excluded entirely: all uppercase letters
# Allowed: 1-9, a-k, m-z
ID_CHARSET = "123456789abcdefghijkmnopqrstuvwxyz"

GUID_LENGTH = 32
