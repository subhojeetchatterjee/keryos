"""Centralised environment variable access with clear error messages for missing secrets."""
import os

_DESCRIPTIONS: dict[str, str] = {
    "SH_CLIENT_ID": "Sentinel Hub / Copernicus Data Space OAuth client ID",
    "SH_CLIENT_SECRET": "Sentinel Hub / Copernicus Data Space OAuth client secret (keep private)",
    "ANTHROPIC_VERTEX_PROJECT_ID": "GCP project ID (needed when Vertex AI LLM features are enabled)",
    "CLOUD_ML_REGION": "Vertex AI region (e.g. us-east5, defaults to us-east5)",
}


def get_env(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    """Return the env var value or raise EnvironmentError with a helpful message."""
    value = os.environ.get(key)
    if not value:
        desc = _DESCRIPTIONS.get(key, "no description available")
        raise EnvironmentError(
            f"Required environment variable {key!r} is not set. "
            f"Purpose: {desc}. "
            "Set it before starting the application."
        )
    return value


def check_sentinel_credentials() -> None:
    """Raise EnvironmentError if both Sentinel Hub credentials are absent."""
    missing = [k for k in ("SH_CLIENT_ID", "SH_CLIENT_SECRET") if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Missing Sentinel Hub credentials: {', '.join(missing)}. "
            "Set SH_CLIENT_ID and SH_CLIENT_SECRET as environment variables."
        )
