"""Golden tests for the PAMAP2 Protocol importer (Plan §13.2)."""

import math

import numpy as np
import pytest

from owtda_cal.pamap2_import import (
    GRAVITY,
    DataIdentityFail,
    DataTimebaseFail,
    check_strictly_increasing,
    clock_segments,
    convert_to_g,
    grid_contiguous_segments,
    grid_map,
    import_subject,
    interpolate_axis,
    interpolate_run,
    parse_rows,
)


def _line(t, act=1, chest=(1.0, 2.0, 3.0), extra="0"):
    tokens = [extra] * 54
    tokens[0] = repr(float(t))
    tokens[1] = act if isinstance(act, str) else str(int(act))
    tokens[21], tokens[22], tokens[23] = (repr(float(v)) if not isinstance(v, str) else v for v in chest)
    return " ".join(tokens) + "\n"


class TestParse:
    def test_valid_row(self):
        ts, act, chest = parse_rows([_line(0.0)])
        assert ts[0] == 0.0 and act[0] == 1
        assert np.array_equal(chest[0], [1.0, 2.0, 3.0])

    def test_column_count(self):
        with pytest.raises(DataIdentityFail):
            parse_rows([_line(0.0).replace(" 0", "", 1)])

    def test_inf_rejected(self):
        with pytest.raises(DataIdentityFail):
            parse_rows([_line(0.0, chest=("Inf", 1.0, 1.0))])

    def test_lowercase_nan_rejected(self):
        with pytest.raises(DataIdentityFail):
            parse_rows([_line(0.0, chest=("nan", 1.0, 1.0))])

    def test_literal_NaN_allowed(self):
        _ts, _act, chest = parse_rows([_line(0.0, chest=("NaN", 1.0, 1.0))])
        assert math.isnan(chest[0, 0])

    def test_activity_validation(self):
        with pytest.raises(DataIdentityFail):
            parse_rows([_line(0.0, act=99)])
        with pytest.raises(DataIdentityFail):
            parse_rows([_line(0.0, act="1.5")])

    def test_non_increasing(self):
        with pytest.raises(DataIdentityFail):
            check_strictly_increasing(np.array([0.0, 0.0]))
        with pytest.raises(DataIdentityFail):
            check_strictly_increasing(np.array([0.0, -0.01]))


class TestTimebase:
    def test_clock_segments(self):
        ts = np.array([0.0, 0.01, 0.02, 1.0, 1.01])
        assert clock_segments(ts) == [(0, 3), (3, 5)]

    def test_grid_map_exact(self):
        ts = np.array([0.0, 0.01, 0.02])
        assert np.array_equal(grid_map(ts), [0, 1, 2])

    def test_grid_map_off_grid(self):
        with pytest.raises(DataTimebaseFail):
            grid_map(np.array([0.0, 0.013]))

    def test_grid_map_duplicate_index(self):
        with pytest.raises(DataTimebaseFail):
            grid_map(np.array([0.0, 0.001]))

    def test_grid_contiguous(self):
        j = np.array([0, 1, 3, 4])
        assert grid_contiguous_segments(j) == [(0, 2), (2, 4)]


class TestInterpolation:
    def test_four_step_formula(self):
        out = interpolate_run(0.0, 4.0, 3)
        assert np.array_equal(out, [1.0, 2.0, 3.0])

    def test_axis_run_interpolated(self):
        v = np.array([0.0, np.nan, np.nan, 3.0])
        filled, bad = interpolate_axis(v)
        assert not bad.any()
        assert np.allclose(filled, [0.0, 1.0, 2.0, 3.0])

    def test_edge_run_is_bad(self):
        v = np.array([np.nan, 1.0, 2.0])
        _filled, bad = interpolate_axis(v)
        assert bad[0] and not bad[1:].any()

    def test_long_run_is_bad(self):
        v = np.concatenate([[0.0], np.full(51, np.nan), [1.0]])
        _filled, bad = interpolate_axis(v)
        assert bad[1:52].all()

    def test_convert_to_g(self):
        assert convert_to_g(np.array([GRAVITY]))[0] == pytest.approx(1.0)


class TestImportSubject:
    def _write(self, tmp_path, lines, name="subject101.dat"):
        p = tmp_path / name
        p.write_text("".join(lines), encoding="ascii")
        return str(p)

    def test_clean_file(self, tmp_path):
        lines = [_line(i * 0.01, act=1, chest=(1.0, 2.0, 3.0)) for i in range(6)]
        res = import_subject(self._write(tmp_path, lines), subject="subject101")
        assert res.final_timestamps.shape[0] == 6
        assert np.allclose(res.final_chest_g, np.array([1.0, 2.0, 3.0]) / GRAVITY)
        assert res.original_entrywise_missing_rate == 0.0
        assert res.dropped_bad_rows == 0

    def test_nan_run_interpolated(self, tmp_path):
        lines = [_line(i * 0.01) for i in range(6)]
        lines[2] = _line(0.02, chest=("NaN", "NaN", "NaN"))
        lines[3] = _line(0.03, chest=("NaN", "NaN", "NaN"))
        res = import_subject(self._write(tmp_path, lines))
        assert res.final_timestamps.shape[0] == 6
        assert res.original_rowwise_missing_rate == pytest.approx(2 / 6)
        assert res.dropped_bad_rows == 0

    def test_long_nan_run_rows_dropped(self, tmp_path):
        lines = [_line(i * 0.01, chest=(1.0, 1.0, 1.0)) for i in range(60)]
        for i in range(5, 56):
            lines[i] = _line(i * 0.01, chest=("NaN", "NaN", "NaN"))
        res = import_subject(self._write(tmp_path, lines))
        assert res.dropped_bad_rows == 51
        assert res.final_timestamps.shape[0] == 5  # largest run (indices 0..4)

    def test_clock_gap_splits(self, tmp_path):
        lines = [_line(i * 0.01) for i in range(6)]
        lines += [_line(1.0 + i * 0.01) for i in range(3)]
        res = import_subject(self._write(tmp_path, lines))
        assert res.provisional_clock_segments == 2
        assert res.final_timestamps.shape[0] == 6  # larger segment chosen

    def test_bad_activity_fails(self, tmp_path):
        lines = [_line(0.0, act=99)]
        with pytest.raises(DataIdentityFail):
            import_subject(self._write(tmp_path, lines))

    def test_all_analysis_segments_enumerated(self, tmp_path):
        lines = [_line(i * 0.01) for i in range(6)]
        lines += [_line(1.0 + i * 0.01) for i in range(3)]
        res = import_subject(self._write(tmp_path, lines))
        assert res.final_segment_count == 2
        assert [s.analysis_segment_id for s in res.analysis_segments] == [0, 1]
        assert res.analysis_segments[0].chest_g.shape[0] == 6
        assert res.analysis_segments[1].chest_g.shape[0] == 3
        # final_* mirrors the largest segment
        assert res.final_timestamps.shape[0] == 6
