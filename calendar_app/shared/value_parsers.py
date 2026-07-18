"""Small, side-effect-free value parsing helpers."""


def as_bool(value, default=False):
    """Convert loose config values to bool with a sensible default."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y", "on"}
