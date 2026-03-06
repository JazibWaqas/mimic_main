"""
MIMIC FastAPI Backend
Handles file uploads, Gemini 3 processing, and video rendering.
"""

import os
import sys
from fastapi import FastAPI, UploadFile, File, WebSocket, HTTPException, BackgroundTasks, Body, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import mimetypes
from fastapi.staticfiles import StaticFiles
import uuid
from pathlib import Path
from typing import List, Optional, Dict
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import hashlib
import time

from dotenv import load_dotenv
from models import *
from engine.orchestrator import run_mimic_pipeline
from engine.processors import generate_thumbnail, convert_to_mp4
from utils import ensure_directory, cleanup_session, get_file_hash, get_bytes_hash, register_file_hash, save_hash_registry

# Load environment variables
load_dotenv()

# Root Directory Setup - Matching test_ref.py structure
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
TEMP_DIR = BASE_DIR / "temp"
SAMPLES_DIR = DATA_DIR / "samples"
CLIPS_DIR = SAMPLES_DIR / "clips"
REFERENCES_DIR = SAMPLES_DIR / "reference"
RESULTS_DIR = DATA_DIR / "results"
CACHE_DIR = DATA_DIR / "cache"

# Sub-cache organization
THUMBNAILS_DIR = CACHE_DIR / "thumbnails"
STANDARDIZED_DIR = CACHE_DIR / "standardized"
MUTED_DIR = CACHE_DIR / "muted"
ADVISOR_CACHE_DIR = CACHE_DIR / "advisor"
CLIP_CACHE_DIR = CACHE_DIR / "clips"
REF_CACHE_DIR = CACHE_DIR / "references"
CRITIQUE_CACHE_DIR = CACHE_DIR / "critiques"

# Ensure dirs exist
CLIPS_DIR.mkdir(parents=True, exist_ok=True)
REFERENCES_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
THUMBNAILS_DIR.mkdir(parents=True, exist_ok=True)
STANDARDIZED_DIR.mkdir(parents=True, exist_ok=True)
MUTED_DIR.mkdir(parents=True, exist_ok=True)
ADVISOR_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CLIP_CACHE_DIR.mkdir(parents=True, exist_ok=True)
REF_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CRITIQUE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
TEMP_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="MIMIC API", version="1.0.0")

