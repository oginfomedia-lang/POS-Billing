"""SFTP storage provider — uploads backups to your own VPS over SSH."""
import os

from app.services.storage.base import StorageProvider


class SFTPStorage(StorageProvider):

    def __init__(self, host: str, port: int, username: str, remote_dir: str,
                 password: str = "", key_path: str = ""):
        self._host = host
        self._port = port
        self._username = username
        self._remote_dir = remote_dir.rstrip("/") + "/"
        self._password = password or None
        self._key_path = key_path or None

    def _connect(self):
        try:
            import paramiko
        except ImportError as exc:
            raise RuntimeError("paramiko is not installed. Run: pip install paramiko") from exc

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        kwargs: dict = dict(hostname=self._host, port=self._port,
                            username=self._username, timeout=30)
        if self._key_path:
            kwargs["key_filename"] = self._key_path
        elif self._password:
            kwargs["password"] = self._password
        client.connect(**kwargs)
        return client

    def _ensure_remote_dir(self, sftp) -> None:
        parts = self._remote_dir.rstrip("/").split("/")
        path = ""
        for part in parts:
            if not part:
                path = "/"
                continue
            path = path.rstrip("/") + "/" + part
            try:
                sftp.stat(path)
            except FileNotFoundError:
                sftp.mkdir(path)

    def upload(self, local_path: str, remote_key: str) -> str:
        filename = os.path.basename(local_path)
        remote_path = self._remote_dir + filename
        client = self._connect()
        try:
            sftp = client.open_sftp()
            self._ensure_remote_dir(sftp)
            sftp.put(local_path, remote_path)
            sftp.close()
        finally:
            client.close()
        return f"sftp://{self._host}{remote_path}"

    def download(self, remote_key: str, local_path: str) -> None:
        remote_path = self._remote_dir + os.path.basename(remote_key)
        client = self._connect()
        try:
            sftp = client.open_sftp()
            sftp.get(remote_path, local_path)
            sftp.close()
        finally:
            client.close()

    def delete(self, remote_key: str) -> None:
        remote_path = self._remote_dir + os.path.basename(remote_key)
        client = self._connect()
        try:
            sftp = client.open_sftp()
            sftp.remove(remote_path)
            sftp.close()
        finally:
            client.close()

    def exists(self, remote_key: str) -> bool:
        remote_path = self._remote_dir + os.path.basename(remote_key)
        client = self._connect()
        try:
            sftp = client.open_sftp()
            try:
                sftp.stat(remote_path)
                return True
            except FileNotFoundError:
                return False
            finally:
                sftp.close()
        finally:
            client.close()
