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


def load_population():
    """250mメッシュ人口 parquet を全都道府県分読み込む。"""
    files = sorted(IN_DIR.glob("mesh250_pop_*.parquet"))
    if not files:
        # CSV フォールバック
        files = sorted(IN_DIR.glob("mesh250_pop_*.csv"))
    if not files:
        raise FileNotFoundError(
            f"250mメッシュ人口ファイルが見つかりません: {IN_DIR}\n"
            "e-Stat から令和2年国勢調査 250mメッシュ人口をダウンロードし、\n"
            "mesh250_pop_{{都道府県コード}}.parquet として input/ に配置してください。"
        )

    dfs = []
    for f in files:
        if f.suffix == ".parquet":
            df = pd.read_parquet(f)
        else:
            df = pd.read_csv(f, dtype=str)
        dfs.append(df)
    pop = pd.concat(dfs, ignore_index=True)

    # 列名を統一（e-Stat CSVは列名がバラバラな場合があるため）
    col_map = {}
    for col in pop.columns:
        cl = col.lower()
        if "mesh" in cl and "code" in cl:
            col_map[col] = "mesh_code"
        elif cl in ("popt", "総人口", "pop_total", "population"):
            col_map[col] = "pop_total"
        elif "65" in cl and ("over" in cl or "以上" in cl):
            col_map[col] = "pop_65over"
    pop = pop.rename(columns=col_map)

    if "mesh_code" not in pop.columns:
        raise ValueError(f"mesh_code 列が見つかりません。列名: {list(pop.columns)}")
    if "pop_total" not in pop.columns:
        raise ValueError(f"pop_total 列が見つかりません。列名: {list(pop.columns)}")

    pop["mesh_code"] = pop["mesh_code"].astype(str).str.zfill(10)
    pop["pop_total"] = pd.to_numeric(pop["pop_total"], errors="coerce").fillna(0).astype(int)
    if "pop_65over" in pop.columns:
        pop["pop_65over"] = pd.to_numeric(pop["pop_65over"], errors="coerce").fillna(0).astype(int)

    return pop[["mesh_code"] + [c for c in ["pop_total", "pop_65over"] if c in pop.columns]]


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
