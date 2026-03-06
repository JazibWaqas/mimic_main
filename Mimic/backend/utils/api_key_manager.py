"""
API Key Manager: Automatic rotation when rate limits are hit.

Loads all API keys from .env (active and commented) and automatically
switches to the next key when a 429/quota error is detected.
"""

import os
import re
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv


class APIKeyManager:
    """Manages multiple Gemini API keys with automatic rotation on rate limits."""
    
    def __init__(self, env_path: Optional[Path] = None):
        """
        Initialize API key manager.
        
        Args:
            env_path: Path to .env file. If None, uses backend/.env
        """
        if env_path is None:
            env_path = Path(__file__).parent.parent / ".env"
        
        self.env_path = env_path
        self.keys: List[str] = []
        self.current_index = 0
        self.exhausted_keys: set[str] = set()
        
        self._load_all_keys()
    
    def _load_all_keys(self) -> None:
        """Parse .env file and extract all API keys (active and commented)."""
        if not self.env_path.exists():
            print(f"[WARN] .env file not found at {self.env_path}")
            return
        
        with open(self.env_path, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                # Extract key from commented line: #GEMINI_API_KEY=key_here
                match = re.search(r'GEMINI_API_KEY\s*=\s*([^\s#]+)', line)
                if match:
                    key = match.group(1).strip()
                    if key and key not in self.keys:
                        self.keys.append(key)
            else:
                # Extract key from active line: GEMINI_API_KEY=key_here
                match = re.search(r'GEMINI_API_KEY\s*=\s*([^\s#]+)', line)
                if match:
                    key = match.group(1).strip()
                    if key:
                        # Put active key first
                        if key not in self.keys:
                            self.keys.insert(0, key)
        
        if not self.keys:
            # Fallback to environment variable
            env_key = os.getenv("GEMINI_API_KEY")
            if env_key:
                self.keys.append(env_key)
        
        print(f"[API KEY MANAGER] Loaded {len(self.keys)} API key(s)")
        if self.keys:
            print(f"[API KEY MANAGER] Key rotation system active.")
    
    def get_current_key(self) -> Optional[str]:
        """Get the currently active API key."""
        if not self.keys:
            return None
        
        # Skip exhausted keys
        while (self.current_index < len(self.keys) and 
               self.keys[self.current_index] in self.exhausted_keys):
            self.current_index += 1
        
        if self.current_index >= len(self.keys):
            print("[API KEY MANAGER] All keys exhausted!")
            return None
        
        return self.keys[self.current_index]
    
    def rotate_key(self, reason: str = "Rate limit detected") -> Optional[str]:
        """
        Rotate to the next API key.
        
        Args:
            reason: Reason for rotation (for logging)
        
        Returns:
            Next API key, or None if all keys exhausted
        """
        if not self.keys:
            return None
        
        current_key = self.get_current_key()
        if current_key:
            self.exhausted_keys.add(current_key)
            print(f"[API KEY MANAGER] Marking current key as exhausted ({reason})")
        
        self.current_index += 1
        
        # Skip exhausted keys
        while (self.current_index < len(self.keys) and 
               self.keys[self.current_index] in self.exhausted_keys):
            self.current_index += 1
        
        if self.current_index >= len(self.keys):
            print("[API KEY MANAGER] All keys exhausted! Cannot rotate further.")
            return None
        
        new_key = self.keys[self.current_index]
        print(f"[API KEY MANAGER] Rotated to key {self.current_index + 1}/{len(self.keys)}")
        return new_key
    
    def reset_exhausted(self) -> None:
        """Reset exhausted keys (useful for testing or after quota reset)."""
        self.exhausted_keys.clear()
        self.current_index = 0
        print("[API KEY MANAGER] Reset exhausted keys")
    
    def get_all_keys_count(self) -> int:
        """Get total number of keys available."""
        return len(self.keys)
    
    def get_remaining_keys_count(self) -> int:
        """Get number of keys not yet exhausted."""
        return len(self.keys) - len(self.exhausted_keys)


# Global instance
_key_manager: Optional[APIKeyManager] = None


def get_key_manager() -> APIKeyManager:
    """Get or create the global API key manager instance."""
    global _key_manager
    if _key_manager is None:
        _key_manager = APIKeyManager()
    return _key_manager


def get_api_key() -> Optional[str]:
    """Get the current active API key."""
    return get_key_manager().get_current_key()


def rotate_api_key(reason: str = "Rate limit detected") -> Optional[str]:
    """Rotate to the next API key."""
    return get_key_manager().rotate_key(reason)
