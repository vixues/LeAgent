"""Tests for the provider-performance store and its CapabilityRouter bias.

The store (``leagent.llm.capabilities.provider_stats``) records live generation
outcomes (success/failure, latency, perceptual quality) and the router uses the
derived reliability score as a *secondary* sort key within a cost tier — a
lightweight in-process bandit for production self-optimization.
"""

from __future__ import annotations

from leagent.llm.capabilities import (
    BackendClass,
    CapabilityContract,
    CapabilityProfile,
    CapabilityRegistry,
    CapabilityRouter,
    Modality,
    TaskType,
)
from leagent.llm.capabilities.provider_stats import (
    NEUTRAL_SCORE,
    ProviderStat,
    ProviderStatsStore,
    get_provider_stats,
    reset_provider_stats,
)


def _img_profile(provider: str, *, cost: int):
    return CapabilityProfile(
        id=f"gen:{provider}",
        provider=provider,
        backend_class=BackendClass.DEDICATED_IMAGE,
        inputs={Modality.TEXT},
        outputs={Modality.IMAGE},
        tasks={TaskType.IMAGE_GEN},
        cost_tier=cost,
        availability=(lambda: True),
    )


# ---------------------------------------------------------------------------
# ProviderStat / ProviderStatsStore
# ---------------------------------------------------------------------------


def test_unobserved_provider_is_neutral():
    store = ProviderStatsStore()
    assert store.reliability("image_gen", "nobody") == NEUTRAL_SCORE
    assert store.get("image_gen", "nobody") is None


def test_success_rate_and_latency():
    stat = ProviderStat()
    assert stat.success_rate == 1.0  # no attempts → optimistic
    stat.successes = 3
    stat.failures = 1
    stat.total_latency_ms = 300.0
    assert stat.success_rate == 0.75
    assert stat.avg_latency_ms == 100.0  # latency averaged over successes


def test_record_attempt_updates_reliability():
    store = ProviderStatsStore()
    store.record_attempt("image_gen", "good", success=True, latency_ms=50)
    store.record_attempt("image_gen", "good", success=True, latency_ms=70)
    store.record_attempt("image_gen", "bad", success=False)
    store.record_attempt("image_gen", "bad", success=True)

    assert store.reliability("image_gen", "good") == 1.0
    assert store.reliability("image_gen", "bad") == 0.5  # 1/2 success, no quality


def test_quality_blends_into_reliability():
    store = ProviderStatsStore()
    store.record_attempt("image_gen", "p", success=True)
    # Pure success rate before quality is observed.
    assert store.reliability("image_gen", "p") == 1.0
    store.record_quality("image_gen", "p", 0.4)
    # 0.5 * success_rate(1.0) + 0.5 * quality(0.4) = 0.7
    assert abs(store.reliability("image_gen", "p") - 0.7) < 1e-9


def test_record_quality_is_robust_to_bad_input():
    store = ProviderStatsStore()
    store.record_quality("image_gen", "p", float("nan"))  # NaN clamps within 0..1 -> still folded
    store.record_quality("image_gen", "p", "not-a-number")  # type: ignore[arg-type]
    # The bogus string is ignored; reliability stays well-defined.
    assert 0.0 <= store.reliability("image_gen", "p") <= 1.0


def test_snapshot_and_clear():
    store = ProviderStatsStore()
    store.record_attempt("image_gen", "p", success=True, latency_ms=10)
    snap = store.snapshot()
    assert "image_gen:p" in snap
    assert snap["image_gen:p"]["successes"] == 1
    store.clear()
    assert store.snapshot() == {}


def test_global_store_singleton_and_reset():
    a = get_provider_stats()
    b = get_provider_stats()
    assert a is b
    a.record_attempt("image_gen", "p", success=True)
    reset_provider_stats()
    assert get_provider_stats().reliability("image_gen", "p") == NEUTRAL_SCORE


# ---------------------------------------------------------------------------
# Router bias
# ---------------------------------------------------------------------------


def test_router_bias_reorders_within_cost_tier():
    reg = CapabilityRegistry()
    # Same cost tier → without stats, registration order (a, b) holds.
    reg.register(_img_profile("alpha", cost=2))
    reg.register(_img_profile("beta", cost=2))
    store = ProviderStatsStore()
    router = CapabilityRouter(reg, stats=store)
    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})

    assert [p.provider for p in router.candidates(contract)] == ["alpha", "beta"]

    # beta proves more reliable on live traffic → it should now rank first.
    store.record_attempt("image_gen", "beta", success=True)
    store.record_attempt("image_gen", "alpha", success=False)
    assert [p.provider for p in router.candidates(contract)] == ["beta", "alpha"]


def test_router_bias_never_crosses_cost_tier():
    reg = CapabilityRegistry()
    reg.register(_img_profile("cheap", cost=1))
    reg.register(_img_profile("pricey", cost=3))
    store = ProviderStatsStore()
    router = CapabilityRouter(reg, stats=store)
    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})

    # Even a flawless expensive provider must not jump ahead of the cheaper tier.
    store.record_attempt("image_gen", "pricey", success=True)
    store.record_quality("image_gen", "pricey", 1.0)
    store.record_attempt("image_gen", "cheap", success=False)
    assert [p.provider for p in router.candidates(contract)] == ["cheap", "pricey"]
