#!/usr/bin/env python3
"""
施設データ準備スクリプト

国土数値情報 S12（駅別乗降客数）・P11（バス停留所）を読み込み、
分析用 GeoDataFrame（parquet）を生成する。

入力（data/ 以下に配置）:
  data/S12/.../*.geojson  or  *.shp   駅別乗降客数（全国・推奨）
  data/N02/.../*.geojson  or  *.shp   鉄道駅（S12 なしの場合フォールバック）
  data/P11/.../*.geojson  or  *.shp   バス停留所（全国）
  data/N07/.../*.geojson  or  *.shp   バス停（P11 なしの場合フォールバック）

出力:
  data/stations.parquet   鉄道駅ポイント（緯度経度）
  data/busstops.parquet   バス停ポイント（緯度経度）

国土数値情報ダウンロード先:
  駅別乗降客数 S12（2024年）: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-S12-2024.html
  バス停留所  P11（2022年）: https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P11.html
  鉄道       N02（代替）  : https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-v3_1.html
  バス停     N07（代替）  : https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N07.html

S12 乗降客数列:
  S12_009=2011年, S12_013=2012年, ..., S12_061=2024年（4列セット×14年）
  MIN_PASSENGERS_PER_DAY 未満の駅を除外する。0 にすると全駅使用。
"""

from pathlib import Path
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

DATA_DIR = Path(__file__).parent.parent / "data"

# 乗降客数フィルタリング閾値（1日あたり・上下計）。0 = フィルターなし（全駅使用）
MIN_PASSENGERS_PER_DAY = 0

# S12 列仕様: 4列セット×14年（2011-2024）。乗降客数は各セットの4列目
# S12_009(2011), S12_013(2012), ..., S12_061(2024)
S12_PASSENGER_COL = "S12_061"   # 2024年（最新）


def load_stations_s12():
    """S12（駅別乗降客数）から鉄道駅ポイントを生成。"""
    # UTF-8 フォルダを優先、なければ全探索
    candidates = sorted(DATA_DIR.glob("S12/**/UTF-8/*.geojson"))
    if not candidates:
        candidates = sorted(DATA_DIR.glob("S12/**/UTF-8/*.shp"))
    if not candidates:
        candidates = (sorted(DATA_DIR.glob("S12/**/*.geojson"))
                      + sorted(DATA_DIR.glob("S12/**/*.shp")))
    if not candidates:
        return None

    gdfs = []
    for p in candidates:
        gdf = gpd.read_file(p)
        if len(gdf) == 0:
            continue

        # LineString → 両端点をポイント化（北口・南口等の複数出口に対応）
        # ホーム線形の start/end がプラットホームの両端に対応するため、
        # 重心1点より実際の出口位置を正確に捕捉できる。
        gdf = gdf.copy()
        orig_crs = gdf.crs
        proj = gdf.to_crs("EPSG:6677")
        rows = []
        for _, row in proj.iterrows():
            geom = row.geometry
            if geom.geom_type == "LineString":
                endpoints = [geom.coords[0], geom.coords[-1]]
            elif geom.geom_type == "MultiLineString":
                lines = list(geom.geoms)
                endpoints = [lines[0].coords[0], lines[-1].coords[-1]]
            else:
                endpoints = [(geom.centroid.x, geom.centroid.y)]
            base = row.drop("geometry").to_dict()
            for pt in endpoints:
                rows.append({**base, "geometry": Point(pt)})
        gdf = gpd.GeoDataFrame(rows, crs="EPSG:6677").to_crs(orig_crs)

        # 乗降客数フィルタリング
        if S12_PASSENGER_COL in gdf.columns and MIN_PASSENGERS_PER_DAY > 0:
            before = len(gdf)
            passengers = pd.to_numeric(gdf[S12_PASSENGER_COL], errors="coerce").fillna(0)
            gdf = gdf[passengers >= MIN_PASSENGERS_PER_DAY].copy()
            print(f"    {p.name}: {before:,} 駅 → {len(gdf):,} 駅 "
                  f"（乗降 {MIN_PASSENGERS_PER_DAY}人/日以上 / {S12_PASSENGER_COL}列）")
        else:
            print(f"    {p.name}: {len(gdf):,} 駅")

        cols = ["geometry"]
        if "S12_001" in gdf.columns:
            gdf = gdf.rename(columns={"S12_001": "station_name", "S12_002": "operator", "S12_003": "line_name"})
            cols += [c for c in ["station_name", "operator", "line_name"] if c in gdf.columns]
        gdfs.append(gdf[cols].copy())

    if not gdfs:
        return None

    combined = pd.concat(gdfs, ignore_index=True)
    stations = gpd.GeoDataFrame(combined, geometry="geometry")
    if stations.crs is None:
        stations = stations.set_crs("EPSG:4326")
    else:
        stations = stations.to_crs("EPSG:4326")
    stations = stations.drop_duplicates(subset=["geometry"])
    return stations


