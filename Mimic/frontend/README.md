# MIMIC Frontend - Complete Documentation

## Overview

MIMIC Frontend is a Next.js 16 application built with React, TypeScript, and Tailwind CSS. It provides a surgical, cinematic interface for AI-powered video synthesis - allowing users to upload reference videos and source clips, generate synthesized outputs, and manage their media library.

**Tech Stack**: Next.js 16 (App Router), React, TypeScript, Tailwind CSS, Shadcn UI, Sonner (toasts), Lucide Icons

---

## Design Philosophy

### Surgical Noir Aesthetic

The frontend follows a "Surgical Noir" design philosophy - dark, precise, and cinematic:

- **Dark Theme**: Deep black backgrounds (`#020204`) with subtle gradients
- **Precision**: Clean lines, minimal UI, focus on content
- **Cinematic**: Glass morphism effects, subtle animations, premium feel
- **Color Coding**: 
  - Indigo (`#6366f1`) for primary actions and reference videos
  - Cyan (`#22d3ee`) for source clips and secondary elements
  - Purple accents for special states

### Key Design Principles

1. **Pragmatic Over Perfect**: Fast iteration with inline Tailwind, extract only when reused 3+ times
2. **Centralized Communication**: All API calls go through `lib/api.ts` - never duplicate fetch logic
3. **Type Safety First**: TypeScript everywhere, shared types in `lib/types.ts`
4. **Visual Hierarchy**: Clear distinction between upload areas, progress, and results
5. **Real-time Feedback**: WebSocket progress updates, live log streaming, immediate visual feedback

---

## Architecture

### File Structure

```
frontend/
├── app/                          # Next.js App Router pages
│   ├── page.tsx                 # Studio (home) - upload & generate
│   ├── gallery/page.tsx         # Assets - browse clips/references/results
│   ├── vault/page.tsx           # Projects - view & compare videos
│   ├── layout.tsx               # Root layout with Header
│   └── globals.css              # Global styles, reusable classes
│
├── lib/                         # Core utilities
│   ├── api.ts                   # Centralized API client (CRITICAL)
│   ├── types.ts                 # TypeScript interfaces
│   └── utils.ts                 # Helper functions (cn, etc.)
│
└── components/                   # Reusable UI components
    ├── header.tsx              # Navigation header
    └── ui/                     # Shadcn components (dialog, card, etc.)
```

### Data Flow

1. **Upload Flow** (Studio Page):
   ```
   User selects files → Frontend stores File objects → 
   Upload to backend via FormData → Backend saves to data/samples/ →
   Returns session_id → Frontend stores session_id
   ```

2. **Generation Flow**:
   ```
   User clicks Generate → Frontend calls /api/generate/{session_id} →
   Backend starts pipeline → WebSocket connection established →
   Real-time progress updates → Logs streamed to "Show Thinking" box →
   On completion → Auto-redirect to Projects page with result selected
   ```

3. **File Serving**:
   ```
   Frontend requests video → Backend serves from data/samples/ or data/results/ →
   URL.createObjectURL() for preview → Direct download links for files
   ```

### State Management

- **Local State**: React `useState` for component-specific state
- **No Global State**: No Redux/Zustand - state passed via props or URL params
- **Session Tracking**: Session IDs stored in component state, passed to backend
- **URL State**: Query params used for deep linking (e.g., `/vault?filename=x&type=results`)

---

## Pages & Functionality

### Studio (`/`) - `app/page.tsx`

**Purpose**: Main upload and generation interface

**Key Features**:
- Reference video upload (single file)
- Source clips upload (multiple files, additive)
- Fixed-height upload boxes (`h-[240px]`) that don't resize
- Real-time progress tracking via WebSocket
- "Show Thinking" log box displaying orchestrator output
- Auto-redirect to Projects page on completion

**State Management**:
- `refFile`: Single File object for reference
- `materialFiles`: Array of File objects for clips
- `isGenerating`: Boolean for generation state
- `progress`: 0-100 percentage
- `statusMsg`: Current step message
- `logMessages`: Array of log strings from orchestrator
- `currentSessionId`: Active session UUID

