"""AWS Free-Tier Lambda package.

A zip-friendly Lambda path that:
  1. Reuses static_site_handler scraping (urllib-based, no pandas/numpy).
  2. Writes S3 with hash-dedupe to stay under Free Tier PUT limits.
  3. Optionally writes Google Sheets when WRITE_SHEETS=1.
  4. Optionally posts a Discord alert on failure.

Independent of the heavier orchestrator/pandas path used by the container image.
"""

__all__: list[str] = []
