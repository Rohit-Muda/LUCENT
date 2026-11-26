import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol
from uuid import uuid4


class StorageError(RuntimeError):
    pass


class UploadSizeLimitExceeded(StorageError):
    pass


class AudioStorage(Protocol):
    def store(self, source: BinaryIO, extension: str, max_bytes: int) -> str: ...

    def delete(self, storage_key: str) -> None: ...

    def path_for(self, storage_key: str) -> Path: ...


class LocalAudioStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def store(self, source: BinaryIO, extension: str, max_bytes: int) -> str:
        if extension not in {".mp3", ".wav"}:
            raise ValueError("Unsupported storage extension.")

        temporary_path: Path | None = None
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".upload-",
                suffix=".tmp",
                dir=self.root,
                delete=False,
            ) as destination:
                temporary_path = Path(destination.name)
                total_bytes = 0
                while chunk := source.read(1024 * 1024):
                    total_bytes += len(chunk)
                    if total_bytes > max_bytes:
                        raise UploadSizeLimitExceeded("Audio exceeds the configured size limit.")
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())

            storage_key = f"{uuid4().hex}{extension}"
            os.replace(temporary_path, self.path_for(storage_key))
            return storage_key
        except UploadSizeLimitExceeded:
            self._remove_temporary_file(temporary_path)
            raise
        except OSError as exc:
            self._remove_temporary_file(temporary_path)
            raise StorageError("Audio could not be stored.") from exc

    def delete(self, storage_key: str) -> None:
        path = self.path_for(storage_key)
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Stored audio could not be removed.") from exc

    def path_for(self, storage_key: str) -> Path:
        relative_path = PurePosixPath(storage_key)
        if (
            relative_path.is_absolute()
            or len(relative_path.parts) != 1
            or relative_path.name in {"", ".", ".."}
            or "\\" in storage_key
        ):
            raise StorageError("Invalid audio storage key.")

        candidate = (self.root / relative_path.name).resolve()
        if candidate.parent != self.root:
            raise StorageError("Invalid audio storage key.")
        return candidate

    def _remove_temporary_file(self, path: Path | None) -> None:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise StorageError("Temporary audio could not be removed.") from exc
