#!/usr/bin/env python3
"""
transit_desert_with_pop.parquet → GeoJSON 変換（tippecanoe 用）

人口のあるメッシュのみ出力してファイルサイズを抑える。
出力後 tippecanoe で PMTiles に変換する。

出力:
  output/transit_desert_web_250m.geojson  (tippecanoe 入力用)
  output/transit_desert_250m.pmtiles      (tippecanoe 実行後)
"""

from pathlib import Path
import json
import numpy as np
import geopandas as gpd
import pandas as pd

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "output"

CATEGORY_CODE = {
    "0_公共交通便利地域": 0,
    "1_公共交通不便地域": 1,
    "2_公共交通空白地域": 2,
}


def main():
    print("transit_desert_with_pop 読み込み...")
    gdf = gpd.read_parquet(OUT_DIR / "transit_desert_with_pop.parquet")
    print(f"  全メッシュ: {len(gdf):,}")

    # 人口ありのメッシュのみ（約116万件）
    gdf_pop = gdf[gdf["pop_total"] > 0].copy()
    print(f"  人口あり: {len(gdf_pop):,}")

    # 必要な列だけ残してシリアライズを軽量化
    gdf_out = gdf_pop[["mesh_code", "category", "pop_total", "pop_65over",
                        "dist_bus_min", "dist_station_min", "geometry"]].copy()
    gdf_out["cat_code"] = gdf_out["category"].map(CATEGORY_CODE)
    gdf_out["dist_bus_min"]     = gdf_out["dist_bus_min"].round(1).fillna(-1)
    gdf_out["dist_station_min"] = gdf_out["dist_station_min"].round(1).fillna(-1)

    out_path = OUT_DIR / "transit_desert_web_250m.geojson"
    print(f"GeoJSON 出力中 → {out_path.name} ...")
    gdf_out.to_file(out_path, driver="GeoJSON")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"  完了: {size_mb:.0f} MB")

    print("\n次のコマンドで PMTiles に変換してください:")
    pmtiles_path = OUT_DIR / "transit_desert_250m.pmtiles"
    cmd = (
        f"tippecanoe \\\n"
        f"  -Z 4 -z 13 \\\n"
        f"  -l transit_desert \\\n"
        f"  --no-tile-size-limit \\\n"
        f"  --no-feature-limit \\\n"
        f"  --coalesce-densest-as-needed \\\n"
        f"  --force \\\n"
        f"  -P \\\n"
        f"  -o {pmtiles_path} \\\n"
        f"  {out_path}"
    )
    print(cmd)

    # コマンドをファイルに保存
    sh_path = OUT_DIR / "make_pmtiles.sh"
    sh_path.write_text(f"#!/bin/bash\n{cmd}\n")
    sh_path.chmod(0o755)
    print(f"\n→ {sh_path.name} に保存済み。bash output/make_pmtiles.sh で実行できます。")


if __name__ == "__main__":
    main()
