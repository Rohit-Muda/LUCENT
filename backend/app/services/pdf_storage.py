import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Protocol
from uuid import uuid4

from backend.app.services.audio_storage import StorageError


class PdfStorage(Protocol):
    def store_bytes(self, content: bytes) -> str: ...

    def delete(self, storage_key: str) -> None: ...

    def path_for(self, storage_key: str) -> Path: ...


class LocalPdfStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def store_bytes(self, content: bytes) -> str:
        if not content:
            raise StorageError("Generated PDF content cannot be empty.")

        temporary_path: Path | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".pdf-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                destination.write(content)
                destination.flush()
                os.fsync(destination.fileno())

            storage_key = f"{uuid4().hex}.pdf"
            os.replace(temporary_path, self.path_for(storage_key))
            return storage_key
        except OSError as exc:
            self._remove_temporary_file(temporary_path)
            raise StorageError("Generated PDF could not be stored.") from exc

    def delete(self, storage_key: str) -> None:
        path = self.path_for(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Stored PDF could not be removed.") from exc

    def path_for(self, storage_key: str) -> Path:
        relative_path = PurePosixPath(storage_key)
        if (
            relative_path.is_absolute()
            or len(relative_path.parts) != 1
            or relative_path.name in {"", ".", ".."}
            or "\\" in storage_key
            or not relative_path.name.endswith(".pdf")
        ):
            raise StorageError("Invalid PDF storage key.")

        candidate = (self.root / relative_path.name).resolve()
        if candidate.parent != self.root:
            raise StorageError("Invalid PDF storage key.")
        return candidate

    def _remove_temporary_file(self, path: Path | None) -> None:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise StorageError("Temporary PDF could not be removed.") from exc
