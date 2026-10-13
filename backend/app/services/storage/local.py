"""Local filesystem storage provider — copies backup files to an archive directory."""
import os
import shutil

from app.services.storage.base import StorageProvider


class LocalStorage(StorageProvider):

    def __init__(self, archive_dir: str):
        os.makedirs(archive_dir, exist_ok=True)
        self._dir = archive_dir

    def _full(self, key: str) -> str:
        return os.path.join(self._dir, os.path.basename(key))

    def upload(self, local_path: str, remote_key: str) -> str:
        dest = self._full(remote_key)
        shutil.copy2(local_path, dest)
        return dest

    def download(self, remote_key: str, local_path: str) -> None:
        shutil.copy2(self._full(remote_key), local_path)

    def delete(self, remote_key: str) -> None:
        path = self._full(remote_key)
        if os.path.exists(path):
            os.remove(path)

    def exists(self, remote_key: str) -> bool:
        return os.path.exists(self._full(remote_key))
