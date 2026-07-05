"""
Amazon S3 normaliser — lists objects in a bucket prefix and processes each
file through the same format-aware pipeline as the file upload normaliser.

Supported object types: .txt .md .pdf .docx .csv .json
Other types are skipped with a warning.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from .base   import BaseNormaliser
from .models import NormalisedChunk

logger = logging.getLogger(__name__)

_SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".csv", ".json"}


class S3Normaliser(BaseNormaliser):
    SOURCE = "s3"

    def __init__(
        self,
        *,
        bucket:     str,
        prefix:     str = "",
        region:     str = "us-east-1",
        access_key: str | None = None,
        secret_key: str | None = None,
    ) -> None:
        import boto3

        kwargs: dict[str, Any] = {"region_name": region}
        if access_key and secret_key:
            kwargs["aws_access_key_id"]     = access_key
            kwargs["aws_secret_access_key"] = secret_key

        self._s3     = boto3.client("s3", **kwargs)
        self._bucket = bucket
        self._prefix = prefix

    def health_check(self) -> bool:
        try:
            self._s3.head_bucket(Bucket=self._bucket)
            return True
        except Exception:
            return False

    def normalise(self, *, query=None, tables=None, collections=None) -> list[NormalisedChunk]:
        from .file import FileNormaliser

        keys = self._list_objects()
        logger.info("s3: found %d objects under s3://%s/%s", len(keys), self._bucket, self._prefix)

        chunks: list[NormalisedChunk] = []
        for key in keys:
            suffix = Path(key).suffix.lower()
            if suffix not in _SUPPORTED:
                logger.debug("s3: skipping unsupported type %s (%s)", suffix, key)
                continue
            try:
                chunks.extend(self._process_object(key, suffix))
            except Exception as e:
                logger.warning("s3: failed to process %s: %s", key, e)

        logger.info("s3: produced %d chunks", len(chunks))
        return chunks

    def _list_objects(self) -> list[str]:
        paginator = self._s3.get_paginator("list_objects_v2")
        keys: list[str] = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        return keys

    def _process_object(self, key: str, suffix: str) -> list[NormalisedChunk]:
        from .file import FileNormaliser

        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as fh:
            self._s3.download_fileobj(self._bucket, key, fh)
            tmp = fh.name

        try:
            fn = FileNormaliser(file_paths=[tmp])
            raw = fn.normalise()
            # Rewrite source/database/collection to reflect S3 origin
            for c in raw:
                c.source     = self.SOURCE
                c.database   = self._bucket
                c.collection = key
            return raw
        finally:
            Path(tmp).unlink(missing_ok=True)
