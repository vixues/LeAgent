// Core API
export {
  api,
  setAuthTokens,
  clearAuthTokens,
  getAccessToken,
  performStreamingRequest,
  type ApiError,
  type StreamEvent,
  type StreamEventHandler,
  type StreamingRequestOptions,
} from './api';

// Helpers
export { URL_KEYS, QUERY_KEYS, CACHE_TIME, PAGINATION } from './helpers/constants';
export {
  checkDuplicateKey,
  registerQueryKey,
  unregisterQueryKey,
  clearQueryKeyRegistry,
  getAllRegisteredKeys,
  createUniqueQueryKey,
  type QueryKey,
  type QueryKeyRegistry,
} from './helpers/check-duplicate-key';

// Services
export {
  useRequestProcessor,
  createQueryFn,
  createMutationFn,
  type QueryOptions,
  type MutationOptions,
} from './services/request-processor';

// Flow Queries
export {
  useGetFlows,
  useGetFlow,
  usePostAddFlow,
  usePatchUpdateFlow,
  usePutUpdateFlow,
  useDeleteFlow,
  useDuplicateFlow,
  useValidateFlow,
  useExportFlow,
  useImportFlow,
  type FlowListParams,
  type FlowListResponse,
  type CreateFlowInput,
  type UpdateFlowInput,
  type DuplicateFlowInput,
  type ImportFlowInput,
} from './queries/flows';

// Message Queries
export {
  useGetMessagesQuery,
  useGetMessage,
  useSendMessage,
  useUpdateMessage,
  useDeleteMessage,
  useStreamMessage,
  addMessageToCache,
  updateMessageInCache,
  type MessageListParams,
  type MessageListResponse,
  type SendMessageInput,
  type UpdateMessageInput,
  type StreamMessageInput,
  type Message,
  type Attachment,
} from './queries/messages';
