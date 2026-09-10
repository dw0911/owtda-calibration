"""Isolated smoke identity domain (Plan §16, ``smoke_*`` ID block).

Plan §16: *"smoke 使用完全独立的身份域，禁止借用 formal logical IDs"*.  Every
smoke artefact -- ledger identity columns, expected/active indexes, seals -- must
be written with the ``smoke_*`` IDs defined here; a validator must reject any
formal logical/concrete ID leaking into smoke, and no smoke artefact may become
an upstream input of a formal phase.

The ``smoke_generation_id`` enters every one of these IDs, so bumping the smoke
generation (``S01`` -> ``S02``, Plan §9.3 umbrella rule) re-keys the whole smoke
namespace without touching any formal identity.
"""

from __future__ import annotations

from .canonical import canonical_decimal_text
from .identity import H

SMOKE_STREAM_FAMILY = "smoke"
SMOKE_ID_PREFIX = "smoke_"


def smoke_master_replicate_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    smoke_generation_id: str,
    phase: str,
    DGP_family: str,
    replicate_id: int,
) -> str:
    return H(
        "smoke_master_replicate",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        smoke_generation_id=smoke_generation_id,
        phase=phase,
        DGP_family=DGP_family,
        replicate_id=replicate_id,
    )


def smoke_physical_cell_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    smoke_generation_id: str,
    phase: str,
    DGP_family: str,
    rho: str | float,
    W: int,
    stride: int,
    T: int,
    M: int,
    data_model_config_hash: str,
) -> str:
    return H(
        "smoke_physical_cell",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        smoke_generation_id=smoke_generation_id,
        phase=phase,
        DGP_family=DGP_family,
        rho=canonical_decimal_text(rho),
        W=W,
        stride=stride,
        T=T,
        M=M,
        data_model_config_hash=data_model_config_hash,
    )


def smoke_base_series_id(
    *,
    smoke_master_replicate_id: str,
    smoke_generation_id: str,
    rho: str | float,
    raw_length: int,
    data_model_config_hash: str,
) -> str:
    return H(
        "smoke_base_series",
        smoke_master_replicate_id=smoke_master_replicate_id,
        smoke_generation_id=smoke_generation_id,
        rho=canonical_decimal_text(rho),
        raw_length=raw_length,
        data_model_config_hash=data_model_config_hash,
    )


def smoke_data_unit_id(
    *,
    smoke_base_series_id: str,
    smoke_physical_cell_id: str,
    smoke_generation_id: str,
) -> str:
    return H(
        "smoke_data_unit",
        smoke_base_series_id=smoke_base_series_id,
        smoke_physical_cell_id=smoke_physical_cell_id,
        smoke_generation_id=smoke_generation_id,
    )


def smoke_feature_sufficient_id(
    *,
    smoke_generation_id: str,
    smoke_data_unit_id: str,
    feature_id: str,
    feature_config_hash: str,
) -> str:
    return H(
        "smoke_feature_sufficient",
        smoke_generation_id=smoke_generation_id,
        smoke_data_unit_id=smoke_data_unit_id,
        feature_id=feature_id,
        feature_config_hash=feature_config_hash,
    )


def smoke_resampling_stream_id(
    *,
    smoke_generation_id: str,
    smoke_data_unit_id: str,
    method_random_family: str,
) -> str:
    return H(
        "smoke_resampling_stream",
        smoke_generation_id=smoke_generation_id,
        smoke_data_unit_id=smoke_data_unit_id,
        method_random_family=method_random_family,
    )


def smoke_evaluation_id(
    *,
    smoke_generation_id: str,
    smoke_data_unit_id: str,
    smoke_feature_sufficient_id: str,
    method_id: str,
    method_config_hash: str,
) -> str:
    return H(
        "smoke_evaluation",
        smoke_generation_id=smoke_generation_id,
        smoke_data_unit_id=smoke_data_unit_id,
        smoke_feature_sufficient_id=smoke_feature_sufficient_id,
        method_id=method_id,
        method_config_hash=method_config_hash,
    )


