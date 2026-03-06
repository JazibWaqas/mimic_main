"""
Utility functions for MIMIC project.
"""

import shutil
from pathlib import Path
from typing import List


def ensure_directory(path: str | Path) -> Path:
    """
    Create directory if it doesn't exist.
    
    Returns:
        Path object for chaining
    """
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_session(session_id: str, cleanup_uploads: bool = False) -> None:
    """
    Clean up temporary processing files for a session.
    
    NOTE: This only cleans temp/ (intermediate processing files).
    Uploaded files in data/uploads/ are kept by default (permanent).
    
    Args:
        session_id: Session ID to clean
        cleanup_uploads: If True, also delete uploaded files from data/uploads/
    """
    BASE_DIR = Path(__file__).resolve().parent.parent
    
    # Clean temp/ (intermediate processing files)
    temp_session_dir = BASE_DIR / "temp" / session_id
    if temp_session_dir.exists():
        shutil.rmtree(temp_session_dir, ignore_errors=True)
        print(f"[CLEANUP] Deleted temp files: {temp_session_dir}")
    
    # Optionally clean uploads/ (permanent files)
    if cleanup_uploads:
        uploads_session_dir = BASE_DIR / "data" / "uploads" / session_id
        if uploads_session_dir.exists():
            shutil.rmtree(uploads_session_dir, ignore_errors=True)
            print(f"[CLEANUP] Deleted uploaded files: {uploads_session_dir}")


def cleanup_all_temp() -> None:
    """Delete all temporary files."""
    temp_dir = Path("temp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)


def get_file_size_mb(path: str | Path) -> float:
    """Get file size in megabytes."""
    return Path(path).stat().st_size / (1024 * 1024)


def format_duration(seconds: float) -> str:
    """Format duration as MM:SS."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def get_fast_hash(path: str | Path) -> str:
    """
    Get a fast content-based hash of a file.
    Reads only the first and last 64KB to ensure speed while maintaining uniqueness.
    """
    import hashlib
    p = Path(path)
    if not p.exists():
        return ""
    
    file_size = p.stat().st_size
    hasher = hashlib.md5()
    
    try:
        with open(p, "rb") as f:
            if file_size < 128 * 1024:
                hasher.update(f.read())
            else:
                # Read first 64KB
                hasher.update(f.read(64 * 1024))
                # Seek to near the end and read another 64KB
                f.seek(max(0, file_size - 64 * 1024))
                hasher.update(f.read(64 * 1024))
        
        # v12.8 Hardening: Include size in the hash for collision resistance
        hasher.update(str(file_size).encode())
        return hasher.hexdigest()
    except Exception:
        # Fallback to filename hash if reading fails
        return hashlib.md5(p.name.encode()).hexdigest()


# ============================================================================
# PERSISTENT HASH REGISTRY (V12.5 Hardened)
# ============================================================================

import json
import hashlib
import time

import threading

_ROOT_DIR = Path(__file__).resolve().parent.parent
_HASH_REGISTRY_PATH = _ROOT_DIR / "data" / "cache" / "hash_registry.json"
_hash_cache = {}
_registry_loaded = False
_registry_lock = threading.Lock()

def _ensure_registry_loaded():
    global _hash_cache, _registry_loaded
    if _registry_loaded: return
    
    with _registry_lock:
        if _registry_loaded: return # Double check
        _HASH_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if _HASH_REGISTRY_PATH.exists():
            try:
                with open(_HASH_REGISTRY_PATH, "r", encoding="utf-8") as f:
                    _hash_cache = json.load(f)
            except:
                _hash_cache = {}
        _registry_loaded = True

def save_hash_registry():
    """Manually persist the hash registry to disk."""
    if not _registry_loaded: return
    with _registry_lock:
        try:
            with open(_HASH_REGISTRY_PATH, "w", encoding="utf-8") as f:
                json.dump(_hash_cache, f)
        except: pass

def get_file_hash(path: str | Path) -> str:
    """
    Get a hash of a file with persistent caching.
    Uses (name, size, mtime) as a fingerprint to avoid re-reading the file.
    """
    _ensure_registry_loaded()
    p = Path(path)
    if not p.exists(): return ""
    
    try:
        stat = p.stat()
        mtime = stat.st_mtime
        size = stat.st_size
        
        key_int = f"{int(mtime)}_{size}"
        
        with _registry_lock:
            if key_int in _hash_cache:
                return _hash_cache[key_int]
        
        # Cache miss: do the work (outside lock to avoid blocking other lookups)
        h = get_fast_hash(p)
        if h:
            with _registry_lock:
                _hash_cache[key_int] = h
            # Save immediately to ensure persistence if called outside refresh loop
            save_hash_registry()
        return h
    except:
        return ""

def get_bytes_hash(content: bytes) -> str:
    import hashlib
    file_size = len(content)
    hasher = hashlib.md5()
    if file_size < 128 * 1024:
        hasher.update(content)
    else:
        hasher.update(content[:64 * 1024])
        hasher.update(content[-64 * 1024:])
    
    # v12.8 Hardening: Include size in the hash for collision resistance
    hasher.update(str(file_size).encode())
    return hasher.hexdigest()


def register_file_hash(path: str | Path, value: str) -> None:
    _ensure_registry_loaded()
    p = Path(path)
    if not p.exists():
        return
    try:
        stat = p.stat()
        key_int = f"{int(stat.st_mtime)}_{stat.st_size}"
        _hash_cache[key_int] = value
    except:
        return


def get_content_hash(content: bytes) -> str:
    return get_bytes_hash(content)


