"""Abstract base class for backup storage providers."""
from abc import ABC, abstractmethod


class StorageProvider(ABC):

    @abstractmethod
    def upload(self, local_path: str, remote_key: str) -> str:
        """Upload a local file and return the remote URL or key."""

    @abstractmethod
    def download(self, remote_key: str, local_path: str) -> None:
        """Download a remote file to local_path."""

    @abstractmethod
    def delete(self, remote_key: str) -> None:
        """Delete a remote file."""

    @abstractmethod
    def exists(self, remote_key: str) -> bool:
        """Return True if the remote file exists."""
