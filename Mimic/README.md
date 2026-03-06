# MIMIC — AI Video Editor That Thinks Like a Director

> *"Give it a viral TikTok and your own clips. It recreates the edit. Intelligently."*

MIMIC is a multi-model AI video editing system that understands creative intent. It doesn't just chop clips to a beat — it analyzes the *soul* of a reference edit and rebuilds it using your footage, making decisions a real editor would make.

**Built originally for the Google Gemini API Developer Competition. Now being refined into a consumer product.**

---

## What It Does

You give MIMIC:
1. A reference video (a TikTok, Reel, or any edit with a vibe you want to replicate)
2. Your own clips
3. Music (optional — can borrow from the reference)

MIMIC produces:
- A professionally-paced edit that captures the reference's rhythm, energy flow, and narrative intent
- A "Vault Report" explaining every clip choice and creative decision
- Zero repeated moments. Zero mechanical metronome cutting.

### Two Modes

**Reference Mode** — The main mode. Gives MIMIC a viral reference video and it extracts its "editorial DNA" — exact cut timing, energy arc, vibe transitions, text overlay context — then rebuilds the edit with your footage. The total duration is locked to the reference exactly.

**Prompt Mode** — No reference video needed. Describe what you want in plain text ("make a nostalgic birthday reel with my trip clips") and MIMIC generates a full editorial blueprint from scratch, informed by what clips you actually have.

---

## How It Works

### The Multi-Model AI Stack
MIMIC uses the best model for the job at each stage — not one model for everything.

| Stage | Model | Why |
|---|---|---|
| Video & clip analysis | Google Gemini 3 Flash | Only model that can watch raw video |
| Blueprint generation (Prompt Mode) | DeepSeek V3 | Fast, structured reasoning from text |
| Strategic editorial advisory | DeepSeek V3 | Generates clip selection brief per reference |
| Vault report & Director's critique | Groq / Llama 3.3 70B | High-quality human-readable explanations |
| Timing, scoring, rendering | Python + FFmpeg | Deterministic — AI never controls timestamps |

### The Pipeline (7 Steps)
1. **Detect cuts** in the reference video (FFmpeg scene detection + BPM analysis)
2. **Analyze the reference** with Gemini — classify each segment by energy, vibe, arc stage, and narrative intent
3. **Analyze your clips** with Gemini — extract creative DNA: energy, motion, subject matter, best moments
4. **Strategic Advisor** (DeepSeek) — writes an editorial brief: "This edit is about friendship. Prioritize group clips in the peak. Penalize scenic shots."
5. **Semantic Editor** — scores every clip against every segment using the brief, energy rules, and global history. Picks the best non-repeated clip for each slot.
6. **Render** (FFmpeg) — extract segments, concatenate, merge audio. Frame-locked to 30fps CFR. Duration is exact.
7. **Reflect** (Groq Llama) — AI critiques the finished edit and generates the Vault Report

### What Makes Edits Good (The Philosophy)
- **Vibe over Math** — Beat snapping is a guide, not a law. If a moment needs to breathe for 4 seconds, it breathes for 4 seconds.
- **No Repeats, Ever** — Global clip history tracks the last 20 renders. The system explores your whole library.
- **The Right Clip in the Right Place** — Advisor reads the reference narrative (e.g., "it's about the people") and enforces subject-aware selection.
- **Sacred Cuts** — If the original editor made a cut at a specific frame, that cut boundary is protected. The algorithm cannot subdivide it.

---

## Quick Start

### Prerequisites
- Python 3.10+
- FFmpeg in PATH
- Node.js 18+
- API keys: Gemini, DeepSeek, Groq

### Installation

```bash
git clone https://github.com/JazibWaqas/Mimic.git
cd Mimic

# Backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r backend/requirements.txt

# Add API keys
# Create backend/.env with:
# GEMINI_API_KEY=...
# DEEPSEEK_API_KEY=...
# GROQ_API_KEY=...

# Frontend
cd frontend
npm install
```

### Running Locally

```bash
# Terminal 1 — Backend
cd backend
.\venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000

# Terminal 2 — Frontend
cd frontend
npm run dev

# Open http://localhost:3000
```

### First Edit
1. Go to **Studio**
2. Upload your clips (MP4, vertical preferred)
3. Upload a reference video **or** type a prompt
4. Add music (optional)
5. Hit **Execute**
6. Check the **Vault tab** for AI reasoning

**First run:** ~30–60s (clips analyzed by Gemini, cached after)
**Subsequent runs:** ~15s (all analysis cached)

---

## Performance

- First-run clip analysis: ~30s for 10 clips (Gemini)
- Re-runs with cache: ~15s
- Tested with 220+ clips in library
- Cache hit rate: 95%+ on reruns
- Timeline accuracy: ±0.001s (Clock-Lock system)

---

## Project Structure

```
Mimic/
├── backend/
│   ├── engine/
│   │   ├── orchestrator.py     # Pipeline entry point
│   │   ├── brain.py            # Gemini 3 (clip + reference analysis)
│   │   ├── generator.py        # DeepSeek V3 (Prompt Mode blueprint)
│   │   ├── gemini_advisor.py   # DeepSeek V3 (editorial brief)
│   │   ├── editor.py           # Python scoring engine (V15.0 Vibe-over-Math)
│   │   ├── reflector.py        # Groq Llama 3.3 70B (vault + critique)
│   │   └── processors.py       # FFmpeg + Librosa
│   ├── models.py               # All Pydantic schemas
│   └── main.py                 # FastAPI server
├── frontend/                   # Next.js 14 UI
├── data/
│   ├── cache/                  # All AI analysis cached by content hash
│   ├── results/                # Rendered videos + logs
│   └── samples/                # Source clips, references, music
└── ContextFiles/
    ├── ARCHITECTURE.md         # Full technical spec
    └── SYSTEM_STATE.md         # Current status + change log
```

---

## Tech Stack

**AI:** Google Gemini 3 Flash · DeepSeek V3 · Groq / Llama 3.3 70B
**Backend:** Python 3.11 · FastAPI · Pydantic · FFmpeg · Librosa
**Frontend:** Next.js 14 · React 18 · TypeScript · Tailwind · Framer Motion

---

## Documentation

- **[ARCHITECTURE.md](ContextFiles/ARCHITECTURE.md)** — Full system design, model routing, scoring logic, data flow
- **[SYSTEM_STATE.md](ContextFiles/SYSTEM_STATE.md)** — Current status, known issues, version history

---

## License

MIT
