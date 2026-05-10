"""
駅・バス停のスナップ先道路ノードを可視化するデバッグスクリプト。

02_calc_transit_desert.py と同じ象限スナップ（NE/NW/SE/SW）を再現する。

出力:
  output/stations_snap.parquet        駅 + スナップ先ノード（1駅あたり最大4象限=4ノード）
  output/busstops_snap.parquet        バス停 + スナップ先ノード
  output/stations_snap_lines.parquet  駅 → スナップ先ノードの接続線
  output/busstops_snap_lines.parquet  バス停 → スナップ先ノードの接続線

使用例:
  # 全駅（デフォルト 500m）
  python3 scripts/06_snap_debug.py

  # 特定駅を絞り込み
  python3 scripts/06_snap_debug.py --filter 北松戸

  # 最大距離を変更
  python3 scripts/06_snap_debug.py --station-max-dist 300 --filter 北松戸
"""

import argparse
from pathlib import Path
import numpy as np
import geopandas as gpd
from scipy.spatial import KDTree
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components as sp_cc
from shapely.geometry import LineString
import pyproj

ROOT = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
OUT_DIR    = ROOT / "output"
NODES_PATH = ROOT.parent / "01_MakeNetwork" / "nationwide_walk" / "KSJ_N13-24_nationwide_walk_道路ノード.parquet"
LINKS_PATH = ROOT.parent / "01_MakeNetwork" / "nationwide_walk" / "KSJ_N13-24_nationwide_walk_道路リンク.parquet"

STATION_QUAD_MAX_DIST_M = 500  # 02_calc_transit_desert.py のデフォルトと合わせる

geod = pyproj.Geod(ellps="WGS84")
QUAD_NAMES = ["NE", "NW", "SE", "SW"]


def snap_distance_m(lon1, lat1, lon2, lat2):
    _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
    return dist

def _m_to_deg(meters):
    return meters / 111_000


def make_snap_quadrant(facilities: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame,
                       node_coords: np.ndarray, name_col: str,
                       max_dist_m: float) -> tuple:
    """
    NE/NW/SE/SW 各象限の最近傍ノードをスナップ（02_calc_transit_desert.py と同実装）。
    """
    max_dist_deg = _m_to_deg(max_dist_m)
    tree = KDTree(node_coords)
    fac_reset = facilities.reset_index(drop=True)
    rows_point = []
    rows_line  = []

    for _, row in fac_reset.iterrows():
        fac_pt = row.geometry
        coord  = np.array([fac_pt.y, fac_pt.x])
        candidates = tree.query_ball_point(coord, r=max_dist_deg)
        if not candidates:
            _, nearest = tree.query([coord])
            candidates = [int(nearest[0])]

        quads: list[list[int]] = [[], [], [], []]
        for ci in candidates:
            nd_lat, nd_lon = node_coords[ci]
            r = 0 if nd_lat >= coord[0] else 2
            c = 0 if nd_lon >= coord[1] else 1
            quads[r + c].append(ci)

        for qi, q in enumerate(quads):
            if not q:
                continue
            q_arr = np.array(q)
            diffs = node_coords[q_arr] - coord
            nearest_in_q = q_arr[int(np.argmin((diffs ** 2).sum(axis=1)))]
            nd = nodes.iloc[nearest_in_q]
            dist = snap_distance_m(fac_pt.x, fac_pt.y,
                                   nd.geometry.x, nd.geometry.y)
            base = {c: row[c] for c in fac_reset.columns if c != "geometry"}
            rows_point.append({**base,
                "quadrant":     QUAD_NAMES[qi],
                "snap_node_id": nd["node_id"],
                "snap_dist_m":  round(dist, 1),
                "geometry":     nd.geometry})
            rows_line.append({
                name_col if name_col in fac_reset.columns else "name":
                    row[name_col] if name_col in fac_reset.columns else "",
                "quadrant":     QUAD_NAMES[qi],
                "snap_node_id": nd["node_id"],
                "snap_dist_m":  round(dist, 1),
                "geometry":     LineString([fac_pt, nd.geometry])})

    return (gpd.GeoDataFrame(rows_point, crs="EPSG:4326"),
            gpd.GeoDataFrame(rows_line,  crs="EPSG:4326"))


def make_snap_nearest(facilities: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame,
                      node_coords: np.ndarray, name_col: str) -> tuple:
    """最近傍1ノードスナップ（バス停用）。"""
    coords = np.array([[p.y, p.x] for p in facilities.geometry])
    _, snap_idx = KDTree(node_coords).query(coords)
    fac_reset = facilities.reset_index(drop=True)
    snapped   = nodes.iloc[snap_idx].reset_index(drop=True)
    rows_point, rows_line = [], []
    for i, row in fac_reset.iterrows():
        nd   = snapped.iloc[i]
        dist = snap_distance_m(row.geometry.x, row.geometry.y,
                               nd.geometry.x, nd.geometry.y)
        base = {c: row[c] for c in fac_reset.columns if c != "geometry"}
        rows_point.append({**base,
            "snap_node_id": nd["node_id"],
            "snap_dist_m":  round(dist, 1),
            "geometry":     nd.geometry})
        rows_line.append({
            name_col if name_col in fac_reset.columns else "name":
                row[name_col] if name_col in fac_reset.columns else "",
            "snap_node_id": nd["node_id"],
            "snap_dist_m":  round(dist, 1),
            "geometry":     LineString([row.geometry, nd.geometry])})
    return (gpd.GeoDataFrame(rows_point, crs="EPSG:4326"),
            gpd.GeoDataFrame(rows_line,  crs="EPSG:4326"))


