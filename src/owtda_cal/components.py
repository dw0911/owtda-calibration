"""Component registry definitions (Plan §15.3, B14).

A component entry binds ``(component_kind, stable_id, component_generation_id)``
to a strict ``config_hash`` and the ``file_manifest_hash`` of the exact source
files implementing it.  Run-level parameters (``rho``, ``W/s/T/M``) are *not*
part of a component config: they belong to the run configuration, which is why
``rho`` is deliberately excluded from the data-generator config below.
"""

from __future__ import annotations

from typing import Any

from . import dgp
from .calibrate import M0_STABLE_ID, M1_STABLE_ID
from .features import (
    BPI_STABLE_ID,
    MOMENTS_STABLE_ID,
    bpi_feature_spec,
    feature_config_hash,
    moments_feature_spec,
)
from .identity import config_hash

COMPONENT_KINDS = ("data", "feature", "method")

DATA_STABLE_N_AR = "SYNTHETIC_N_AR_V1"
DATA_STABLE_N_CIRCLE = "SYNTHETIC_N_CIRCLE_V1"


def data_generator_spec(family: str) -> dict[str, Any]:
    """Run-parameter-free generator config (``rho`` lives in the run config)."""
    if family == dgp.DGP_FAMILY_N_AR:
        return {
            "schema_version": 1,
            "config_kind": "data_generator",
            "stable_id": DATA_STABLE_N_AR,
            "generator_version": dgp.N_AR_VERSION,
            "distribution": "gaussian_ar1",
            "unit": "unitless",
            "rho_role": "run_parameter",
        }
    if family == dgp.DGP_FAMILY_N_CIRCLE:
        return {
            "schema_version": 1,
            "config_kind": "data_generator",
            "stable_id": DATA_STABLE_N_CIRCLE,
            "generator_version": dgp.N_CIRCLE_VERSION,
            "distribution": "circle_random_walk",
            "unit": "unitless",
            "rho_role": "run_parameter",
        }
    raise ValueError(f"unknown DGP family {family!r}")


def data_generator_config_hash(family: str) -> str:
    return config_hash("data_generator", 1, data_generator_spec(family))


def method_spec(stable_id: str) -> dict[str, Any]:
    common = {
        "schema_version": 1,
        "config_kind": "method",
        "stable_id": stable_id,
        "B": 999,
        "p_value_rule": "(1+exceed)/(B+1)",
        "reject_rule": "p<=0.05",
    }
    if stable_id == M0_STABLE_ID:
        return {**common, "resample": "naive_permutation", "index_space": "window_index_1_to_M"}
    if stable_id == M1_STABLE_ID:
        return {
            **common,
            "resample": "dmb_triangular_multiplier",
            "b_rule": "max(floor(W/s)+1,ceil(M**(1/3)))",
            "covariance": "triangular_kernel_extended_iid",
        }
    raise ValueError(f"unknown method stable_id {stable_id!r}")


def method_config_hash(stable_id: str) -> str:
    return config_hash("method", 1, method_spec(stable_id))


def component_definitions() -> list[dict[str, Any]]:
    """The frozen synthetic component set (data / feature / method).

    ``code_files`` must cover every source file the component's numerics depend
    on (B15b completeness fix: the resampler's statistic/scan and the RNG/ID
    helpers were missing from the original manifests).
    """
    identity_core = ["src/owtda_cal/canonical.py", "src/owtda_cal/identity.py"]
    return [
        {
            "component_kind": "data",
            "stable_id": DATA_STABLE_N_AR,
            "config_hash": data_generator_config_hash(dgp.DGP_FAMILY_N_AR),
            "code_files": [
                "src/owtda_cal/dgp.py",
                "src/owtda_cal/seeding.py",
                *identity_core,
            ],
        },
        {
            "component_kind": "data",
            "stable_id": DATA_STABLE_N_CIRCLE,
            "config_hash": data_generator_config_hash(dgp.DGP_FAMILY_N_CIRCLE),
            "code_files": [
                "src/owtda_cal/dgp.py",
                "src/owtda_cal/seeding.py",
                *identity_core,
            ],
        },
        {
            "component_kind": "feature",
            "stable_id": BPI_STABLE_ID,
            "config_hash": feature_config_hash(bpi_feature_spec()),
            "code_files": [
                "src/owtda_cal/features.py",
                "src/owtda_cal/bpi.py",
                "src/owtda_cal/ph.py",
                "src/owtda_cal/pointcloud.py",
                "src/owtda_cal/hashing.py",
                *identity_core,
            ],
        },
        {
            "component_kind": "feature",
            "stable_id": MOMENTS_STABLE_ID,
            "config_hash": feature_config_hash(moments_feature_spec()),
            "code_files": [
                "src/owtda_cal/features.py",
                "src/owtda_cal/moments.py",
                "src/owtda_cal/pointcloud.py",
                "src/owtda_cal/hashing.py",
                *identity_core,
            ],
        },
        {
            "component_kind": "method",
            "stable_id": M0_STABLE_ID,
            "config_hash": method_config_hash(M0_STABLE_ID),
            "code_files": [
                "src/owtda_cal/calibrate.py",
                "src/owtda_cal/scan.py",
                "src/owtda_cal/seeding.py",
                *identity_core,
            ],
        },
        {
            "component_kind": "method",
            "stable_id": M1_STABLE_ID,
            "config_hash": method_config_hash(M1_STABLE_ID),
            "code_files": [
                "src/owtda_cal/calibrate.py",
                "src/owtda_cal/scan.py",
                "src/owtda_cal/seeding.py",
                *identity_core,
            ],
        },
    ]


__all__ = [
    "COMPONENT_KINDS",
    "DATA_STABLE_N_AR",
    "DATA_STABLE_N_CIRCLE",
    "data_generator_spec",
    "data_generator_config_hash",
    "method_spec",
    "method_config_hash",
    "component_definitions",
]
