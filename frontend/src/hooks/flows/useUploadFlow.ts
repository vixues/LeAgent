import { useCallback, useState, useRef } from 'react';
import { useFlowsManagerStore } from '@/stores/flowsManagerStore';
import { useAlertStore } from '@/stores/alertStore';
import type { FlowData } from '@/types/flow';

export interface UploadFlowOptions {
  acceptedFormats?: string[];
  maxFileSize?: number;
  validateFlow?: (flow: Partial<FlowData>) => { valid: boolean; errors?: string[] };
  onUploadStart?: () => void;
  onUploadSuccess?: (flow: FlowData) => void;
  onUploadError?: (error: Error) => void;
}

export interface UploadFlowState {
  isUploading: boolean;
  progress: number;
  fileName: string | null;
  error: Error | null;
}

const DEFAULT_ACCEPTED_FORMATS = ['.json', '.yaml', '.yml', '.leagent'];
const DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

export function useUploadFlow(options: UploadFlowOptions = {}) {
  const {
    acceptedFormats = DEFAULT_ACCEPTED_FORMATS,
    maxFileSize = DEFAULT_MAX_FILE_SIZE,
    validateFlow,
    onUploadStart,
    onUploadSuccess,
    onUploadError,
  } = options;

  const { importFlow } = useFlowsManagerStore();
  const { success, error: showError } = useAlertStore();
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [state, setState] = useState<UploadFlowState>({
    isUploading: false,
    progress: 0,
    fileName: null,
    error: null,
  });

  const validateFileType = useCallback((file: File): boolean => {
    const extension = '.' + file.name.split('.').pop()?.toLowerCase();
    return acceptedFormats.includes(extension);
  }, [acceptedFormats]);

  const validateFileSize = useCallback((file: File): boolean => {
    return file.size <= maxFileSize;
  }, [maxFileSize]);

  const parseFlowFile = useCallback(async (file: File): Promise<Partial<FlowData>> => {
    const text = await file.text();
    const extension = file.name.split('.').pop()?.toLowerCase();

    if (extension === 'yaml' || extension === 'yml') {
      const { parse } = await import('yaml');
      return parse(text) as Partial<FlowData>;
    }

    return JSON.parse(text) as Partial<FlowData>;
  }, []);

  const processFile = useCallback(async (file: File): Promise<FlowData> => {
    if (!validateFileType(file)) {
      throw new Error(`Invalid file type. Accepted formats: ${acceptedFormats.join(', ')}`);
    }

    if (!validateFileSize(file)) {
      const maxMB = maxFileSize / (1024 * 1024);
      throw new Error(`File too large. Maximum size: ${maxMB}MB`);
    }

    setState((prev) => ({ ...prev, progress: 20 }));

    const flowData = await parseFlowFile(file);
    setState((prev) => ({ ...prev, progress: 50 }));

    if (validateFlow) {
      const validation = validateFlow(flowData);
      if (!validation.valid) {
        throw new Error(`Invalid flow: ${validation.errors?.join(', ')}`);
      }
    }

    setState((prev) => ({ ...prev, progress: 70 }));

    const importedFlow = await importFlow(JSON.stringify(flowData));
    setState((prev) => ({ ...prev, progress: 100 }));

    return importedFlow;
  }, [validateFileType, validateFileSize, parseFlowFile, validateFlow, importFlow, acceptedFormats, maxFileSize]);

  const uploadFile = useCallback(async (file: File): Promise<FlowData | null> => {
    setState({
      isUploading: true,
      progress: 0,
      fileName: file.name,
      error: null,
    });

    onUploadStart?.();

    try {
      const flow = await processFile(file);
      setState((prev) => ({
        ...prev,
        isUploading: false,
        progress: 100,
      }));

      success(`Flow "${flow.name}" imported successfully`);
      onUploadSuccess?.(flow);
      return flow;
    } catch (err) {
      const error = err instanceof Error ? err : new Error('Upload failed');
      setState((prev) => ({
        ...prev,
        isUploading: false,
        error,
      }));

      showError(error.message);
      onUploadError?.(error);
      return null;
    }
  }, [processFile, success, showError, onUploadStart, onUploadSuccess, onUploadError]);

  const uploadFiles = useCallback(async (files: FileList | File[]): Promise<FlowData[]> => {
    const results: FlowData[] = [];
    const fileArray = Array.from(files);

    for (const file of fileArray) {
      const flow = await uploadFile(file);
      if (flow) {
        results.push(flow);
      }
    }

    return results;
  }, [uploadFile]);

  const handleFileInputChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      uploadFiles(files);
    }
    if (event.target) {
      event.target.value = '';
    }
  }, [uploadFiles]);

  const openFilePicker = useCallback(() => {
    if (!fileInputRef.current) {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = acceptedFormats.join(',');
      input.multiple = true;
      input.style.display = 'none';
      input.addEventListener('change', (e) => {
        const target = e.target as HTMLInputElement;
        if (target.files && target.files.length > 0) {
          uploadFiles(target.files);
        }
        input.remove();
        fileInputRef.current = null;
      });
      document.body.appendChild(input);
      fileInputRef.current = input;
    }
    fileInputRef.current.click();
  }, [acceptedFormats, uploadFiles]);

  const handleDrop = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();

    const files = event.dataTransfer.files;
    if (files && files.length > 0) {
      uploadFiles(files);
    }
  }, [uploadFiles]);

  const handleDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.stopPropagation();
  }, []);

  const reset = useCallback(() => {
    setState({
      isUploading: false,
      progress: 0,
      fileName: null,
      error: null,
    });
  }, []);

  return {
    ...state,
    uploadFile,
    uploadFiles,
    openFilePicker,
    handleFileInputChange,
    handleDrop,
    handleDragOver,
    reset,
    acceptedFormats,
    maxFileSize,
  };
}

export default useUploadFlow;
