// ============================================================================
// TYPESCRIPT TYPES
// ============================================================================
// Shared types across the application
// ============================================================================

export interface Clip {
    session_id: string;
    filename: string;
    path: string;
    clip_hash?: string;
    thumbnail_url?: string;
    size: number;
    created_at: number;
    tags?: string[];
    vibes?: string[];
    subjects?: string[];
    description?: string[];
    energy?: string;
    quality?: number;
}

export interface Result {
    filename: string;
    path: string;
    thumbnail_url?: string;
    size: number;
    created_at: number;
}

export interface Reference {
    filename: string;
    path: string;
    thumbnail_url?: string;
    size: number;
    created_at: number;
}

export interface ProgressData {
    status: "uploaded" | "processing" | "complete" | "error";
    progress: number;
    message: string;
}

export interface DirectorCritique {
    overall_score: number;
    monologue: string;
    star_performers: string[];
    dead_weight: string[];
    missing_ingredients: string[];
    remake_actions: { type: string; segment: string; suggestion: string }[];
    technical_fidelity: string;
}

export interface StyleConfig {
    text: {
        font: string;
        weight: number | string;
        color: string;
        shadow: boolean;
        position: 'top' | 'center' | 'bottom';
        animation: 'fade' | 'none';
    };
    color: {
        preset: 'neutral' | 'warm' | 'cool' | 'high_contrast' | 'vintage';
    };
    texture: {
        grain: boolean;
    };
}
