"""
Utils package for MIMIC backend.
"""

import sys
from pathlib import Path

# Import API key manager from this package
from .api_key_manager import get_key_manager, get_api_key, rotate_api_key

# Import utility functions from parent utils.py file
# We need to import from the parent module
_parent_utils = Path(__file__).parent.parent / "utils.py"
if _parent_utils.exists():
    import importlib.util
    spec = importlib.util.spec_from_file_location("utils_module", _parent_utils)
    utils_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(utils_module)
    
    ensure_directory = utils_module.ensure_directory
    cleanup_session = utils_module.cleanup_session
    cleanup_all_temp = utils_module.cleanup_all_temp
    get_file_size_mb = utils_module.get_file_size_mb
    format_duration = utils_module.format_duration
    get_fast_hash = utils_module.get_fast_hash
    get_file_hash = utils_module.get_file_hash
    get_content_hash = utils_module.get_content_hash
    get_bytes_hash = utils_module.get_bytes_hash
    register_file_hash = utils_module.register_file_hash
    save_hash_registry = utils_module.save_hash_registry
else:
    # Fallback if utils.py doesn't exist
    def ensure_directory(path):
        Path(path).mkdir(parents=True, exist_ok=True)
        return Path(path)
    
    def cleanup_session(session_id: str, cleanup_uploads: bool = False):
        pass

    def get_fast_hash(path):
        return ""
        
    def get_file_hash(path):
        return ""
        
    def get_content_hash(content):
        return ""

    def get_bytes_hash(content):
        return ""

    def register_file_hash(path, value):
        return None
        
    def save_hash_registry():
        pass

__all__ = [
    'get_key_manager', 'get_api_key', 'rotate_api_key',
    'ensure_directory', 'cleanup_session', 'cleanup_all_temp',
    'get_file_size_mb', 'format_duration', 'get_fast_hash',
    'get_file_hash', 'get_content_hash', 'get_bytes_hash',
    'register_file_hash', 'save_hash_registry'
]
