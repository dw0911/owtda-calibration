"""The formal concrete-identity derivations (task pack §9 step 5 prerequisite).

Building the formal expected plan needs the concrete identities of a data unit,
a feature-sufficient row and an evaluation row.  Until now only the **smoke**
namespace had those derivations (``smoke_ids.smoke_feature_sufficient_id`` /
``smoke_evaluation_id``); the formal domain had ``cells`` (master replicate,
physical cell, base series, data unit) and ``scope`` (logical keys) but nothing
for feature-sufficient / evaluation.  Without them the plan cannot be expanded
for 82,800 / 165,600 / 331,200 rows at all -- and borrowing the smoke functions
is forbidden (Plan §16: the two namespaces must not be mixed).

This module adds the missing formal derivations with the *formal* domain-separated
kinds, mirroring the smoke structure field for field so the two can be compared:

    master_replicate -> base_series -> data_unit -> feature_sufficient
                                                 -> evaluation

**Governance note:** this is a contract addition.  It defines new identity kinds,
so it must be registered (and reflected in the freeze) before any formal run may
use it; it is deliberately *not* referenced by ``scope``, ``smoke`` or any runner
yet.  ``cells.master_replicate_id`` / ``physical_cell_id`` / ``base_series_id`` /
``data_unit_id`` and ``scope.logical_*`` are reused unchanged -- only the missing
tail of the chain is added here.
"""

from __future__ import annotations

from .canonical import canonical_decimal_text
from .identity import H

FEATURE_SUFFICIENT_KIND = "synthetic_feature_sufficient"
EVALUATION_KIND = "synthetic_evaluation"
RESAMPLING_STREAM_KIND = "synthetic_resampling_stream"


def feature_sufficient_id(
    *,
    data_generation_id: str,
    data_unit_id: str,
    feature_id: str,
    feature_config_hash: str,
) -> str:
    """``H("synthetic_feature_sufficient", ...)`` -- formal counterpart of the smoke id."""
    return H(
        FEATURE_SUFFICIENT_KIND,
        data_generation_id=data_generation_id,
        data_unit_id=data_unit_id,
        feature_id=feature_id,
        feature_config_hash=feature_config_hash,
    )


def evaluation_id(
    *,
    data_generation_id: str,
    data_unit_id: str,
    feature_sufficient_id: str,
    method_id: str,
    method_config_hash: str,
) -> str:
    """``H("synthetic_evaluation", ...)`` -- one concrete evaluation."""
    return H(
        EVALUATION_KIND,
        data_generation_id=data_generation_id,
        data_unit_id=data_unit_id,
        feature_sufficient_id=feature_sufficient_id,
        method_id=method_id,
        method_config_hash=method_config_hash,
    )


def resampling_stream_id(
    *,
    data_generation_id: str,
    data_unit_id: str,
    method_random_family: str,
) -> str:
    """The formal resampling stream identity for one data unit and method family."""
    return H(
        RESAMPLING_STREAM_KIND,
        data_generation_id=data_generation_id,
        data_unit_id=data_unit_id,
        method_random_family=method_random_family,
    )


def rho_text(rho: str | float) -> str:
    """The canonical decimal spelling of a rho level (kept next to the ids)."""
    return canonical_decimal_text(rho)


__all__ = [
    "EVALUATION_KIND",
    "FEATURE_SUFFICIENT_KIND",
    "RESAMPLING_STREAM_KIND",
    "evaluation_id",
    "feature_sufficient_id",
    "resampling_stream_id",
    "rho_text",
]
