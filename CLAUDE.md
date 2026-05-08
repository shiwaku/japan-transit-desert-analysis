# 公共交通空白地域分析 — Claude Code 向けプロジェクト仕様

## 概要

「車がないと生活できない地域（公共交通空白地域）」を全国250mメッシュで可視化し、該当人口を定量化する。

### 国土交通省による定義

出典: **国土数値情報とQGISを活用した交通空白地の抽出と人口分析**（国土交通省 政策統括官付 地理空間情報課、2025年4月）
URL: https://nlftp.mlit.go.jp/ksj/manual/QGIS_manual_01.htm

参考: **「交通空白」解消に関する取組**（国土交通省）
URL: https://www.mlit.go.jp/sogoseisaku/transport/sosei_transport_tk_000237.html

```
公共交通便利地域: 最寄り鉄道駅 1,000m以内
公共交通不便地域: 最寄り鉄道駅 1,000m超・最寄りバス停 500m以内
公共交通空白地域: 最寄り鉄道駅 1,000m超 AND 最寄りバス停 500m超  ← 車がないと生活できない地域
```

距離は**道路ネットワーク上の徒歩距離**（walk 3.6 km/h、Multi-source Dijkstra）。

### 公式定義との相違点・優位点

| 項目 | 国交省公式手順 | 本分析 |
|---|---|---|
| 距離計算 | 直線距離（ユークリッド） | **道路ネットワーク距離（Dijkstra）** |
| 駅データ | N02（全駅） | **S12（全駅・乗降客数情報付き）** |
| バス停データ | N07 | **P11（都道府県別最新）** |
| メッシュ解像度 | 250mまたは500m | **250m固定** |

**優位点**:
- 川・山で隔てられた「直線は近いが実際には遠い」エリアを正確に捕捉
- S12を使用することで駅名・運営者・乗降客数などの属性情報を保持できる
- 全処理スクリプト化で再現・更新が容易

### 分析結果（令和2年国勢調査・2026年5月実行）

駅スナップ: S12ホーム線形両端点 → 最近傍1道路ノード（スナップノード数: 18,801）

| カテゴリ | 人口 | 割合 |
|---|---|---|
| 公共交通便利地域 | 5,181万人 | 41.1% |
| 公共交通不便地域 | 5,503万人 | 43.7% |
| **公共交通空白地域** | **1,910万人** | **15.2%** |

65歳以上では **611万人**（高齢者全体の17.3%）が空白地域に居住。

## ディレクトリ構成

```
09_transit-desert-analysis/
├── CLAUDE.md
├── README.md                      # GitHubリポジトリ向け概要説明
├── design.md                      # 設計書（定義・アルゴリズム・データフロー・実測値）
├── run_analysis.sh                # 全処理一括実行スクリプト（Step1〜3）
├── Makefile                       # make all / make facilities 等
├── requirements.txt               # Python依存パッケージ
├── LICENSE                        # MIT
├── scripts/
│   ├── 01_prepare_facilities.py   # S12/P11 → stations/busstops.parquet（名称列付き）
│   ├── 02_calc_transit_desert.py  # Multi-source Dijkstra → transit_desert.parquet
│   ├── 03_aggregate.py            # 人口結合・pop_total>0フィルタ → transit_desert_with_pop.parquet
│   ├── 04_pref_ranking.py         # 都道府県別空白率ランキング・可視化
│   └── 05_export_geojson.py       # GeoJSON出力 + tippecanoe PMTiles変換
├── docs/
│   ├── index.html                 # MapLibre GL JS ウェブビューワー（住所検索・スマホ対応）
│   └── pale.json                  # 国土地理院ベクトルタイル淡色スタイル
├── data/
│   ├── S12/                       # 駅別乗降客数（要ダウンロード）
│   ├── P11/                       # バス停留所（要ダウンロード）
│   ├── stations.parquet           # 生成済み鉄道駅ポイント（19,854件・S12ホーム線形の両端点・駅名・運営者・路線名付き）
│   └── busstops.parquet           # 生成済みバス停ポイント（242,985件・バス停名・バス会社名付き）
├── input/
│   └── mesh250_pop_00.parquet     # 250mメッシュ人口（e-Stat 令和2年国勢調査）
└── output/
    ├── transit_desert.parquet          # 全メッシュ別カテゴリ（5,935,127件・184MB）
    ├── transit_desert.qml              # QGISスタイル（全件用・3色）
    ├── transit_desert_with_pop.parquet # 人口ありメッシュのみ（1,155,496件・45MB・QGIS推奨）
    ├── transit_desert_with_pop.qml     # QGISスタイル（人口あり用・categorized）
    ├── transit_desert.pmtiles          # ウェブ公開用PMTiles（204MB・S3配置済み）
    ├── make_pmtiles.sh                 # tippecanoe実行スクリプト
    ├── summary_national.csv            # 全国集計
    ├── summary_pref.csv                # 1次メッシュ別集計
    ├── pref_ranking.csv                # 都道府県別空白率ランキング
    ├── pref_ranking.png                # 空白率ランキング横棒グラフ
    ├── urban_rural_compare.png         # 都市vs地方の3色パイチャート比較
    └── Map.qgz                         # QGISプロジェクト
```

