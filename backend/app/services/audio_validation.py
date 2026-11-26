import math
from pathlib import Path

from mutagen import File as MutagenFile
from mutagen import MutagenError
from mutagen.mp3 import MP3
from mutagen.wave import WAVE

from backend.app.errors import ApiError

_GENERIC_MIME_TYPES = {"", "application/octet-stream", "binary/octet-stream"}
_MIME_TYPES_BY_EXTENSION = {
    ".mp3": {"audio/mpeg", "audio/mp3", "audio/x-mp3", "audio/mpeg3", "audio/x-mpeg-3"},
    ".wav": {"audio/wav", "audio/x-wav", "audio/wave", "audio/vnd.wave"},
}


class ValidatedAudio:
    def __init__(self, extension: str, size_bytes: int, duration_seconds: float) -> None:
        self.extension = extension
        self.size_bytes = size_bytes
        self.duration_seconds = duration_seconds


def sanitize_original_filename(filename: str | None) -> str:
    if not filename:
        raise ApiError(422, "invalid_filename", "An audio filename is required.")

    basename = filename.replace("\\", "/").split("/")[-1]
    sanitized = "".join(character for character in basename if character.isprintable()).strip()
    if sanitized in {"", ".", ".."}:
        raise ApiError(422, "invalid_filename", "An audio filename is required.")
    return sanitized[:255]


def validate_audio_file(
    path: Path,
    filename: str,
    content_type: str | None,
    max_size_bytes: int,
    max_duration_seconds: int,
) -> ValidatedAudio:
    extension = Path(filename).suffix.lower()
    if extension not in _MIME_TYPES_BY_EXTENSION:
        raise ApiError(415, "unsupported_audio_format", "Only MP3 and WAV audio files are supported.")

    declared_type = (content_type or "").split(";", maxsplit=1)[0].strip().lower()
    if declared_type not in _GENERIC_MIME_TYPES | _MIME_TYPES_BY_EXTENSION[extension]:
        raise ApiError(415, "audio_content_type_mismatch", "The declared media type does not match the file extension.")

    try:
        size_bytes = path.stat().st_size
    except OSError as exc:
        raise ApiError(422, "invalid_audio", "The uploaded audio could not be read.") from exc

    if size_bytes == 0:
        raise ApiError(422, "empty_audio", "The uploaded audio file is empty.")
    if size_bytes > max_size_bytes:
        raise ApiError(413, "audio_too_large", "The uploaded audio exceeds the configured size limit.")

    try:
        audio = MutagenFile(path, easy=False)
    except (MutagenError, OSError, EOFError, ValueError) as exc:
        raise ApiError(422, "invalid_audio", "The uploaded file is not readable audio.") from exc

    expected_type = MP3 if extension == ".mp3" else WAVE
    if not isinstance(audio, expected_type) or audio.info is None:
        raise ApiError(422, "audio_content_mismatch", "The file content does not match its audio extension.")

    duration_seconds = float(audio.info.length)
    if not math.isfinite(duration_seconds) or duration_seconds <= 0:
        raise ApiError(422, "invalid_audio_duration", "The audio duration could not be determined.")
    if duration_seconds > max_duration_seconds:
        raise ApiError(413, "audio_too_long", "The audio exceeds the configured duration limit.")

    return ValidatedAudio(extension, size_bytes, duration_seconds)
