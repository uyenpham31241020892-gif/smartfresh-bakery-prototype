# BÁO CÁO KẾT QUẢ TEST CHÍNH THỨC 62 NGÀY (01/07/2022 – 31/08/2022)

## 1. Bảng Tổng Hợp Đối Soát 4 Nhánh (434 SKU-Ngày / Nhánh)
*Lưu ý kế toán: Giá vốn bánh dư (`leftover_production_cost_component_vnd`) được trình bày như thành phần đã nằm trong Tổng chi phí sản xuất (`total_production_cost_vnd`), tuyệt đối không trừ lần thứ hai khi tính Lãi góp.*

| branch      |   sku_days |   revenue_vnd |   delta_revenue_vs_baseline_vnd |   delta_revenue_vs_baseline_pct |   contribution_vnd_if_costs_supplied | cost_status                                    |   waste_units |   lost_units_SCENARIO |   scenario_request_fill_rate |   stock_available_at2130_rate |   stockout_before2130_sku_day_rate | scope                                                   |   delta_contribution_vs_baseline_vnd_assumed |
|:------------|-----------:|--------------:|--------------------------------:|--------------------------------:|-------------------------------------:|:-----------------------------------------------|--------------:|----------------------:|-----------------------------:|------------------------------:|-----------------------------------:|:--------------------------------------------------------|---------------------------------------------:|
| BASELINE    |        434 |     277031800 |                               0 |                       0         |                            130334332 | ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT |          1503 |                  4462 |                     0.704718 |                      0.47235  |                           0.546083 | COMPLETE_PREDECLARED_SIMULATION_NOT_AEON_FIELD_EVIDENCE |                                            0 |
| JOINT_M1_M2 |        434 |     296967115 |                        19935315 |                       7.19604   |                            140133307 | ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT |          1436 |                  3702 |                     0.756415 |                      0.518433 |                           0.504608 | COMPLETE_PREDECLARED_SIMULATION_NOT_AEON_FIELD_EVIDENCE |                                      9798975 |
| M1_ONLY     |        434 |     277091545 |                           59745 |                       0.0215661 |                            130157233 | ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT |          1469 |                  4446 |                     0.706515 |                      0.476959 |                           0.541475 | COMPLETE_PREDECLARED_SIMULATION_NOT_AEON_FIELD_EVIDENCE |                                      -177099 |
| M2_ONLY     |        434 |     297018500 |                        19986700 |                       7.21459   |                            140536756 | ASSUMED_COMPONENT_COSTS_NOT_ACTUAL_AEON_PROFIT |          1495 |                  3699 |                     0.755163 |                      0.520737 |                           0.502304 | COMPLETE_PREDECLARED_SIMULATION_NOT_AEON_FIELD_EVIDENCE |                                     10202424 |

## 2. Khoảng Bất Định Bootstrap 95% (Theo Ngày Nguồn) Cho Chênh Lệch Lãi Góp So Với Baseline
| branch      |   total_cm_diff_vs_baseline_vnd |   bootstrap_95ci_low_vnd |   bootstrap_95ci_high_vnd |
|:------------|--------------------------------:|-------------------------:|--------------------------:|
| BASELINE    |                     0           |              0           |               0           |
| M1_ONLY     |               -177099           |        -599043           |          192130           |
| M2_ONLY     |                     1.02024e+07 |              4.02083e+06 |               1.6339e+07  |
| JOINT_M1_M2 |                     9.79898e+06 |              3.4908e+06  |               1.61329e+07 |

