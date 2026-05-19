"""Webhook event manager for outbound webhook delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, Field

from leagent.services.base import Service, ServiceType, service_factory
from leagent.services.event.manager import Event, EventType

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.services.cache.service import CacheService
    from leagent.services.event.manager import EventManager

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
MAX_RETRIES = 5
RETRY_DELAYS = [1, 5, 30, 120, 600]


class WebhookStatus(str, Enum):
    """Webhook delivery status."""

    PENDING = "pending"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DISABLED = "disabled"


class WebhookSubscription(BaseModel):
    """Webhook subscription configuration."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    url: str
    secret: str | None = None

    event_types: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)

    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    user_id: UUID | None = None
    flow_id: UUID | None = None

    max_retries: int = MAX_RETRIES
    timeout_seconds: int = DEFAULT_TIMEOUT

    metadata: dict[str, Any] = Field(default_factory=dict)


class WebhookDelivery(BaseModel):
    """Record of a webhook delivery attempt."""

    id: UUID = Field(default_factory=uuid4)
    subscription_id: UUID
    event_id: UUID
    event_type: str

    status: WebhookStatus = WebhookStatus.PENDING
    attempt: int = 0
    max_attempts: int = MAX_RETRIES

    request_url: str
    request_headers: dict[str, str] = Field(default_factory=dict)
    request_body: str = ""

    response_status: int | None = None
    response_body: str | None = None
    response_headers: dict[str, str] = Field(default_factory=dict)

    error: str | None = None
    duration_ms: int | None = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: datetime | None = None
    next_retry_at: datetime | None = None


class WebhookSubscriptionCreate(BaseModel):
    """Schema for creating a webhook subscription."""

    name: str
    url: str
    event_types: list[str]
    secret: str | None = None
    headers: dict[str, str] = Field(default_factory=dict)
    max_retries: int = MAX_RETRIES
    timeout_seconds: int = DEFAULT_TIMEOUT


class WebhookSubscriptionUpdate(BaseModel):
    """Schema for updating a webhook subscription."""

    name: str | None = None
    url: str | None = None
    event_types: list[str] | None = None
    headers: dict[str, str] | None = None
    is_active: bool | None = None
    max_retries: int | None = None
    timeout_seconds: int | None = None