**Key Functions**:
- `handleRefUpload`: Sets reference file, shows toast
- `handleMaterialUpload`: Appends new clips (additive), resets input
- `startMimic`: Uploads files, starts generation, connects WebSocket
- `checkStatus`: Polls `/api/status/{session_id}` for progress
- `addLogMessage`: Adds timestamped log entries

**Layout**:
- Left: Upload boxes (Reference + Source Clips) - full width
- Right: "Show Thinking" log box (fixed `w-80`)
- Bottom: Progress bar (shown during generation)

**Design Notes**:
- Upload boxes use fixed height to prevent resizing
- Clips show as thumbnails in grid when uploaded
- Reference shows video preview with overlay when selected
- Log box scrolls automatically, shows monospace font

### Assets (`/gallery`) - `app/gallery/page.tsx`

**Purpose**: Browse and manage all media files

**Key Features**:
- Three categories: Clips, Reference Videos, Results
- "Type" dropdown to filter by category
- Search bar with "Filters" button
- Tag-based filtering (mock tags currently)
- Recently Uploaded section (top scroll box)
- All Files section (bottom scroll box)
- Click file to open in Projects page

**State Management**:
- `clips`, `references`, `results`: Arrays of respective types
- `selectedCategory`: Current filter ("clips" | "references" | "results" | null)
- `searchQuery`: Search text input
- `selectedTags`: Array of selected filter tags
- `recentItems`, `allItems`: Filtered/computed arrays

**Data Flow**:
- Fetches all three types on mount via `Promise.all`
- Filters based on category, search, and tags
- Sorts by modification time for "recent"
- Navigates to Projects with `?filename=x&type=y` on click

**Design Notes**:
- Horizontal scroll boxes for file browsing
- Cards show video thumbnails with hover effects
- Tag filtering via dialog overlay
- Responsive grid layout

### Projects (`/vault`) - `app/vault/page.tsx`

**Purpose**: View and compare generated videos

**Key Features**:
- View mode toggle: Results, References, or Clips
- Side-by-side comparison mode
- Dedicated dropdowns for each side (left: outputs, right: references)
- Video player with metadata display
- Download and delete actions
- Deep linking via URL params

**State Management**:
- `viewMode`: Current category view
- `selectedItem`, `selectedItem2`: Currently displayed videos
- `sideBySideMode`: Boolean for comparison view
- `showLeftDropdown`, `showRightDropdown`: Dropdown visibility

**Layout Modes**:
1. **Single View**: One video player, one dropdown for category selection
2. **Side-by-Side**: Two video players, separate dropdowns (left=outputs, right=references)

**Design Notes**:
- Video player constrained width (not full page)
- Metadata shown below video
- Action buttons (Download, Delete) in header
- Smooth transitions between views

---

## Styling System

### Global Styles (`app/globals.css`)

**Color Palette**:
- Background: `#020204` (deep black)
- Cards: `#08080c` (slightly lighter)
- Borders: `rgba(255, 255, 255, 0.05)` (subtle white)
- Accents: Indigo (`#6366f1`), Cyan (`#22d3ee`)

**Reusable Classes**:

- `.module`: Base card style with rounded corners, padding, border
- `.module-active-indigo`: Active state for reference-related cards
- `.module-active-cyan`: Active state for clip-related cards
- `.module-progress`: Progress bar container styling
- `.shiny-text`: Animated gradient text effect
- `.btn-premium`: Premium button with glow and shimmer
- `.custom-scrollbar`: Thin, styled scrollbars
- `.bg-mesh`: Deep space gradient background

**Typography**:
- Primary: Inter (sans-serif)
- Mono: JetBrains Mono (for logs/code)
- Font features: `cv02`, `cv03`, `cv04`, `cv11` (OpenType features)

**Animations**:
- `glimmer`: Shiny text animation
- `slideDown`: Smooth fade-in from top
- `slowPulse`: Subtle pulsing for active states

### Tailwind Usage

- **Inline Classes**: Preferred for fast iteration
- **Responsive**: `md:`, `xl:` breakpoints used throughout
- **Custom Colors**: Defined in CSS variables, accessed via Tailwind
- **Spacing**: Consistent use of Tailwind spacing scale

---

## API Integration

### Centralized Client (`lib/api.ts`)

