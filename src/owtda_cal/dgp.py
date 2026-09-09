"""Synthetic DGP generators (Plan §7, §15.2-§15.4).

Implements H0 NULL master generation for N-AR and N-CIRCLE:

  * latent innovations always span t=-999..12288 (shape ``[13288]``) and their
    ``innovation_hash`` is computed over the full float64 array;
  * a stationary initial value is drawn at t=-1000 from its own stream and the
    first 1,000 values are discarded (burn-in), leaving the formal series
    X_1..X_12288;
  * N-CIRCLE draws one shared observation-noise master (``[12288,2]``);
  * innovation streams are rho-free, so two rho levels of the same replicate
    share the base innovations while producing different raw series.

All draws go through ``make_rng(root_key_hex, stream_kind, **fields)`` with the
exact consumption shapes of Plan §15.2/§15.4.  No formal data are persisted by
this module; it only builds arrays and identities for later pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
from scipy.special import ndtr

from . import hashing
from .canonical import canonical_decimal_text
from .cells import L_LATENT, L_MASTER

Family = Literal["N_AR", "N_CIRCLE"]
DGP_FAMILY_N_AR = "N_AR"
DGP_FAMILY_N_CIRCLE = "N_CIRCLE"

N_AR_VERSION = "N_AR_V1"
N_CIRCLE_VERSION = "N_CIRCLE_V1"

BURN_IN = 1000
NOISE_SCALE_N_CIRCLE = "0.08"
ROTATION = "I2"


def n_ar_data_model_spec(rho: str | float) -> dict:
    """Canonical data-model config for N-AR (rho enters the hash)."""
    return {
        "schema_version": 1,
        "config_kind": "data_model",
        "family": DGP_FAMILY_N_AR,
        "generator_version": N_AR_VERSION,
        "latent_law": "stationary_gaussian_ar1",
        "initial_index": -1000,
        "discarded_indices": "-999..0",
        "rho": canonical_decimal_text(rho),
        "innovation_law": "iid_N0_1",
        "unit": "dimensionless",
    }


def n_circle_data_model_spec(rho: str | float) -> dict:
    return {
        "schema_version": 1,
        "config_kind": "data_model",
        "family": DGP_FAMILY_N_CIRCLE,
        "generator_version": N_CIRCLE_VERSION,
        "latent_law": "stationary_gaussian_ar1_then_scipy_ndtr_float64",
        "initial_index": -1000,
        "discarded_indices": "-999..0",
        "rho": canonical_decimal_text(rho),
        "observation_noise": "iid_N2_0_I2_times_0.08",
        "rotation": ROTATION,
        "unit": "dimensionless",
    }


def data_model_config_hash(spec: dict) -> str:
    from .identity import config_hash

    return config_hash("data_model", spec["schema_version"], spec)


def _ar1_states(rho: float, initial: float, innovations: np.ndarray) -> np.ndarray:
    """Recur states X_-1000..X_12288 (len L_LATENT+1)."""
    states = np.empty(L_LATENT + 1, dtype=np.float64)
    states[0] = initial
    sigma = np.sqrt(1.0 - rho * rho)
    for i in range(L_LATENT):
        states[i + 1] = rho * states[i] + sigma * innovations[i]
    return states


def _formal_prefix(states: np.ndarray, T: int) -> np.ndarray:
    """X_1..X_T from a state array whose index i maps to t = i-1000."""
    return states[BURN_IN + 1 : BURN_IN + 1 + T].copy()


def _raw_for_window_cell(prefix_1d: np.ndarray) -> np.ndarray:
    """N-AR raw series per cell is [T,1] (univariate)."""
    return prefix_1d.reshape(-1, 1)


@dataclass(frozen=True)
class NullMaster:
    """H0 NULL synthetic master path (one replicate)."""

    family: Family
    rho_text: str
    data_generation_id: str
    DGP_family: str
    master_replicate_id: str
    initial_value: float
    innovations: np.ndarray  # float64 [13288]
    noise: np.ndarray | None  # N-CIRCLE only: float64 [12288,2]
    # latent (copula) states X_-1000..X_12288 for N-AR / G for N-CIRCLE
    latent_states: np.ndarray
    # formal observation path X_1..X_12288 for the rho level
    formal_path: np.ndarray
    innovation_hash: str
    noise_hash: str | None

    def raw_prefix(self, T: int) -> np.ndarray:
        """Raw series X_1..X_T for a cell, reshaped to [T,d]."""
        if self.family == DGP_FAMILY_N_AR:
            return _raw_for_window_cell(_formal_prefix(self.latent_states, T))
        if T > self.formal_path.shape[0]:
            raise ValueError(f"T={T} exceeds master length {self.formal_path.shape[0]}")
        return self.formal_path[:T]

    def raw_prefix_1d(self, T: int) -> np.ndarray:
        return self.latent_states[BURN_IN + 1 : BURN_IN + 1 + T].copy()

    def raw_series_hash(self, T: int) -> str:
        raw = self.raw_prefix(T)
        return hashing.array_hash("synthetic_raw_series_v1", raw, dtype_code=">f8")


def generate_null_master(
    *,
    family: Family,
    rho: str | float,
    root_key_hex: str,
    data_generation_id: str,
    master_replicate_id: str,
) -> NullMaster:
    """Generate one H0 NULL master path for the given family/rho/replicate."""
    from .seeding import make_rng

    rho_text = canonical_decimal_text(rho)
    if family not in (DGP_FAMILY_N_AR, DGP_FAMILY_N_CIRCLE):
        raise ValueError(f"unknown family {family!r}")
    base_fields = {
        "data_generation_id": data_generation_id,
        "DGP_family": family,
        "master_replicate_id": master_replicate_id,
    }

    initial = make_rng(root_key_hex, "null_initial", **base_fields).standard_normal()
    innovations = make_rng(root_key_hex, "null_innovation", **base_fields).standard_normal(
        L_LATENT
    )
    rho_f = float(rho_text)

    noise = None
    noise_hash = None
    if family == DGP_FAMILY_N_CIRCLE:
        noise = (
            make_rng(root_key_hex, "null_observation_noise", **base_fields)
            .standard_normal(size=(L_MASTER, 2))
            .astype(np.float64, order="C", copy=False)
        )
        noise_hash = hashing.array_hash(
            "synthetic_observation_noise_v1", noise, dtype_code=">f8"
        )

    latent = _ar1_states(rho_f, float(initial), innovations)
    g_formal = _formal_prefix(latent, L_MASTER)
    if family == DGP_FAMILY_N_AR:
        formal_path = g_formal
    else:
        u = ndtr(g_formal)  # scipy.special.ndtr, float64 elementwise
        c = np.cos(2.0 * np.pi * u)
        s = np.sin(2.0 * np.pi * u)
        formal_path = np.column_stack([c, s]) + 0.08 * noise

    innovation_hash = hashing.array_hash(
        "synthetic_latent_innovation_v1", innovations, dtype_code=">f8"
    )
    return NullMaster(
        family=family,
        rho_text=rho_text,
        data_generation_id=data_generation_id,
        DGP_family=family,
        master_replicate_id=master_replicate_id,
        initial_value=float(initial),
        innovations=innovations,
        noise=noise,
        latent_states=latent,
        formal_path=formal_path,
        innovation_hash=innovation_hash,
        noise_hash=noise_hash,
    )


def delay_embedding_3(raw_window: np.ndarray) -> np.ndarray:
    """Window-local (x_t, x_{t+3}, x_{t+6}) embedding, t=1..W-6 (Plan §5.1).

    ``raw_window`` is a 1-D float64 array of length W.  Returns shape
    ``(W-6, 3)`` in C order.
    """
    w = np.asarray(raw_window, dtype=np.float64)
    if w.ndim != 1:
        raise ValueError("delay_embedding_3 expects a 1-D window array")
    if w.shape[0] < 7:
        raise ValueError(f"window too short for d=3, tau=3: len={w.shape[0]}")
    n = w.shape[0] - 6
    return np.column_stack([w[k : k + n] for k in (0, 3, 6)])


__all__ = [
    "Family",
    "DGP_FAMILY_N_AR",
    "DGP_FAMILY_N_CIRCLE",
    "N_AR_VERSION",
    "N_CIRCLE_VERSION",
    "BURN_IN",
    "NOISE_SCALE_N_CIRCLE",
    "ROTATION",
    "n_ar_data_model_spec",
    "n_circle_data_model_spec",
    "data_model_config_hash",
    "NullMaster",
    "generate_null_master",
    "delay_embedding_3",
]
