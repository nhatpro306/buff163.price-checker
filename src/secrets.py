"""Config/secret resolution for local dev and AWS Lambda.

Resolution order for any name (e.g. ``DATABASE_URL``):
1. Direct env var ``DATABASE_URL`` (local dev, GitHub Actions secrets).
2. ``DATABASE_URL_SECRET_ARN`` env → fetch from AWS Secrets Manager (Lambda).
3. ``default``.

Values are never logged. The fetched value is also written back into
``os.environ`` so existing code that reads ``os.getenv(name)`` (e.g. the
Postgres store) keeps working unchanged.
"""

from __future__ import annotations

import os


def _fetch_from_secrets_manager(secret_arn: str) -> str:
    # boto3 is provided by the AWS Lambda Python runtime; imported lazily so it
    # is not required for local dev or tests.
    import boto3  # noqa: PLC0415

    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_arn)
    secret = response.get("SecretString")
    if not secret:
        raise RuntimeError("Secret has no SecretString value.")
    return str(secret)


def get_secret(name: str, *, default: str | None = None) -> str | None:
    """Resolve a secret/config value (env → Secrets Manager ARN → default)."""
    direct = os.getenv(name)
    if direct:
        return direct

    arn = os.getenv(f"{name}_SECRET_ARN")
    if arn:
        value = _fetch_from_secrets_manager(arn)
        # Hydrate env so downstream os.getenv(name) callers see it.
        os.environ.setdefault(name, value)
        return value

    return default


def require_secret(name: str) -> str:
    value = get_secret(name)
    if not value:
        raise RuntimeError(
            f"Missing required secret/config: {name} "
            f"(set the {name} env var or {name}_SECRET_ARN)."
        )
    return value


def hydrate_secrets(names: tuple[str, ...]) -> list[str]:
    """Resolve each name (populating os.environ from Secrets Manager if needed).

    Returns the list of names that were successfully resolved. Never logs values.
    """
    resolved: list[str] = []
    for name in names:
        if get_secret(name) is not None:
            resolved.append(name)
    return resolved


__all__ = ["get_secret", "require_secret", "hydrate_secrets"]