def load_stations_n02():
    """N02（鉄道）から鉄道駅ポイントを生成（S12 フォールバック）。"""
    candidates = (sorted(DATA_DIR.glob("N02/**/*.geojson"))
                  + sorted(DATA_DIR.glob("N02/**/*.shp")))
    if not candidates:
        raise FileNotFoundError(
            "鉄道データが見つかりません。\n"
            f"  S12（推奨）: {DATA_DIR / 'S12/'}\n"
            f"  N02（代替）: {DATA_DIR / 'N02/'}"
        )

    gdfs = []
    for p in candidates:
        gdf = gpd.read_file(p)
        gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
        if len(gdf):
            gdfs.append(gdf[["geometry"]])

    stations = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True), crs="EPSG:4326"
    ).drop_duplicates(subset=["geometry"])
    return stations


def load_busstops_p11():
    """P11（バス停留所）からバス停ポイントを生成。"""
    candidates = (sorted(DATA_DIR.glob("P11/**/*.geojson"))
                  + sorted(DATA_DIR.glob("P11/**/*.shp")))
    if not candidates:
        return None

    gdfs = []
    for p in candidates:
        gdf = gpd.read_file(p)
        gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
        if len(gdf):
            cols = ["geometry"]
            if "P11_001" in gdf.columns:
                gdf = gdf.rename(columns={"P11_001": "stop_name", "P11_002": "operator"})
                cols += [c for c in ["stop_name", "operator"] if c in gdf.columns]
            gdfs.append(gdf[cols].copy())

    if not gdfs:
        return None

    combined = pd.concat(gdfs, ignore_index=True)
    busstops = gpd.GeoDataFrame(combined, geometry="geometry")
    if busstops.crs is None:
        busstops = busstops.set_crs("EPSG:4326")
    else:
        busstops = busstops.to_crs("EPSG:4326")
    busstops = busstops.drop_duplicates(subset=["geometry"])
    return busstops


def load_busstops_n07():
    """N07（バス停）からバス停ポイントを生成（P11 フォールバック）。"""
    candidates = (sorted(DATA_DIR.glob("N07/**/*.geojson"))
                  + sorted(DATA_DIR.glob("N07/**/*.shp")))
    if not candidates:
        raise FileNotFoundError(
            "バス停データが見つかりません。\n"
            f"  P11（推奨）: {DATA_DIR / 'P11/'}\n"
            f"  N07（代替）: {DATA_DIR / 'N07/'}"
        )

    gdfs = []
    for p in candidates:
        gdf = gpd.read_file(p)
        gdf = gdf[gdf.geometry.geom_type == "Point"].copy()
        if len(gdf):
            gdfs.append(gdf[["geometry"]])

    busstops = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True), crs="EPSG:4326"
    ).drop_duplicates(subset=["geometry"])
    return busstops


def main():
    print("鉄道駅データ読み込み...")
    stations = load_stations_s12()
    if stations is not None:
        print(f"  S12 使用: {len(stations):,} 駅")
    else:
        print("  S12 なし → N02 で代替")
        stations = load_stations_n02()
        print(f"  N02 使用: {len(stations):,} 駅")
    stations.to_parquet(DATA_DIR / "stations.parquet")
    print(f"  → stations.parquet")

    print("バス停データ読み込み...")
    busstops = load_busstops_p11()
    if busstops is not None:
        print(f"  P11 使用: {len(busstops):,} バス停")
    else:
        print("  P11 なし → N07 で代替")
        busstops = load_busstops_n07()
        print(f"  N07 使用: {len(busstops):,} バス停")
    busstops.to_parquet(DATA_DIR / "busstops.parquet")
    print(f"  → busstops.parquet")


if __name__ == "__main__":
    main()
