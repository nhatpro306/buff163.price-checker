"""S3 writer with hash-dedupe for the free-tier scraper.

Cost control: PUT only when the object body actually changed. We compare a
SHA-256 hash of the new payload against the previous object's `x-amz-meta-sha`
metadata. Identical payloads skip the PUT entirely. This keeps S3 PUTs well
under the 2,000/month Free Tier limit even at a 30-minute schedule.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

LOG = logging.getLogger(__name__)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _existing_sha(client: Any, bucket: str, key: str) -> str | None:
    try:
        head = client.head_object(Bucket=bucket, Key=key)
    except Exception:
        return None
    meta = head.get("Metadata") or {}
    return meta.get("sha")


def put_json(
    client: Any,
    bucket: str,
    key: str,
    payload: Any,
    *,
    cache_control: str = "public, max-age=300",
    dedupe: bool = True,
) -> dict[str, Any]:
    """Write JSON to S3. Returns {written: bool, sha: str, key: str}.

    When dedupe is True, skips PUT if the previous object has the same SHA.
    """
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    sha = _sha256_bytes(body)
    if dedupe and _existing_sha(client, bucket, key) == sha:
        LOG.info("s3_skip_unchanged bucket=%s key=%s sha=%s", bucket, key, sha[:8])
        return {"written": False, "sha": sha, "key": key}

    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json; charset=utf-8",
        CacheControl=cache_control,
        Metadata={"sha": sha},
    )
    LOG.info("s3_put bucket=%s key=%s bytes=%d sha=%s", bucket, key, len(body), sha[:8])
    return {"written": True, "sha": sha, "key": key}


def put_text(
    client: Any,
    bucket: str,
    key: str,
    body: str,
    *,
    content_type: str,
    cache_control: str = "public, max-age=300",
    dedupe: bool = True,
) -> dict[str, Any]:
    """Write text (HTML/CSS/JS) to S3 with the same dedupe logic."""
    data = body.encode("utf-8")
    sha = _sha256_bytes(data)
    if dedupe and _existing_sha(client, bucket, key) == sha:
        LOG.info("s3_skip_unchanged bucket=%s key=%s sha=%s", bucket, key, sha[:8])
        return {"written": False, "sha": sha, "key": key}
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        CacheControl=cache_control,
        Metadata={"sha": sha},
    )
    LOG.info("s3_put bucket=%s key=%s bytes=%d sha=%s", bucket, key, len(data), sha[:8])
    return {"written": True, "sha": sha, "key": key}
