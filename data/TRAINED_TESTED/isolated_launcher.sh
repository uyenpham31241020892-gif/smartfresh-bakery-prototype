#!/usr/bin/env bash
set -euo pipefail

# ==============================================================================
# CẤU HÌNH CÁCH LY QUYỀN FILESYSTEM GIỮA CUSTODIAN VÀ MODEL AGENT
# ==============================================================================
WORKSPACE_ROOT="$(pwd)"
RUNTIME_DIR="${WORKSPACE_ROOT}/03_TEST_POS_RUNTIME"
CUSTODIAN_DIR="${WORKSPACE_ROOT}/01_ORIGINAL_BASELINE_PRIVATE"
FROZEN_ZIP="${WORKSPACE_ROOT}/TRAINED_MODELS_FROZEN.zip"
AGENT_WORK_DIR="${WORKSPACE_ROOT}/agent_sandbox"

echo "[1/4] Giải nén gói model đã khóa vào vùng sandbox của Agent..."
mkdir -p "${AGENT_WORK_DIR}"
unzip -o "${FROZEN_ZIP}" -d "${AGENT_WORK_DIR}"

echo "[2/4] Kiểm tra cách ly: Đảm bảo thư mục Custodian không nằm trong AGENT_WORK_DIR..."
if [ -d "${CUSTODIAN_DIR}" ]; then
    # Nếu chạy trên Linux với quyền quản trị, khóa quyền đọc của user chạy agent đối với CUSTODIAN_DIR
    chmod 700 "${CUSTODIAN_DIR}" || true
fi

echo "[3/4] Chạy kiểm tra tích hợp trên Fixture/Development trước khi mở Test..."
python3 run_official_test_62days.py \
    --mode SMOKE_DEV \
    --runtime-dir "${RUNTIME_DIR}" \
    --agent-dir "${AGENT_WORK_DIR}"

echo "[4/4] Khởi chạy đánh giá chính thức 62 ngày (01/07/2022 - 31/08/2022) cho 4 nhánh..."
python3 run_official_test_62days.py \
    --mode OFFICIAL_FROZEN_TEST \
    --runtime-dir "${RUNTIME_DIR}" \
    --custodian-dir "${CUSTODIAN_DIR}" \
    --agent-dir "${AGENT_WORK_DIR}" \
    --output-dir "${WORKSPACE_ROOT}/test_deliverables_v610"