## 3. Phân Rã Theo Từng SKU (7 Món Khảo Sát)
| branch      | sku_id    |   realized_revenue_vnd |   total_production_cost_vnd |   leftover_production_cost_component_vnd |   additional_disposal_cost_vnd |   markdown_operation_cost_vnd |   contribution_margin_vnd |   waste_units |   simulated_lost_sales_units |   service_available_to_2130 |
|:------------|:----------|-----------------------:|----------------------------:|-----------------------------------------:|-------------------------------:|------------------------------:|--------------------------:|--------------:|-----------------------------:|----------------------------:|
| BASELINE    | TP-CP-001 |            1.22342e+07 |                 6.4377e+06  |                              2.44951e+06 |                          41550 |                         14700 |               5.74025e+06 |           277 |                           78 |                    0.758065 |
| BASELINE    | TP-CR-001 |            4.8593e+07  |                 2.18275e+07 |                              1.26087e+06 |                          18300 |                          3850 |               2.67433e+07 |           122 |                          972 |                    0.274194 |
| BASELINE    | TP-DN-001 |            6.67968e+07 |                 3.21473e+07 |                              1.40712e+06 |                          15600 |                             0 |               3.46339e+07 |           104 |                         1833 |                    0.193548 |
| BASELINE    | TP-DN-002 |            4.2195e+07  |                 2.46094e+07 |                              2.73438e+06 |                          31800 |                          5250 |               1.75486e+07 |           212 |                          509 |                    0.435484 |
| BASELINE    | TP-DN-003 |            4.3135e+07  |                 2.50221e+07 |                              2.66989e+06 |                          31050 |                          6300 |               1.80755e+07 |           207 |                          519 |                    0.419355 |
| BASELINE    | TP-DN-004 |            4.5665e+07  |                 2.75289e+07 |                              3.47388e+06 |                          39750 |                          6650 |               1.80897e+07 |           265 |                          393 |                    0.516129 |
| BASELINE    | TP-RV-001 |            1.84128e+07 |                 8.86236e+06 |                              2.83452e+06 |                          47400 |                             0 |               9.50304e+06 |           316 |                          158 |                    0.709677 |
| JOINT_M1_M2 | TP-CP-001 |            1.27274e+07 |                 6.29622e+06 |                              2.14885e+06 |                          36450 |                         13300 |               6.38143e+06 |           243 |                           60 |                    0.758065 |
| JOINT_M1_M2 | TP-CR-001 |            5.55295e+07 |                 2.54654e+07 |                              1.90164e+06 |                          27600 |                          3850 |               3.00326e+07 |           184 |                          687 |                    0.451613 |
| JOINT_M1_M2 | TP-DN-001 |            7.50464e+07 |                 3.63686e+07 |                              1.79949e+06 |                          19950 |                          1050 |               3.86568e+07 |           133 |                         1553 |                    0.290323 |
| JOINT_M1_M2 | TP-DN-002 |            4.48638e+07 |                 2.64151e+07 |                              2.74727e+06 |                          31950 |                          7350 |               1.84093e+07 |           213 |                          406 |                    0.483871 |
| JOINT_M1_M2 | TP-DN-003 |            4.50738e+07 |                 2.65699e+07 |                              2.92785e+06 |                          34050 |                          8750 |               1.84611e+07 |           227 |                          438 |                    0.467742 |
| JOINT_M1_M2 | TP-DN-004 |            4.69575e+07 |                 2.82106e+07 |                              3.14616e+06 |                          36000 |                          9800 |               1.87011e+07 |           240 |                          340 |                    0.580645 |
| JOINT_M1_M2 | TP-RV-001 |            1.67688e+07 |                 7.24776e+06 |                              1.75812e+06 |                          29400 |                           700 |               9.49094e+06 |           196 |                          218 |                    0.596774 |
| M1_ONLY     | TP-CP-001 |            1.22342e+07 |                 6.4377e+06  |                              2.44951e+06 |                          41550 |                         14700 |               5.74025e+06 |           277 |                           78 |                    0.758065 |
| M1_ONLY     | TP-CR-001 |            4.87523e+07 |                 2.19102e+07 |                              1.18852e+06 |                          17250 |                          3850 |               2.6821e+07  |           115 |                          964 |                    0.274194 |
| M1_ONLY     | TP-DN-001 |            6.66336e+07 |                 3.21473e+07 |                              1.36653e+06 |                          15150 |                           700 |               3.44705e+07 |           101 |                         1833 |                    0.193548 |
| M1_ONLY     | TP-DN-002 |            4.21775e+07 |                 2.4661e+07  |                              2.5925e+06  |                          30150 |                          5600 |               1.74808e+07 |           201 |                          508 |                    0.435484 |
| M1_ONLY     | TP-DN-003 |            4.30975e+07 |                 2.50221e+07 |                              2.63119e+06 |                          30600 |                          6650 |               1.80381e+07 |           204 |                          519 |                    0.419355 |
| M1_ONLY     | TP-DN-004 |            4.58425e+07 |                 2.76338e+07 |                              3.3559e+06  |                          38400 |                          6650 |               1.81637e+07 |           256 |                          386 |                    0.548387 |
| M1_ONLY     | TP-RV-001 |            1.83539e+07 |                 8.86236e+06 |                              2.82555e+06 |                          47250 |                          1400 |               9.44288e+06 |           315 |                          158 |                    0.709677 |
| M2_ONLY     | TP-CP-001 |            1.27274e+07 |                 6.29622e+06 |                              2.14885e+06 |                          36450 |                         13300 |               6.38143e+06 |           243 |                           60 |                    0.758065 |
| M2_ONLY     | TP-CR-001 |            5.54935e+07 |                 2.54241e+07 |                              1.96365e+06 |                          28500 |                          3500 |               3.00374e+07 |           190 |                          689 |                    0.451613 |
| M2_ONLY     | TP-DN-001 |            7.50288e+07 |                 3.63145e+07 |                              1.78596e+06 |                          19800 |                             0 |               3.86945e+07 |           132 |                         1553 |                    0.290323 |
| M2_ONLY     | TP-DN-002 |            4.494e+07   |                 2.62087e+07 |                              2.94074e+06 |                          34200 |                          5600 |               1.86915e+07 |           228 |                          399 |                    0.5      |
| M2_ONLY     | TP-DN-003 |            4.5195e+07  |                 2.65699e+07 |                              3.17291e+06 |                          36900 |                          7000 |               1.85812e+07 |           246 |                          436 |                    0.467742 |
| M2_ONLY     | TP-DN-004 |            4.6865e+07  |                 2.81581e+07 |                              3.40834e+06 |                          39000 |                          8750 |               1.86591e+07 |           260 |                          344 |                    0.580645 |
| M2_ONLY     | TP-RV-001 |            1.67688e+07 |                 7.24776e+06 |                              1.75812e+06 |                          29400 |                             0 |               9.49164e+06 |           196 |                          218 |                    0.596774 |

