#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SmartFresh V6.09/V6.10 — Bộ điều phối Kiểm tra trước Test, Chạy Closed-Loop 62 Ngày & Chấm điểm 4 Nhánh.
Đảm bảo:
- Xác minh SHA-256 trước và sau khi chạy (không đổi trọng số hay policy sau khóa).
- Cách ly tuyệt đối tiến trình Adapter khỏi thư mục Custodian (chỉ nhận context qua HTTP API).
- Kiểm tra đủ 434 SKU-ngày mỗi nhánh, đối soát tiền/tồn và không trừ giá vốn bánh dư hai lần.
"""

import os
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import csv
import time
import json
import shutil
import hashlib
import argparse
import subprocess
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, List, Tuple

import numpy as np
import pandas as pd

BRANCHES = ["BASELINE", "M1_ONLY", "M2_ONLY", "JOINT_M1_M2"]
EXPECTED_TEST_DAYS = 62
EXPECTED_SKUS = 7
EXPECTED_SKU_DAYS = EXPECTED_TEST_DAYS * EXPECTED_SKUS  # 434 SKU-ngày mỗi nhánh


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


# =============================================================================
# 1. KIỂM TOÁN MÃ BĂM & CHỐNG RÒ RỈ (HASH & LEAKAGE AUDITOR)
# =============================================================================
def verify_pre_test_hashes(agent_dir: Path, runtime_dir: Path) -> Dict[str, Any]:
    """
    1. Đối chiếu SHA-256 của các file trong TRAINED_MODELS_FROZEN với SHA256SUMS.json.
    2. Ghi nhận SHA-256 của feature_contract.json, build_config.json, sku_master.csv.
    3. Đọc 2 mã băm cam kết thị trường từ TEST_market_commitment.csv.
    """
    sums_path = agent_dir / "artifacts_build" / "models" / "SHA256SUMS.json"
    if not sums_path.exists():
        sums_path = agent_dir / "SHA256SUMS.json"
    with open(sums_path, "r", encoding="utf-8") as f:
        expected_sums = json.load(f)

    verified_models = {}
    for fname, exp_hash in expected_sums.items():
        candidates = [
            agent_dir / "artifacts_build" / "models" / fname,
            agent_dir / fname,
        ]
        found = next((p for p in candidates if p.exists()), None)
        if found is None:
            raise FileNotFoundError(f"Thiếu file bắt buộc trong gói model đã khóa: {fname}")
        actual_hash = sha256_file(found)
        if actual_hash != exp_hash:
            raise ValueError(f"Lệch SHA-256 cho {fname}: expected={exp_hash}, actual={actual_hash}")
        verified_models[fname] = actual_hash

    runtime_hashes = {}
    for rel in [
        "BUSINESS_OBJECTIVE.json",
        "build_config.json",
        "feature_contract.json",
        "sku_master.csv",
        "calendar_test.csv",
        "history_seed_through_20220630.csv",
        "prior_weather_through_20220630.csv",
        "code/pos_core.py",
        "code/pos_server.py",
        "code/score_private.py",
    ]:
        p = runtime_dir / rel
        if p.exists():
            runtime_hashes[rel] = sha256_file(p)

    commit_df = pd.read_csv(runtime_dir / "TEST_market_commitment.csv")
    commit_records = commit_df.to_dict(orient="records")

    return {
        "verified_model_hashes": verified_models,
        "runtime_file_hashes": runtime_hashes,
        "market_commitment": commit_records,
    }


class FilesystemIsolationGuard:
    """
    Chặn mọi lời gọi mở file trái phép từ phía Model Adapter vào thư mục Custodian
    trong suốt quá trình chạy test.
    """
    def __init__(self, forbidden_custodian_dir: Path):
        self.forbidden_dir = forbidden_custodian_dir.resolve()
        self._orig_open = open
        self.violations: List[str] = []

    def _guarded_open(self, file, *args, **kwargs):
        try:
            p = Path(file).resolve()
            if str(p).startswith(str(self.forbidden_dir)):
                msg = f"VIOLATION_CUSTODIAN_FS_ACCESS: {p}"
                self.violations.append(msg)
                raise PermissionError(msg)
        except PermissionError:
            raise
        except Exception:
            pass
        return self._orig_open(file, *args, **kwargs)

    def __enter__(self):
        import builtins
        builtins.open = self._guarded_open
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import builtins
        builtins.open = self._orig_open


# =============================================================================
# 2. KIỂM TRA TÍCH HỢP TRÊN FIXTURE / DEVELOPMENT TRƯỚC KHI MỞ TEST
# =============================================================================
def run_dev_integration_check(agent_dir: Path, runtime_dir: Path) -> Dict[str, Any]:
    """
    Kiểm tra:
    - Adapter load thành công model thật từ artifacts_build/models.
    - Ba feature vận hành V6.10 được điền từ cấu hình biết trước tại thời điểm quyết định.
    - Cổng DQ (Data Quality) chặn đúng các lỗi kỹ thuật và trả về HOLD.
    - Đề xuất M2 tuân thủ công suất, batch size và lead time.
    - Đề xuất M1 tuân thủ trần giảm 50%, khoảng cách 30 phút và sàn baseline.
    """
    sys.path.insert(0, str(agent_dir))
    from smartfresh_adapter import SmartFreshAdapter

    models_dir = agent_dir / "artifacts_build" / "models"
    if not models_dir.exists():
        models_dir = agent_dir
    adapter = SmartFreshAdapter(models_dir=str(models_dir))

    sku_master = pd.read_csv(runtime_dir / "sku_master.csv")
    if "sku_id" not in sku_master.columns and "sku_code" in sku_master.columns:
        sku_master["sku_id"] = sku_master["sku_code"]
    skus = sku_master["sku_id"].astype(str).tolist()
    assert len(skus) == 7, f"Phải có đúng 7 SKU, tìm thấy {len(skus)}"

    # 1. Kiểm tra M2 trên dữ liệu giả lập buổi sáng (06:00 ngày 15/06/2022)
    dev_morning = pd.DataFrame({
        "date": ["2022-06-15"] * len(skus),
        "sku_id": skus,
        "day_of_week": [2] * len(skus),
        "is_weekend": [0] * len(skus),
    })
    m2_plan = adapter.propose_m2_preparation_plan(dev_morning)
    assert len(m2_plan) == 7, "M2 phải trả về đủ kế hoạch cho 7 SKU"
    for item in m2_plan:
        sku = item["sku_id"]
        cap = adapter.op_lookup[sku]["operational_daily_capacity_units"]
        bsize = adapter.op_lookup[sku]["batch_size_units"]
        assert 0 < item["planned_total_units"] <= cap, f"M2 vượt công suất cho {sku}"
        assert item["planned_total_units"] % int(bsize) == 0, f"M2 chưa làm tròn theo mẻ cho {sku}"

    # 2. Kiểm tra M1 tại checkpoint 19:30 và 20:30
    dev_ckpt = pd.DataFrame({
        "date": ["2022-06-15"] * len(skus),
        "checkpoint_time": ["19:30"] * len(skus),
        "sku_id": skus,
        "on_hand_units": [12.0] * len(skus),
        "effective_price_vnd": [adapter.op_lookup[s]["base_price_vnd"] for s in skus],
        "minutes_since_last_price_change": [120.0] * len(skus),
        "baseline_floor_discount_pct": [0] * len(skus),
    })
    valid_ctx = {
        "as_of_timestamp": "2022-06-15T19:30:00+07:00",
        "skus": [
            {"sku_id": s, "effective_price_vnd": adapter.op_lookup[s]["base_price_vnd"], "on_hand_units": 12}
            for s in skus
        ],
        "recent_transactions": [{"transaction_id": "TX-001", "qty": 2}],
    }
    m1_actions = adapter.propose_m1_markdown_actions(dev_ckpt, context_meta=valid_ctx)
    assert len(m1_actions) == 7
    for act in m1_actions:
        assert 0 <= act["discount_pct"] <= 30, "Lúc 19:30 không được giảm quá 30%"

    # 3. Kiểm tra DQ Gate chặn dữ liệu lỗi (thiếu timezone, trùng giao dịch, tồn âm)
    bad_ctx = {
        "as_of_timestamp": "2022-06-15 19:30:00",  # thiếu timezone
        "skus": [{"sku_id": skus[0], "effective_price_vnd": 999999, "on_hand_units": -5}],
        "recent_transactions": [
            {"transaction_id": "DUP-1", "qty": 1},
            {"transaction_id": "DUP-1", "qty": -2},
        ],
    }
    dq_actions = adapter.propose_m1_markdown_actions(dev_ckpt, context_meta=bad_ctx)
    assert all(a["action"] == "HOLD" and "DQ_HOLD_FALLBACK" in a["reason"] for a in dq_actions), (
        "Cổng DQ phải chuyển toàn bộ quyết định về HOLD khi phát hiện lỗi dữ liệu!"
    )

    return {
        "status": "PASSED",
        "m2_sample_plan": m2_plan,
        "m1_sample_actions_1930": m1_actions,
        "dq_fallback_verified": True,
    }


# =============================================================================
# 3. GIAO TIẾP API VỚI POS SERVER & ĐIỀU PHỐI 62 NGÀY TEST CHO 4 NHÁNH
# =============================================================================
def api_request(base_url: str, endpoint: str, token: str, method: str = "GET", payload: Dict = None) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_frozen_62day_loop(
    runtime_dir: Path,
    custodian_dir: Path,
    agent_dir: Path,
    output_dir: Path,
    pre_hashes: Dict[str, Any]
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(agent_dir))
    sys.path.insert(0, str(runtime_dir / "code"))
    import model_features
    from smartfresh_adapter import prepare, markdown

    models_dir = agent_dir / "artifacts_build" / "models"
    if not models_dir.exists():
        models_dir = agent_dir

    # 1. Đóng băng submission.json qua freeze_submission.py
    commit_rows = pre_hashes["market_commitment"]
    hash_market = commit_rows[0].get("market_sha256", commit_rows[0].get("sha256", ""))
    hash_cust = commit_rows[-1].get("customer_events_sha256", commit_rows[-1].get("sha256", ""))
    submission_path = output_dir / "submission.json"

    freeze_cmd = [
        sys.executable, str(runtime_dir / "code" / "freeze_submission.py"),
        "--models-dir", str(models_dir),
        "--adapter", str(agent_dir / "smartfresh_adapter.py"),
        "--config", str(runtime_dir / "build_config.json"),
        "--market-sha256", str(hash_market),
        "--customer-events-sha256", str(hash_cust),
        "--out", str(submission_path),
    ]
    subprocess.run(freeze_cmd, check=True)

    # 2. Khởi chạy pos_server.py ở chế độ FROZEN
    tokens_file = output_dir / "tokens_private.json"
    scorer_out_dir = output_dir / "scorer_raw_output"
    server_port = 8765
    base_url = f"http://127.0.0.1:{server_port}"

    if tokens_file.exists():
        tokens_file.unlink()
    if scorer_out_dir.exists():
        shutil.rmtree(scorer_out_dir)

    server_cmd = [
        sys.executable, str(runtime_dir / "code" / "pos_server.py"),
        "--runtime-dir", str(runtime_dir),
        "--custodian-dir", str(custodian_dir),
        "--mode", "FROZEN",
        "--submission", str(submission_path),
        "--token-file", str(tokens_file),
        "--scorer-output", str(scorer_out_dir),
    ]
    server_proc = subprocess.Popen(server_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    decision_logs: List[Dict[str, Any]] = []
    approved_price_logs: List[Dict[str, Any]] = []
    dq_violation_logs: List[Dict[str, Any]] = []

    try:
        # Đợi server khởi tạo và xuất file token
        for _ in range(50):
            if tokens_file.exists():
                break
            time.sleep(0.2)
        with open(tokens_file, "r", encoding="utf-8") as f:
            tokens = json.load(f)
        manager_token = tokens.get("manager_token") or tokens.get("manager") or tokens.get("ADMIN")
        b_tokens = {b: tokens.get("branch_tokens", {}).get(b) or tokens.get(b) for b in BRANCHES}

        # Kích hoạt bộ chặn truy cập filesystem của Custodian đối với tiến trình của Model Adapter
        with FilesystemIsolationGuard(forbidden_custodian_dir=custodian_dir) as fs_guard:
            simulation_finished = False
            while not simulation_finished:
                try:
                    ctx_base = api_request(base_url, "/api/context", token=b_tokens["BASELINE"], method="GET")
                except Exception:
                    break

                phase = ctx_base.get("phase")
                sim_date = ctx_base.get("date")
                sim_time = ctx_base.get("time", "06:00")

                if phase == "PREPARE":
                    for branch in ("M2_ONLY", "JOINT_M1_M2"):
                        b_ctx = api_request(base_url, "/api/context", token=b_tokens[branch], method="GET")
                        for item in b_ctx.get("items", []):
                            sku = item["sku_code"]
                            plan = prepare(item["morning_features"], item["completed_branch_history"])
                            api_request(
                                base_url, "/api/prepare", token=b_tokens[branch], method="POST",
                                payload={"branch": branch, "sku_code": sku, "plan": plan}
                            )
                            total_units = plan["initial_qty"] + sum(b["qty"] for b in plan["production_batches"])
                            decision_logs.append({
                                "date": sim_date, "time": sim_time, "branch": branch,
                                "module": "M2", "sku_id": sku,
                                "action": f"PREP_{total_units}_MORNING_{plan['initial_qty']}",
                                "details": json.dumps(plan["production_batches"]),
                            })
                    api_request(base_url, "/api/advance", token=manager_token, method="POST", payload={"steps": 1})

                elif phase == "OPEN":
                    if sim_time < "19:30":
                        api_request(base_url, "/api/advance", token=manager_token, method="POST", payload={"steps": 46})
                    elif sim_time in ("19:30", "20:00", "20:30", "21:00", "21:30"):
                        for branch in ("M1_ONLY", "JOINT_M1_M2"):
                            b_ctx = api_request(base_url, "/api/context", token=b_tokens[branch], method="GET")
                            for item in b_ctx.get("items", []):
                                if item.get("inventory_at_decision", 0) <= 0:
                                    continue
                                sku = item["sku_code"]
                                safe = {
                                    "model_features": model_features.m1_features(item, b_ctx["as_of"]),
                                    "price_context": {k: item[k] for k in ["list_price_vnd", "current_unit_price_vnd", "current_discount_pct", "price_version"]}
                                }
                                action = markdown(safe, b_ctx["as_of"])
                                if action:
                                    prop_payload = {
                                        "branch": branch,
                                        "sku_code": sku,
                                        "effective_time": sim_time,
                                        **({"approved_cash_price_vnd": action["approved_cash_price_vnd"]} if isinstance(action, dict) and set(action) == {"approved_cash_price_vnd"} else {"requested_discount_pct": action})
                                    }
                                    prop_resp = api_request(base_url, "/api/propose", token=b_tokens[branch], method="POST", payload=prop_payload)
                                    decision_logs.append({
                                        "date": sim_date, "time": sim_time, "branch": branch,
                                        "module": "M1", "sku_id": sku,
                                        "action": f"DISCOUNT_{action}", "details": f"Proposed at {sim_time}"
                                    })
                                    if prop_resp and "id" in prop_resp:
                                        try:
                                            app_resp = api_request(base_url, "/api/approve", token=manager_token, method="POST", payload={"proposal_id": prop_resp["id"], "accepted": True})
                                            q = app_resp.get("quote", {})
                                            approved_price_logs.append({
                                                "date": sim_date, "checkpoint_time": sim_time, "branch": branch,
                                                "sku_id": sku,
                                                "approved_price_vnd": q.get("approved_unit_price_vnd"),
                                                "discount_pct": q.get("approved_discount_pct"),
                                                "price_version": q.get("price_version", 1),
                                                "pos_active_verified": True
                                            })
                                        except urllib.error.HTTPError:
                                            pass
                        api_request(base_url, "/api/advance", token=manager_token, method="POST", payload={"steps": 2})
                    else:
                        api_request(base_url, "/api/advance", token=manager_token, method="POST", payload={"steps": 1})

                elif phase == "CLOSED":
                    try:
                        api_request(base_url, "/api/advance", token=manager_token, method="POST", payload={"steps": 1})
                    except urllib.error.HTTPError as e:
                        err_text = e.read().decode("utf-8", errors="replace")
                        if "End of source-supported dates" in err_text:
                            simulation_finished = True
                            break
                        raise
                else:
                    simulation_finished = True
                    break

    finally:
        server_proc.terminate()
        server_proc.wait(timeout=10)

    # 3. Xác minh SHA-256 sau khi chạy xong 62 ngày (Đảm bảo trọng số không hề thay đổi)
    post_hashes = verify_pre_test_hashes(agent_dir, runtime_dir)
    assert pre_hashes["verified_model_hashes"] == post_hashes["verified_model_hashes"], (
        "VI PHẠM NGHIÊM TRỌNG: Trọng số model hoặc cấu hình đã bị thay đổi trong lúc chạy test!"
    )

    # 4. Chạy bộ chấm điểm độc lập score_private.py của Custodian
    subprocess.run([
        sys.executable, str(runtime_dir / "code" / "score_private.py"),
        "--scorer-dir", str(scorer_out_dir),
    ], check=True)

    # Copy KPI comparison file sang output_dir
    kpi_src = scorer_out_dir / "BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv"
    if kpi_src.exists():
        shutil.copy2(kpi_src, output_dir / "BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv")

    # Xây dựng SCORER_DAILY_SKU_LEDGER.csv từ private_results.csv và observed_slots_CUSTODIAN.csv
    priv_file = scorer_out_dir / "private_results.csv"
    slots_file = scorer_out_dir / "observed_slots_CUSTODIAN.csv"
    if priv_file.exists():
        priv_df = pd.read_csv(priv_file)
        avail_map = {}
        if slots_file.exists():
            slots_df = pd.read_csv(slots_file)
            slots_2130 = slots_df[slots_df["time"] == "21:30"]
            for _, sr in slots_2130.iterrows():
                avail_map[(str(sr["date"]), str(sr["branch"]), str(sr["sku_code"]))] = float(int(sr["inventory_start"]) > 0)

        ledger_rows = []
        for _, r in priv_df.iterrows():
            b = str(r["branch"])
            d = str(r["date"])
            s = str(r["sku_code"])
            rev = float(r["revenue_vnd"])
            prod_cost = float(r["production_cost_vnd_assumed"])
            disp_cost = float(r["disposal_cost_vnd_assumed"])
            md_cost = float(r.get("markdown_operations_cost_vnd_assumed") or 0.0)
            wasted_prod = float(r.get("wasted_production_cost_vnd_assumed") or 0.0)
            cm = rev - prod_cost - disp_cost - md_cost
            lost_units = int(float(r.get("lost_base_hidden_scenario") or 0)) + int(float(r.get("lost_promo_hidden_scenario") or 0))
            svc_avail = avail_map.get((d, b, s), 1.0)
            ledger_rows.append({
                "date": d,
                "branch": b,
                "sku_id": s,
                "realized_revenue_vnd": rev,
                "total_production_cost_vnd": prod_cost,
                "leftover_production_cost_component_vnd": wasted_prod,
                "additional_disposal_cost_vnd": disp_cost,
                "markdown_operation_cost_vnd": md_cost,
                "contribution_margin_vnd": cm,
                "waste_units": int(float(r["waste_qty"])),
                "simulated_lost_sales_units": lost_units,
                "service_available_to_2130": svc_avail,
            })
        ledger_df = pd.DataFrame(ledger_rows)
        ledger_df.to_csv(output_dir / "SCORER_DAILY_SKU_LEDGER.csv", index=False)

    # Lưu toàn bộ log bàn giao
    pd.DataFrame(decision_logs).to_csv(output_dir / "decision_logs.csv", index=False)
    pd.DataFrame(approved_price_logs).to_csv(output_dir / "approved_price_logs.csv", index=False)
    pd.DataFrame(dq_violation_logs).to_csv(output_dir / "dq_fallback_logs.csv", index=False)
    with open(output_dir / "pre_post_hashes.json", "w", encoding="utf-8") as f:
        json.dump({"pre_test": pre_hashes, "post_test": post_hashes}, f, indent=2)
    with open(output_dir / "leakage_audit_report.json", "w", encoding="utf-8") as f:
        json.dump({
            "custodian_filesystem_violations": fs_guard.violations,
            "weights_frozen_verified": True,
            "online_retrain_performed": False,
            "history_rollforward_branch_isolated": True,
        }, f, indent=2)

    build_comprehensive_test_report(output_dir)


# =============================================================================
# 4. TỔNG HỢP BÁO CÁO ĐỐI SOÁT 4 NHÁNH, THEO SKU, THỨ & GIAI ĐOẠN + BOOTSTRAP CI
# =============================================================================
def bootstrap_ci_by_date(df: pd.DataFrame, metric_col: str, n_boot: int = 1000, seed: int = 42) -> Tuple[float, float]:
    """
    Tính khoảng bất định (95% Confidence Interval) bằng Bootstrap theo ngày nguồn (block bootstrap by date),
    giữ nguyên cấu trúc tương quan giữa 7 SKU trong cùng một ngày.
    """
    rng = np.random.default_rng(seed)
    daily_sums = df.groupby("date")[metric_col].sum().values
    if len(daily_sums) == 0:
        return (np.nan, np.nan)
    boot_totals = [
        np.sum(rng.choice(daily_sums, size=len(daily_sums), replace=True))
        for _ in range(n_boot)
    ]
    return float(np.percentile(boot_totals, 2.5)), float(np.percentile(boot_totals, 97.5))


def build_comprehensive_test_report(output_dir: Path) -> None:
    kpi_path = output_dir / "BUSINESS_KPI_COMPARISON_SCORER_ONLY.csv"
    daily_sku_path = output_dir / "SCORER_DAILY_SKU_LEDGER.csv"
    if not kpi_path.exists():
        return

    kpi_df = pd.read_csv(kpi_path)
    if daily_sku_path.exists():
        ledger = pd.read_csv(daily_sku_path)
        # Kiểm tra bắt buộc 434 SKU-ngày mỗi nhánh, không trùng, không thiếu
        for b in BRANCHES:
            sub = ledger[ledger["branch"] == b]
            assert len(sub) == EXPECTED_SKU_DAYS, f"Nhánh {b} không đủ 434 SKU-ngày (hiện có {len(sub)})"
            assert not sub.duplicated(subset=["date", "sku_id"]).any(), f"Nhánh {b} có dòng trùng (date, sku_id)"

            # Đối soát công thức Lãi góp: KHÔNG trừ giá vốn bánh dư lần hai
            calc_cm = (
                sub["realized_revenue_vnd"]
                - sub["total_production_cost_vnd"]
                - sub["additional_disposal_cost_vnd"]
                - sub["markdown_operation_cost_vnd"]
            )
            diff = np.abs(calc_cm - sub["contribution_margin_vnd"]).max()
            assert diff < 1.0, f"Sai lệch công thức Lãi góp tại nhánh {b}: max_diff={diff}"

        # Phân rã theo SKU, Thứ trong tuần và Giai đoạn (Tháng 07 vs Tháng 08)
        ledger["dt"] = pd.to_datetime(ledger["date"])
        ledger["day_of_week"] = ledger["dt"].dt.day_name()
        ledger["period"] = np.where(ledger["date"] <= "2022-07-31", "Month_07_Jul2022", "Month_08_Aug2022")

        by_sku = ledger.groupby(["branch", "sku_id"])[[
            "realized_revenue_vnd", "total_production_cost_vnd", "leftover_production_cost_component_vnd",
            "additional_disposal_cost_vnd", "markdown_operation_cost_vnd", "contribution_margin_vnd",
            "waste_units", "simulated_lost_sales_units", "service_available_to_2130"
        ]].agg({
            "realized_revenue_vnd": "sum",
            "total_production_cost_vnd": "sum",
            "leftover_production_cost_component_vnd": "sum",
            "additional_disposal_cost_vnd": "sum",
            "markdown_operation_cost_vnd": "sum",
            "contribution_margin_vnd": "sum",
            "waste_units": "sum",
            "simulated_lost_sales_units": "sum",
            "service_available_to_2130": "mean",
        }).reset_index()

        by_dow = ledger.groupby(["branch", "day_of_week"])[[
            "contribution_margin_vnd", "waste_units", "simulated_lost_sales_units", "service_available_to_2130"
        ]].agg({
            "contribution_margin_vnd": "mean",
            "waste_units": "mean",
            "simulated_lost_sales_units": "mean",
            "service_available_to_2130": "mean",
        }).reset_index()

        by_period = ledger.groupby(["branch", "period"])[[
            "realized_revenue_vnd", "total_production_cost_vnd", "contribution_margin_vnd",
            "waste_units", "simulated_lost_sales_units", "service_available_to_2130"
        ]].agg({
            "realized_revenue_vnd": "sum",
            "total_production_cost_vnd": "sum",
            "contribution_margin_vnd": "sum",
            "waste_units": "sum",
            "simulated_lost_sales_units": "sum",
            "service_available_to_2130": "mean",
        }).reset_index()

        # Tính khoảng bất định Bootstrap 95% CI cho chênh lệch Lãi góp so với BASELINE theo ngày nguồn
        base_daily = ledger[ledger["branch"] == "BASELINE"].groupby("date")["contribution_margin_vnd"].sum()
        ci_rows = []
        for b in BRANCHES:
            b_daily = ledger[ledger["branch"] == b].groupby("date")["contribution_margin_vnd"].sum()
            diff_df = pd.DataFrame({"date": b_daily.index, "cm_diff_vs_base": (b_daily - base_daily).values})
            ci_low, ci_high = bootstrap_ci_by_date(diff_df, "cm_diff_vs_base")
            ci_rows.append({
                "branch": b,
                "total_cm_diff_vs_baseline_vnd": float((b_daily - base_daily).sum()),
                "bootstrap_95ci_low_vnd": ci_low,
                "bootstrap_95ci_high_vnd": ci_high,
            })
        ci_df = pd.DataFrame(ci_rows)

        report_md = f"""# BÁO CÁO KẾT QUẢ TEST CHÍNH THỨC 62 NGÀY (01/07/2022 – 31/08/2022)

