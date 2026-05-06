#!/usr/bin/env python3
"""
都道府県別 公共交通空白率ランキング

transit_desert_with_pop.parquet を都道府県ポリゴンで空間結合し、
カテゴリ別人口をグラフ化する。

出力:
  output/pref_ranking.csv       都道府県別カテゴリ別人口
  output/pref_ranking.png       横棒グラフ（空白率ランキング）
  output/urban_rural_compare.png 東京都 vs 秋田県 比較グラフ
"""

from pathlib import Path
import numpy as np
import pandas as pd
import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

ROOT    = Path(__file__).parent.parent
OUT_DIR = ROOT / "output"
PREF_PARQUET = ROOT.parent / "02_ShortestRouteSearch" / "out" / "prefecture.parquet"

# 日本語フォント
for font in ["Noto Sans CJK JP", "IPAexGothic", "Hiragino Sans", "Yu Gothic", "MS Gothic"]:
    try:
        rcParams["font.family"] = font
        plt.figure(); plt.title("テスト"); plt.close()
        break
    except Exception:
        pass


CATS = ["0_公共交通便利地域", "1_公共交通不便地域", "2_公共交通空白地域"]
COLORS = {"0_公共交通便利地域": "#59CB8F", "1_公共交通不便地域": "#FFC800", "2_公共交通空白地域": "#DC1E1E"}
LABELS = {"0_公共交通便利地域": "便利地域", "1_公共交通不便地域": "不便地域", "2_公共交通空白地域": "空白地域"}


def load_and_join():
    print("transit_desert_with_pop 読み込み...")
    gdf = gpd.read_parquet(OUT_DIR / "transit_desert_with_pop.parquet")
    gdf = gdf[gdf["pop_total"] > 0].copy()
    print(f"  人口あり: {len(gdf):,} メッシュ")

    print("都道府県ポリゴン読み込み・結合...")
    pref = gpd.read_parquet(PREF_PARQUET).to_crs("EPSG:4326")

    # 重心でpoint-in-polygon（高速）
    cents = gdf.copy()
    cents.geometry = gdf.geometry.centroid
    joined = gpd.sjoin(cents[["mesh_code","category","pop_total","pop_65over","geometry"]],
                       pref[["prefecture","geometry"]],
                       how="left", predicate="within")

    # 海上・境界外メッシュは最近傍で補完
    missing = joined["prefecture"].isna()
    if missing.sum() > 0:
        print(f"  sjoin 未割当: {missing.sum()} メッシュ → 最近傍補完")
        nn = gpd.sjoin_nearest(
            cents[missing][["mesh_code","category","pop_total","pop_65over","geometry"]],
            pref[["prefecture","geometry"]], how="left"
        )
        joined.loc[missing, "prefecture"] = nn["prefecture"].values

    return joined


def make_ranking_chart(summary: pd.DataFrame):
    """都道府県別空白率横棒グラフ"""
    pref_total = summary.groupby("prefecture")["pop_total"].sum().rename("total")
    desert = (summary[summary["category"] == "2_公共交通空白地域"]
              .groupby("prefecture")["pop_total"].sum()
              .rename("desert"))
    rate = (desert / pref_total * 100).fillna(0).sort_values(ascending=True)

    fig, ax = plt.subplots(figsize=(10, 14))
    colors = [plt.cm.RdYlGn_r(v / 60) for v in rate.values]
    bars = ax.barh(rate.index, rate.values, color=colors, edgecolor="none", height=0.75)

    # 値ラベル
    for bar, val in zip(bars, rate.values):
        ax.text(val + 0.3, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}%", va="center", ha="left", fontsize=8)

    ax.set_xlabel("公共交通空白地域 人口割合 (%)", fontsize=11)
    ax.set_title("都道府県別 公共交通空白地域人口割合\n（令和2年国勢調査 × 道路ネットワーク距離）",
                 fontsize=13, pad=15)
    ax.set_xlim(0, rate.max() + 8)
    ax.axvline(rate.mean(), color="gray", linestyle="--", linewidth=0.8, alpha=0.7)
    ax.text(rate.mean() + 0.2, -0.5, f"全国平均\n{rate.mean():.1f}%",
            fontsize=8, color="gray", va="top")
    ax.spines[["top","right","bottom"]].set_visible(False)
    ax.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    out = OUT_DIR / "pref_ranking.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out.name}")
    return rate


def make_comparison_chart(joined: gpd.GeoDataFrame, rate: pd.Series):
    """都市 vs 地方 比較グラフ"""
    top_desert  = rate.tail(3).index.tolist()   # 空白率ワースト3
    bottom_desert = rate.head(3).index.tolist() # 空白率ベスト3
    targets = bottom_desert + top_desert

    fig, axes = plt.subplots(2, 3, figsize=(14, 8))
    axes = axes.flatten()

    for ax, pref_name in zip(axes, targets):
        sub = joined[joined["prefecture"] == pref_name]
        total = sub["pop_total"].sum()
        vals, lbls, clrs = [], [], []
        for cat in CATS:
            v = sub[sub["category"] == cat]["pop_total"].sum()
            vals.append(v)
            lbls.append(f"{LABELS[cat]}\n{v/total*100:.1f}%")
            clrs.append(COLORS[cat])
        wedges, texts = ax.pie(vals, labels=None, colors=clrs,
                               startangle=90, wedgeprops=dict(edgecolor="white", linewidth=1))
        r = rate[pref_name]
        ax.set_title(f"{pref_name}\n空白率 {r:.1f}% / {total/10000:.0f}万人",
                     fontsize=10, pad=8)

    # 凡例
    patches = [mpatches.Patch(color=COLORS[c], label=LABELS[c]) for c in CATS]
    fig.legend(handles=patches, loc="lower center", ncol=3, fontsize=10,
               bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("公共交通アクセス分布：都市圏 vs 地方圏（ベスト3 vs ワースト3）",
                 fontsize=13, y=1.01)
    fig.tight_layout()
    out = OUT_DIR / "urban_rural_compare.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  → {out.name}")


def main():
    joined = load_and_join()

    summary = (joined.groupby(["prefecture", "category"])["pop_total"]
               .sum().reset_index())
    summary.to_csv(OUT_DIR / "pref_ranking.csv", index=False, encoding="utf-8-sig")
    print(f"  → pref_ranking.csv")

    print("\n空白率ランキング（上位10）:")
    pref_total = summary.groupby("prefecture")["pop_total"].sum()
    desert = (summary[summary["category"] == "2_公共交通空白地域"]
              .groupby("prefecture")["pop_total"].sum())
    rate_display = (desert / pref_total * 100).sort_values(ascending=False)
    print(rate_display.head(10).apply(lambda x: f"{x:.1f}%").to_string())

    print("\nチャート生成...")
    rate = make_ranking_chart(summary)
    make_comparison_chart(joined, rate)
    print("完了")


if __name__ == "__main__":
    main()
