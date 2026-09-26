from __future__ import annotations

import asyncio
import io
import json
import time
import uuid
from pathlib import PurePosixPath

import urllib3
from minio import Minio
from minio.error import S3Error

from app.config import settings


import logging

logger = logging.getLogger(__name__)

# Avatar files are public-readable. Documents are private and proxied through
# FastAPI; avatars are loaded directly by <img src> from the bucket, so the
# avatar bucket needs an anonymous GetObject policy on the prefix.
def _public_read_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


# Extensions accepted by both the upload route and the multi-extension cleanup
# step. Keep in sync with ALLOWED_AVATAR_EXT in app/api/users.py.
_AVATAR_EXTS = ("jpg", "png", "webp")


class StorageService:
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        avatar_bucket: str,
        secure: bool,
    ) -> None:
        self._http_client = urllib3.PoolManager(
            timeout=urllib3.util.Timeout(connect=1.5, read=3.0),
            retries=urllib3.util.Retry(total=1, connect=1, read=1),
        )
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            http_client=self._http_client,
        )
        self._bucket = bucket
        self._avatar_bucket = avatar_bucket

    async def ensure_bucket(self) -> None:
        def _ensure() -> None:
            try:
                if not self._client.bucket_exists(self._bucket):
                    self._client.make_bucket(self._bucket)
            except Exception as e:
                logger.warning(
                    "MinIO storage unreachable for bucket %s: %s (MinIO is optional for non-document flows)",
                    self._bucket,
                    e,
                )

        await asyncio.to_thread(_ensure)

    async def ensure_avatar_bucket(self) -> None:
        def _ensure() -> None:
            try:
                if not self._client.bucket_exists(self._avatar_bucket):
                    self._client.make_bucket(self._avatar_bucket)
                # Idempotent: re-setting the same policy is a no-op.
                self._client.set_bucket_policy(
                    self._avatar_bucket, _public_read_policy(self._avatar_bucket)
                )
            except Exception as e:
                logger.warning(
                    "MinIO storage unreachable for avatar bucket %s: %s",
                    self._avatar_bucket,
                    e,
                )

        await asyncio.to_thread(_ensure)

    async def upload_file(
        self, file_data: bytes, filename: str, user_id: uuid.UUID
    ) -> str:
        sanitized = PurePosixPath(filename).name or "file"
        object_key = f"{user_id}/{uuid.uuid4().hex}_{sanitized}"

        def _put() -> None:
            self._client.put_object(
                self._bucket,
                object_key,
                io.BytesIO(file_data),
                length=len(file_data),
            )

        await asyncio.to_thread(_put)
        return object_key

    async def download_file(self, file_path: str) -> bytes:
        def _get() -> bytes:
            response = self._client.get_object(self._bucket, file_path)
            try:
                return response.read()
            finally:
                response.close()
                response.release_conn()

        return await asyncio.to_thread(_get)

    async def delete_file(self, file_path: str) -> bool:
        def _delete() -> bool:
            try:
                self._client.remove_object(self._bucket, file_path)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_delete)

    async def upload_avatar(
        self,
        file_data: bytes,
        user_id: uuid.UUID,
        ext: str,
        content_type: str,
    ) -> tuple[str, int]:
        object_key = f"{user_id}.{ext}"
        mtime = int(time.time())

        def _put() -> None:
            self._client.put_object(
                self._avatar_bucket,
                object_key,
                io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type,
            )

        await asyncio.to_thread(_put)
        return object_key, mtime

    async def delete_avatar(self, user_id: uuid.UUID) -> None:
        def _delete() -> None:
            for ext in _AVATAR_EXTS:
                try:
                    self._client.remove_object(
                        self._avatar_bucket, f"{user_id}.{ext}"
                    )
                except S3Error:
                    # NoSuchKey on the extensions the user doesn't have — fine.
                    pass

        await asyncio.to_thread(_delete)


_storage_singleton: StorageService | None = None


def get_storage() -> StorageService:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = StorageService(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            bucket=settings.MINIO_BUCKET,
            avatar_bucket=settings.MINIO_AVATAR_BUCKET,
            secure=settings.MINIO_SECURE,
        )
    return _storage_singleton
