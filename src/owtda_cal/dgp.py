"""Synthetic DGP generators (Plan §7, §12.1-§12.2, §15.2-§15.4).

Implements

  * H0 NULL master generation for N-AR and N-CIRCLE, and
  * the two ``CIRCLE_BASED_H1`` alternatives (shape change / mean shift).

Shared latent contract:

  * latent innovations always span t=-999..12288 (shape ``[13288]``) and their
    ``innovation_hash`` is computed over the full float64 array;
  * a stationary initial value is drawn at t=-1000 from its own stream and the
    first 1,000 values are discarded (burn-in), leaving the formal series
    X_1..X_12288;
  * N-CIRCLE (and H1) draw one shared observation-noise master (``[12288,2]``);
  * innovation streams are rho-free, so two rho levels of the same replicate
    share the base innovations while producing different raw series.

H1 (Plan §12.1/§12.2): the latent AR/copula path ``U_t`` and the observation
noise ``eta_t`` are *continuous across* the change point; only the deterministic
skeleton changes at ``tau = floor(T/2)``:

  * shape change: ``C(u)=(cos 2pi u, sin 2pi u)`` before ``tau`` and
    ``F(u)=(sin 2pi u, sin 4pi u)`` after it (circle vs figure-eight);
  * mean shift: ``C(U_t) + delta*v*1(t>tau)`` with ``delta=0.5`` and ``v`` on
    the unit circle, drawn once per replicate from the dedicated
    ``shift_direction`` stream and shared by every derived cell.

Both sides have identical pointwise mean and covariance; no second-order
process-matching claim is made.  Every H1 cell rejoins the N-CIRCLE H0 model
identity through :func:`build_null_signature` with the effect set to zero.

All draws go through ``make_rng(root_key_hex, stream_kind, **fields)`` with the
exact consumption shapes of Plan §15.2/§15.4.  ``stream_prefix``/``stream_fields``
let the blind smoke reuse the same generators with the isolated ``smoke_``
stream kinds and the smoke-only named fields.  No formal data are persisted by
this module; it only builds arrays and identities for later pipeline stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from scipy.special import ndtr

from . import hashing
from .canonical import canonical_decimal_text
from .cells import L_LATENT, L_MASTER

Family = Literal["N_AR", "N_CIRCLE"]
DGP_FAMILY_N_AR = "N_AR"
DGP_FAMILY_N_CIRCLE = "N_CIRCLE"
DGP_FAMILY_H1 = "CIRCLE_BASED_H1"

N_AR_VERSION = "N_AR_V1"
N_CIRCLE_VERSION = "N_CIRCLE_V1"
H1_VERSION = "CIRCLE_BASED_H1_V1"

H1_SCENARIO_SHAPE = "shape_change"
H1_SCENARIO_MEAN = "mean_shift"
H1_SCENARIOS = (H1_SCENARIO_SHAPE, H1_SCENARIO_MEAN)
H1_MEAN_SHIFT_DELTA = "0.5"
H1_MEAN_SHIFT_DELTA_FLOAT = 0.5
H1_CHANGE_POINT_RULE = "floor(T/2)"
H1_PRE_EFFECT_MAP = "circle_cos_sin"
H1_POST_EFFECT_MAP_SHAPE = "figure_eight_sin2_sin4"
H1_POST_EFFECT_MAP_MEAN = "circle_cos_sin"
H1_POST_EFFECT_MAP_MEAN_SHIFT = "unit_circle_direction_uniform"

BURN_IN = 1000
NOISE_SCALE_N_CIRCLE = "0.08"
NOISE_SCALE_FLOAT = 0.08
ROTATION = "I2"
LATENT_LAW_N_CIRCLE = "stationary_gaussian_ar1_then_scipy_ndtr_float64"
OBSERVATION_NOISE_N_CIRCLE = "iid_N2_0_I2_times_0.08"
INITIAL_INDEX = -1000
DISCARDED_INDICES = "-999..0"
UNIT = "dimensionless"

NULL_SIGNATURE_KIND = "null_model_signature"
NULL_FAMILY_N_CIRCLE = "N_CIRCLE"


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
        "latent_law": LATENT_LAW_N_CIRCLE,
        "initial_index": INITIAL_INDEX,
        "discarded_indices": DISCARDED_INDICES,
        "rho": canonical_decimal_text(rho),
        "observation_noise": OBSERVATION_NOISE_N_CIRCLE,
        "rotation": ROTATION,
        "unit": UNIT,
    }


def h1_data_model_spec(scenario: str, rho: str | float) -> dict:
    """Canonical data-model config for one ``CIRCLE_BASED_H1`` alternative.

    Plan §12.1: both alternatives are the *same* ``DGP_family`` and share
    ``master_replicate_id``/``cluster_id`` per replicate; they differ only in
    ``scenario_id`` (and hence in this hash), so their physical/data-unit
    identities differ.  Plan §15.3: ``W/s/T/M`` are deliberately excluded --
    they live in ``physical_cell_id``.
    """
    if scenario not in H1_SCENARIOS:
        raise ValueError(f"unknown H1 scenario {scenario!r}")
    shape = scenario == H1_SCENARIO_SHAPE
    return {
        "schema_version": 1,
        "config_kind": "data_model",
        "family": DGP_FAMILY_H1,
        "generator_version": H1_VERSION,
        "scenario_id": scenario,
        "latent_law": LATENT_LAW_N_CIRCLE,
        "initial_index": INITIAL_INDEX,
        "discarded_indices": DISCARDED_INDICES,
        "rho": canonical_decimal_text(rho),
        "pre_effect_map": H1_PRE_EFFECT_MAP,
        "post_effect_map": (
            H1_POST_EFFECT_MAP_SHAPE if shape else H1_POST_EFFECT_MAP_MEAN
        ),
        "mean_shift_delta": "0" if shape else H1_MEAN_SHIFT_DELTA,
        "mean_shift_direction": (
            None if shape else H1_POST_EFFECT_MAP_MEAN_SHIFT
        ),
        "change_point_rule": H1_CHANGE_POINT_RULE,
        "observation_noise": OBSERVATION_NOISE_N_CIRCLE,
        "rotation": ROTATION,
        "unit": UNIT,
    }


def data_model_config_hash(spec: dict) -> str:
    from .identity import config_hash

    return config_hash("data_model", spec["schema_version"], spec)


def build_null_signature(*, rho: str | float, W: int, stride: int, T: int, M: int) -> str:
    """``H("null_model_signature", ...)`` -- the shared H0 model identity (Plan §7).

    N-CIRCLE H0 cells and *every* H1 cell call this single function: an H1 cell
    first sets its shape/mean effect to zero and then contributes its own
    ``rho, W, s, T, M``, so the two alternatives rejoin exactly the
    ``null_model_config_hash`` of the matching N-CIRCLE H0 cell (Plan §12.1).

    Phase, scenario and effect parameters are deliberately absent from the
    payload, so a change to the noise law, burn-in, rotation, generator version
    or window geometry changes the signature and breaks the source-null join.
    """
    from .identity import H

    return H(
        NULL_SIGNATURE_KIND,
        null_family=NULL_FAMILY_N_CIRCLE,
        generator_version=N_CIRCLE_VERSION,
        latent_law=LATENT_LAW_N_CIRCLE,
        initial_index=INITIAL_INDEX,
        discarded_indices=DISCARDED_INDICES,
        rho=canonical_decimal_text(rho),
        observation_noise=OBSERVATION_NOISE_N_CIRCLE,
        rotation=ROTATION,
        unit=UNIT,
        W=W,
        stride=stride,
        T=T,
        M=M,
    )


def h1_change_point(T: int) -> int:
    """``tau = floor(T/2)`` (Plan §12.1): pre-effect for t<=tau, post for t>tau."""
    if not isinstance(T, int) or T < 2:
        raise ValueError(f"T must be an int >= 2, got {T!r}")
    return T // 2


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
    stream_prefix: str = "null_",
    stream_fields: dict[str, Any] | None = None,
) -> NullMaster:
    """Generate one H0 NULL master path for the given family/rho/replicate.

    ``stream_prefix``/``stream_fields`` are only used by the blind smoke, which
    must consume ``smoke_initial`` / ``smoke_innovation`` /
    ``smoke_observation_noise`` with the smoke-only named fields
    ``{smoke_generation_id, phase, DGP_family, replicate_id}`` (Plan §15.2).
    """
    from .seeding import make_rng

    rho_text = canonical_decimal_text(rho)
    if family not in (DGP_FAMILY_N_AR, DGP_FAMILY_N_CIRCLE):
        raise ValueError(f"unknown family {family!r}")
    base_fields: dict[str, Any] = {
        "data_generation_id": data_generation_id,
        "DGP_family": family,
        "master_replicate_id": master_replicate_id,
    }
    if stream_fields is not None:
        base_fields = dict(stream_fields)

    initial = make_rng(
        root_key_hex, f"{stream_prefix}initial", **base_fields
    ).standard_normal()
    innovations = make_rng(
        root_key_hex, f"{stream_prefix}innovation", **base_fields
    ).standard_normal(L_LATENT)
    rho_f = float(rho_text)

    noise = None
    noise_hash = None
    if family == DGP_FAMILY_N_CIRCLE:
        noise = (
            make_rng(root_key_hex, f"{stream_prefix}observation_noise", **base_fields)
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


@dataclass(frozen=True)
class H1Master:
    """One ``CIRCLE_BASED_H1`` master replicate (one alternative, one rho).

    The master stores the *shared* continuous latent copula path ``U_1..U_12288``
    and the shared observation noise; the change point is a cell-level property
    (``tau = floor(T/2)``), so both strides of a replicate read their own prefix
    of the same draws (Plan §12.1, §15.3).
    """

    scenario: str
    rho_text: str
    data_generation_id: str
    DGP_family: str
    master_replicate_id: str
    initial_value: float
    innovations: np.ndarray  # float64 [13288]
    noise: np.ndarray  # float64 [12288,2]
    latent_states: np.ndarray  # G states, len L_LATENT+1
    latent_u: np.ndarray  # U_1..U_12288 (float64 [12288])
    circle: np.ndarray  # C(U_t), float64 [12288,2]
    shape_map: np.ndarray | None  # F(U_t) for the shape alternative
    shift_direction_value: float | None  # V ~ U(0,1), mean-shift only
    shift_direction_v: tuple[float, float] | None  # (cos 2piV, sin 2piV)
    shift_direction_seed: str | None  # 32-hex sub-seed, mean-shift only
    innovation_hash: str
    noise_hash: str

    def change_point(self, T: int) -> int:
        return h1_change_point(T)

    def raw_prefix(self, T: int) -> np.ndarray:
        """Raw series X_1..X_T for a cell, float64 C order ``[T,2]``."""
        if not isinstance(T, int) or not 2 <= T <= L_MASTER:
            raise ValueError(f"T must be an int in [2, {L_MASTER}], got {T!r}")
        tau = h1_change_point(T)
        post = (np.arange(1, T + 1) > tau).reshape(-1, 1)
        if self.scenario == H1_SCENARIO_SHAPE:
            assert self.shape_map is not None
            skeleton = np.where(post, self.shape_map[:T], self.circle[:T])
        else:
            assert self.shift_direction_v is not None
            direction = np.asarray(self.shift_direction_v, dtype=np.float64)
            skeleton = self.circle[:T] + (
                H1_MEAN_SHIFT_DELTA_FLOAT * post * direction
            )
        return np.ascontiguousarray(skeleton + NOISE_SCALE_FLOAT * self.noise[:T])

    def raw_series_hash(self, T: int) -> str:
        raw = self.raw_prefix(T)
        return hashing.array_hash("synthetic_raw_series_v1", raw, dtype_code=">f8")


def generate_h1_master(
    *,
    scenario: str,
    rho: str | float,
    root_key_hex: str,
    data_generation_id: str,
    master_replicate_id: str,
    stream_prefix: str = "h1_",
    stream_fields: dict[str, Any] | None = None,
) -> H1Master:
    """Generate one H1 alternative master replicate (Plan §12.1/§12.2).

    Consumption (Plan §15.2, float64 C order): ``{prefix}initial`` shape ``()``,
    ``{prefix}innovation`` shape ``[13288]``, ``{prefix}observation_noise`` shape
    ``[12288,2]``; ``{prefix}shift_direction`` performs exactly one
    ``rng.random(dtype=np.float64)`` draw and is consumed by the mean-shift
    alternative only (the shape alternative reports a null seed).
    """
    from .seeding import derive_seed_hex, make_rng

    if scenario not in H1_SCENARIOS:
        raise ValueError(f"unknown H1 scenario {scenario!r}")
    rho_text = canonical_decimal_text(rho)
    fields: dict[str, Any] = {
        "data_generation_id": data_generation_id,
        "master_replicate_id": master_replicate_id,
    }
    if stream_fields is not None:
        fields = dict(stream_fields)

    initial = make_rng(
        root_key_hex, f"{stream_prefix}initial", **fields
    ).standard_normal()
    innovations = make_rng(
        root_key_hex, f"{stream_prefix}innovation", **fields
    ).standard_normal(L_LATENT)
    noise = (
        make_rng(root_key_hex, f"{stream_prefix}observation_noise", **fields)
        .standard_normal(size=(L_MASTER, 2))
        .astype(np.float64, order="C", copy=False)
    )

    latent = _ar1_states(float(rho_text), float(initial), innovations)
    u = np.ascontiguousarray(ndtr(_formal_prefix(latent, L_MASTER)))
    circle = np.column_stack([np.cos(2.0 * np.pi * u), np.sin(2.0 * np.pi * u)])

    shape_map: np.ndarray | None = None
    shift_value: float | None = None
    shift_v: tuple[float, float] | None = None
    shift_seed: str | None = None
    if scenario == H1_SCENARIO_SHAPE:
        shape_map = np.column_stack(
            [np.sin(2.0 * np.pi * u), np.sin(4.0 * np.pi * u)]
        )
    else:
        shift_seed = derive_seed_hex(
            root_key_hex, f"{stream_prefix}shift_direction", **fields
        )
        shift_value = float(
            make_rng(
                root_key_hex, f"{stream_prefix}shift_direction", **fields
            ).random(dtype=np.float64)
        )
        angle = 2.0 * np.pi * shift_value
        shift_v = (float(np.cos(angle)), float(np.sin(angle)))

    return H1Master(
        scenario=scenario,
        rho_text=rho_text,
        data_generation_id=data_generation_id,
        DGP_family=DGP_FAMILY_H1,
        master_replicate_id=master_replicate_id,
        initial_value=float(initial),
        innovations=innovations,
        noise=noise,
        latent_states=latent,
        latent_u=u,
        circle=circle,
        shape_map=shape_map,
        shift_direction_value=shift_value,
        shift_direction_v=shift_v,
        shift_direction_seed=shift_seed,
        innovation_hash=hashing.array_hash(
            "synthetic_latent_innovation_v1", innovations, dtype_code=">f8"
        ),
        noise_hash=hashing.array_hash(
            "synthetic_observation_noise_v1", noise, dtype_code=">f8"
        ),
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
    "DGP_FAMILY_H1",
    "N_AR_VERSION",
    "N_CIRCLE_VERSION",
    "H1_VERSION",
    "H1_SCENARIO_SHAPE",
    "H1_SCENARIO_MEAN",
    "H1_SCENARIOS",
    "H1_MEAN_SHIFT_DELTA",
    "H1_MEAN_SHIFT_DELTA_FLOAT",
    "H1_CHANGE_POINT_RULE",
    "BURN_IN",
    "NOISE_SCALE_N_CIRCLE",
    "NOISE_SCALE_FLOAT",
    "ROTATION",
    "LATENT_LAW_N_CIRCLE",
    "OBSERVATION_NOISE_N_CIRCLE",
    "INITIAL_INDEX",
    "DISCARDED_INDICES",
    "UNIT",
    "NULL_SIGNATURE_KIND",
    "NULL_FAMILY_N_CIRCLE",
    "n_ar_data_model_spec",
    "n_circle_data_model_spec",
    "h1_data_model_spec",
    "data_model_config_hash",
    "build_null_signature",
    "h1_change_point",
    "NullMaster",
    "H1Master",
    "generate_null_master",
    "generate_h1_master",
    "delay_embedding_3",
]
