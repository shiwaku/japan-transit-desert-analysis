#!/usr/bin/env python3
"""
人口集計スクリプト

transit_desert.parquet と 250mメッシュ人口を結合し、
移動難民ゾーンの人口を都道府県別・カテゴリ別に集計する。

入力:
  output/transit_desert.parquet           メッシュ別カテゴリ
  input/mesh250_pop_*.parquet             250mメッシュ人口（都道府県別・e-Stat変換済み）

出力:
  output/transit_desert_with_pop.parquet  人口付きメッシュ
  output/summary_pref.csv                 都道府県別集計
  output/summary_national.csv             全国集計

e-Stat 250mメッシュ人口データ:
  https://www.e-stat.go.jp/gis/statmap-search?page=1&type=2&aggregateUnitForBoundary=Q&toukeiCode=00200521
  令和2年国勢調査 / 250mメッシュ / 全国（都道府県別DL）
  CSV を parquet に変換後 input/ に配置
"""

from pathlib import Path
import pandas as pd
import geopandas as gpd

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "output"
IN_DIR  = ROOT / "input"

QML_CONTENT = """\
<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.34.0" styleCategories="Symbology">
  <renderer-v2 type="categorizedSymbol" attr="category" forceraster="0" symbollevels="0" usingSymbolLevels="0" enableorderby="0">
    <categories>
      <category symbol="0" value="0_公共交通便利地域" label="鉄道駅 walk 1,000m以内" render="true"/>
      <category symbol="1" value="1_公共交通不便地域" label="鉄道駅1,000m超・バス停 500m以内" render="true"/>
      <category symbol="2" value="2_公共交通空白地域" label="鉄道駅1,000m超 AND バス停500m超" render="true"/>
    </categories>
    <symbols>
      <symbol name="0" type="fill" alpha="1" clip_to_extent="1" is_animated="0" frame_rate="10"><data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties><layer class="SimpleFill" enabled="1" pass="0" locked="0"><Option type="Map"><Option name="color" type="QString" value="89,203,143,200"/><Option name="outline_style" type="QString" value="no"/><Option name="style" type="QString" value="solid"/></Option></layer></symbol>
      <symbol name="1" type="fill" alpha="1" clip_to_extent="1" is_animated="0" frame_rate="10"><data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties><layer class="SimpleFill" enabled="1" pass="0" locked="0"><Option type="Map"><Option name="color" type="QString" value="255,200,0,200"/><Option name="outline_style" type="QString" value="no"/><Option name="style" type="QString" value="solid"/></Option></layer></symbol>
      <symbol name="2" type="fill" alpha="1" clip_to_extent="1" is_animated="0" frame_rate="10"><data_defined_properties><Option type="Map"><Option name="name" type="QString" value=""/><Option name="properties"/><Option name="type" type="QString" value="collection"/></Option></data_defined_properties><layer class="SimpleFill" enabled="1" pass="0" locked="0"><Option type="Map"><Option name="color" type="QString" value="220,30,30,200"/><Option name="outline_style" type="QString" value="no"/><Option name="style" type="QString" value="solid"/></Option></layer></symbol>
    </symbols>
    <rotation/><sizescale/>
  </renderer-v2>
  <blendMode>0</blendMode><featureBlendMode>0</featureBlendMode><layerOpacity>1</layerOpacity>
</qgis>
"""


def write_qml():
    qml_path = OUT_DIR / "transit_desert_with_pop.qml"
    qml_path.write_text(QML_CONTENT, encoding="utf-8")
    print(f"  {qml_path.name} 出力")


def load_population():
    """250mメッシュ人口 parquet を読み込む。"""
    pop_path = IN_DIR / "2020_pop_census_mesh250.parquet"
    if not pop_path.exists():
        raise FileNotFoundError(
            f"{pop_path.name} が見つかりません。\n"
            "input/2020_pop_census_mesh250.parquet を配置してください。"
        )
    pop = pd.read_parquet(pop_path, columns=["KEY_CODE", "人口（総数）", "６５歳以上人口　総数"])
    pop = pop.rename(columns={
        "KEY_CODE":        "mesh_code",
        "人口（総数）":         "pop_total",
        "６５歳以上人口　総数":  "pop_65over",
    })
    pop["mesh_code"] = pop["mesh_code"].astype(str).str.zfill(10)
    pop["pop_total"]  = pd.to_numeric(pop["pop_total"],  errors="coerce").fillna(0).astype(int)
    pop["pop_65over"] = pd.to_numeric(pop["pop_65over"], errors="coerce").fillna(0).astype(int)
    return pop[["mesh_code", "pop_total", "pop_65over"]]


def main():
    print("transit_desert.parquet 読み込み...")
    gdf = gpd.read_parquet(OUT_DIR / "transit_desert.parquet")
    gdf["mesh_code"] = gdf["mesh_code"].astype(str).str.zfill(10)
    print(f"  {len(gdf):,} メッシュ")

    print("250mメッシュ人口読み込み...")
    pop = load_population()
    print(f"  {len(pop):,} メッシュ（人口データ）")

    # 結合
    merged = gdf.merge(pop, on="mesh_code", how="left")
    merged["pop_total"] = merged["pop_total"].fillna(0).astype(int)
    if "pop_65over" in merged.columns:
        merged["pop_65over"] = merged["pop_65over"].fillna(0).astype(int)

    # 人口ありメッシュのみに絞り込む
    merged_pop = merged[merged["pop_total"] > 0].copy()
    print(f"  人口あり: {len(merged_pop):,} メッシュ / 全体: {len(merged):,} メッシュ")

    out = OUT_DIR / "transit_desert_with_pop.parquet"
    merged_pop.to_parquet(out)
    print(f"  {out.name} 出力（pop_total > 0 のみ）")

    write_qml()

    # 全国集計（人口ありメッシュのみ）
    national = (
        merged_pop.groupby("category")[["pop_total"]]
        .sum()
        .reset_index()
    )
    if "pop_65over" in merged_pop.columns:
        national = national.merge(
            merged_pop.groupby("category")[["pop_65over"]].sum().reset_index(),
            on="category"
        )
    total_pop = merged_pop["pop_total"].sum()
    national["割合(%)"] = (national["pop_total"] / total_pop * 100).round(1)
    print("\n=== 全国集計 ===")
    print(national.to_string(index=False))
    national.to_csv(OUT_DIR / "summary_national.csv", index=False, encoding="utf-8-sig")

    # 都道府県別集計（mesh_code の先頭4桁 = 1次メッシュ → 都道府県への変換は近似）
    print("\n=== カテゴリ '2_公共交通空白地域' 上位1次メッシュ（人口） ===")
    desert = merged_pop[merged_pop["category"] == "2_公共交通空白地域"].copy()
    if len(desert) > 0:
        desert["mesh1"] = desert["mesh_code"].str[:4]
        by_mesh1 = (
            desert.groupby("mesh1")[["pop_total"]]
            .sum()
            .sort_values("pop_total", ascending=False)
            .head(20)
        )
        print(by_mesh1.to_string())

    by_mesh1_all = (
        merged_pop.groupby(["category", merged_pop["mesh_code"].str[:4]])[["pop_total"]]
        .sum()
        .reset_index()
    )
    by_mesh1_all.to_csv(OUT_DIR / "summary_pref.csv", index=False, encoding="utf-8-sig")
    print(f"\nsummary_pref.csv / summary_national.csv を {OUT_DIR} に出力しました。")


if __name__ == "__main__":
    main()