## 国交省公表数値との比較

| 比較項目 | 国交省 QGIS手順（2025年4月） | 本試算 |
|---|---|---|
| **公共交通空白地域 人口** | **約735万人（5.8%）** | **約1,910万人（15.2%）** |
| 距離計算方法 | 直線距離（バッファ） | 道路ネットワーク距離（Dijkstra） |
| 駅データ | N02（2023年） | S12（2024年・ホーム線形両端点） |
| バス停データ | P11（2022年） | P11（2022年）同一 |
| メッシュ解像度 | 250m | 250m 同一 |
| 人口データ | 令和2年国勢調査 | 令和2年国勢調査 同一 |

差異の主因: 道路ネットワーク距離は直線距離の1.2〜1.5倍になることが多い。直線800〜900m圏内の地域でも歩行ネットワーク上は1km超となり「空白地域」に分類されるため、本試算の空白人口が約2.6倍多くなる。

> 出典: 国土数値情報とQGISを活用した交通空白地の抽出と人口分析（国土交通省 政策統括官付 地理空間情報課、2025年4月）

## データダウンロード

### 鉄道駅 S12（駅別乗降客数・推奨）
https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-S12-2024.html
→ 展開して `data/S12/` に配置
→ ホーム線形の両端点をポイント化（19,854件・ジオメトリ重複除去後）。S12_061 列に乗降客数（2024年版）を保持

代替: 鉄道 N02（全国版）
https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N02-v3_1.html

### バス停 P11（バス停留所・推奨）
https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P11.html
→ 都道府県別47ファイルを展開して `data/P11/` に配置

代替: バス停 N07（全国版）
https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N07.html

### 250mメッシュ人口（令和2年国勢調査）
https://www.e-stat.go.jp/gis/statmap-search?page=1&type=2&aggregateUnitForBoundary=Q&toukeiCode=00200521
→ KEY_CODE / 人口（総数）/ ６５歳以上人口　総数 の列を含む parquet を `input/mesh250_pop_00.parquet` として配置
→ 列名は `03_aggregate.py` が自動変換するので変更不要

## 実行手順

```bash
cd 09_transit-desert-analysis

# Step 1: 施設データ準備（S12/P11 配置後）
python3 scripts/01_prepare_facilities.py

# Step 2〜4: 全処理一括（約40分）
bash run_analysis.sh

# Step 5: 人口集計（mesh250_pop_00.parquet 配置後）
python3 scripts/03_aggregate.py

# Step 6: チャート生成
python3 scripts/04_pref_ranking.py

# Step 7: PMTiles生成
python3 scripts/05_export_geojson.py
bash output/make_pmtiles.sh
```

## 施設データカラム仕様

### stations.parquet（19,854件）

S12ホーム線形の両端点をポイントとして使用（北口・南口等の複数出口に対応）。

| カラム | 元列 | 内容 |
|---|---|---|
| `geometry` | — | ポイント（EPSG:4326） |
| `station_name` | S12_001 | 駅名 |
| `operator` | S12_002 | 運営者名 |
| `line_name` | S12_003 | 路線名 |

### busstops.parquet（242,985件）

| カラム | 元列 | 内容 |
|---|---|---|
| `geometry` | — | ポイント（EPSG:4326） |
| `stop_name` | P11_001 | バス停名 |
| `operator` | P11_002 | バス会社名 |