## 4. Phân Rã Theo Thứ Trong Tuần (Trung Bình / SKU-Ngày)
| branch      | day_of_week   |   contribution_margin_vnd |   waste_units |   simulated_lost_sales_units |   service_available_to_2130 |
|:------------|:--------------|--------------------------:|--------------:|-----------------------------:|----------------------------:|
| BASELINE    | Friday        |                    221268 |       2.73016 |                     11.0317  |                    0.428571 |
| BASELINE    | Monday        |                    258440 |       3.73016 |                     10.3968  |                    0.428571 |
| BASELINE    | Saturday      |                    400091 |       3.66667 |                     14.7937  |                    0.412698 |
| BASELINE    | Sunday        |                    543646 |       4.20635 |                     14.0794  |                    0.444444 |
| BASELINE    | Thursday      |                    267078 |       3.26786 |                     11.8393  |                    0.410714 |
| BASELINE    | Tuesday       |                    197850 |       3.33333 |                      4.26984 |                    0.634921 |
| BASELINE    | Wednesday     |                    210102 |       3.28571 |                      5.73016 |                    0.539683 |
| JOINT_M1_M2 | Friday        |                    250685 |       4.04762 |                      7.73016 |                    0.555556 |
| JOINT_M1_M2 | Monday        |                    271242 |       2.25397 |                     10.8095  |                    0.460317 |
| JOINT_M1_M2 | Saturday      |                    468929 |       5.49206 |                      7.7619  |                    0.539683 |
| JOINT_M1_M2 | Sunday        |                    548133 |       5.47619 |                     12.0317  |                    0.52381  |
| JOINT_M1_M2 | Thursday      |                    282167 |       1.76786 |                     11.6607  |                    0.392857 |
| JOINT_M1_M2 | Tuesday       |                    206154 |       2.14286 |                      4.38095 |                    0.587302 |
| JOINT_M1_M2 | Wednesday     |                    228381 |       1.80952 |                      5.68254 |                    0.555556 |
| M1_ONLY     | Friday        |                    221268 |       2.73016 |                     11.0317  |                    0.428571 |
| M1_ONLY     | Monday        |                    258278 |       3.71429 |                     10.3968  |                    0.428571 |
| M1_ONLY     | Saturday      |                    400091 |       3.66667 |                     14.7937  |                    0.412698 |
| M1_ONLY     | Sunday        |                    543798 |       4.04762 |                     14.0794  |                    0.444444 |
| M1_ONLY     | Thursday      |                    264524 |       3.08929 |                     11.6786  |                    0.410714 |
| M1_ONLY     | Tuesday       |                    196665 |       3.20635 |                      4.26984 |                    0.634921 |
| M1_ONLY     | Wednesday     |                    210756 |       3.20635 |                      5.61905 |                    0.571429 |
| M2_ONLY     | Friday        |                    250835 |       4.09524 |                      7.73016 |                    0.555556 |
| M2_ONLY     | Monday        |                    270832 |       2.31746 |                     10.873   |                    0.460317 |
| M2_ONLY     | Saturday      |                    467760 |       5.84127 |                      7.79365 |                    0.539683 |
| M2_ONLY     | Sunday        |                    551335 |       5.39683 |                     12.0317  |                    0.52381  |
| M2_ONLY     | Thursday      |                    282602 |       2.16071 |                     11.6786  |                    0.410714 |
| M2_ONLY     | Tuesday       |                    209893 |       2.36508 |                      4.22222 |                    0.587302 |
| M2_ONLY     | Wednesday     |                    228884 |       1.79365 |                      5.68254 |                    0.555556 |

