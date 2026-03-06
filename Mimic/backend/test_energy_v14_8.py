# v14.8 INTENT-AWARE ENERGY VALIDATION TEST
print('='*70)
print('v14.8 INTENT-AWARE ENERGY MATCHING - VALIDATION TEST')
print('='*70)

# Test the vibe-gating logic
EMOTION_DRIVEN_VIBES = {
    'peace', 'stillness', 'calm', 'warmth', 'nostalgia', 'love',
    'reflection', 'intimate', 'quiet', 'tender', 'gentle', 'soft',
    'bittersweet', 'memory', 'longing', 'wonder', 'innocence'
}
TEMPO_DRIVEN_VIBES = {
    'hype', 'energy', 'action', 'intensity', 'celebration',
    'dynamic', 'fast', 'power', 'explosive', 'rush'
}

test_cases = [
    ('peace, stillness', 'Low', 'Medium', True, 'Emotion-driven Intro'),
    ('joy, vitality', 'Medium', 'High', False, 'Neutral Peak (no emotion vibes)'),
    ('nostalgia, love', 'Low', 'Medium', True, 'Emotion-driven Outro'),
    ('hype, energy', 'High', 'Medium', False, 'Tempo-driven (strict)'),
    ('curiosity, wonder', 'Medium', 'High', True, 'Emotion-driven Build-up'),
    ('celebration, intensity', 'High', 'Medium', False, 'Tempo-driven celebration'),
]

print('\n📊 TEST CASES:\n')
for vibe, target_energy, clip_energy, should_relax, description in test_cases:
    segment_vibes_lower = set(v.strip().lower() for v in vibe.split(','))
    is_emotion_driven = bool(segment_vibes_lower & EMOTION_DRIVEN_VIBES)
    is_tempo_driven = bool(segment_vibes_lower & TEMPO_DRIVEN_VIBES)
    
    energy_order = {'Low': 0, 'Medium': 1, 'High': 2}
    clip_level = energy_order.get(clip_energy, 1)
    target_level = energy_order.get(target_energy, 1)
    energy_distance = abs(clip_level - target_level)
    is_adjacent = energy_distance == 1
    
    will_relax = is_emotion_driven and not is_tempo_driven and is_adjacent
    
    status = '✅ PASS' if will_relax == should_relax else '❌ FAIL'
    emoji = '✨' if will_relax else '🔒'
    
    print(f'{status} {emoji} {description}')
    print(f'     Vibe: "{vibe}" | Target: {target_energy} | Clip: {clip_energy}')
    print(f'     Emotion: {is_emotion_driven} | Tempo: {is_tempo_driven} | Adjacent: {is_adjacent}')
    print(f'     Expected: {"Relax" if should_relax else "Strict"} | Got: {"Relax" if will_relax else "Strict"}')
    print()

print('='*70)
print('VALIDATION COMPLETE')
print('='*70)