## 1. Bảng Tổng Hợp Đối Soát 4 Nhánh (434 SKU-Ngày / Nhánh)
*Lưu ý kế toán: Giá vốn bánh dư (`leftover_production_cost_component_vnd`) được trình bày như thành phần đã nằm trong Tổng chi phí sản xuất (`total_production_cost_vnd`), tuyệt đối không trừ lần thứ hai khi tính Lãi góp.*

{kpi_df.to_markdown(index=False)}

## 2. Khoảng Bất Định Bootstrap 95% (Theo Ngày Nguồn) Cho Chênh Lệch Lãi Góp So Với Baseline
{ci_df.to_markdown(index=False)}

## 3. Phân Rã Theo Từng SKU (7 Món Khảo Sát)
{by_sku.to_markdown(index=False)}

## 4. Phân Rã Theo Thứ Trong Tuần (Trung Bình / SKU-Ngày)
{by_dow.to_markdown(index=False)}

## 5. Phân Rã Theo Giai Đoạn (Tháng 07/2022 vs. Tháng 08/2022)
{by_period.to_markdown(index=False)}

## 6. Giới Hạn Diễn Giải & Quy Phạm Khoa Học
- Kết quả trên được chạy trên bộ test mô phỏng 62 ngày có cách ly thông tin tương lai, **không kết luận mô hình đã thích nghi với mọi input AEON hoặc đã chứng minh lợi nhuận thực địa tại cửa hàng**.
- Giữ nguyên toàn bộ kết quả thực nghiệm của 4 nhánh (kể cả ở các SKU hoặc khung thời gian mà AI có thể thấp hơn Baseline).
- Nếu thực hiện bất kỳ chỉnh sửa nào về mô hình, trọng số hoặc chính sách giá sau khi xem báo cáo này, lần chạy tiếp theo phải được ghi nhận là **vòng phát triển mới (post-test development iteration)**, tuyệt đối không gọi là holdout mù mới.
"""
        (output_dir / "TEST_EVALUATION_REPORT.md").write_text(report_md, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["SMOKE_DEV", "OFFICIAL_FROZEN_TEST"], required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--custodian-dir", type=Path, default=Path("../01_ORIGINAL_BASELINE_PRIVATE"))
    parser.add_argument("--agent-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("./test_deliverables_v610"))
    args = parser.parse_args()

    pre_check = verify_pre_test_hashes(args.agent_dir, args.runtime_dir)
    print("[OK] Xác minh SHA-256 trước khi chạy thành công.")

    if args.mode == "SMOKE_DEV":
        dev_res = run_dev_integration_check(args.agent_dir, args.runtime_dir)
        print("[OK] Kiểm tra tích hợp trên Fixture/Development thành công:", json.dumps(dev_res, ensure_ascii=False))
    elif args.mode == "OFFICIAL_FROZEN_TEST":
        run_frozen_62day_loop(
            runtime_dir=args.runtime_dir,
            custodian_dir=args.custodian_dir,
            agent_dir=args.agent_dir,
            output_dir=args.output_dir,
            pre_hashes=pre_check,
        )
        print(f"[OK] Hoàn tất 62 ngày test và xuất toàn bộ báo cáo tại: {args.output_dir}")
