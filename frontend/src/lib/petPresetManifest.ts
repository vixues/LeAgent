import type { PetBuiltinAppearance } from '@/lib/builtinPets';
import type { PetBehaviorSettings, PetNestSettings } from '@/lib/petSettings';

export interface PetPresetManifestPet {
  id: PetBuiltinAppearance;
  label: string;
  static: string;
  motion: string;
  supportedStates: string[];
  motionDefaults?: Partial<PetBehaviorSettings>;
  recommendedNest?: Partial<PetNestSettings>;
}

export interface PetPresetManifest {
  version: number;
  license?: string;
  basePath?: string;
  pets: PetPresetManifestPet[];
}

export async function loadPetPresetManifest(): Promise<PetPresetManifest> {
  const base = import.meta.env.BASE_URL || '/';
  const normalized = base.endsWith('/') ? base : `${base}/`;
  const res = await fetch(`${normalized}pet-presets/manifest.json`);
  if (!res.ok) {
    throw new Error(`Failed to load pet preset manifest: ${res.status}`);
  }
  return (await res.json()) as PetPresetManifest;
}

export function findPresetManifestPet(
  manifest: PetPresetManifest | undefined,
  id: string | null | undefined,
): PetPresetManifestPet | null {
  if (!manifest || !id) return null;
  return manifest.pets.find((pet) => pet.id === id) ?? null;
}