def main():
    parser = argparse.ArgumentParser(description="駅・バス停スナップデバッグ")
    parser.add_argument("--station-max-dist", type=float, default=STATION_QUAD_MAX_DIST_M,
                        metavar="METERS",
                        help=f"駅象限スナップの最大距離（m）（デフォルト: {STATION_QUAD_MAX_DIST_M}m）")
    parser.add_argument("--filter", type=str, default="", metavar="NAME",
                        help="駅名の部分一致フィルタ（例: 北松戸）。空の場合は全駅")
    args = parser.parse_args()

    print("ノード・リンク読み込み...")
    nodes = gpd.read_parquet(NODES_PATH)
    print(f"  ノード数: {len(nodes):,}")

    # 最大連結成分のノードのみをスナップ対象とする（孤立ノード除外）
    if LINKS_PATH.exists():
        links = gpd.read_parquet(LINKS_PATH)
        n1 = links["node1"].astype(int).to_numpy()
        n2 = links["node2"].astype(int).to_numpy()
        all_nids = list(set(n1.tolist() + n2.tolist()))
        n2i_cc = {nid: i for i, nid in enumerate(all_nids)}
        n_total = len(all_nids)
        rows_idx = np.array([n2i_cc[v] for v in n1], dtype=np.int32)
        cols_idx = np.array([n2i_cc[v] for v in n2], dtype=np.int32)
        g_cc = csr_matrix(
            (np.ones(len(rows_idx), dtype=np.int8), (rows_idx, cols_idx)),
            shape=(n_total, n_total)
        )
        n_comp, labels_cc = sp_cc(g_cc, directed=False)
        comp_sizes_cc = np.bincount(labels_cc)
        large_comps_cc = set(int(i) for i in np.where(comp_sizes_cc >= 1000)[0])
        connected_ids = {nid for nid, i in n2i_cc.items() if labels_cc[i] in large_comps_cc}
        n_isolated = n_total - len(connected_ids)
        print(f"  連結成分数: {n_comp:,}  有効成分数: {len(large_comps_cc):,}  有効ノード: {len(connected_ids):,}  "
              f"孤立ノード除外: {n_isolated:,}件")
        nodes = nodes[nodes["node_id"].astype(int).isin(connected_ids)].reset_index(drop=True)
        print(f"  フィルタ後ノード数: {len(nodes):,}")
    else:
        print(f"  警告: {LINKS_PATH.name} が見つかりません。孤立ノード除外をスキップ")

    node_coords = np.array([[p.y, p.x] for p in nodes.geometry])

    print("駅データ読み込み...")
    stations = gpd.read_parquet(DATA_DIR / "stations.parquet")
    if args.filter:
        stations = stations[stations["station_name"].str.contains(args.filter, na=False)]
        print(f"  フィルタ '{args.filter}': {len(stations):,} 件")
    else:
        print(f"  駅数: {len(stations):,}")

    print("バス停データ読み込み...")
    busstops = gpd.read_parquet(DATA_DIR / "busstops.parquet")
    print(f"  バス停数: {len(busstops):,}")

    print(f"駅スナップ処理（NE/NW/SE/SW 4象限・最大 {args.station_max_dist:.0f}m）...")
    st_point, st_lines = make_snap_quadrant(
        stations, nodes, node_coords, "station_name", max_dist_m=args.station_max_dist)
    st_point.to_parquet(OUT_DIR / "stations_snap.parquet")
    st_lines.to_parquet(OUT_DIR / "stations_snap_lines.parquet")
    print(f"  スナップリンク数: {len(st_lines):,}")
    print(f"  スナップ距離: 平均 {st_point['snap_dist_m'].mean():.1f}m  "
          f"最大 {st_point['snap_dist_m'].max():.1f}m  "
          f"中央値 {st_point['snap_dist_m'].median():.1f}m")

    print("バス停スナップ処理（最近傍1ノード）...")
    bs_point, bs_lines = make_snap_nearest(busstops, nodes, node_coords, "stop_name")
    bs_point.to_parquet(OUT_DIR / "busstops_snap.parquet")
    bs_lines.to_parquet(OUT_DIR / "busstops_snap_lines.parquet")
    print(f"  スナップ距離: 平均 {bs_point['snap_dist_m'].mean():.1f}m  "
          f"最大 {bs_point['snap_dist_m'].max():.1f}m  "
          f"中央値 {bs_point['snap_dist_m'].median():.1f}m")

    if not args.filter:
        print("\n【駅スナップ距離 上位20件】")
        top = st_point[["station_name", "operator", "line_name", "snap_dist_m",
                         "quadrant"]]\
                .sort_values("snap_dist_m", ascending=False).head(20)
        print(top.to_string(index=False))

    print("\n出力完了:")
    for f in ["stations_snap.parquet", "stations_snap_lines.parquet",
              "busstops_snap.parquet",  "busstops_snap_lines.parquet"]:
        p = OUT_DIR / f
        if p.exists():
            print(f"  {p}  ({p.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
