"""Async S3/MinIO object storage client wrapper using aioboto3."""

import aioboto3
import structlog

from src.core.config import get_settings

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class StorageClient:
    """Async S3-compatible storage client for PDF proposals and field installation photos."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._session = aioboto3.Session()

    async def upload_bytes(
        self,
        *,
        object_key: str,
        data: bytes,
        content_type: str,
    ) -> str:
        """Upload raw bytes to the configured MinIO/S3 bucket and return the storage key."""
        async with self._session.client(
            "s3",
            endpoint_url=self._settings.s3_endpoint_url,
            aws_access_key_id=self._settings.minio_root_user,
            aws_secret_access_key=self._settings.minio_root_password,
            region_name=self._settings.s3_region,
        ) as s3_client:
            await s3_client.put_object(
                Bucket=self._settings.minio_bucket_name,
                Key=object_key,
                Body=data,
                ContentType=content_type,
            )
        logger.info(
            "storage_object_uploaded",
            bucket=self._settings.minio_bucket_name,
            object_key=object_key,
            size_bytes=len(data),
        )
        return object_key

    async def generate_presigned_download_url(
        self,
        *,
        object_key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        """Generate a presigned GET URL using the public S3 endpoint."""
        async with self._session.client(
            "s3",
            endpoint_url=self._settings.s3_public_endpoint_url,
            aws_access_key_id=self._settings.minio_root_user,
            aws_secret_access_key=self._settings.minio_root_password,
            region_name=self._settings.s3_region,
        ) as s3_client:
            url: str = await s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": self._settings.minio_bucket_name,
                    "Key": object_key,
                },
                ExpiresIn=expires_in_seconds,
            )
            return url


def get_storage_client() -> StorageClient:
    """FastAPI dependency provider for StorageClient."""
    return StorageClient()