@service_factory(ServiceType.WEBHOOK)
class WebhookEventManager(Service):
    """Webhook event manager for outbound webhook delivery.

    Features:
    - Webhook subscription management
    - Automatic event delivery
    - Signature verification (HMAC-SHA256)
    - Retry logic with exponential backoff
    - Delivery tracking and logging
    - Rate limiting
    """

    def __init__(
        self,
        settings: Settings,
        event_manager: EventManager | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        super().__init__(settings)
        self._event_manager = event_manager
        self._cache = cache_service
        self._subscriptions: dict[UUID, WebhookSubscription] = {}
        self._deliveries: dict[UUID, WebhookDelivery] = {}
        self._http_client: httpx.AsyncClient | None = None
        self._retry_queue: asyncio.Queue[WebhookDelivery] = asyncio.Queue()
        self._retry_task: asyncio.Task | None = None
        self._shutdown_event = asyncio.Event()
        self._stats = {
            "deliveries_attempted": 0,
            "deliveries_successful": 0,
            "deliveries_failed": 0,
            "retries": 0,
        }

    @property
    def name(self) -> str:
        return "WebhookEventManager"

    def set_dependencies(
        self,
        event_manager: EventManager | None = None,
        cache_service: CacheService | None = None,
    ) -> None:
        """Set service dependencies."""
        self._event_manager = event_manager
        self._cache = cache_service

    async def _do_start(self) -> None:
        """Initialize HTTP client and start retry worker."""
        # Do not inherit HTTP(S)_PROXY / ALL_PROXY from the environment: SOCKS URLs
        # (common with local VPN tools) are unsupported by httpx and raise at client init.
        self._http_client = httpx.AsyncClient(
            timeout=httpx.Timeout(DEFAULT_TIMEOUT),
            follow_redirects=True,
            trust_env=False,
        )

        self._retry_task = asyncio.create_task(self._retry_worker())

        if self._event_manager:
            self._event_manager.subscribe_all(self._handle_event)

        logger.info("WebhookEventManager started")

    async def _do_stop(self) -> None:
        """Shutdown HTTP client and retry worker."""
        self._shutdown_event.set()

        if self._retry_task:
            self._retry_task.cancel()
            try:
                await asyncio.wait_for(self._retry_task, timeout=5.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

        if self._http_client:
            await self._http_client.aclose()

    async def _do_health_check(self) -> dict[str, Any]:
        return {
            "subscriptions": len(self._subscriptions),
            "active_subscriptions": sum(1 for s in self._subscriptions.values() if s.is_active),
            "pending_retries": self._retry_queue.qsize(),
            "stats": self._stats.copy(),
        }

    def _compute_signature(
        self,
        payload: str,
        secret: str,
        timestamp: int,
    ) -> str:
        """Compute HMAC-SHA256 signature for webhook payload."""
        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    async def create_subscription(
        self,
        data: WebhookSubscriptionCreate,
        *,
        user_id: UUID | None = None,
        flow_id: UUID | None = None,
    ) -> WebhookSubscription:
        """Create a new webhook subscription.

        Args:
            data: Subscription configuration
            user_id: Owner user ID
            flow_id: Associated flow ID

        Returns:
            The created subscription
        """
        subscription = WebhookSubscription(
            name=data.name,
            url=data.url,
            secret=data.secret,
            event_types=data.event_types,
            headers=data.headers,
            max_retries=data.max_retries,
            timeout_seconds=data.timeout_seconds,
            user_id=user_id,
            flow_id=flow_id,
        )

        self._subscriptions[subscription.id] = subscription

        if self._cache:
            await self._cache.set(
                f"webhook:{subscription.id}",
                subscription.model_dump(mode="json"),
                namespace="webhooks",
            )

        logger.info("Created webhook subscription %s for %s", subscription.id, data.url)
        return subscription

    async def get_subscription(self, subscription_id: UUID) -> WebhookSubscription | None:
        """Get a webhook subscription by ID."""
        if subscription_id in self._subscriptions:
            return self._subscriptions[subscription_id]

        if self._cache:
            cached = await self._cache.get(f"webhook:{subscription_id}", namespace="webhooks")
            if cached:
                subscription = WebhookSubscription.model_validate(cached)
                self._subscriptions[subscription_id] = subscription
                return subscription

        return None

    async def update_subscription(
        self,
        subscription_id: UUID,
        data: WebhookSubscriptionUpdate,
    ) -> WebhookSubscription | None:
        """Update a webhook subscription."""
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            return None

        if data.name is not None:
            subscription.name = data.name
        if data.url is not None:
            subscription.url = data.url
        if data.event_types is not None:
            subscription.event_types = data.event_types
        if data.headers is not None:
            subscription.headers = data.headers
        if data.is_active is not None:
            subscription.is_active = data.is_active
        if data.max_retries is not None:
            subscription.max_retries = data.max_retries
        if data.timeout_seconds is not None:
            subscription.timeout_seconds = data.timeout_seconds

        subscription.updated_at = datetime.utcnow()
        self._subscriptions[subscription_id] = subscription

        if self._cache:
            await self._cache.set(
                f"webhook:{subscription_id}",
                subscription.model_dump(mode="json"),
                namespace="webhooks",
            )

        return subscription

    async def delete_subscription(self, subscription_id: UUID) -> bool:
        """Delete a webhook subscription."""
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]

            if self._cache:
                await self._cache.delete(f"webhook:{subscription_id}", namespace="webhooks")

            return True

        return False

    async def list_subscriptions(
        self,
        *,
        user_id: UUID | None = None,
        flow_id: UUID | None = None,
        active_only: bool = False,
    ) -> list[WebhookSubscription]:
        """List webhook subscriptions with optional filtering."""
        subscriptions = list(self._subscriptions.values())

        if user_id:
            subscriptions = [s for s in subscriptions if s.user_id == user_id]
        if flow_id:
            subscriptions = [s for s in subscriptions if s.flow_id == flow_id]
        if active_only:
            subscriptions = [s for s in subscriptions if s.is_active]

        return subscriptions

    async def _handle_event(self, event: Event) -> None:
        """Handle incoming events and dispatch to subscribed webhooks."""
        event_type = event.type.value if isinstance(event.type, EventType) else event.type

        for subscription in self._subscriptions.values():
            if not subscription.is_active:
                continue

            if subscription.event_types and event_type not in subscription.event_types:
                continue

            await self.deliver(subscription, event)

    async def deliver(
        self,
        subscription: WebhookSubscription,
        event: Event,
    ) -> WebhookDelivery:
        """Deliver an event to a webhook endpoint.

        Args:
            subscription: Target subscription
            event: Event to deliver

        Returns:
            Delivery record
        """
        payload = {
            "id": str(event.id),
            "type": event.type.value if isinstance(event.type, EventType) else event.type,
            "timestamp": event.timestamp.isoformat(),
            "source": event.source,
            "data": event.data,
            "metadata": event.metadata,
        }

        if event.correlation_id:
            payload["correlation_id"] = str(event.correlation_id)
        if event.user_id:
            payload["user_id"] = str(event.user_id)

        payload_json = json.dumps(payload)

        headers = {
            "Content-Type": "application/json",
            "User-Agent": f"LeAgent-Webhook/{self._settings.version}",
            "X-Webhook-ID": str(subscription.id),
            "X-Event-ID": str(event.id),
            "X-Event-Type": payload["type"],
            **subscription.headers,
        }

        if subscription.secret:
            timestamp = int(time.time())
            signature = self._compute_signature(payload_json, subscription.secret, timestamp)
            headers["X-Webhook-Signature"] = signature
            headers["X-Webhook-Timestamp"] = str(timestamp)

        delivery = WebhookDelivery(
            subscription_id=subscription.id,
            event_id=event.id,
            event_type=payload["type"],
            request_url=subscription.url,
            request_headers=headers,
            request_body=payload_json,
            max_attempts=subscription.max_retries,
        )

        self._deliveries[delivery.id] = delivery

        await self._attempt_delivery(delivery, subscription)

        return delivery

    async def _attempt_delivery(
        self,
        delivery: WebhookDelivery,
        subscription: WebhookSubscription,
    ) -> None:
        """Attempt to deliver a webhook."""
        if self._http_client is None:
            delivery.status = WebhookStatus.FAILED
            delivery.error = "HTTP client not initialized"
            return

        delivery.attempt += 1
        self._stats["deliveries_attempted"] += 1

        start_time = time.time()

        try:
            response = await self._http_client.post(
                delivery.request_url,
                content=delivery.request_body,
                headers=delivery.request_headers,
                timeout=subscription.timeout_seconds,
            )

            delivery.duration_ms = int((time.time() - start_time) * 1000)
            delivery.response_status = response.status_code
            delivery.response_headers = dict(response.headers)

            try:
                delivery.response_body = response.text[:10000]
            except Exception:
                pass

            if 200 <= response.status_code < 300:
                delivery.status = WebhookStatus.DELIVERED
                delivery.delivered_at = datetime.utcnow()
                self._stats["deliveries_successful"] += 1

                if self._event_manager:
                    await self._event_manager.emit_typed(
                        EventType.WEBHOOK_SENT,
                        "webhook_manager",
                        {
                            "subscription_id": str(subscription.id),
                            "event_id": str(delivery.event_id),
                            "status_code": response.status_code,
                        },
                    )

                logger.debug(
                    "Webhook delivered: %s -> %s (%dms)",
                    delivery.event_type,
                    subscription.url,
                    delivery.duration_ms,
                )
            else:
                await self._handle_delivery_failure(
                    delivery,
                    subscription,
                    f"HTTP {response.status_code}",
                )

        except httpx.TimeoutException:
            delivery.duration_ms = int((time.time() - start_time) * 1000)
            await self._handle_delivery_failure(delivery, subscription, "Request timeout")

        except Exception as e:
            delivery.duration_ms = int((time.time() - start_time) * 1000)
            await self._handle_delivery_failure(delivery, subscription, str(e))

    async def _handle_delivery_failure(
        self,
        delivery: WebhookDelivery,
        subscription: WebhookSubscription,
        error: str,
    ) -> None:
        """Handle a failed delivery attempt."""
        delivery.error = error

        if delivery.attempt < delivery.max_attempts:
            delivery.status = WebhookStatus.RETRYING
            delay_index = min(delivery.attempt - 1, len(RETRY_DELAYS) - 1)
            delay = RETRY_DELAYS[delay_index]
            delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)

            await self._retry_queue.put(delivery)
            self._stats["retries"] += 1

            logger.warning(
                "Webhook delivery failed, retry %d/%d in %ds: %s",
                delivery.attempt,
                delivery.max_attempts,
                delay,
                error,
            )
        else:
            delivery.status = WebhookStatus.FAILED
            self._stats["deliveries_failed"] += 1

            logger.error(
                "Webhook delivery permanently failed after %d attempts: %s",
                delivery.attempt,
                error,
            )

    async def _retry_worker(self) -> None:
        """Background worker for processing delivery retries."""
        while not self._shutdown_event.is_set():
            try:
                try:
                    delivery = await asyncio.wait_for(
                        self._retry_queue.get(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    continue

                if delivery.next_retry_at:
                    delay = (delivery.next_retry_at - datetime.utcnow()).total_seconds()
                    if delay > 0:
                        await asyncio.sleep(delay)

                subscription = await self.get_subscription(delivery.subscription_id)
                if subscription and subscription.is_active:
                    await self._attempt_delivery(delivery, subscription)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Retry worker error: %s", e)

    async def get_delivery(self, delivery_id: UUID) -> WebhookDelivery | None:
        """Get a delivery record by ID."""
        return self._deliveries.get(delivery_id)

    async def list_deliveries(
        self,
        *,
        subscription_id: UUID | None = None,
        status: WebhookStatus | None = None,
        limit: int = 100,
    ) -> list[WebhookDelivery]:
        """List delivery records with optional filtering."""
        deliveries = list(self._deliveries.values())

        if subscription_id:
            deliveries = [d for d in deliveries if d.subscription_id == subscription_id]
        if status:
            deliveries = [d for d in deliveries if d.status == status]

        deliveries.sort(key=lambda d: d.created_at, reverse=True)
        return deliveries[:limit]

    async def retry_delivery(self, delivery_id: UUID) -> bool:
        """Manually retry a failed delivery."""
        delivery = await self.get_delivery(delivery_id)
        if not delivery:
            return False

        if delivery.status != WebhookStatus.FAILED:
            return False

        subscription = await self.get_subscription(delivery.subscription_id)
        if not subscription:
            return False

        delivery.attempt = 0
        delivery.status = WebhookStatus.PENDING
        delivery.error = None

        await self._attempt_delivery(delivery, subscription)
        return True

    async def test_subscription(
        self,
        subscription_id: UUID,
    ) -> WebhookDelivery:
        """Send a test event to a webhook subscription."""
        subscription = await self.get_subscription(subscription_id)
        if not subscription:
            raise ValueError(f"Subscription {subscription_id} not found")

        test_event = Event(
            type="test.ping",
            source="webhook_manager",
            data={
                "message": "This is a test webhook delivery",
                "subscription_id": str(subscription_id),
            },
        )

        return await self.deliver(subscription, test_event)

    def get_stats(self) -> dict[str, Any]:
        """Get webhook manager statistics."""
        return {
            **self._stats,
            "subscriptions": len(self._subscriptions),
            "pending_deliveries": sum(
                1 for d in self._deliveries.values() if d.status == WebhookStatus.PENDING
            ),
            "failed_deliveries": sum(
                1 for d in self._deliveries.values() if d.status == WebhookStatus.FAILED
            ),
        }


_webhook_manager: WebhookEventManager | None = None


def get_webhook_manager() -> WebhookEventManager:
    """Get the global webhook manager instance."""
    if _webhook_manager is None:
        raise RuntimeError("WebhookEventManager not initialized")
    return _webhook_manager


async def init_webhook_manager(
    settings: Settings,
    event_manager: EventManager | None = None,
    cache_service: CacheService | None = None,
) -> WebhookEventManager:
    """Initialize and start the global webhook manager."""
    global _webhook_manager
    _webhook_manager = WebhookEventManager(settings, event_manager, cache_service)
    await _webhook_manager.start()
    return _webhook_manager
