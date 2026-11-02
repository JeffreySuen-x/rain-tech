"""Explicit, CLI-only private local configuration. Never discovers other projects."""
import json
import os
from pathlib import Path
import stat

ALLOWED = frozenset('SHUYU_ENV SHUYU_DB SHUYU_PUBLIC_ORIGIN SHUYU_SECRET SHUYU_ASSET_ROOT SHUYU_PROVIDER_CAPABILITIES SHUYU_PROVIDER_THINKING SHUYU_PROVIDER_ASR_ADAPTER SHUYU_PROVIDER_VISION_MODEL SHUYU_PROVIDER_ASR_MODEL SHUYU_PROVIDER_URL SHUYU_PROVIDER_KEY SHUYU_PROVIDER_MODEL SHUYU_STATIC_DIR'.split())


def load_config(path, environ=None):
    """Validate before applying; explicit environment always wins. Errors contain no values."""
    if os.name != 'posix':
        raise ValueError('Private CLI configuration requires POSIX permission checks; use explicit environment variables on Windows')
    env = os.environ if environ is None else environ
    try:
        path = Path(path).absolute()
        if any(p.is_symlink() for p in (path, *path.parents)):
            raise ValueError()
        parent = path.parent.stat()
        if parent.st_uid != os.getuid() or stat.S_IMODE(parent.st_mode) != 0o700:
            raise ValueError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'r', encoding='utf-8') as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o600 or metadata.st_size > 65536:
                raise ValueError()
            def pairs(items):
                result = {}
                for key, value in items:
                    if key in result:
                        raise ValueError()
                    result[key] = value
                return result
            data = json.load(stream, object_pairs_hook=pairs)
        if not isinstance(data, dict) or set(data) - ALLOWED or any(not isinstance(v, str) or '\x00' in v for v in data.values()):
            raise ValueError()
    except (OSError, ValueError, UnicodeError):
        raise ValueError('Invalid or insecure local configuration') from None
    for key, value in data.items():
        env.setdefault(key, value)