**Critical Rule**: All backend communication MUST go through `lib/api.ts`. Never write `fetch()` directly in components.

**Available Methods**:

```typescript
// Upload
api.uploadFiles(reference: File, clips: File[]): Promise<{session_id, ...}>

// Generation
api.startGeneration(sessionId: string): Promise<{status, ...}>
api.connectProgress(sessionId: string): WebSocket

// Assets
api.fetchClips(): Promise<{clips: Clip[]}>
api.fetchReferences(): Promise<{references: Reference[]}>
api.fetchResults(): Promise<{results: Result[]}>

// File serving (direct URLs)
http://localhost:8000/api/files/clips/{filename}
http://localhost:8000/api/files/reference/{filename}
http://localhost:8000/api/files/results/{filename}
```

**WebSocket Protocol**:
- Connects to `ws://localhost:8000/ws/progress/{session_id}`
- Receives JSON: `{status, progress, message, logs}`
- `status`: "uploaded" | "processing" | "complete" | "error"
- `progress`: 0.0 to 1.0
- `logs`: Array of log strings from orchestrator

---

## Development Guidelines

### Adding a New Page

1. Create file in `app/{route}/page.tsx`
2. Use `"use client"` directive
3. Import from `@/lib/api` for backend calls
4. Use existing styling patterns (`.module`, etc.)
5. Add route to Header navigation if needed

### Adding an API Call

1. Add method to `lib/api.ts`
2. Use `API_BASE` constant (currently `http://localhost:8000`)
3. Handle errors appropriately
4. Return typed data (add types to `lib/types.ts` if needed)

### Styling Guidelines

1. **Prefer Inline Tailwind**: Faster iteration, easier to see in code
2. **Extract to CSS**: Only when used 3+ times or complex patterns
3. **Use Existing Classes**: `.module`, `.btn-premium`, etc. before creating new
4. **Responsive First**: Design mobile, enhance for desktop
5. **Consistent Spacing**: Use Tailwind scale (4px increments)

### Component Extraction

- Extract when used 3+ times
- Keep props minimal and typed
- Use `cn()` utility for conditional classes
- Prefer composition over configuration

---

## Known Issues & Limitations

### Current Issues

1. **Duplicate File Detection**: Backend hash comparison may not always work correctly - files are being renamed and saved even when duplicates exist. Enhanced logging added to debug.

2. **File Upload Box Resizing**: Fixed with `h-[240px]` constraint, but requires careful overflow handling.

3. **WebSocket Reconnection**: No automatic reconnection if WebSocket drops - relies on polling fallback.

4. **Tag System**: Currently using mock tags - not persisted or connected to backend.

5. **Video Playback Errors**: Some browsers may show `AbortError` for video play/pause - handled with `.catch(() => {})`.

6. **Progress Polling**: Falls back to polling if WebSocket fails, but may miss updates during reconnection.

### Technical Debt

- No error boundaries for graceful error handling
- No loading skeletons (just loading states)
- No pagination for large file lists
- No file preview before upload
- No drag-and-drop (click to upload only)
- No batch operations (delete multiple, etc.)

### Browser Compatibility

- Tested primarily on Chrome/Edge
- Custom scrollbars may look different in Firefox
- WebSocket support required (all modern browsers)

---

## How It Was Made

### Evolution

1. **Initial Setup**: Next.js 16 with App Router, Tailwind CSS, Shadcn UI
2. **Design Iteration**: Multiple iterations to achieve "Surgical Noir" aesthetic
3. **Reference Implementation**: Studied `src/` folder from another project for card layouts and styling patterns
4. **Component Refinement**: Started with sidebar, removed it, added type dropdowns
5. **Upload Flow**: Fixed resizing issues, added additive clip upload
6. **Progress Tracking**: Added WebSocket integration, log streaming
7. **Navigation**: Implemented deep linking, auto-redirect on completion

### Key Decisions

- **No Sidebar**: Removed in favor of dropdown menus (cleaner, more space)
- **Fixed Upload Boxes**: Prevent resizing with fixed heights and overflow handling
- **Auto-Redirect**: On completion, redirect to Projects page (Option B from user preference)
- **Log Streaming**: Real-time orchestrator output in "Show Thinking" box
- **Full Width Layout**: Removed `max-w-2xl` constraint for better use of space

