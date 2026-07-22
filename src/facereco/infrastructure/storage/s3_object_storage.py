"""Implémentation S3/MinIO du port ObjectStoragePort.

La base ne stocke jamais que des références (`storage_uri`) — les images
sources restent dans le stockage objet, jamais en base (§5, P2/P6).
"""

from __future__ import annotations

from urllib.parse import urlparse

import boto3

from facereco.domain.ports.object_storage import ObjectStoragePort


def _parse_s3_uri(storage_uri: str) -> tuple[str, str]:
    parsed = urlparse(storage_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"URI de stockage invalide, attendu s3://bucket/key : {storage_uri}")
    return parsed.netloc, parsed.path.lstrip("/")


class S3ObjectStorage(ObjectStoragePort):
    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "us-east-1",
    ) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def get_image_bytes(self, storage_uri: str) -> bytes:
        bucket, key = _parse_s3_uri(storage_uri)
        response = self._client.get_object(Bucket=bucket, Key=key)
        return bytes(response["Body"].read())

    def build_signed_url(self, storage_uri: str, expires_in_seconds: int = 300) -> str:
        bucket, key = _parse_s3_uri(storage_uri)
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in_seconds,
            )
        )
