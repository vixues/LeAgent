import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useFlowsManagerStore } from '@/stores/flowsManagerStore';
import { useFlowStore } from '@/stores/flow';
import { useAlertStore } from '@/stores/alertStore';


export interface DeleteFlowOptions {
  confirmRequired?: boolean;
  onDeleteStart?: (flowId: string) => void;
  onDeleteSuccess?: (flowId: string) => void;
  onDeleteError?: (error: Error, flowId: string) => void;
  onDeleteCancelled?: (flowId: string) => void;
}

export interface DeleteConfirmation {
  flowId: string;
  flowName: string;
  isOpen: boolean;
}

export interface DeleteFlowState {
  isDeleting: boolean;
  deletingFlowIds: Set<string>;
  error: Error | null;
  confirmation: DeleteConfirmation | null;
}

export function useDeleteFlow(options: DeleteFlowOptions = {}) {
  const {
    confirmRequired = true,
    onDeleteStart,
    onDeleteSuccess,
    onDeleteError,
    onDeleteCancelled,
  } = options;

  const queryClient = useQueryClient();
  const { deleteFlow: deleteFlowFromStore, getFlowById, currentFlowId, setCurrentFlowId, flows } = useFlowsManagerStore();
  const { flowId: activeFlowId, resetFlow } = useFlowStore();
  const { success, error: showError, warning } = useAlertStore();

  const [state, setState] = useState<DeleteFlowState>({
    isDeleting: false,
    deletingFlowIds: new Set(),
    error: null,
    confirmation: null,
  });

  const mutation = useMutation({
    mutationFn: async (flowId: string) => {
      await deleteFlowFromStore(flowId);
      return flowId;
    },
    onMutate: (flowId) => {
      setState((prev) => ({
        ...prev,
        isDeleting: true,
        deletingFlowIds: new Set([...prev.deletingFlowIds, flowId]),
      }));
      onDeleteStart?.(flowId);
    },
    onSuccess: (flowId) => {
      setState((prev) => {
        const newDeletingIds = new Set(prev.deletingFlowIds);
        newDeletingIds.delete(flowId);
        return {
          ...prev,
          isDeleting: newDeletingIds.size > 0,
          deletingFlowIds: newDeletingIds,
          error: null,
        };
      });

      if (activeFlowId === flowId) {
        resetFlow();
      }

      if (currentFlowId === flowId) {
        const remainingFlows = flows.filter((f) => f.id !== flowId);
        setCurrentFlowId(remainingFlows.length > 0 ? remainingFlows[0]!.id : null);
      }

      queryClient.invalidateQueries({ queryKey: ['flows'] });
      queryClient.removeQueries({ queryKey: ['flow', flowId] });

      success('Flow deleted successfully');
      onDeleteSuccess?.(flowId);
    },
    onError: (err, flowId) => {
      const error = err instanceof Error ? err : new Error('Failed to delete flow');
      setState((prev) => {
        const newDeletingIds = new Set(prev.deletingFlowIds);
        newDeletingIds.delete(flowId);
        return {
          ...prev,
          isDeleting: newDeletingIds.size > 0,
          deletingFlowIds: newDeletingIds,
          error,
        };
      });

      showError(`Failed to delete flow: ${error.message}`);
      onDeleteError?.(error, flowId);
    },
  });

  const requestDelete = useCallback((flowId: string) => {
    const flow = getFlowById(flowId);
    if (!flow) {
      showError('Flow not found');
      return;
    }

    if (confirmRequired) {
      setState((prev) => ({
        ...prev,
        confirmation: {
          flowId,
          flowName: flow.name,
          isOpen: true,
        },
      }));
    } else {
      mutation.mutate(flowId);
    }
  }, [confirmRequired, getFlowById, mutation, showError]);

  const confirmDelete = useCallback(() => {
    const { confirmation } = state;
    if (confirmation) {
      setState((prev) => ({ ...prev, confirmation: null }));
      mutation.mutate(confirmation.flowId);
    }
  }, [state, mutation]);

  const cancelDelete = useCallback(() => {
    const { confirmation } = state;
    if (confirmation) {
      onDeleteCancelled?.(confirmation.flowId);
    }
    setState((prev) => ({ ...prev, confirmation: null }));
  }, [state, onDeleteCancelled]);

  const deleteFlowImmediate = useCallback(async (flowId: string) => {
    return mutation.mutateAsync(flowId);
  }, [mutation]);

  const deleteMultipleFlows = useCallback(async (flowIds: string[]) => {
    if (flowIds.length === 0) return;

    if (confirmRequired) {
      warning(`Are you sure you want to delete ${flowIds.length} flows?`);
    }

    const results = await Promise.allSettled(
      flowIds.map((id) => mutation.mutateAsync(id))
    );

    const succeeded = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.filter((r) => r.status === 'rejected').length;

    if (failed > 0) {
      warning(`Deleted ${succeeded} flows, ${failed} failed`);
    } else {
      success(`Deleted ${succeeded} flows`);
    }

    return results;
  }, [confirmRequired, mutation, warning, success]);

  const isFlowDeleting = useCallback((flowId: string) => {
    return state.deletingFlowIds.has(flowId);
  }, [state.deletingFlowIds]);

  return {
    ...state,
    requestDelete,
    confirmDelete,
    cancelDelete,
    deleteFlowImmediate,
    deleteMultipleFlows,
    isFlowDeleting,
  };
}

export default useDeleteFlow;
