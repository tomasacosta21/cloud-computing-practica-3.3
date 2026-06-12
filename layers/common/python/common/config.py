import os


def get_env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_int_env(name: str, default: int | None = None, *, required: bool = False) -> int | None:
    value = get_env(name, None, required=required)
    if value is None or value == "":
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be an integer") from exc


def get_float_env(
    name: str, default: float | None = None, *, required: bool = False
) -> float | None:
    value = get_env(name, None, required=required)
    if value is None or value == "":
        return default

    try:
        return float(value)
    except ValueError as exc:
        raise RuntimeError(f"Environment variable {name} must be a number") from exc


def table_name() -> str:
    return get_env("TABLE_NAME", required=True) or ""


def uploads_bucket_name() -> str:
    return get_env("UPLOADS_BUCKET_NAME", required=True) or ""
