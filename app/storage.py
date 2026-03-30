from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import boto3

from app.config import Settings


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        ...

    def get_bytes(self, key: str) -> bytes:
        ...

    def delete_object(self, key: str) -> None:
        ...


@dataclass
class MemoryObjectStorage:
    objects: dict[str, bytes] = field(default_factory=dict)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.objects[key]

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        client_kwargs = {
            "service_name": "s3",
            "region_name": settings.s3_region,
        }
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        if settings.s3_access_key_id:
            client_kwargs["aws_access_key_id"] = settings.s3_access_key_id
        if settings.s3_secret_access_key:
            client_kwargs["aws_secret_access_key"] = settings.s3_secret_access_key

        self.client = boto3.client(**client_kwargs)

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get_bytes(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    def delete_object(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def build_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "s3":
        return S3ObjectStorage(settings)
    return MemoryObjectStorage()
