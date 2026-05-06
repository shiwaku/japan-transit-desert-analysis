#!/bin/bash
# 公共交通空白地域 全国分析 一括実行スクリプト
#
# 実行前に完了していること:
#   python3 scripts/01_prepare_facilities.py  (stations.parquet / busstops.parquet)
#
# 所要時間（目安）:
#   ① ネットワーク生成  : 3〜5時間
#   ② アクセスリンク生成: 1〜2時間
#   ③ Dijkstra 分析    : 20〜60分
#   合計               : 5〜8時間

set -e  # エラーで停止

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MAKE_NET_DIR="$REPO_ROOT/01_MakeNetwork"
SCRIPT_DIR="$REPO_ROOT/09_/scripts"

echo "======================================"
echo " 公共交通空白地域 全国分析 開始"
echo " $(date)"
echo "======================================"

# ── Step 1: 全国道路ネットワーク生成（全道路・walkモード） ──
echo ""
echo "[Step 1] 全国道路ネットワーク生成..."
echo "  モード: walk（3.6 km/h）, フィルター: なし（全道路）"
echo "  出力先: $MAKE_NET_DIR/nationwide_walk/"
echo "  開始: $(date)"
cd "$MAKE_NET_DIR"
python3 ksj_to_network_csv.py --nationwide --mode walk --case nationwide_walk
echo "  完了: $(date)"

# ── Step 2: L5 アクセスリンク生成 ──
echo ""
echo "[Step 2] L5 アクセスリンク生成..."
echo "  開始: $(date)"
python3 make_access_links.py --nationwide --level 5 --case nationwide_walk
echo "  完了: $(date)"

# ── Step 3: 公共交通空白地域算出（Dijkstra） ──
echo ""
echo "[Step 3] 公共交通空白地域算出（Dijkstra）..."
echo "  開始: $(date)"
cd "$REPO_ROOT/09_"
python3 scripts/02_calc_transit_desert.py
echo "  完了: $(date)"

echo ""
echo "======================================"
echo " 全処理完了: $(date)"
echo " 出力: 09_/output/transit_desert.parquet"
echo "======================================"