def smoke_experiment_id(
    *,
    project_id: str,
    protocol_id: str,
    freeze_id: str,
    evidence_generation_id: str,
    smoke_generation_id: str,
    phase: str,
) -> str:
    return H(
        "smoke_experiment",
        project_id=project_id,
        protocol_id=protocol_id,
        freeze_id=freeze_id,
        evidence_generation_id=evidence_generation_id,
        smoke_generation_id=smoke_generation_id,
        phase=phase,
    )


def smoke_logical_cell_id(
    *,
    smoke_experiment_id: str,
    smoke_generation_id: str,
    DGP_family: str,
    scenario_id: str,
    rho: str | float,
    W: int,
    stride: int,
    T: int,
    M: int,
) -> str:
    return H(
        "smoke_logical_cell",
        smoke_experiment_id=smoke_experiment_id,
        smoke_generation_id=smoke_generation_id,
        DGP_family=DGP_family,
        scenario_id=scenario_id,
        rho=canonical_decimal_text(rho),
        W=W,
        stride=stride,
        T=T,
        M=M,
    )


def smoke_logical_data_key(
    *,
    smoke_generation_id: str,
    smoke_logical_cell_id: str,
    smoke_master_replicate_id: str,
) -> str:
    return H(
        "smoke_logical_data",
        smoke_generation_id=smoke_generation_id,
        smoke_logical_cell_id=smoke_logical_cell_id,
        smoke_master_replicate_id=smoke_master_replicate_id,
    )


def smoke_logical_feature_key(
    *,
    smoke_generation_id: str,
    smoke_logical_data_key: str,
    feature_id: str,
) -> str:
    return H(
        "smoke_logical_feature",
        smoke_generation_id=smoke_generation_id,
        smoke_logical_data_key=smoke_logical_data_key,
        feature_id=feature_id,
    )


def smoke_logical_evaluation_key(
    *,
    smoke_generation_id: str,
    smoke_logical_data_key: str,
    feature_id: str,
    method_id: str,
) -> str:
    return H(
        "smoke_logical_evaluation",
        smoke_generation_id=smoke_generation_id,
        smoke_logical_data_key=smoke_logical_data_key,
        feature_id=feature_id,
        method_id=method_id,
    )


def smoke_method_stream_fields(
    *,
    smoke_generation_id: str,
    phase: str,
    smoke_data_unit_id: str,
) -> dict[str, str]:
    """Exact named fields of ``smoke_M0_permutation``/``smoke_M1_gaussian_innovation``.

    Plan §15.2 lists ``{smoke_generation_id, phase, smoke_data_unit_id,
    resample_index}``; the caller adds ``resample_index``.
    """
    return {
        "smoke_generation_id": smoke_generation_id,
        "phase": phase,
        "smoke_data_unit_id": smoke_data_unit_id,
    }


def smoke_data_stream_fields(
    *,
    smoke_generation_id: str,
    phase: str,
    DGP_family: str,
    replicate_id: int,
) -> dict[str, object]:
    """Exact named fields of the ``smoke_*`` data streams (Plan §15.2)."""
    return {
        "smoke_generation_id": smoke_generation_id,
        "phase": phase,
        "DGP_family": DGP_family,
        "replicate_id": replicate_id,
    }


__all__ = [
    "SMOKE_STREAM_FAMILY",
    "SMOKE_ID_PREFIX",
    "smoke_master_replicate_id",
    "smoke_physical_cell_id",
    "smoke_base_series_id",
    "smoke_data_unit_id",
    "smoke_feature_sufficient_id",
    "smoke_resampling_stream_id",
    "smoke_evaluation_id",
    "smoke_experiment_id",
    "smoke_logical_cell_id",
    "smoke_logical_data_key",
    "smoke_logical_feature_key",
    "smoke_logical_evaluation_key",
    "smoke_method_stream_fields",
    "smoke_data_stream_fields",
]
