import { describe, it, expect } from 'vitest';
import {
  defaultBehaviorSettings,
  mergePetSettings,
  parsePetSettings,
  resolveActionWeights,
  resolvePetClip,
  resolvedBehavior,
  resolvedNest,
} from './petSettings';

describe('mergePetSettings', () => {
  it('merges appearance without dropping nest', () => {
    const base = JSON.stringify({
      appearance_file_id: 'a1',
      nest: { themeId: 'wood', backgroundFileId: null, accent: '#ff0000' },
      behavior: { mode: 'auto', manualMode: 'calm' },
    });
    const next = mergePetSettings(base, { appearance_file_id: 'a2' });
    const p = parsePetSettings(next);
    expect(p.appearance_file_id).toBe('a2');
    expect(resolvedNest(p).themeId).toBe('wood');
    expect(resolvedNest(p).accent).toBe('#ff0000');
  });

  it('merges partial nest over defaults', () => {
    const next = mergePetSettings(null, { nest: { themeId: 'night' } });
    const p = parsePetSettings(next);
    expect(resolvedNest(p).themeId).toBe('night');
    expect(resolvedNest(p).backgroundFileId).toBeNull();
    expect(resolvedNest(p).backgroundOpacity).toBe(0.25);
    expect(resolvedNest(p).backgroundPattern).toBe('none');
    expect(resolvedNest(p).backgroundFit).toBe('cover');
    expect(resolvedNest(p).backgroundPosition).toBe('center');
  });

  it('merges nest opacity and pattern without dropping other nest fields', () => {
    const base = JSON.stringify({
      nest: {
        themeId: 'wood',
        accent: '#111111',
        backgroundFileId: 'bg1',
        backgroundOpacity: 0.4,
        backgroundPattern: 'dots',
      },
    });
    const next = mergePetSettings(base, { nest: { backgroundPattern: 'grid' } });
    const p = parsePetSettings(next);
    const n = resolvedNest(p);
    expect(n.themeId).toBe('wood');
    expect(n.accent).toBe('#111111');
    expect(n.backgroundFileId).toBe('bg1');
    expect(n.backgroundOpacity).toBe(0.4);
    expect(n.backgroundPattern).toBe('grid');
  });

  it('merges background fit and position without dropping nest fields', () => {
    const base = JSON.stringify({
      nest: {
        themeId: 'wood',
        accent: '#222222',
        backgroundFileId: 'bg1',
        backgroundOpacity: 0.6,
        backgroundPattern: 'noise',
        backgroundFit: 'cover',
        backgroundPosition: 'center',
      },
    });
    const next = mergePetSettings(base, { nest: { backgroundFit: 'contain', backgroundPosition: 'top' } });
    const n = resolvedNest(parsePetSettings(next));
    expect(n.themeId).toBe('wood');
    expect(n.backgroundFileId).toBe('bg1');
    expect(n.backgroundFit).toBe('contain');
    expect(n.backgroundPosition).toBe('top');
  });

  it('merges rich behavior motion fields without dropping behavior mode', () => {
    const base = JSON.stringify({
      behavior: {
        mode: 'manual',
        manualMode: 'focus',
        autoReactivity: 'subtle',
        motionStyle: 'focused',
        motionSpeed: 0.8,
        idleAnimation: 'blink',
      },
    });
    const next = mergePetSettings(base, {
      behavior: { manualMode: 'wave', motionStyle: 'playful', motionSpeed: 1.4, idleAnimation: 'tailWag' },
    });
    const b = resolvedBehavior(parsePetSettings(next));
    expect(b.mode).toBe('manual');
    expect(b.manualMode).toBe('wave');
    expect(b.autoReactivity).toBe('subtle');
    expect(b.motionStyle).toBe('playful');
    expect(b.motionSpeed).toBe(1.4);
    expect(b.idleAnimation).toBe('tailWag');
  });

  it('clears built-in appearance when an uploaded appearance is selected', () => {
    const next = JSON.parse(
      mergePetSettings('{"appearance_builtin":"cat","nest":{"themeId":"night"}}', {
        appearance_file_id: 'file-1',
      }),
    );

    expect(next.appearance_file_id).toBe('file-1');
    expect(next.appearance_builtin).toBeNull();
    expect(next.nest.themeId).toBe('night');
  });

  it('clears uploaded appearance when a built-in appearance is selected', () => {
    const next = JSON.parse(
      mergePetSettings('{"appearance_file_id":"file-1","behavior":{"mode":"manual","manualMode":"focus"}}', {
        appearance_builtin: 'rabbit',
      }),
    );

    expect(next.appearance_builtin).toBe('rabbit');
    expect(next.appearance_file_id).toBeNull();
    expect(next.behavior.manualMode).toBe('focus');
  });

  it('merges clips per state without dropping other states', () => {
    const base = JSON.stringify({
      clips: {
        wave: { fileId: 'a', loop: 'loop', speed: 1 },
        jump: { fileId: 'b', loop: 'once' },
      },
    });
    const next = parsePetSettings(mergePetSettings(base, { clips: { wave: { speed: 1.5 } } }));
    expect(next.clips?.wave?.fileId).toBe('a');
    expect(next.clips?.wave?.speed).toBe(1.5);
    expect(next.clips?.jump?.fileId).toBe('b');
  });

  it('merges a new clip key without losing nest', () => {
    const base = JSON.stringify({ nest: { themeId: 'wood' } });
    const p = parsePetSettings(
      mergePetSettings(base, { clips: { working: { fileId: 'w1', speed: 2, mirror: true } } }),
    );
    expect(resolvedNest(p).themeId).toBe('wood');
    expect(p.clips?.working?.fileId).toBe('w1');
    expect(p.clips?.working?.mirror).toBe(true);
  });

  it('default behavior has autopilot roamRange and no stored actionWeights', () => {
    const b = defaultBehaviorSettings();
    expect(b.autopilot).toBe(true);
    expect(b.roamRange).toBe('normal');
    expect(b.actionWeights).toBeUndefined();
  });

  it('merges partial actionWeights and keeps other behavior keys', () => {
    const next = parsePetSettings(
      mergePetSettings('{}', {
        behavior: { mode: 'auto', actionWeights: { walk: 5, idle: 0 } as Record<string, number> },
      }),
    );
    const b = resolvedBehavior(next);
    expect(b.mode).toBe('auto');
    expect(b.actionWeights?.walk).toBe(5);
    expect(b.actionWeights?.idle).toBe(0);
    const w = resolveActionWeights(b.actionWeights);
    expect(w.walk).toBe(5);
    expect(w.idle).toBe(0);
    expect(w.jump).toBe(1); // default for unspecified key
  });
});

describe('resolvePetClip', () => {
  it('resolves by visual first', () => {
    const s = parsePetSettings(
      JSON.stringify({
        behavior: { idleAnimation: 'blink' },
        clips: {
          idle: { fileId: 'id1' },
          blink: { fileId: 'bl1' },
        },
      }),
    );
    const r = resolvePetClip('idle', 'blink', s);
    expect(r?.key).toBe('idle');
    expect(r?.binding.fileId).toBe('id1');
  });

  it('falls back to idleAnimation clip when visual is idle', () => {
    const s = parsePetSettings(
      JSON.stringify({
        clips: { breath: { fileId: 'br' } },
      }),
    );
    const r = resolvePetClip('idle', 'breath', s);
    expect(r?.key).toBe('breath');
    expect(r?.binding.fileId).toBe('br');
  });

  it('returns null when unbound', () => {
    expect(resolvePetClip('walk', 'breath', parsePetSettings('{}'))).toBeNull();
  });
});
