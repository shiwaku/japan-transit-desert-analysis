#!/usr/bin/env python3
"""
公共交通空白地域算出スクリプト（道路距離版）

各250mメッシュについて：
  ① 最寄りバス停までの道路距離（walkモード・Multi-source Dijkstra）
  ② 最寄り鉄道駅までの道路距離（walkモード・Multi-source Dijkstra）
を計算し、国土交通省定義に基づく公共交通カテゴリを判定する。

判定基準（国土交通省 国土数値情報QGISマニュアル 2025年4月準拠）:
  公共交通便利地域: 最寄り鉄道駅 walk 1,000m以内（≒16.7分）
  公共交通不便地域: 鉄道駅 1,000m超・最寄りバス停 walk 500m以内（≒8.3分）
  公共交通空白地域: 鉄道駅 1,000m超 AND バス停 500m超

入力:
  data/stations.parquet               鉄道駅ポイント（S12）
  data/busstops.parquet               バス停ポイント（P11）
  ../01_MakeNetwork/nationwide_walk/  全国walkモード道路ネットワーク
    KSJ_N13-24_nationwide_walk_道路リンク.parquet
    KSJ_N13-24_nationwide_walk_道路ノード.parquet
    KSJ_N13-24_nationwide_walk_アクセスリンク_L5.parquet

出力:
  output/transit_desert.parquet       250mメッシュ別判定結果
  output/transit_desert.qml          QGISスタイル（3カテゴリ）

ネットワーク生成コマンド（初回のみ・run_analysis.sh で自動実行）:
  python3 ksj_to_network_csv.py --nationwide --mode walk --case nationwide_walk
  python3 make_access_links.py   --nationwide --level 5  --case nationwide_walk
"""

import argparse
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix, coo_matrix
from scipy.sparse import vstack as sp_vstack
from scipy.sparse.csgraph import dijkstra as sp_dijkstra
from scipy.sparse.csgraph import connected_components as sp_cc
from scipy.spatial import KDTree
from shapely.geometry import box as sbox

ROOT     = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
OUT_DIR  = ROOT / "output"
OUT_DIR.mkdir(exist_ok=True)

NATIONWIDE_WALK_DIR = ROOT.parent / "01_MakeNetwork" / "nationwide_walk"
LINKS_PATH  = NATIONWIDE_WALK_DIR / "KSJ_N13-24_nationwide_walk_道路リンク.parquet"
NODES_PATH  = NATIONWIDE_WALK_DIR / "KSJ_N13-24_nationwide_walk_道路ノード.parquet"
ACCESS_PATH = NATIONWIDE_WALK_DIR / "KSJ_N13-24_nationwide_walk_アクセスリンク_L5.parquet"

# walk 3.6 km/h = 60 m/分 での距離閾値（分）
BUS_MIN     = 500  / 60   # 8.33分（500m相当）
STATION_MIN = 1000 / 60   # 16.67分（1,000m相当）

# 駅スナップ 象限探索の最大距離（m）: --station-max-dist で上書き可能
# 各S12端点から NE/NW/SE/SW 4象限それぞれの最近傍ノードを採用する。
# 線路をまたいだ東西口・南北口を確実にカバーするための実装。
STATION_QUAD_MAX_DIST_M = 500

def _m_to_deg(meters: float) -> float:
    """メートル → 度変換（緯度方向近似・日本緯度帯）。"""
    return meters / 111_000


def build_graph(links: gpd.GeoDataFrame):
    """道路リンクから scipy CSR グラフを構築。"""
    n1 = links["node1"].astype(int).to_numpy()
    n2 = links["node2"].astype(int).to_numpy()
    ws = links["time_001min"].astype(float).to_numpy() * 0.01  # 分単位

    src = np.concatenate([n1, n2])
    dst = np.concatenate([n2, n1])
    w   = np.concatenate([ws, ws])

    unique = np.unique(np.concatenate([src, dst]))
    n2i    = {int(n): i for i, n in enumerate(unique.tolist())}
    nv     = len(unique)

    rows = np.array([n2i[int(n)] for n in src], dtype=np.int32)
    cols = np.array([n2i[int(n)] for n in dst], dtype=np.int32)
    G    = csr_matrix((w, (rows, cols)), shape=(nv, nv))
    return unique, n2i, G


