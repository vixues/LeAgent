import { describe, it, expect } from 'vitest';
import { inferThreeJsSceneOptions } from './GenUiThreeJsFrame';

describe('GenUiThreeJsFrame', () => {
  it('infers a rich polyhedron scene from legacy sceneScript hints', () => {
    const opts = inferThreeJsSceneOptions({
      title: 'Polyhedron',
      height: 520,
      background: '#0a0e1a',
      cameraZ: 6,
      sceneScript: 'const geo = new THREE.IcosahedronGeometry(1.8, 0); const particles = new THREE.Points();',
    });

    expect(opts.title).toBe('Polyhedron');
    expect(opts.height).toBe(520);
    expect(opts.background).toBe('#0a0e1a');
    expect(opts.geometry).toBe('icosahedron');
    expect(opts.cameraZ).toBe(6);
    expect(opts.particles).toBeGreaterThan(300);
  });

  it('accepts structured high-performance scene props', () => {
    const opts = inferThreeJsSceneOptions({
      geometry: 'torus-knot',
      color: '#60a5fa',
      accentColor: '0xfbbf24',
      particles: 2000,
      orbiters: 12,
      quality: 'high',
    });

    expect(opts.geometry).toBe('torusKnot');
    expect(opts.color).toBe(0x60a5fa);
    expect(opts.accentColor).toBe(0xfbbf24);
    expect(opts.particles).toBe(1200);
    expect(opts.orbiters).toBe(12);
    expect(opts.dpr).toBe(2);
  });
});