## 5. Phân Rã Theo Giai Đoạn (Tháng 07/2022 vs. Tháng 08/2022)
| branch      | period           |   realized_revenue_vnd |   total_production_cost_vnd |   contribution_margin_vnd |   waste_units |   simulated_lost_sales_units |   service_available_to_2130 |
|:------------|:-----------------|-----------------------:|----------------------------:|--------------------------:|--------------:|-----------------------------:|----------------------------:|
| BASELINE    | Month_07_Jul2022 |            1.25385e+08 |                 6.34928e+07 |               6.18059e+07 |           480 |                         2197 |                    0.423963 |
| BASELINE    | Month_08_Aug2022 |            1.51646e+08 |                 8.29425e+07 |               6.85284e+07 |          1023 |                         2265 |                    0.520737 |
| JOINT_M1_M2 | Month_07_Jul2022 |            1.46017e+08 |                 7.7984e+07  |               6.78854e+07 |           820 |                         1405 |                    0.576037 |
| JOINT_M1_M2 | Month_08_Aug2022 |            1.50951e+08 |                 7.85896e+07 |               7.22479e+07 |           616 |                         2297 |                    0.460829 |
| M1_ONLY     | Month_07_Jul2022 |            1.25563e+08 |                 6.36381e+07 |               6.18387e+07 |           469 |                         2188 |                    0.428571 |
| M1_ONLY     | Month_08_Aug2022 |            1.51529e+08 |                 8.30363e+07 |               6.83185e+07 |          1000 |                         2258 |                    0.525346 |
| M2_ONLY     | Month_07_Jul2022 |            1.45905e+08 |                 7.78903e+07 |               6.78664e+07 |           848 |                         1413 |                    0.576037 |
| M2_ONLY     | Month_08_Aug2022 |            1.51113e+08 |                 7.83291e+07 |               7.26704e+07 |           647 |                         2286 |                    0.465438 |

## 6. Giới Hạn Diễn Giải & Quy Phạm Khoa Học
- Kết quả trên được chạy trên bộ test mô phỏng 62 ngày có cách ly thông tin tương lai, **không kết luận mô hình đã thích nghi với mọi input AEON hoặc đã chứng minh lợi nhuận thực địa tại cửa hàng**.
- Giữ nguyên toàn bộ kết quả thực nghiệm của 4 nhánh (kể cả ở các SKU hoặc khung thời gian mà AI có thể thấp hơn Baseline).
- Nếu thực hiện bất kỳ chỉnh sửa nào về mô hình, trọng số hoặc chính sách giá sau khi xem báo cáo này, lần chạy tiếp theo phải được ghi nhận là **vòng phát triển mới (post-test development iteration)**, tuyệt đối không gọi là holdout mù mới.