### Design References

- Inspired by "File Index" page from `src/` folder
- Card styling borrowed from reference project
- Color scheme evolved from initial design to current "Surgical Noir"

---

## Data Flow Details

### Upload Process

1. User selects files in Studio page
2. Files stored as `File` objects in React state
3. On "Generate" click:
   - `api.uploadFiles()` creates FormData
   - POST to `/api/upload`
   - Backend saves to `data/samples/clips/` or `data/samples/reference/`
   - Backend checks for duplicates via hash comparison
   - Returns `{session_id, reference: {...}, clips: [...]}`
4. Frontend stores `session_id` and calls `api.startGeneration()`

### Generation Process

1. `api.startGeneration(session_id)` POSTs to `/api/generate/{session_id}`
2. Backend starts pipeline in background task
3. WebSocket connection: `api.connectProgress(session_id)`
4. Backend streams progress updates:
   - `{status: "processing", progress: 0.5, message: "...", logs: [...]}`
5. Frontend updates UI:
   - Progress bar percentage
   - Status message
   - Log messages array
6. On completion:
   - `{status: "complete", progress: 1.0, output_path: "..."}`
   - Frontend redirects to `/vault?filename={filename}&type=results`

### File Display

1. Assets/Projects pages fetch file lists via API
2. Backend returns metadata: `{filename, size, ...}`
3. Frontend constructs video URLs:
   - Clips: `http://localhost:8000/api/files/clips/{filename}`
   - References: `http://localhost:8000/api/files/reference/{filename}`
   - Results: `http://localhost:8000/api/files/results/{filename}`
4. Videos displayed via `<video>` elements with `src={url}`

---

## Testing & Debugging

### Development Server

```bash
cd frontend
npm install
npm run dev
```

Runs on `http://localhost:3000`

### Backend Connection

- Backend must be running on `http://localhost:8000`
- CORS configured for `http://localhost:3000`
- WebSocket endpoint: `ws://localhost:8000/ws/progress/{session_id}`

### Debugging Tips

1. **Check Browser Console**: React errors, network failures
2. **Check Backend Logs**: Upload deduplication, hash calculations
3. **WebSocket Inspector**: Use browser DevTools Network tab → WS
4. **State Inspection**: React DevTools for component state
5. **Network Tab**: Check API responses, file serving

### Common Issues

- **Files not loading**: Check backend is running, CORS configured
- **WebSocket not connecting**: Check backend WebSocket endpoint, session_id valid
- **Progress stuck**: Check backend logs, WebSocket messages
- **Upload fails**: Check file size limits, backend disk space

---

## Future Improvements

### Planned Features

- Drag-and-drop file upload
- File preview before upload
- Batch operations (delete multiple, etc.)
- Real tag system (backend integration)
- Pagination for large file lists
- Error boundaries for graceful failures
- Loading skeletons for better UX
- File metadata editing
- Export/import project configurations

### Technical Improvements

- WebSocket reconnection logic
- Better error handling and user feedback
- Optimistic UI updates
- Virtual scrolling for large lists
- Image optimization for thumbnails
- Service worker for offline support

---

## Quick Reference

### Key Files

- `app/page.tsx`: Studio page (upload & generate)
- `app/gallery/page.tsx`: Assets page (browse files)
- `app/vault/page.tsx`: Projects page (view results)
- `lib/api.ts`: **CRITICAL** - All API calls here
- `lib/types.ts`: TypeScript interfaces
- `app/globals.css`: Reusable styles

### Key Classes

- `.module`: Base card style
- `.module-active-indigo`: Active reference state
- `.module-active-cyan`: Active clip state
- `.btn-premium`: Premium button
- `.custom-scrollbar`: Styled scrollbars
- `.shiny-text`: Animated text

### Key Functions

- `api.uploadFiles()`: Upload reference + clips
- `api.startGeneration()`: Start video generation
- `api.connectProgress()`: WebSocket for progress
- `api.fetchClips/References/Results()`: Get file lists

---

**Status**: ✅ Production Ready
**Last Updated**: January 23, 2026
**Version**: 3.3
**Maintainer**: MIMIC Team
