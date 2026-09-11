"""Audit A03: degenerate numeric inputs must satisfy the frozen contract exactly.

Audit input: ``Y_i = (0.1, 0.2, 0.3, 0, 0, 0, 0, 0, 0)`` for every ``i``.
Frozen contract (Plan §3.3 / SAP): ``T_obs = 0``, ``p = 1``, ``reject = 0``.

On the audited revision this produced ``T_obs ≈ 1e-30`` (float residue of the
cumulative-sum means) and, for M1, ``b``-block multiplier resampling turned the
residue into ``p = 0.001`` with ``reject = true``.  The lesson recorded here is
that a small *absolute* error does not imply a small *decision* error: the p-value
depends on the relative ranking of resampled statistics.
"""

import numpy as np
import pytest

from owtda_cal import calibrate as calibrate_mod
from owtda_cal import scan
from owtda_cal.calibrate import calibrate_m0, calibrate_m1, dmb_block_length

ROW = np.array([0.1, 0.2, 0.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])
ROOT = "cd" * 32
#: the three geometries probed by the audit
AUDIT_CASES = ((48, 64), (192, 64), (383, 8))


def _constant(M: int) -> np.ndarray:
    return np.tile(ROW, (M, 1))


@pytest.mark.parametrize("M,stride", AUDIT_CASES)
def test_constant_feature_is_exactly_zero(M, stride):
    a = _constant(M)
    curve = scan.statistic_curve(a)
    assert curve["degenerate_constant"] is True
    assert np.all(curve["values"] == 0.0)  # exact zero, not ~1e-30
    assert float(curve["values"].max()) == 0.0
    reference = scan.statistic_curve(a, reference=True)
    assert np.all(reference["values"] == 0.0)  # slow path agrees exactly


@pytest.mark.parametrize("M,stride", AUDIT_CASES)
def test_constant_feature_never_rejects(M, stride):
    a = _constant(M)
    m0 = calibrate_m0(
        a, root_key_hex=ROOT, method_generation_id="m", data_unit_id="u"
    )
    assert m0["observed_statistic"] == 0.0
    assert m0["exceed_count"] == 999
    assert m0["p_value"] == 1.0
    assert m0["reject"] is False

    m1 = calibrate_m1(
        a, root_key_hex=ROOT, method_generation_id="m", data_unit_id="u",
        W=64, stride=stride,
    )
    assert m1["observed_statistic"] == 0.0
    assert m1["exceed_count"] == 999  # every resample ties at zero, so >= holds
    assert m1["p_value"] == 1.0
    assert m1["reject"] is False
    assert m1["b"] == dmb_block_length(W=64, stride=stride, M=M)


def test_constant_path_still_consumes_the_same_random_draws(monkeypatch):
    """The fix may not change the RNG consumption structure (Plan §15.2)."""
    sizes: list[int] = []
    real = calibrate_mod.m1_gaussian_draw

    def spy(*args, **kwargs):
        sizes.append(kwargs["size"])
        return real(*args, **kwargs)

    monkeypatch.setattr(calibrate_mod, "m1_gaussian_draw", spy)
    M, stride = 48, 64
    calibrate_m1(
        _constant(M), root_key_hex=ROOT, method_generation_id="m",
        data_unit_id="u", W=64, stride=stride,
    )
    expected = M + dmb_block_length(W=64, stride=stride, M=M) - 1
    assert sizes == [expected] * 999


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_input_is_rejected(bad):
    a = np.ones((20, 3))
    a[5, 1] = bad
    with pytest.raises(ValueError):
        scan.statistic_curve(a)


def test_empty_feature_dimension_is_rejected():
    with pytest.raises(ValueError):
        scan.statistic_curve(np.ones((20, 0)))


def test_non_finite_input_is_rejected_by_both_calibrators():
    a = np.ones((20, 2))
    a[3, 0] = np.nan
    with pytest.raises(ValueError):
        calibrate_m0(a, root_key_hex=ROOT, method_generation_id="m", data_unit_id="u")
    with pytest.raises(ValueError):
        calibrate_m1(
            a, root_key_hex=ROOT, method_generation_id="m", data_unit_id="u",
            W=64, stride=64,
        )


def test_small_but_non_constant_signal_is_preserved():
    """No amplitude truncation: a tiny genuine signal must stay positive."""
    a = np.zeros((192, 2))
    a[:, 0] = 1e-12 * np.arange(192, dtype=np.float64)
    a[:, 1] = 1e-12
    curve = scan.statistic_curve(a)
    assert curve["degenerate_constant"] is False
    assert float(curve["values"].max()) > 0.0


def test_near_constant_rows_are_not_treated_as_constant():
    """Exact equality only: one differing ULP must not take the degenerate path."""
    a = _constant(192)
    a[-1, 0] = np.nextafter(a[-1, 0], np.inf)
    curve = scan.statistic_curve(a)
    assert curve["degenerate_constant"] is False
    assert float(curve["values"].max()) > 0.0


def test_too_small_matrix_has_no_candidates():
    """M=1 leaves no candidate, which is a contract error rather than a value."""
    with pytest.raises(ValueError):
        scan.statistic_curve(np.array([[1.0, 2.0]]))


def test_two_identical_rows_are_degenerate():
    curve = scan.statistic_curve(np.tile(ROW, (2, 1)))
    assert curve["degenerate_constant"] is True
    assert np.all(curve["values"] == 0.0)
