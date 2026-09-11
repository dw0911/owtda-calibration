# H1 alternative 构造效度复审包

生成时间（UTC）：2026-09-11T08:45:00Z；回答审计项：`H1-ALTERNATIVE-CONSTRUCT-CONTRACTS = PENDING_CODE_REVIEW`。

> 本包所有取值均可在交付 revision 上重算：`python audit/build_h1_review_packet.py`。引用不存在的测试会判 `MISSING_TEST`（自校验，失败即 FAIL）。

## 1. 受审函数（按源码哈希固定）

| 函数 | 文件 | 起止行 | 源码 SHA256 |
|---|---|---|---|
| `h1_data_model_spec` | `src/owtda_cal/dgp.py` | 118–152 | `de2a8cf30e441ac2…` |
| `h1_change_point` | `src/owtda_cal/dgp.py` | 193–197 | `340c014fdd1a49e0…` |
| `generate_h1_master` | `src/owtda_cal/dgp.py` | 387–475 | `462f939a15c9efd5…` |
| `build_null_signature` | `src/owtda_cal/dgp.py` | 161–190 | `e9ee1ae1cbf8b7b8…` |
| `H1Master.raw_prefix` | `src/owtda_cal/dgp.py` | 365–380 | `5448e31415b35304…` |

## 2. 构造合同

| # | 合同 | 类型 | 观测 | 判定 |
|---|---|---|---|---|
| 1 | tau = floor(T/2), the true continuous boundary is tau_true = tau + 1/2, and tau_true coincides exactly with the k=96 candidate window centre under the scan convention (Plan §12.4 blocking gate) for every H1 geometry; equivalently tau is the midpoint of the k=96/k=97 sample centres | STRUCTURAL | `[{"T": 12288, "stride": 64, "W": 64, "tau": 6144, "tau_true": 6144.5, "k96_centre": 6144.5, "k97_centre": 6208.5, "sample_centre_step": 64.0, "tau_equals_mid…` | PASS |
| 2 | shape alternative: the raw series is bitwise the documented composition (skeleton + 0.08 eta, skeleton = C(u) before tau and F(u) = (sin 2pi u, sin 4pi u) after it); recovering the skeleton back out of the raw series is only exact to float64 rounding | NUMERICAL | `{"raw_series_bitwise_equal_to_documented_composition": true, "pre_skeleton_equal_within_fp_rounding": true, "post_skeleton_equal_within_fp_rounding": true, "…` | PASS |
| 3 | mean shift: the raw series is bitwise the documented composition (C(u) + 0.5 v 1(t>tau) + 0.08 eta) with |v| = 1 | NUMERICAL | `{"raw_series_bitwise_equal_to_documented_composition": true, "pre_skeleton_equal_within_fp_rounding": true, "post_offset_equals_delta_v_within_fp_rounding": …` | PASS |
| 4 | both maps have identical mean (0) and covariance (1/2 I_2) under U ~ Uniform(0,1); no claim of second-order process equality is made | NUMERICAL | `{"grid_points": 4096, "circle_mean": [3.3637372401362775e-17, -3.519705122483356e-17], "figure_eight_mean": [-3.519705122483356e-17, 7.056779714341346e-17], …` | PASS |
| 5 | both alternatives consume one shared latent path and one shared noise master (independent of rho, scenario, s, T, M) | IDENTITY | `{"innovation_hash_equal": true, "noise_hash_equal": true, "latent_path_equal": true}` | PASS |
| 6 | RNG consumption shapes are exactly (), [13288], [12288,2] in float64 C order with a 1000-step burn-in | CONTRACT | `{"latent_innovation_shape": [13288], "latent_innovation_dtype": "float64", "observation_noise_shape": [12288, 2], "observation_noise_c_order": true, "burn_in…` | PASS |
| 7 | one master serves every T: the draws are shared prefixes and the pre-effect segment agrees bitwise up to the shorter tau; beyond it the series intentionally differ because tau = floor(T/2) is a cell property | STRUCTURAL | `{"draws_are_shared_prefixes": true, "pre_effect_segments_agree_bitwise": true, "post_effect_segments_differ_by_design": true, "short_tau": 1560, "long_tau": …` | PASS |
| 8 | every H1 cell rejoins the N-CIRCLE H0 model identity: eight distinct cells collapse to four null signatures, one per (rho, s) | IDENTITY | `{"cells": 8, "distinct_signatures": 4}` | PASS |

### 各合同锁定的测试

- **1** 锚点 `dgp.h1_change_point + scan.estimated_change_raw_time`（容差：exact float equality (error 0.0)）→ `test_floor_half_of_T`、`test_boundary_sits_between_k96_and_k97_centres`、`test_19_window_index_to_raw_time_hand_reversal`、`test_hand_mapping`
- **2** 锚点 `dgp.generate_h1_master / H1Master.raw_prefix`（容差：raw series bitwise; skeleton recovery and implicit identity <= 1e-15）→ `test_shape_change_switches_circle_to_figure_eight`、`test_figure_eight_identity_on_the_post_effect_half`、`test_pre_effect_half_is_the_unit_circle`
- **3** 锚点 `dgp.generate_h1_master / H1Master.raw_prefix`（容差：raw series bitwise; recovered offset <= 1e-15; |v|-1 <= 1e-15）→ `test_mean_shift_is_a_constant_unit_circle_offset`、`test_shift_direction_is_a_single_random_draw`
- **4** 锚点 `audit/build_h1_review_packet.py::_map_moments`（容差：trapezoid grid exact for these harmonics; <= 1e-12）→ `test_the_two_maps_share_mean_and_covariance`、`test_marginal_moments_are_close_on_both_sides`
- **5** 锚点 `dgp.generate_h1_master`（容差：hash equality + array equality）→ `test_rho_free_and_scenario_free_base_draws`、`test_alternatives_differ_only_in_scenario`
- **6** 锚点 `dgp.generate_h1_master`（容差：exact shapes/dtypes）→ `test_draw_shapes_and_dtypes`、`test_raw_prefix_is_float64_c_order`
- **7** 锚点 `H1Master.raw_prefix`（容差：bitwise equality on the pre-effect segment; deliberate divergence after）→ `test_short_length_is_a_bitwise_prefix_of_the_long_length`、`test_shared_draws_agree_between_strides`
- **8** 锚点 `dgp.build_null_signature`（容差：8 cells -> 4 signatures）→ `test_signature_is_scenario_and_phase_independent`、`test_signature_separates_geometries`、`test_geometry_matches_the_n_circle_h0_cells`

## 3. 刻意不作的声明

- no second-order process matching between the two segments: only pointwise mean and covariance of the maps coincide
- H1 cells do NOT reuse the N-CIRCLE H0 draws (streams differ); they rejoin the H0 *model identity*, which is what size/power comparison requires
- no size, power or rejection-rate value is claimed here; those are L2 and remain unstarted
- the finite-sample empirical moments of one realised path are not claimed to be exactly equal; equality holds for the maps' laws

## 4. 结论

- 合同数 8，全部 PASS：**True**；
- H1 cell 8 个 → null signature 4 个（每 (rho, s) 一个），与对应 N-CIRCLE H0 单元一致。