def multisource_dijkstra(G: csr_matrix, source_idxs: np.ndarray) -> np.ndarray:
    """
    スーパーソースノードを追加して全始点を同時投入する Multi-source Dijkstra。
    戻り値: shape=(G.shape[0],)  各ノードの最近傍始点（駅/バス停）までの最短時間（分）
    """
    nv = G.shape[0]
    super_row = np.zeros(len(source_idxs), dtype=np.int32)
    super_col = source_idxs.astype(np.int32)
    super_w   = np.zeros(len(source_idxs), dtype=np.float64)

    extra = coo_matrix(
        (super_w, (super_row, super_col)),
        shape=(1, nv + 1)
    ).tocsr()

    G_pad = csr_matrix(
        (G.data, G.indices, G.indptr),
        shape=(nv, nv + 1)
    )
    G_ext = sp_vstack([G_pad, extra], format="csr")

    dist = sp_dijkstra(G_ext, directed=True, indices=nv)
    return dist[:nv]


def snap_to_nodes(coords: np.ndarray, node_coords: np.ndarray,
                  nodes_df: gpd.GeoDataFrame, n2i: dict) -> np.ndarray:
    """バス停を最近傍1道路ノードにスナップし、グラフインデックスを返す。"""
    tree = KDTree(node_coords)
    _, snap_idx = tree.query(coords)
    snap_nids = nodes_df.iloc[snap_idx]["node_id"].astype(int).to_numpy()
    idxs = np.array([n2i[int(nid)] for nid in snap_nids if int(nid) in n2i],
                    dtype=np.int32)
    return np.unique(idxs)


def snap_to_nodes_quadrant(coords: np.ndarray, node_coords: np.ndarray,
                            nodes_df: gpd.GeoDataFrame, n2i: dict,
                            max_dist_m: float = STATION_QUAD_MAX_DIST_M) -> np.ndarray:
    """
    各駅ポイントについて NE/NW/SE/SW 4象限の最近傍道路ノードをスナップ。
    線路をまたいだ東西口・南北口を確実にカバーするための実装。

    象限の定義（駅座標を原点として）:
      NE: lat >= 駅 AND lon >= 駅
      NW: lat >= 駅 AND lon <  駅
      SE: lat <  駅 AND lon >= 駅
      SW: lat <  駅 AND lon <  駅

    max_dist_m 以内のノードのみ対象。象限内にノードがなければその象限はスキップ。
    全象限にノードがなければ（孤立エリア等）最近傍1ノードにフォールバック。
    """
    max_dist_deg = _m_to_deg(max_dist_m)
    tree = KDTree(node_coords)
    snap_set = set()

    for coord in coords:
        lat, lon = coord
        candidates = tree.query_ball_point(coord, r=max_dist_deg)
        if not candidates:
            _, nearest = tree.query([coord])
            nid = int(nodes_df.iloc[int(nearest[0])]["node_id"])
            if nid in n2i:
                snap_set.add(n2i[nid])
            continue

        # 4象限に分類: インデックス 0=NE, 1=NW, 2=SE, 3=SW
        quads: list[list[int]] = [[], [], [], []]
        for ci in candidates:
            nd_lat, nd_lon = node_coords[ci]
            row = 0 if nd_lat >= lat else 2
            col = 0 if nd_lon >= lon else 1
            quads[row + col].append(ci)

        # 各象限の最近傍ノードを採用
        for q in quads:
            if not q:
                continue
            q_arr = np.array(q)
            diffs = node_coords[q_arr] - coord
            nearest_in_q = q_arr[int(np.argmin((diffs ** 2).sum(axis=1)))]
            nid = int(nodes_df.iloc[nearest_in_q]["node_id"])
            if nid in n2i:
                snap_set.add(n2i[nid])

    return np.unique(np.array(list(snap_set), dtype=np.int32))