## 道路ネットワーク仕様

### nationwide_walk（本分析で使用）

| 項目 | 値 |
|---|---|
| 対象道路 | 全道路（フィルターなし） |
| 移動速度 | walk 3.6 km/h |
| 道路リンク数 | 24,045,959件 |
| 道路ノード数 | 18,614,424件 |
| L5アクセスリンク数 | 5,935,127件 |

全道路対象が必要な理由: 徒歩圏500m/1,000m判定には生活道路・細街路を含む全リンクが必要。フィルター済みネットワークでは歩道・路地が欠落し、空白地域が過大評価される。

### ネットワーク生成コマンド

```bash
cd 01_MakeNetwork
python3 ksj_to_network_csv.py --nationwide --mode walk --case nationwide_walk
python3 make_access_links.py  --nationwide --level 5  --case nationwide_walk
```

出力先: `01_MakeNetwork/nationwide_walk/`

## 判定カテゴリ

| カテゴリ | 条件 | 色 |
|---|---|---|
| 0_公共交通便利地域 | 鉄道駅 ≤ 16.7分（1km相当） | 緑 |
| 1_公共交通不便地域 | 鉄道駅 > 16.7分・バス停 ≤ 8.3分（500m相当） | 黄 |
| 2_公共交通空白地域 | 鉄道駅 > 16.7分 AND バス停 > 8.3分 | 赤 |

## 距離計算の方法

Multi-source Dijkstra（scipy.sparse.csgraph.dijkstra）を使用した道路ネットワーク距離。

- 駅: S12ホーム線形の両端点 → KDTree で各端点を最近傍1道路ノードにスナップ（北口・南口対応）
- バス停: KDTree で最近傍1道路ノードにスナップ
- スーパーソースノード方式で全始点を1回のDijkstraで処理
- アクセスリンク経由でノード距離→メッシュ距離に変換
- 閾値: バス停 8.33分（500m）・鉄道駅 16.67分（1,000m）
- `--station-snap-radius`（m）で各端点周辺の追加スナップも可能（デフォルト0=無効）

## PMTiles・ウェブビューワー

**PMTiles S3配置先**:
```
https://pmtiles-data.s3.ap-northeast-1.amazonaws.com/mlit/ksj/transit_desert.pmtiles
```

**ビューワー**: `docs/index.html`
- MapLibre GL JS v4 + PMTiles v3
- 背景地図: 国土地理院ベクトルタイル淡色（`docs/pale.json`）
- 住所検索: Nominatim API → flyTo → queryRenderedFeatures
- スマホ対応: `@media (max-width: 600px)` ボトムシート型

## 出力ファイル用途

| ファイル | QGIS | ウェブ | 集計 |
|---|---|---|---|
| `transit_desert_with_pop.parquet` + `.qml` | **推奨**（45MB・名称付き） | — | — |
| `transit_desert.parquet` + `.qml` | 全件（184MB） | — | — |
| `transit_desert.pmtiles` | — | S3配置済み | — |
| `summary_national.csv` | — | — | ✓ |
| `pref_ranking.png` / `urban_rural_compare.png` | — | — | ✓ |

## 注意事項

- `make_access_links.py` の `--nationwide` は従来 L3 専用だったが、L5 対応に修正済み
  （line 137-139 の level強制上書きを削除）
- L5 アクセスリンクは約594万件で処理に約8分かかる
- `02_calc_transit_desert.py` の Dijkstra 処理は全国で約6分（駅140秒 + バス停18秒）
- 250mメッシュ人口データは `*`（秘匿値）を含む列がある → `03_aggregate.py` で 0 扱い
- `transit_desert_with_pop.parquet` は `pop_total > 0` のみ（1,155,496件・45MB）。全5.9Mメッシュは `transit_desert.parquet`
- P11 SHPファイルは SJIS エンコードを含むが pyogrio が自動処理（警告は無視可）

## 今後の拡張案

- バス運行本数によるフィルタリング（本数ゼロまたは少ない停留所を除外）
- 鉄道の運行本数データ活用（https://gtfs-gis.jp/railway_honsu/）
- GTFS/GTFSリアルタイムデータとの統合
- 経年変化分析（廃線・廃止バス路線の影響）
