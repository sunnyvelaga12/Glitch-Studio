"""
storage_service.py — Private Object Storage Service for VirtualHR

Abstracts document storage (S3 / MinIO / Local private storage adapter).
Supports:
  - Private bucket access only (no public ACLs)
  - Encryption at rest (AES256 SSE-S3)
  - Tenant-scoped object key paths: {company_id}/{document_id}/{filename}
  - Short-lived signed download URLs with configurable expiration (5–15 mins)
"""

import abc
import hashlib
import hmac
import logging
import os
import time
from pathlib import Path
from typing import Optional

from app.config import settings

logger = logging.getLogger(__name__)


class BaseStorageService(abc.ABC):
    @abc.abstractmethod
    async def save_file(self, company_id: str, document_id: str, filename: str, content: bytes) -> str:
        """Save file to storage and return storage_key."""
        pass

    @abc.abstractmethod
    async def get_signed_url(self, storage_key: str, expiration_seconds: int = 900) -> str:
        """Generate a short-lived signed download URL (5-15 min max expiration)."""
        pass

    async def get_presigned_url(self, storage_key: str, expires_in: int = 900) -> str:
        """Alias method for get_signed_url."""
        return await self.get_signed_url(storage_key, expiration_seconds=expires_in)

    @abc.abstractmethod
    async def verify_signed_url(self, storage_key: str, expires_at: int, signature: str) -> bool:
        """Verify authenticity and timestamp of a signed download URL."""
        pass


class LocalPrivateStorageService(BaseStorageService):
    """
    Local private object storage adapter for development and self-hosted testing environments.
    Stores files in a secure directory outside the public web root.
    """

    def __init__(self, base_dir: str = "./uploads"):
        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_object_path(self, storage_key: str) -> Path:
        return (self.base_dir / storage_key).resolve()

    async def save_file(self, company_id: str, document_id: str, filename: str, content: bytes) -> str:
        safe_filename = Path(filename).name.replace(" ", "_")
        storage_key = f"{company_id}/{document_id}/{safe_filename}"
        file_path = self._get_object_path(storage_key)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "wb") as f:
            f.write(content)

        logger.info(f"[LOCAL STORAGE] Saved file to private storage: {storage_key} ({len(content)} bytes)")
        return storage_key

    async def get_signed_url(self, storage_key: str, expiration_seconds: int = 900) -> str:
        exp_limit = min(expiration_seconds, settings.SIGNED_URL_EXPIRATION_SECONDS)
        expires_at = int(time.time()) + exp_limit
        
        sig_data = f"{storage_key}:{expires_at}"
        signature = hmac.new(
            settings.JWT_SECRET.encode("utf-8"),
            sig_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return f"/api/hr/documents/download?key={storage_key}&expires={expires_at}&sig={signature}"

    async def verify_signed_url(self, storage_key: str, expires_at: int, signature: str) -> bool:
        if time.time() > expires_at:
            logger.warning("Signed URL signature expired")
            return False

        sig_data = f"{storage_key}:{expires_at}"
        expected_sig = hmac.new(
            settings.JWT_SECRET.encode("utf-8"),
            sig_data.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature, expected_sig)


class S3PrivateStorageService(BaseStorageService):
    """
    Production Amazon S3 / MinIO / Cloudflare R2 / GCS private object storage adapter.
    Enforces private bucket access, server-side encryption (AES256), and pre-signed download URLs.
    """

    def __init__(self):
        try:
            import boto3
            session_kwargs = {}
            if settings.AWS_ACCESS_KEY_ID and settings.AWS_SECRET_ACCESS_KEY:
                session_kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
                session_kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY
                session_kwargs["region_name"] = settings.AWS_REGION

            client_kwargs = {}
            if settings.S3_ENDPOINT_URL:
                client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

            self.s3_client = boto3.client("s3", **session_kwargs, **client_kwargs)
            self.bucket_name = settings.STORAGE_BUCKET_NAME
            logger.info(f"[PROD S3 STORAGE] Initialized S3 client for bucket '{self.bucket_name}'")
        except Exception as e:
            logger.error(f"[PROD S3 STORAGE] Failed to initialize boto3 S3 client: {e}")
            self.s3_client = None
            self.bucket_name = settings.STORAGE_BUCKET_NAME

    async def save_file(self, company_id: str, document_id: str, filename: str, content: bytes) -> str:
        safe_filename = Path(filename).name.replace(" ", "_")
        storage_key = f"{company_id}/{document_id}/{safe_filename}"

        if not self.s3_client:
            logger.warning("boto3 client unavailable — falling back to local private storage save")
            fallback = LocalPrivateStorageService(base_dir=settings.STORAGE_LOCAL_DIR)
            return await fallback.save_file(company_id, document_id, filename, content)

        try:
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=content,
                ServerSideEncryption="AES256",  # Encrypted at rest
            )
            logger.info(f"[PROD S3 STORAGE] Successfully uploaded encrypted file to s3://{self.bucket_name}/{storage_key}")
            return storage_key
        except Exception as e:
            logger.error(f"[PROD S3 STORAGE] S3 upload error for {storage_key}: {e}")
            raise RuntimeError(f"S3 Object Storage Upload Failed: {str(e)}")

    async def get_signed_url(self, storage_key: str, expiration_seconds: int = 900) -> str:
        exp_limit = min(expiration_seconds, settings.SIGNED_URL_EXPIRATION_SECONDS)

        if not self.s3_client:
            fallback = LocalPrivateStorageService(base_dir=settings.STORAGE_LOCAL_DIR)
            return await fallback.get_signed_url(storage_key, exp_limit)

        try:
            url = self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": storage_key},
                ExpiresIn=exp_limit,
            )
            return url
        except Exception as e:
            logger.error(f"[PROD S3 STORAGE] Presigned URL generation failed for {storage_key}: {e}")
            raise RuntimeError(f"Failed to generate S3 pre-signed download URL: {str(e)}")

    async def verify_signed_url(self, storage_key: str, expires_at: int, signature: str) -> bool:
        fallback = LocalPrivateStorageService(base_dir=settings.STORAGE_LOCAL_DIR)
        return await fallback.verify_signed_url(storage_key, expires_at, signature)


def get_storage_service() -> BaseStorageService:
    if settings.STORAGE_PROVIDER == "s3" or settings.is_production:
        return S3PrivateStorageService()
    return LocalPrivateStorageService(base_dir=settings.STORAGE_LOCAL_DIR)
