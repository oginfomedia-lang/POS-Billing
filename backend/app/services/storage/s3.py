"""AWS S3 storage provider. boto3 is imported lazily so it stays optional."""
import os

from app.services.storage.base import StorageProvider


class S3Storage(StorageProvider):

    def __init__(self, bucket: str, prefix: str = "", region: str = "ap-south-1"):
        self._bucket = bucket
        self._prefix = prefix.rstrip("/") + "/" if prefix else ""
        self._region = region
        self._client = None

    def _boto(self):
        if self._client is None:
            try:
                import boto3  # lazy import — boto3 not required if S3 unused
            except ImportError as exc:
                raise RuntimeError("boto3 is not installed. Run: pip install boto3") from exc
            self._client = boto3.client(
                "s3",
                region_name=self._region,
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            )
        return self._client

    def _key(self, remote_key: str) -> str:
        return self._prefix + os.path.basename(remote_key)

    def upload(self, local_path: str, remote_key: str) -> str:
        key = self._key(remote_key)
        self._boto().upload_file(local_path, self._bucket, key)
        return f"s3://{self._bucket}/{key}"

    def download(self, remote_key: str, local_path: str) -> None:
        self._boto().download_file(self._bucket, self._key(remote_key), local_path)

    def delete(self, remote_key: str) -> None:
        self._boto().delete_object(Bucket=self._bucket, Key=self._key(remote_key))

    def exists(self, remote_key: str) -> bool:
        try:
            self._boto().head_object(Bucket=self._bucket, Key=self._key(remote_key))
            return True
        except Exception:
            return False
