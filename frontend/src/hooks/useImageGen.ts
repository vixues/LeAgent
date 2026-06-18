import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { adminApi } from '@/api/admin';
import type {
  ImageGenPreset,
  ImageGenCredentialUpdate,
  ImageGenLocalConfig,
  ImageGenTestRequest,
  ImageGenCustomProviderUpdate,
} from '@/types/admin';

const QK = {
  presets: ['image-gen', 'presets'] as const,
  default: ['image-gen', 'default'] as const,
  backends: ['image-gen', 'backends'] as const,
  credentials: ['image-gen', 'credentials'] as const,
  local: ['image-gen', 'local'] as const,
  providers: ['image-gen', 'providers'] as const,
  models: (backend: string) => ['image-gen', 'models', backend] as const,
};

export function useImageGenPresets() {
  return useQuery({ queryKey: QK.presets, queryFn: adminApi.imageGen.presets.list });
}

export function useImageGenDefault() {
  return useQuery({ queryKey: QK.default, queryFn: adminApi.imageGen.default.get });
}

export function useImageGenBackends() {
  return useQuery({ queryKey: QK.backends, queryFn: adminApi.imageGen.backends });
}

export function useImageGenCredentials() {
  return useQuery({ queryKey: QK.credentials, queryFn: adminApi.imageGen.credentials.list });
}

export function useImageGenLocal() {
  return useQuery({ queryKey: QK.local, queryFn: adminApi.imageGen.local.get });
}

export function useImageGenModels(backend: string | undefined) {
  return useQuery({
    queryKey: QK.models(backend ?? ''),
    queryFn: () => adminApi.imageGen.models(backend as string),
    enabled: !!backend,
    staleTime: 5 * 60 * 1000,
  });
}

function useInvalidatePresets() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: QK.presets });
    qc.invalidateQueries({ queryKey: QK.default });
  };
}

export function useCreatePreset() {
  const invalidate = useInvalidatePresets();
  return useMutation({
    mutationFn: (data: ImageGenPreset) => adminApi.imageGen.presets.create(data),
    onSuccess: invalidate,
  });
}

export function useUpdatePreset() {
  const invalidate = useInvalidatePresets();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: ImageGenPreset }) =>
      adminApi.imageGen.presets.update(id, data),
    onSuccess: invalidate,
  });
}

export function useDeletePreset() {
  const invalidate = useInvalidatePresets();
  return useMutation({
    mutationFn: (id: string) => adminApi.imageGen.presets.delete(id),
    onSuccess: invalidate,
  });
}

export function useSetDefaultPreset() {
  const invalidate = useInvalidatePresets();
  return useMutation({
    mutationFn: (presetId: string) => adminApi.imageGen.default.set(presetId),
    onSuccess: invalidate,
  });
}

export function useSetCredentials() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ backend, data }: { backend: string; data: ImageGenCredentialUpdate }) =>
      adminApi.imageGen.credentials.set(backend, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.credentials });
      qc.invalidateQueries({ queryKey: QK.backends });
    },
  });
}

export function useSetLocalConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ImageGenLocalConfig) => adminApi.imageGen.local.set(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: QK.local });
      qc.invalidateQueries({ queryKey: QK.backends });
    },
  });
}

export function useTestImageGen() {
  return useMutation({
    mutationFn: (data: ImageGenTestRequest) => adminApi.imageGen.test(data),
  });
}

export function useImageGenCustomProviders() {
  return useQuery({ queryKey: QK.providers, queryFn: adminApi.imageGen.providers.list });
}

function useInvalidateProviders() {
  const qc = useQueryClient();
  return () => {
    qc.invalidateQueries({ queryKey: QK.providers });
    qc.invalidateQueries({ queryKey: QK.backends });
  };
}

export function useCreateCustomProvider() {
  const invalidate = useInvalidateProviders();
  return useMutation({
    mutationFn: (data: ImageGenCustomProviderUpdate) => adminApi.imageGen.providers.create(data),
    onSuccess: invalidate,
  });
}

export function useUpdateCustomProvider() {
  const invalidate = useInvalidateProviders();
  return useMutation({
    mutationFn: ({ name, data }: { name: string; data: ImageGenCustomProviderUpdate }) =>
      adminApi.imageGen.providers.update(name, data),
    onSuccess: invalidate,
  });
}

export function useDeleteCustomProvider() {
  const invalidate = useInvalidateProviders();
  return useMutation({
    mutationFn: (name: string) => adminApi.imageGen.providers.delete(name),
    onSuccess: invalidate,
  });
}