# CORS for Next.js frontend - Apply Fix 1 from Section 9.5
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")
ALLOWED_ORIGINS = [
    FRONTEND_URL,
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Allow common dev ports
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Track active sessions
active_sessions = {}
session_locks: Dict[str, asyncio.Lock] = {} # Lock for each session to prevent race conditions
video_exts = {".mp4", ".mov", ".avi", ".mpg", ".mpeg", ".3gp", ".m4v", ".mkv"}

# ============================================================================
# STATE MANAGEMENT (V12.0)
# ============================================================================

# Conversion Mapping (v11.8): Track original source hashes to their converted MP4 paths
SOURCE_MAP_PATH = CACHE_DIR / "source_map.json"
source_map = {}

def load_source_map():
    global source_map
    if SOURCE_MAP_PATH.exists():
        try:
            with open(SOURCE_MAP_PATH, "r", encoding="utf-8") as f:
                source_map = json.load(f)
        except Exception as e:
            print(f"[WARN] Failed to load source_map: {e}")
            source_map = {}

def save_source_map():
    try:
        with open(SOURCE_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(source_map, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save source_map: {e}")

# Session Persistence (v12.1): Track active sessions across restarts
SESSIONS_PATH = CACHE_DIR / "active_sessions.json"

def load_active_sessions():
    global active_sessions
    if SESSIONS_PATH.exists():
        try:
            with open(SESSIONS_PATH, "r", encoding="utf-8") as f:
                active_sessions = json.load(f)
                print(f"[RECOVERY] Restored {len(active_sessions)} active sessions from disk.")
        except Exception as e:
            print(f"[WARN] Failed to load sessions: {e}")
            active_sessions = {}

def save_active_sessions():
    try:
        # We don't save the locks, they are ephemeral
        with open(SESSIONS_PATH, "w", encoding="utf-8") as f:
            json.dump(active_sessions, f, indent=2)
    except Exception as e:
        print(f"[WARN] Failed to save sessions: {e}")

load_source_map()
load_active_sessions()

class LibraryIndex:
    """
    Singleton index for the entire MIMIC library (clips, results, references).
    Prevents repeated O(N) filesystem scans on every request.
    Handles background thumbnail generation.
    """
    _clips: List[dict] = []
    _results: List[dict] = []
    _references: List[dict] = []
    _hashes: dict[str, Path] = {}
    
    _last_refresh: float = 0
    _refresh_interval: float = 30.0 # Refresh every 30 seconds if requested
    _lock = asyncio.Lock()
    _is_refreshing = False

    @classmethod
    async def get_clips(cls, limit: int = None, offset: int = 0) -> List[dict]:
        await cls._ensure_fresh()
        data = cls._clips
        if limit is not None:
            return data[offset : offset + limit]
        return data

    @classmethod
    async def get_results(cls, limit: int = None, offset: int = 0) -> List[dict]:
        await cls._ensure_fresh()
        data = cls._results
        if limit is not None:
            return data[offset : offset + limit]
        return data

    @classmethod
    async def get_references(cls, limit: int = None, offset: int = 0) -> List[dict]:
        await cls._ensure_fresh()
        data = cls._references
        if limit is not None:
            return data[offset : offset + limit]
        return data

    @classmethod
    async def get_hashes(cls) -> dict[str, Path]:
        await cls._ensure_fresh()
        return cls._hashes.copy()

    @classmethod
    async def _ensure_fresh(cls):
        now = time.time()
        if not cls._last_refresh or (now - cls._last_refresh > cls._refresh_interval):
            if not cls._is_refreshing:
                await cls._refresh()

    @classmethod
    def update_sync(cls, clip_hash: str, path: Path):
        """Immediate manual update when a new clip is added/uploaded."""
        cls._hashes[clip_hash] = path
        # We don't fully rebuild the lists here to keep upload fast, 
        # a refresh will catch the metadata soon.

    @classmethod
    async def _refresh(cls):
        async with cls._lock:
            if cls._is_refreshing: return
            cls._is_refreshing = True
            
            start_time = time.time()
            print(f"[INDEX] Global Refresh Started...")
            
            try:
                new_clips = []
                new_results = []
                new_references = []
                new_hashes = {}
                
                # 1. Scan Clips
                if CLIPS_DIR.exists():
                    clip_files = [p for p in CLIPS_DIR.glob("*.mp4") if p.is_file()]
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        results = list(executor.map(lambda p: cls._process_file(p, "clip"), clip_files))
                        for meta, p, h in results:
                            if meta: 
                                new_clips.append(meta)
                                if h: new_hashes[h] = p
                
                # 2. Scan Results
                if RESULTS_DIR.exists():
                    result_files = [p for p in RESULTS_DIR.glob("*.mp4") if p.is_file()]
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        results = list(executor.map(lambda p: cls._process_file(p, "result"), result_files))
                        for meta, p, h in results:
                            if meta: 
                                new_results.append(meta)
                                # We don't necessarily need results in the global clip hash index
                
                # 3. Scan References
                if REFERENCES_DIR.exists():
                    ref_files = [p for p in REFERENCES_DIR.glob("*.mp4") if p.is_file()]
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        results = list(executor.map(lambda p: cls._process_file(p, "ref"), ref_files))
                        for meta, p, h in results:
                            if meta: 
                                new_references.append(meta)

                # Sort all by newest first
                new_clips.sort(key=lambda x: x["created_at"], reverse=True)
                new_results.sort(key=lambda x: x["created_at"], reverse=True)
                new_references.sort(key=lambda x: x["created_at"], reverse=True)
                
                # Atomic Swap
                cls._clips = new_clips
                cls._results = new_results
                cls._references = new_references
                cls._hashes = new_hashes
                cls._last_refresh = time.time()
                
                save_hash_registry()
                elapsed = time.time() - start_time
                print(f"[INDEX] Refresh Complete ({elapsed:.2f}s). Index: {len(new_clips)} clips, {len(new_results)} results, {len(new_references)} refs.")
                
            except Exception as e:
                print(f"[INDEX] Refresh Error: {e}")
            finally:
                cls._is_refreshing = False

    @staticmethod
    def _process_file(p: Path, type_tag: str):
        """Helper to extract metadata and ensure thumbnail exists in a thread-safe way."""
        try:
            # 1. Identity Verification (Source of Truth)
            # v12.1: We must use content hash for identity unification
            h = get_file_hash(p)
            if not h: 
                print(f"[INDEX] ERR: Could not compute identity for {p.name}")
                return None, p, None
            
            # 2. Thumbnail Linkage (Deterministic)
            # v12.1 Unified: Use a single content-based thumbnail for all views
            thumb_name = f"thumb_{h}.jpg"
            thumb_path = THUMBNAILS_DIR / thumb_name
            
            if not thumb_path.exists():
                try:
                    generate_thumbnail(str(p), str(thumb_path))
                except Exception as te:
                    print(f"[THUMB] Failed for {p.name}: {te}")

            stat = p.stat()
            meta = {
                "filename": p.name,
                "path": f"/api/files/{'samples/clips' if type_tag == 'clip' else 'results' if type_tag == 'result' else 'references'}/{p.name}",
                "thumbnail_url": f"/api/files/thumbnails/{thumb_name}",
                "size": stat.st_size,
                "created_at": stat.st_mtime,
                "hash": h,
                "intelligence_status": "missing", # Default
                "version": "unknown"
            }
            
            # 3. Intelligence Contract Enforcement
            if type_tag == "clip":
                meta["session_id"] = "samples" 
                intelligence_path = CLIP_CACHE_DIR / f"clip_comprehensive_{h}.json"
                if intelligence_path.exists():
                    try:
                        with open(intelligence_path, 'r', encoding='utf-8') as f:
                            intel = json.load(f)
                            # Verify Version Contract (v12.1 Invariant)
                            cache_ver = intel.get("_cache_version", intel.get("cache_version", "0.0"))
                            from engine.brain import CLIP_CACHE_VERSION
                            
                            if cache_ver == CLIP_CACHE_VERSION:
                                meta["intelligence_status"] = "authoritative"
                                meta["vibes"] = intel.get("vibes", [])
                                meta["subjects"] = intel.get("primary_subject", [])
                                meta["description"] = intel.get("content_description", "")
                                meta["energy"] = intel.get("energy", "Unknown")
                                meta["quality"] = intel.get("clip_quality", 0)
                                meta["version"] = cache_ver
                            else:
                                meta["intelligence_status"] = "legacy"
                                meta["version"] = cache_ver
                    except Exception as e:
                        print(f"[INDEX] ERR: Failed to read contract for {p.name}: {e}")
            
            elif type_tag == "ref":
                # Find best matching reference intelligence
                from engine.brain import REFERENCE_CACHE_VERSION
                # v12.1 Refined pattern: catch vX and legacy formats
                matches = list(REF_CACHE_DIR.glob(f"ref_{h}_*.json"))
                if matches:
                    # Sort candidates by version match and time
                    candidates = []
                    for m in matches:
                        try:
                            with open(m, 'r', encoding='utf-8') as f:
                                intel = json.load(f)
                                ver = intel.get("_contract", {}).get("version", intel.get("_cache_version", "0.0"))
                                candidates.append({"ver": ver, "mtime": m.stat().st_mtime})
                        except: continue
                    
                    if candidates:
                        candidates.sort(key=lambda x: (x["ver"] == REFERENCE_CACHE_VERSION, x["mtime"]), reverse=True)
                        best = candidates[0]
                        meta["version"] = best["ver"]
                        if best["ver"] == REFERENCE_CACHE_VERSION:
                            meta["intelligence_status"] = "authoritative"
                        else:
                            meta["intelligence_status"] = "legacy"

            elif type_tag == "result":
                meta["original_filename"] = p.name
                meta["original_size"] = stat.st_size
                # Results often have a .json sidecar
                json_path = p.with_suffix(".json")
                if json_path.exists():
                    meta["intelligence_status"] = "authoritative"
                
            return meta, p, h
        except Exception as e:
            print(f"[INDEX] Global Error processing {p}: {e}")
            return None, p, None

# ============================================================================
# ENDPOINTS
# ============================================================================

@app.post("/api/identify")
async def identify_reference(reference: UploadFile = File(...)):
    """
    Fast identity scan of reference video to determine session_id.
    """
    ext = Path(reference.filename).suffix.lower()
    if ext not in video_exts:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported reference format '{ext}'. Allowed: {', '.join(sorted(video_exts))}"
        )
    
    content = await reference.read()
    content_hash = hashlib.md5(content).hexdigest()[:12]
    return {"session_id": f"sess_{content_hash}"}

@app.post("/api/upload")
async def upload_files(
    reference: Optional[UploadFile] = File(None),
    clips: List[UploadFile] = File(...),
    music: Optional[UploadFile] = File(None)
):
    """
    Upload reference video (optional), user clips, and music (optional).
    Saves directly to data/samples/ structure.
    """
    if reference:
        ext = Path(reference.filename).suffix.lower()
        if ext not in video_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Reference format '{ext}' is not supported. Allowed: {', '.join(sorted(video_exts))}"
            )
    
    if music and not (music.filename.lower().endswith('.mp3') or music.filename.lower().endswith('.wav') or music.filename.lower().endswith('.mp4')):
        raise HTTPException(status_code=400, detail="Music must be .mp3, .wav, or .mp4 format")
    
    for clip in clips:
        ext = Path(clip.filename).suffix.lower()
        if ext not in video_exts:
            raise HTTPException(
                status_code=400,
                detail=f"Clip format '{ext}' is not supported for {clip.filename}. Allowed: {', '.join(sorted(video_exts))}"
            )
    
    # Calculate session_id
    if reference:
        ref_content = await reference.read()
        ref_hash = hashlib.md5(ref_content).hexdigest()
        session_id = f"sess_{ref_hash}"
    elif music:
        music_content = await music.read()
        music_hash = hashlib.md5(music_content).hexdigest()
        session_id = f"text_music_{music_hash}"
    else:
        session_id = f"text_{uuid.uuid4().hex[:12]}"
    
    print(f"\n[UPLOAD] New upload request")
    print(f"[UPLOAD] Session ID: {session_id}")
    
    # Save Music if provided
    music_path = None
    if music:
        music_dir = DATA_DIR / "samples" / "music"
        music_dir.mkdir(parents=True, exist_ok=True)
        music_path = music_dir / music.filename
        
        # Reset read pointer if we read it for hash
        if not reference: await music.seek(0)
        content = await music.read()
        
        with open(music_path, "wb") as f:
            f.write(content)
        print(f"[UPLOAD] Music saved to: {music_path}")

    ref_path = None
    if reference:
        # Check if file with same content already exists
        existing_ref = None
        for existing_file in REFERENCES_DIR.glob("*.mp4"):
            if existing_file.is_file():
                try:
                    with open(existing_file, 'rb') as f:
                        existing_hash = hashlib.md5(f.read()).hexdigest()
                    if existing_hash == ref_hash:
                        existing_ref = existing_file
                        print(f"[UPLOAD] Reference content already exists: {existing_file.name} (reusing)")
                        break
                except Exception:
                    continue
        
        if existing_ref:
            ref_path = existing_ref
        else:
            # Save new reference
            ref_path = REFERENCES_DIR / reference.filename
            if ref_path.exists():
                base_name = ref_path.stem
                counter = 1
                while ref_path.exists():
                    ref_path = REFERENCES_DIR / f"{base_name}_{counter}{ref_path.suffix}"
                    counter += 1
                print(f"[UPLOAD] Reference filename conflict, saved as: {ref_path.name}")
            
            with open(ref_path, "wb") as f:
                f.write(ref_content)
            print(f"[UPLOAD] Reference saved to: {ref_path}")
    
    # Save clips to data/samples/clips/
    clip_paths = []
    skipped_count = 0
    
    # v12.0: Use the optimized Singleton Library Index
    existing_hashes = await LibraryIndex.get_hashes()
    
    print(f"[UPLOAD] Protocol initialized - Cross-referencing {len(existing_hashes)} library assets...")
    
    temp_upload_dir = TEMP_DIR / "uploads"
    temp_upload_dir.mkdir(parents=True, exist_ok=True)

    async def process_clip(clip):
        clip_content = await clip.read()
        file_size = len(clip_content)
        clip_ext = Path(clip.filename).suffix.lower()
        clip_hash = get_bytes_hash(clip_content) if clip_ext == ".mp4" else ""
        
        # 1. Direct Content Check (Source-to-Source)
        # If we've seen THESE EXACT BYTES before, return the previous path immediately
        if clip_hash and clip_hash in source_map:
            cached_path = Path(source_map[clip_hash])
            if cached_path.exists():
                return {
                    "path": str(cached_path),
                    "original_filename": clip.filename,
                    "original_size": file_size,
                    "was_skipped": True,
                    "clip_hash": clip_hash
                }
        
        # 2. Library Cross-Reference (for direct MP4 uploads)
        if clip_hash and clip_hash in existing_hashes:
            existing_clip = existing_hashes[clip_hash]
            # Update source map for future speed
            source_map[clip_hash] = str(existing_clip)
            return {
                "path": str(existing_clip),
                "original_filename": clip.filename,
                "original_size": file_size,
                "was_skipped": True,
                "clip_hash": clip_hash
            }
        
        # Save new clip
        target_name = f"{Path(clip.filename).stem}.mp4" if clip_ext != ".mp4" else clip.filename
        clip_path = CLIPS_DIR / target_name
        
        # v11.8: Use the hash in the filename for collision-free uniqueness if requested,
        # otherwise use the iterating name but guard the source_map carefully.
        if clip_path.exists():
            base_name = clip_path.stem
            counter = 1
            while clip_path.exists():
                clip_path = CLIPS_DIR / f"{base_name}_{counter}{clip_path.suffix}"
                counter += 1

        if clip_ext != ".mp4":
            raw_path = temp_upload_dir / clip.filename
            with open(raw_path, "wb") as f:
                f.write(clip_content)
            try:
                convert_to_mp4(str(raw_path), str(clip_path))
            except Exception as e:
                raise HTTPException(
                    status_code=400,
                    detail=f"Conversion failed for {clip.filename}. {e}"
                )
            finally:
                if raw_path.exists():
                    raw_path.unlink()
        else:
            with open(clip_path, "wb") as f:
                f.write(clip_content)

        clip_hash = get_file_hash(clip_path)
        if not clip_hash:
            clip_hash = get_bytes_hash(clip_content)
            register_file_hash(clip_path, clip_hash)

        # 3. Update the mapping for future fast-tracking
        source_map[clip_hash] = str(clip_path)
        LibraryIndex.update_sync(clip_hash, clip_path) # Update global index immediately
        return {
            "path": str(clip_path),
            "original_filename": clip.filename,
            "original_size": file_size,
            "was_skipped": False,
            "clip_hash": clip_hash
        }

    # Process clips in parallel using asyncio.gather
    clip_results = await asyncio.gather(*[process_clip(clip) for clip in clips])
    
    clip_paths = []
    for res in clip_results:
        clip_paths.append(res["path"])
        if res["was_skipped"]:
            skipped_count += 1
        else:
            print(f"[UPLOAD] New clip saved: {Path(res['path']).name}")
    
    print(f"[UPLOAD] {len(clips)} clips processed, {len(clip_paths)} clips will be used ({len(clip_paths) - skipped_count} new, {skipped_count} existing reused)")
    
    # Persist the source map to disk
    save_source_map()
    
    # Store session info
    active_sessions[session_id] = {
        "reference_path": str(ref_path) if ref_path else None,
        "music_path": str(music_path) if music_path else None,
        "clip_paths": clip_paths,
        "status": "uploaded",
        "progress": 0.0,
        "logs": [],
        "iteration": 0,
        "created_at": time.time()
    }
    save_active_sessions()
    
    print(f"[UPLOAD] Protocol initialized - session {session_id[:8]} active\n")
    
    reference_payload = {
        "filename": ref_path.name if ref_path else "text_prompt",
        "size": ref_path.stat().st_size if ref_path else 0
    }
    if ref_path:
        # v12.1 Unified Thumbnail
        ref_thumb_name = f"thumb_{ref_hash}.jpg"
        ref_thumb_path = THUMBNAILS_DIR / ref_thumb_name
        try:
            if not ref_thumb_path.exists():
                generate_thumbnail(str(ref_path), str(ref_thumb_path))
            reference_payload["thumbnail_url"] = f"/api/files/thumbnails/{ref_thumb_name}"
            
            # Signature for frontend matching
            reference_payload["original_filename"] = getattr(reference, "filename", ref_path.name)
            reference_payload["original_size"] = ref_path.stat().st_size
        except Exception as e:
            print(f"[THUMB] Ref thumbnail failed: {e}")

    with ThreadPoolExecutor(max_workers=5) as executor:
        def get_payload_with_meta(res):
            clip_path = Path(res["path"])
            clip_hash = get_file_hash(clip_path)
            # v12.1 Unified Thumbnail
            thumb_name = f"thumb_{clip_hash}.jpg"
            thumb_path = THUMBNAILS_DIR / thumb_name
            try:
                if not thumb_path.exists():
                    generate_thumbnail(str(clip_path), str(thumb_path))
                thumb_url = f"/api/files/thumbnails/{thumb_name}"
            except Exception as e:
                print(f"[THUMB] Clip thumbnail failed: {e}")
                thumb_url = None

            return {
                "filename": clip_path.name,
                "size": clip_path.stat().st_size,
                "original_filename": res["original_filename"],
                "original_size": res["original_size"],
                "thumbnail_url": thumb_url,
                "clip_hash": res.get("clip_hash") or clip_hash
            }
            
        clips_payload = list(executor.map(get_payload_with_meta, clip_results))

    return {
        "session_id": session_id,
        "reference": reference_payload,
        "clips": clips_payload
    }


@app.post("/api/generate/{session_id}")
async def generate_video(
    session_id: str, 
    background_tasks: BackgroundTasks,
    text_prompt: Optional[str] = Query(None, description="Text prompt for Creator Mode"),
    target_duration: Optional[float] = Query(15.0, description="Target duration in seconds"),
    style_config: Optional[StyleConfig] = Body(None) # v14.9 Style Control (Post-Editor Layer)
):
    """
    Start video generation pipeline.
    Client should connect to WebSocket for real-time progress.
    """
    # Session recovery not needed - files are in data/samples/ and session info is in memory
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please upload files first.")
    
    session = active_sessions[session_id]
    
    # মার্ক as processing
    # v12.1: Implement session locking to prevent race conditions
    if session_id not in session_locks:
        session_locks[session_id] = asyncio.Lock()
    
    async with session_locks[session_id]:
        if session["status"] == "processing":
            return {"status": "already_processing", "session_id": session_id}
        
        # Prepare for iteration - detect next number from disk to stay persistent
        tag = session_id if len(session_id) < 12 else session_id[:12]
        existing_versions = []
        
        # Scan RESULTS_DIR for existing versions of this session
        if RESULTS_DIR.exists():
            for f in RESULTS_DIR.glob(f"*_{tag}_v*.mp4"):
                try:
                    # Extract N from ..._vN
                    v_part = f.stem.split("_v")[-1]
                    if v_part.isdigit():
                        existing_versions.append(int(v_part))
                except: pass
                
        # Default to memory count if not found on disk, but prioritize disk
        disk_max = max(existing_versions) if existing_versions else 0
        current_iteration = max(disk_max + 1, session.get("iteration", 0) + 1)
        
        session["iteration"] = current_iteration
        
        # Mark as processing
        session["status"] = "processing"
        session["progress"] = 0.0
    
    # Run pipeline in background
    print(f"[GENERATE] Executing iteration v{current_iteration} for session: {session_id}")
    if text_prompt:
        print(f"[GENERATE] Text Prompt: {text_prompt}")
    
    background_tasks.add_task(
        process_video_pipeline,
        session_id,
        session.get("reference_path"),
        session.get("clip_paths"),
        current_iteration,
        text_prompt,
        target_duration,
        session.get("music_path"),
        style_config
    )
    
    return {"status": "processing", "session_id": session_id, "iteration": current_iteration}


def process_video_pipeline(
    session_id: str, 
    ref_path: str = None, 
    clip_paths: List[str] = None, 
    iteration: int = 1,
    text_prompt: Optional[str] = None,
    target_duration: float = 15.0,
    music_path: Optional[str] = None,
    style_config: Optional[StyleConfig] = None # v14.9 Style Control (Post-Editor Layer)
):
    """
    Run the MIMIC pipeline with progress updates.
    Uses Gemini API for analysis.
    """
    import time
    import sys
    from io import StringIO
    start_time = time.time()
    
    # Initialize logs list in session
    if session_id in active_sessions:
        active_sessions[session_id]["logs"] = []
    
    # Custom stdout handler to capture orchestrator output
    class LogCapture:
        def __init__(self, original_stdout, session_id):
            self.original_stdout = original_stdout
            self.session_id = session_id
            self.buffer = ""

        def _should_store_line(self, line: str) -> bool:
            """Filter noisy debug output for WS/UI logs without affecting stdout or file logs."""
            s = (line or "").strip()
            if not s:
                return False

            # Always keep warnings/errors/progress and top-level pipeline markers.
            keep_prefixes = (
                "[PROGRESS]",
                "[PIPELINE]",
                "[GENERATE]",
                "[WARN]",
                "[ERROR]",
                "[OK]",
                "✅",
                "❌",
            )
            if s.startswith(keep_prefixes):
                return True

            # Drop high-volume debug noise (X-RAY, cache spam, deep analysis dumps)
            drop_prefixes = (
                "[CACHE]",
                "[NEW]",
                "[THUMB]",
                "[INDEX]",
                "🔬",
            )
            if s.startswith(drop_prefixes):
                return False

            drop_contains = (
                "X-RAY",
                "TOP 5 CANDIDATES",
                "SEGMENT SCORING",
                "CLIP USAGE ANALYSIS",
                "BLUEPRINT SEGMENTS",
                "END OF X-RAY REPORT",
            )
            if any(token in s for token in drop_contains):
                return False

            return False
        
        def write(self, s):
            # Write to original stdout (console)
            self.original_stdout.write(s)
            self.original_stdout.flush()
            
            # Store in session logs
            if self.session_id in active_sessions:
                if s.strip():  # Only store non-empty lines
                    # Split by newlines and add each line
                    lines = s.split('\n')
                    for line in lines:
                        if self._should_store_line(line):
                            active_sessions[self.session_id]["logs"].append(line.strip())
                            # Keep only last 500 lines to avoid memory issues
                            if len(active_sessions[self.session_id]["logs"]) > 500:
                                active_sessions[self.session_id]["logs"].pop(0)
        
        def flush(self):
            self.original_stdout.flush()
    
    # Capture stdout
    log_capture = LogCapture(sys.stdout, session_id)
    original_stdout = sys.stdout
    sys.stdout = log_capture
    
    print(f"\n{'='*60}")
    print(f"[PIPELINE] STARTING NEW PIPELINE RUN")
    print(f"{'='*60}")
    print(f"[PIPELINE] Session ID: {session_id}")
    print(f"[PIPELINE] Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[PIPELINE] Reference: {ref_path}")
    print(f"[PIPELINE] Clips ({len(clip_paths) if clip_paths else 0}): {clip_paths}")
    print(f"{'='*60}\n")
    
    def progress_callback(step: int, total: int, message: str):
        if session_id in active_sessions:
            active_sessions[session_id]["progress"] = step / total
            active_sessions[session_id]["current_step"] = message
            print(f"[PROGRESS] Step {step}/{total}: {message}")
    
    try:
        if session_id not in active_sessions:
            print(f"[PIPELINE] ERROR: Session {session_id} not found in active_sessions")
            return
        
        session = active_sessions[session_id]
        
        # Run pipeline with Gemini API
        print(f"[PIPELINE] Running pipeline with Gemini...")
        result = run_mimic_pipeline(
            reference_path=ref_path,
            clip_paths=clip_paths,
            session_id=session_id,
            output_dir=str(RESULTS_DIR),
            progress_callback=progress_callback,
            iteration=iteration,
            text_prompt=text_prompt,
            target_duration=target_duration,
            music_path=music_path,
            style_config=style_config
        )
        
        elapsed = time.time() - start_time
        
        if result.success:
            print(f"\n[PIPELINE] SUCCESS - Pipeline completed in {elapsed:.1f}s")
            print(f"[PIPELINE] Output: {result.output_path}")
            
            # Generate thumbnail for the result immediately for Vault UI
            res_path = Path(result.output_path)
            res_hash = get_file_hash(res_path)
            # v12.1 Unified Thumbnail: Content-addressed only
            res_thumb_name = f"thumb_{res_hash}.jpg"
            res_thumb_path = THUMBNAILS_DIR / res_thumb_name
            res_thumb_url = None
            try:
                if not res_thumb_path.exists():
                    generate_thumbnail(str(res_path), str(res_thumb_path))
                res_thumb_url = f"/api/files/thumbnails/{res_thumb_name}"
            except Exception as te:
                print(f"[THUMB] Result thumbnail failed: {te}")

            active_sessions[session_id]["status"] = "complete"
            active_sessions[session_id]["output_path"] = result.output_path
            active_sessions[session_id]["thumbnail_url"] = res_thumb_url
            active_sessions[session_id]["blueprint"] = result.blueprint.model_dump() if result.blueprint else None
            active_sessions[session_id]["clip_index"] = result.clip_index.model_dump() if result.clip_index else None
            
            save_active_sessions()
            
            # Trigger index refresh safely in background thread
            try:
                asyncio.run(LibraryIndex._refresh())
            except Exception as e:
                print(f"[WARN] Post-render index refresh skipped: {e}")
        else:
            print(f"\n[PIPELINE] FAILED - Error: {result.error}")
            active_sessions[session_id]["status"] = "error"
            active_sessions[session_id]["error"] = result.error
            
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n[PIPELINE] EXCEPTION after {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        active_sessions[session_id]["status"] = "error"
        active_sessions[session_id]["error"] = str(e)
    finally:
        # Restore stdout
        sys.stdout = original_stdout


@app.get("/api/status/{session_id}")
async def get_status(session_id: str):
    """
    Get current processing status.
    
    Returns:
        {
            "status": "uploaded" | "processing" | "complete" | "error",
            "progress": 0.0-1.0,
            "current_step": "Analyzing reference...",
            "output_path": "..." (if complete)
        }
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return active_sessions[session_id]


@app.get("/api/download/{session_id}")
async def download_video(session_id: str):
    """
    Download final video.
    """
    if session_id not in active_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = active_sessions[session_id]
    
    if session["status"] != "complete":
        raise HTTPException(status_code=400, detail="Video not ready")
    
    output_path = session["output_path"]
    
    if not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")
    
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"mimic_output_{session_id}.mp4"
    )


@app.websocket("/ws/progress/{session_id}")
async def websocket_progress(websocket: WebSocket, session_id: str):
    """
    WebSocket for real-time progress updates.
    """
    print(f"[WS] Connection attempt for session: {session_id}")
    # Accept WebSocket connection (CORS is handled at HTTP level)
    origin = websocket.headers.get("origin")
    print(f"[WS] Origin: {origin}")
    allowed_origins = [FRONTEND_URL, "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001"]
    
    # In development, be more lenient
    if origin and origin not in allowed_origins:
        # Log but allow in development (localhost variants)
        if "localhost" in origin or "127.0.0.1" in origin:
            print(f"[WS] Allowing localhost origin: {origin}")
        else:
            print(f"[WS] Rejecting connection from origin: {origin}")
            await websocket.close(code=1008, reason="Origin not allowed")
            return
    
    try:
        await websocket.accept()
        print(f"[WS] Connection accepted for session: {session_id}")
    except Exception as e:
        print(f"[WS] Failed to accept connection: {e}")
        return
    
    try:
        # Wait up to 10 seconds for session to be created
        wait_count = 0
        max_wait = 10
        
        while wait_count < max_wait:
            if session_id in active_sessions:
                print(f"[WS] Session found: {session_id}")
                break
            await asyncio.sleep(0.5)
            wait_count += 0.5
        
        if session_id not in active_sessions:
            print(f"[WS] Session not found after {max_wait}s: {session_id}")
            await websocket.send_json({
                "status": "error",
                "progress": 0.0,
                "message": "Session not found. Make sure you've uploaded files first."
            })
            await websocket.close(code=1000)
            return
        
        # Send initial status
        session = active_sessions[session_id]
        await websocket.send_json({
            "status": session["status"],
            "progress": session.get("progress", 0.0),
            "message": session.get("current_step", "Waiting to start...")
        })
        
        while True:
            if session_id in active_sessions:
                session = active_sessions[session_id]
                await websocket.send_json({
                    "status": session["status"],
                    "progress": session.get("progress", 0.0),
                    "message": session.get("current_step", ""),
                    "logs": session.get("logs", [])
                })
                
                # Stop sending if complete or error
                if session["status"] in ["complete", "error"]:
                    print(f"[WS] Session {session_id} finished with status: {session['status']}")
                    break
            else:
                # Session was deleted
                await websocket.send_json({
                    "status": "error",
                    "progress": 0.0,
                    "message": "Session expired"
                })
                break
            
            await asyncio.sleep(1)  # Update every second
            
    except Exception as e:
        print(f"[WS] Error in WebSocket handler: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.send_json({
                "status": "error",
                "progress": 0.0,
                "message": f"Error: {str(e)}"
            })
        except:
            pass
    finally:
        try:
            await websocket.close(code=1000)
            print(f"[WS] Connection closed for session: {session_id}")
        except:
            pass


@app.get("/api/history")
async def get_history():
    """
    Get list of past projects (optional feature).
    For hackathon, can just return sessions from memory.
    """
    history = [
        {
            "session_id": sid,
            "status": session["status"],
            "created_at": session.get("created_at", ""),
            "reference_filename": Path(session["reference_path"]).name,
            "clip_count": len(session["clip_paths"])
        }
        for sid, session in active_sessions.items()
    ]
    return {"projects": history}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    """
    Clean up session files.
    """
    if session_id in active_sessions:
        cleanup_session(session_id)
        del active_sessions[session_id]
        return {"status": "deleted"}
    
    raise HTTPException(status_code=404, detail="Session not found")


# Serve static files for previews (using explicit endpoints instead)
# Files are served via /api/files/ endpoints for better control

@app.get("/api/references")
async def list_reference_samples(limit: Optional[int] = None, offset: int = 0):
    """
    List all reference videos from data/samples/reference/.
    Uses the LibraryIndex in-memory cache for speed.
    """
    references = await LibraryIndex.get_references(limit=limit, offset=offset)
    return {"references": references}

@app.get("/api/clips")
async def list_all_clips(limit: Optional[int] = None, offset: int = 0):
    """
    List all clips from data/samples/clips/.
    Uses the LibraryIndex in-memory cache for speed.
    """
    all_clips = await LibraryIndex.get_clips(limit=limit, offset=offset)
    print(f"[API] Returning {len(all_clips)} clips from LibraryIndex")
    return {"clips": all_clips}

@app.delete("/api/clips/{session_id}/{filename}")
async def delete_specific_clip(session_id: str, filename: str):
    """
    Delete a specific clip from data/samples/clips/.
    """
    clip_path = CLIPS_DIR / filename
    if clip_path.exists():
        clip_path.unlink()
        print(f"[API] Deleted clip: {clip_path}")
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Clip not found")

@app.get("/api/results")
async def list_all_results(limit: Optional[int] = None, offset: int = 0):
    """
    List all generated videos in the results folder.
    Uses the LibraryIndex in-memory cache for speed.
    """
    results = await LibraryIndex.get_results(limit=limit, offset=offset)
    return {"results": results}

@app.delete("/api/results/{filename}")
async def delete_result(filename: str):
    """
    Delete a generated video from the vault.
    """
    result_path = RESULTS_DIR / filename
    if result_path.exists():
        result_path.unlink()
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Result not found")

@app.post("/api/rename")
async def rename_file(type: str, old_filename: str, new_filename: str):
    """
    Rename a file in the data/ structure.
    """
    if not new_filename.endswith(".mp4"):
        new_filename += ".mp4"
        
    if type == "results":
        src = RESULTS_DIR / old_filename
        dst = RESULTS_DIR / new_filename
    elif type == "references":
        src = REFERENCES_DIR / old_filename
        dst = REFERENCES_DIR / new_filename
    elif type == "clips":
        src = CLIPS_DIR / old_filename
        dst = CLIPS_DIR / new_filename
    else:
        raise HTTPException(status_code=400, detail="Invalid type")
        
    if not src.exists():
        raise HTTPException(status_code=404, detail="Source file not found")
    if dst.exists():
        raise HTTPException(status_code=400, detail="Target filename already exists")
        
    # Rename video
    src.rename(dst)
    
    # Rename associated JSON if it exists (for results)
    if type == "results":
        src_json = src.with_suffix(".json")
        dst_json = dst.with_suffix(".json")
        if src_json.exists():
            src_json.rename(dst_json)
            
    return {"status": "renamed", "new_filename": new_filename}

# Hash Registry removed - moved to utils.py for global speed


@app.get("/api/intelligence")
async def get_intelligence(type: str, filename: str):
    """
    Find and serve the AI intelligence/analysis JSON for a specific file.
    
    Types: 
    - results: Look for master JSON in data/results/
    - references: Look for ref_{hash}_h*.json in data/cache/references/
    - clips: Look for clip_comprehensive_{hash}.json in data/cache/clips/
    """
    try:
        if type == "results":
            # Strip extension and search for master JSON
            stem = Path(filename).stem
            # In orchestrator.py, results are saved as "{ref_name}_{session_id}.json"
            # The frontend sends the filename of the MP4, e.g., "ref4_12345678.mp4"
            json_name = f"{stem}.json"
            json_path = RESULTS_DIR / json_name
            
            if not json_path.exists():
                # Try finding any JSON that starts with the stem (in case of extension mismatch)
                matches = list(RESULTS_DIR.glob(f"{stem}*.json"))
                if matches:
                    json_path = matches[0]
            
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
                    
        elif type == "references":
            ref_path = REFERENCES_DIR / filename
            if not ref_path.exists():
                raise HTTPException(status_code=404, detail="Reference video not found")
            
            ref_hash = get_file_hash(ref_path)
            # Reference cache naming: ref_{hash}_v{ver}_h{fingerprint}.json
            # v12.1 Resolve Ambiguity: Find ALL matches, prioritize correct version, then latest time.
            from engine.brain import REFERENCE_CACHE_VERSION
            matches = list(REF_CACHE_DIR.glob(f"ref_{ref_hash}_*.json"))
            if not matches:
                 return {"status": "pending", "message": "Reference analysis missing"}
            
            # Create candidates list with metadata for sorting
            candidates = []
            for m in matches:
                try:
                    with open(m, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        ver = data.get("_cache_version", data.get("cache_version", "0.0"))
                        candidates.append({
                            "path": m,
                            "version": ver,
                            "mtime": m.stat().st_mtime,
                            "data": data
                        })
                except: continue
            
            if not candidates:
                 return {"status": "pending", "message": "Reference analysis unreadable"}

            # SORT: 1. Current Version Matches first, 2. Latest time first
            candidates.sort(key=lambda x: (x["version"] == REFERENCE_CACHE_VERSION, x["mtime"]), reverse=True)
            
            target = candidates[0]
            data = target["data"]
            
            # Inject authority indicators for frontend peace of mind
            data["_status"] = "complete"
            data["_authority"] = "authoritative" if target["version"] == REFERENCE_CACHE_VERSION else "legacy"
            data["_engine_version"] = target["version"]
            
            if target["version"] != REFERENCE_CACHE_VERSION:
                print(f"[INTEL] WARN: Serving legacy intelligence ({target['version']}) for {filename}")
            
            return data

        elif type == "clips":
            clip_path = CLIPS_DIR / filename
            if not clip_path.exists():
                raise HTTPException(status_code=404, detail="Clip video not found")
            
            clip_hash = get_file_hash(clip_path)
            # Clip cache naming: clip_comprehensive_{hash}.json
            json_path = CLIP_CACHE_DIR / f"clip_comprehensive_{clip_hash}.json"
            if json_path.exists():
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Verify Version Contract
                    from engine.brain import CLIP_CACHE_VERSION
                    ver = data.get("_cache_version", data.get("cache_version", "0.0"))
                    if ver != CLIP_CACHE_VERSION:
                         print(f"[INTEL] WARN: Serving legacy intelligence ({ver}) for clip {filename}")
                    return data
                    
        # If we reached here, the intelligence is not yet on disk
        return {
            "status": "pending",
            "message": "Editorial debrief pending - synchronization in progress",
            "type": type,
            "filename": filename
        }
        
    except Exception as e:
        print(f"[INTEL] Error fetching intelligence: {e}")
        # Even on exception, during a demo, we prefer a soft failure
        return {
            "status": "error",
            "message": str(e)
        }

# ============================================================================
# FILE SERVING ENDPOINTS (Explicit file serving for reliability)
# ============================================================================

@app.get("/api/files/results/{filename}")
async def serve_result_file(filename: str):
    """
    Serve a result video file explicitly.
    """
    result_path = RESULTS_DIR / filename
    if not result_path.exists() or not result_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(result_path),
        media_type=mimetypes.guess_type(str(result_path))[0] or "application/octet-stream",
        filename=filename
    )

@app.get("/api/files/references/{filename}")
async def serve_reference_file(filename: str):
    """
    Serve a reference video file explicitly.
    """
    ref_path = DATA_DIR / "samples" / "reference" / filename
    if not ref_path.exists() or not ref_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(ref_path),
        media_type=mimetypes.guess_type(str(ref_path))[0] or "application/octet-stream",
        filename=filename
    )

@app.get("/api/files/samples/clips/{filename}")
async def serve_sample_clip_file(filename: str):
    """
    Serve a sample clip video file explicitly.
    """
    clip_path = DATA_DIR / "samples" / "clips" / filename
    if not clip_path.exists() or not clip_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(
        path=str(clip_path),
        media_type=mimetypes.guess_type(str(clip_path))[0] or "application/octet-stream",
        filename=filename
    )

@app.get("/api/files/thumbnails/{filename}")
async def serve_thumbnail_file(filename: str):
    """
    Serve a thumbnail image file explicitly.
    """
    thumb_path = THUMBNAILS_DIR / filename
    if not thumb_path.exists() or not thumb_path.is_file():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(
        path=str(thumb_path),
        media_type="image/jpeg",
        filename=filename
    )


# Health check
@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/api/results/{filename}/style")
async def apply_style(
    filename: str,
    style_config: StyleConfig = Body(...)
):
    """
    v14.9: Apply visual styling (color, text, texture) to an existing result video.
    Uses clean master approach - always applies styling to unstyled version.
    """
    from engine.stylist import apply_visual_styling
    
    print(f"[STYLE] Request received for {filename}")
    print(f"[STYLE] Preset: {style_config.color.preset}, Font: {style_config.text.font}")
    
    result_path = RESULTS_DIR / filename
    if not result_path.exists():
        print(f"[STYLE] ERROR: File not found: {result_path}")
        raise HTTPException(status_code=404, detail="Result video not found")
    
    # Check for clean master (the unstyled export)
    clean_master_path = RESULTS_DIR / f"{Path(filename).stem}_clean.mp4"
    
    if clean_master_path.exists():
        source_video = str(clean_master_path)
        print(f"[STYLE] Using clean master: {clean_master_path}")
    else:
        # First style application - current video becomes clean master
        source_video = str(result_path)
        print(f"[STYLE] Creating clean master from: {result_path}")
        import shutil
        shutil.copy2(source_video, clean_master_path)
    
    # Temp output path
    temp_output = RESULTS_DIR / f"{Path(filename).stem}_styled_tmp.mp4"
    if temp_output.exists():
        temp_output.unlink()
    
    # Read existing metadata to keep AI-generated text content
    json_path = RESULTS_DIR / f"{Path(filename).stem}.json"
    blueprint_data = {}
    if json_path.exists():
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                master_data = json.load(f)
                blueprint_data = master_data.get("blueprint", {})
        except Exception as e:
            print(f"[STYLE] WARN: Could not read master JSON: {e}")

    try:
        # Apply visual styling
        print(f"[STYLE] Calling stylist...")
        apply_visual_styling(
            input_video=source_video,
            output_video=str(temp_output),
            text_overlay=blueprint_data.get("text_overlay", ""),
            text_style=blueprint_data.get("text_style", {}),
            color_grading=blueprint_data.get("color_grading", {}),
            text_events=blueprint_data.get("text_events", []),
            style_config=style_config # v14.9 authoritative style
        )
        
        if not temp_output.exists():
            raise Exception("Styling failed - no output file created")
        
        # Replace original with restyled version
        result_path.unlink()
        temp_output.rename(result_path)
        
        # Update master JSON report
        if json_path.exists():
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    master_data = json.load(f)
                
                # Persist style_config
                master_data["style_config"] = style_config.model_dump()
                
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(master_data, f, indent=2)
                print(f"[STYLE] Updated master JSON with new StyleConfig")
            except Exception as json_error:
                print(f"[STYLE] WARN: Failed updating result JSON: {json_error}")

        return {
            "status": "success",
            "filename": filename,
            "style_config": style_config
        }
        
    except Exception as e:
        print(f"[STYLE] EXCEPTION: {e}")
        if temp_output.exists():
            temp_output.unlink()
        raise HTTPException(status_code=500, detail=f"Styling failed: {str(e)}")


# ============================================================================
# BACKGROUND REFRESH LOOP
# ============================================================================

async def refresh_index_loop():
    """Background task to keep the LibraryIndex fresh."""
    while True:
        try:
            # We use the internal _refresh to avoid the interval check 
            # and ensure it actually refreshes.
            await LibraryIndex._refresh()
        except Exception as e:
            print(f"[BACK] Refresh loop error: {e}")
        await asyncio.sleep(60) # Refresh every minute

@app.on_event("startup")
async def startup_event():
    # Initial refresh
    asyncio.create_task(LibraryIndex._refresh())
    # Start periodic refresh loop
    asyncio.create_task(refresh_index_loop())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