def main(station_max_dist_m: float = STATION_QUAD_MAX_DIST_M):
    t0 = time.time()
    print(f"駅スナップ: NE/NW/SE/SW 4象限 各最近傍1ノード（最大 {station_max_dist_m:.0f}m）")

    # ── 施設データ読み込み ──
    print("施設データ読み込み...")
    stations = gpd.read_parquet(DATA_DIR / "stations.parquet")
    busstops = gpd.read_parquet(DATA_DIR / "busstops.parquet")
    print(f"  鉄道駅: {len(stations):,}  バス停: {len(busstops):,}")

    # ── 道路ネットワーク読み込み ──
    print("道路ネットワーク読み込み...")
    for p in (LINKS_PATH, NODES_PATH, ACCESS_PATH):
        if not p.exists():
            raise FileNotFoundError(
                f"{p.name} が見つかりません。\n"
                "run_analysis.sh を実行するか、以下を先に実行してください:\n"
                "  python3 ksj_to_network_csv.py --nationwide --mode walk --case nationwide_walk\n"
                "  python3 make_access_links.py   --nationwide --level 5  --case nationwide_walk"
            )
    links  = gpd.read_parquet(LINKS_PATH)
    nodes  = gpd.read_parquet(NODES_PATH)
    access = gpd.read_parquet(ACCESS_PATH)
    print(f"  リンク: {len(links):,}  ノード: {len(nodes):,}  "
          f"アクセス: {len(access):,}  ({time.time()-t0:.1f}s)")

    # ── グラフ構築 ──
    print("グラフ構築...")
    unique_nodes, n2i, G = build_graph(links)
    print(f"  グラフ: ノード {G.shape[0]:,} / エッジ {G.nnz:,}  ({time.time()-t0:.1f}s)")

    # 最大連結成分のノードのみをスナップ対象とする（孤立ノード除外）
    print("連結成分解析...")
    n_comp, comp_labels = sp_cc(G, directed=False)
    comp_sizes = np.bincount(comp_labels)
    large_comps = set(int(i) for i in np.where(comp_sizes >= 1000)[0])
    connected_node_ids = set(unique_nodes[np.isin(comp_labels, list(large_comps))].tolist())
    n_isolated = len(unique_nodes) - len(connected_node_ids)
    print(f"  連結成分数: {n_comp:,}  有効成分数: {len(large_comps):,}  有効ノード: {len(connected_node_ids):,}  "
          f"孤立ノード除外: {n_isolated:,}件  ({time.time()-t0:.1f}s)")

    # 駅・バス停スナップ用ノードを最大連結成分に限定
    nodes_conn = nodes[nodes["node_id"].astype(int).isin(connected_node_ids)].reset_index(drop=True)
    node_coords_conn = np.array([[p.y, p.x] for p in nodes_conn.geometry])

    # ── ① 駅 Multi-source Dijkstra ──
    print("駅 → 全ノード Dijkstra（Multi-source）...")
    st_coords  = np.array([[p.y, p.x] for p in stations.geometry])
    st_idxs    = snap_to_nodes_quadrant(st_coords, node_coords_conn, nodes_conn, n2i,
                                         max_dist_m=station_max_dist_m)
    print(f"  スナップ駅ノード数: {len(st_idxs):,}")
    dist_station_node = multisource_dijkstra(G, st_idxs)
    print(f"  完了  ({time.time()-t0:.1f}s)")

    # ── ② バス停 Multi-source Dijkstra ──
    print("バス停 → 全ノード Dijkstra（Multi-source）...")
    bs_coords  = np.array([[p.y, p.x] for p in busstops.geometry])
    bs_idxs    = snap_to_nodes(bs_coords, node_coords_conn, nodes_conn, n2i)  # 最近傍1ノード
    print(f"  スナップバス停数: {len(bs_idxs):,}")
    dist_bus_node = multisource_dijkstra(G, bs_idxs)
    print(f"  完了  ({time.time()-t0:.1f}s)")

    # ── アクセスリンク経由でメッシュ単位の距離に変換 ──
    print("メッシュ距離変換...")
    mesh_codes = access["mesh_code"].astype(str).to_numpy()
    road_nids  = access["road_node"].astype(int).to_numpy()
    acc_time   = access["time_001min"].astype(float).to_numpy() * 0.01  # 分

    graph_idxs = np.array([n2i.get(int(n), -1) for n in road_nids], dtype=np.int32)
    valid      = graph_idxs >= 0
    safe_idxs  = np.where(valid, graph_idxs, 0)

    dist_station = np.where(valid,
                            dist_station_node[safe_idxs] + acc_time, np.inf)
    dist_bus     = np.where(valid,
                            dist_bus_node[safe_idxs]     + acc_time, np.inf)

    # ── 判定 ──
    far_station = dist_station > STATION_MIN
    far_bus     = dist_bus     > BUS_MIN
    category = np.where(
        ~far_station,   "0_公共交通便利地域",
        np.where(~far_bus, "1_公共交通不便地域",
                            "2_公共交通空白地域")
    )

    # ── L5ポリゴン生成 ──
    print("メッシュポリゴン生成...")
    codes_s = pd.Series(mesh_codes).str.zfill(10)
    pp_ = codes_s.str[0:2].astype(int).values
    qq_ = codes_s.str[2:4].astype(int).values
    r_  = codes_s.str[4].astype(int).values
    s_  = codes_s.str[5].astype(int).values
    t_  = codes_s.str[6].astype(int).values
    u_  = codes_s.str[7].astype(int).values
    v_  = codes_s.str[8].astype(int).values
    w_  = codes_s.str[9].astype(int).values
    dlat2 = (2/3)/8;  dlon2 = 1.0/8
    dlat3 = dlat2/10; dlon3 = dlon2/10
    dlat4 = dlat3/2;  dlon4 = dlon3/2
    dlat5 = dlat4/2;  dlon5 = dlon4/2
    lats_sw = pp_/1.5 + r_*dlat2 + t_*dlat3 + ((v_-1)//2)*dlat4 + ((w_-1)//2)*dlat5
    lons_sw = (qq_+100).astype(float) + s_*dlon2 + u_*dlon3 + ((v_-1)%2)*dlon4 + ((w_-1)%2)*dlon5
    geoms = [sbox(lo, la, lo+dlon5, la+dlat5)
             for lo, la in zip(lons_sw, lats_sw)]

    # ── 出力 ──
    gdf = gpd.GeoDataFrame({
        "mesh_code":         mesh_codes,
        "dist_bus_min":      np.where(np.isfinite(dist_bus),
                                      np.round(dist_bus, 2), np.nan),
        "dist_station_min":  np.where(np.isfinite(dist_station),
                                      np.round(dist_station, 2), np.nan),
        "far_bus":           far_bus,
        "far_station":       far_station,
        "category":          category,
    }, geometry=geoms, crs="EPSG:4326")

    out_parquet = OUT_DIR / "transit_desert.parquet"
    gdf.to_parquet(out_parquet)
    print(f"\n{out_parquet.name}: {len(gdf):,} メッシュ")
    for cat, grp in gdf.groupby("category"):
        print(f"  {cat}: {len(grp):,} メッシュ")

    write_qml(OUT_DIR / "transit_desert.qml")
    print(f"\ntransit_desert.qml 出力")
    print(f"総処理時間: {time.time()-t0:.1f}s")


def write_qml(path: Path):
    cats = [
        ("0_公共交通便利地域", "89,203,143,200",  "鉄道駅 walk 1,000m以内"),
        ("1_公共交通不便地域", "255,200,0,200",   "鉄道駅1,000m超・バス停 500m以内"),
        ("2_公共交通空白地域", "220,30,30,200",   "鉄道駅1,000m超 AND バス停500m超"),
    ]
    cat_xml = "\n".join(
        f'      <category symbol="{i}" value="{v}" label="{l}" render="true"/>'
        for i, (v, _, l) in enumerate(cats)
    )
    sym_xml = "\n".join(
        f'      <symbol name="{i}" type="fill" alpha="1" clip_to_extent="1"'
        f' is_animated="0" frame_rate="10">'
        f'<data_defined_properties><Option type="Map">'
        f'<Option name="name" type="QString" value=""/>'
        f'<Option name="properties"/>'
        f'<Option name="type" type="QString" value="collection"/>'
        f'</Option></data_defined_properties>'
        f'<layer class="SimpleFill" enabled="1" pass="0" locked="0">'
        f'<Option type="Map">'
        f'<Option name="color" type="QString" value="{c}"/>'
        f'<Option name="outline_style" type="QString" value="no"/>'
        f'<Option name="style" type="QString" value="solid"/>'
        f'</Option></layer></symbol>'
        for i, (_, c, _) in enumerate(cats)
    )
    content = (
        "<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>\n"
        '<qgis version="3.34.0" styleCategories="Symbology">\n'
        '  <renderer-v2 type="categorizedSymbol" attr="category"'
        ' forceraster="0" symbollevels="0" usingSymbolLevels="0" enableorderby="0">\n'
        '    <categories>\n' + cat_xml + '\n    </categories>\n'
        '    <symbols>\n' + sym_xml + '\n    </symbols>\n'
        '    <rotation/><sizescale/>\n  </renderer-v2>\n'
        '  <blendMode>0</blendMode><featureBlendMode>0</featureBlendMode>'
        '<layerOpacity>1</layerOpacity>\n</qgis>\n'
    )
    path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="公共交通空白地域算出スクリプト（道路距離版）"
    )
    parser.add_argument(
        "--station-max-dist", type=float,
        default=STATION_QUAD_MAX_DIST_M,
        metavar="METERS",
        help=f"駅スナップ 象限探索の最大距離（m）（デフォルト: {STATION_QUAD_MAX_DIST_M}m）",
    )
    args = parser.parse_args()
    main(station_max_dist_m=args.station_max_dist)
