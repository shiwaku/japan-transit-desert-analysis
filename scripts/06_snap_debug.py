"""
駅・バス停のスナップ先道路ノードを可視化するデバッグスクリプト。

出力:
  output/stations_snap.parquet      駅 + スナップ先ノード座標・距離
  output/busstops_snap.parquet      バス停 + スナップ先ノード座標・距離
  output/stations_snap_lines.parquet  駅 → スナップ先ノードの接続線
  output/busstops_snap_lines.parquet  バス停 → スナップ先ノードの接続線
"""

from pathlib import Path
import numpy as np
import geopandas as gpd
from scipy.spatial import KDTree
from shapely.geometry import LineString, Point
import pyproj

ROOT = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
OUT_DIR   = ROOT / "output"
NODES_PATH = ROOT.parent / "01_MakeNetwork" / "nationwide_walk" / "KSJ_N13-24_nationwide_walk_道路ノード.parquet"

# 緯度経度→メートル距離変換用
geod = pyproj.Geod(ellps="WGS84")

def snap_distance_m(lon1, lat1, lon2, lat2):
    """2点間の測地線距離（m）"""
    _, _, dist = geod.inv(lon1, lat1, lon2, lat2)
    return dist


def make_snap_output(facilities: gpd.GeoDataFrame, nodes: gpd.GeoDataFrame,
                     node_coords: np.ndarray, name_col: str) -> tuple:
    """
    施設をノードにスナップし、点 GDF と接続線 GDF を返す。
    """
    coords = np.array([[p.y, p.x] for p in facilities.geometry])
    _, snap_idx = KDTree(node_coords).query(coords)
    snapped_nodes = nodes.iloc[snap_idx].reset_index(drop=True)

    # スナップ距離（m）
    snap_dist = np.array([
        snap_distance_m(
            facilities.geometry.iloc[i].x, facilities.geometry.iloc[i].y,
            snapped_nodes.geometry.iloc[i].x, snapped_nodes.geometry.iloc[i].y
        )
        for i in range(len(facilities))
    ])

    # 点出力（スナップ先ノード位置に駅・バス停情報を付与）
    fac_reset = facilities.reset_index(drop=True)
    point_gdf = fac_reset.copy()
    point_gdf["snap_node_id"] = snapped_nodes["node_id"].values
    point_gdf["snap_lon"]     = [g.x for g in snapped_nodes.geometry]
    point_gdf["snap_lat"]     = [g.y for g in snapped_nodes.geometry]
    point_gdf["snap_dist_m"]  = np.round(snap_dist, 1)
    point_gdf["snap_geom"]    = snapped_nodes.geometry.values

    # 接続線出力
    lines = [
        LineString([fac_reset.geometry.iloc[i], snapped_nodes.geometry.iloc[i]])
        for i in range(len(fac_reset))
    ]
    line_gdf = fac_reset[[name_col]].copy() if name_col in fac_reset.columns else fac_reset.iloc[:, :1].copy()
    line_gdf["snap_node_id"] = snapped_nodes["node_id"].values
    line_gdf["snap_dist_m"]  = np.round(snap_dist, 1)
    line_gdf = gpd.GeoDataFrame(line_gdf, geometry=lines, crs="EPSG:4326")

    return point_gdf, line_gdf


def main():
    print("ノード読み込み...")
    nodes = gpd.read_parquet(NODES_PATH)
    node_coords = np.array([[p.y, p.x] for p in nodes.geometry])
    print(f"  ノード数: {len(nodes):,}")

    print("駅データ読み込み...")
    stations = gpd.read_parquet(DATA_DIR / "stations.parquet")
    print(f"  駅数: {len(stations):,}")

    print("バス停データ読み込み...")
    busstops = gpd.read_parquet(DATA_DIR / "busstops.parquet")
    print(f"  バス停数: {len(busstops):,}")

    print("駅スナップ処理...")
    st_point, st_lines = make_snap_output(stations, nodes, node_coords, "station_name")
    st_point.to_parquet(OUT_DIR / "stations_snap.parquet")
    st_lines.to_parquet(OUT_DIR / "stations_snap_lines.parquet")
    print(f"  スナップ距離: 平均 {st_point['snap_dist_m'].mean():.1f}m  "
          f"最大 {st_point['snap_dist_m'].max():.1f}m  "
          f"中央値 {st_point['snap_dist_m'].median():.1f}m")

    print("バス停スナップ処理...")
    bs_point, bs_lines = make_snap_output(busstops, nodes, node_coords, "stop_name")
    bs_point.to_parquet(OUT_DIR / "busstops_snap.parquet")
    bs_lines.to_parquet(OUT_DIR / "busstops_snap_lines.parquet")
    print(f"  スナップ距離: 平均 {bs_point['snap_dist_m'].mean():.1f}m  "
          f"最大 {bs_point['snap_dist_m'].max():.1f}m  "
          f"中央値 {bs_point['snap_dist_m'].median():.1f}m")

    # スナップ距離が大きい駅トップ20
    print("\n【駅スナップ距離 上位20件】")
    top = st_point[["station_name", "operator", "line_name", "snap_dist_m"]]\
            .sort_values("snap_dist_m", ascending=False).head(20)
    print(top.to_string(index=False))

    print("\n出力完了:")
    for f in ["stations_snap.parquet", "stations_snap_lines.parquet",
              "busstops_snap.parquet",  "busstops_snap_lines.parquet"]:
        p = OUT_DIR / f
        print(f"  {p}  ({p.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
