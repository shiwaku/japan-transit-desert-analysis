# 公共交通空白地域の全国250mメッシュ分析

> 「実家に帰ると、車がないとコンビニにも行けない」
> 「親が運転をやめたら、買い物はどうする？」
> 「地元の友人はほぼ全員、車を持っていることが前提で生活している」

そんな地方の現実を、全国250mメッシュで可視化したのがこのプロジェクトです。

国土交通省の定義に基づき、「車がないと生活できない地域（公共交通空白地域）」を全国規模で定量化します。

## 分析結果（令和2年国勢調査）

| カテゴリ | 人口 | 割合 |
|---|---|---|
| 公共交通便利地域（鉄道駅 walk 1km以内） | **4,656万人** | 37.0% |
| 公共交通不便地域（バス停 walk 500m以内） | **5,924万人** | 47.0% |
| **公共交通空白地域（車なしでは生活困難）** | **2,014万人** | **16.0%** |

**日本人の約6人に1人（2,014万人）が公共交通空白地域に住んでいる。**

65歳以上では **638万人**（高齢者全体の18.1%）が空白地域に居住。

## ウェブビューワー

`docs/index.html` — MapLibre GL JS + PMTiles による全国インタラクティブマップ。GitHub Pages で公開中。

- 住所検索で「あなたの自宅」の交通区分を判定
- ホバー/タップで最寄り駅・バス停までの徒歩時間と人口を表示
- スマホ対応（ボトムシート型検索パネル）

PMTiles: `https://pmtiles-data.s3.ap-northeast-1.amazonaws.com/mlit/ksj/transit_desert.pmtiles`

## 分析定義

国土交通省 国土数値情報QGISマニュアル（2025年4月）準拠。

> 出典: [国土数値情報とQGISを活用した交通空白地の抽出と人口分析](https://nlftp.mlit.go.jp/ksj/manual/QGIS_manual_01.htm)（国土交通省 政策統括官付 地理空間情報課、2025年4月）
>
> 参考: [「交通空白」解消に関する取組](https://www.mlit.go.jp/sogoseisaku/transport/sosei_transport_tk_000237.html)（国土交通省）

| カテゴリ | 定義 | 補足 |
|---|---|---|
| **公共交通便利地域** | 最寄り鉄道駅まで徒歩1,000m以内 | |
| **公共交通不便地域** | 鉄道駅1,000m超・最寄りバス停500m以内 | バス依存 |
| **公共交通空白地域** | 鉄道駅1,000m超 AND バス停500m超 | 車なしでは生活困難 |

距離は**道路ネットワーク上の徒歩距離**（walk 3.6 km/h）で計算する。

### 公式定義との相違点・優位点

| 項目 | 国交省公式手順 | 本分析 |
|---|---|---|
| 距離計算 | 直線距離 | **道路ネットワーク距離（Dijkstra）** |
| 駅データ | N02（全駅） | **S12（全駅・乗降客数情報付き）** |
| バス停データ | N07 | **P11（都道府県別最新）** |

道路ネットワーク距離により、川・山で隔てられた「直線は近いが実際には遠い」ケースを正確に捕捉できる。S12を使用することで駅名・運営者・乗降客数などの属性情報も保持できる。

## データソース

| データ | 提供元 | URL |
|---|---|---|
| 駅別乗降客数（S12・2024年） | 国土数値情報 | https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-S12-2024.html |
| バス停留所（P11・2022年） | 国土数値情報 | https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-P11.html |
| 道路データ（N13・2024年） | 国土数値情報 | https://nlftp.mlit.go.jp/ksj/gml/datalist/KsjTmplt-N13-v2_1.html |
| 250mメッシュ人口 | e-Stat 令和2年国勢調査 | https://www.e-stat.go.jp/gis/statmap-search?page=1&type=2&aggregateUnitForBoundary=Q&toukeiCode=00200521 |

### S12（駅別乗降客数）について

N02（鉄道路線）の代わりに S12 を使用。駅名・運営者・路線名・乗降客数の属性を保持できる。

- S12のジオメトリは線型（ホーム線形）→ 重心をポイントとして使用
- 全国 **10,534 駅**（フィルタなし・全駅使用）

## 道路ネットワーク規模

全国道路ネットワーク（N13 2024年版・全道路・walkモード）。

| 項目 | 規模（実測） |
|---|---|
| 道路リンク数（双方向） | 24,045,959件 |
| 道路ノード数 | 18,614,424件 |
| L5アクセスリンク数 | 5,935,127件 |
| 対象メッシュ（全国L5） | 5,935,127メッシュ |
| ネットワーク生成時間（Step1） | 約 25分 |
| アクセスリンク生成時間（Step2） | 約 8分 |
| Dijkstra処理時間 × 2回（Step3） | 約 6分 |

※ フィルターなし（全道路対象）。徒歩500m/1,000m圏の判定には生活道路・細街路を含む全道路が必要なため。

## 実行環境

```
Python 3.9+
geopandas / pandas / pyarrow / scipy / shapely / matplotlib
```

```bash
pip install -r requirements.txt
```

## セットアップ

### 1. データのダウンロード・配置

**駅別乗降客数（S12 2024年・全国1ファイル）**

```
data/S12/S12-25_GML/UTF-8/S12-25_NumberOfPassengers.geojson
```

**バス停留所（P11 2022年・都道府県別47ファイル）**

```
data/P11/P11-22_01_GML/P11-22_01.geojson  ← 北海道
data/P11/P11-22_02_GML/P11-22_02.geojson  ← 青森県
...
```

**250mメッシュ人口（e-Stat 令和2年国勢調査）**

```
input/mesh250_pop_00.parquet   # 全国（KEY_CODE・人口（総数）・65歳以上人口　総数）
```

列名は `03_aggregate.py` が自動変換するため、KEY_CODE / 人口（総数）/ ６５歳以上人口　総数 のまま可。

**道路データ（N13・全国160ファイル）**

```
../geoparquet/N13-24_3622.parquet
../geoparquet/N13-24_3623.parquet
...（全160ファイル）
```

### 2. 施設データ準備

```bash
cd 09_transit-desert-analysis
python3 scripts/01_prepare_facilities.py
# → data/stations.parquet（10,534駅・駅名・運営者・路線名付き）
# → data/busstops.parquet（242,985バス停・バス停名・バス会社名付き）
```

### 3. 全処理一括実行（約40分）

```bash
bash run_analysis.sh
```

内部で以下を順番に実行する：

```bash
# Step1: 全国walkモードネットワーク生成（約25分）
python3 ksj_to_network_csv.py --nationwide --mode walk --case nationwide_walk

# Step2: L5アクセスリンク生成（約8分）
python3 make_access_links.py --nationwide --level 5 --case nationwide_walk

# Step3: 公共交通空白地域算出・Dijkstra（約6分）
python3 scripts/02_calc_transit_desert.py
```

### 4. 人口集計

```bash
python3 scripts/03_aggregate.py
```

## アルゴリズム

```
[stations.parquet]  [busstops.parquet]
        │                   │
        └─────────┬──────────┘
                  ▼
      KDTree で最近傍道路ノードにスナップ
                  │
        ┌─────────┴─────────┐
        ▼                   ▼
 Multi-source Dijkstra  Multi-source Dijkstra
   （駅 → 全ノード）       （バス停 → 全ノード）
        │                   │
        └─────────┬──────────┘
                  ▼
     アクセスリンク経由でメッシュ単位の時間に変換
     dist_to_station[mesh] = dist[road_node] + acc_time
     dist_to_bus[mesh]     = dist[road_node] + acc_time
                  │
                  ▼
     閾値判定（walk 3.6 km/h）
     バス停  > 8.3分（500m相当）  → far_bus
     鉄道駅  > 16.7分（1,000m相当）→ far_station
```

Multi-source Dijkstra はスーパーソースノード方式で実装。駅10,534件・バス停242,985件をそれぞれ一括投入し、1回の探索で全メッシュへの最短徒歩時間を算出する。

## 出力ファイル

| ファイル | サイズ | 内容 |
|---|---|---|
| `output/transit_desert.parquet` | 184MB | 全メッシュ別カテゴリ・徒歩時間（5,935,127件） |
| `output/transit_desert.qml` | — | QGISスタイル（全件用） |
| `output/transit_desert_with_pop.parquet` | 45MB | **人口あり1,155,496件のみ**（QGIS・分析用途に推奨） |
| `output/transit_desert_with_pop.qml` | — | QGISスタイル（人口あり用） |
| `output/transit_desert.pmtiles` | 204MB | ウェブ公開用 PMTiles（S3にも配置済み） |
| `output/summary_national.csv` | — | 全国集計（カテゴリ別人口・割合） |
| `output/summary_pref.csv` | — | 1次メッシュ別集計 |
| `output/pref_ranking.png` | — | 都道府県別空白率ランキング |
| `output/urban_rural_compare.png` | — | 都市vs地方の密度比較 |

### 出力カラム（transit_desert.parquet）

| カラム | 内容 |
|---|---|
| `mesh_code` | L5メッシュコード（10桁） |
| `dist_bus_min` | 最寄りバス停までの徒歩時間（分）|
| `dist_station_min` | 最寄り鉄道駅までの徒歩時間（分）|
| `far_bus` | バス停 > 8.3分（500m超）|
| `far_station` | 鉄道駅 > 16.7分（1,000m超）|
| `category` | 判定カテゴリ（3種）|
| `geometry` | L5メッシュポリゴン（EPSG:4326）|

`transit_desert_with_pop.parquet` は上記に加えて `pop_total`（総人口）・`pop_65over`（65歳以上人口）を含む。

### 施設データカラム（stations.parquet / busstops.parquet）

| カラム | stations | busstops |
|---|---|---|
| `geometry` | ポイント（EPSG:4326） | ポイント（EPSG:4326） |
| `station_name` / `stop_name` | 駅名 | バス停名 |
| `operator` | 運営者名 | バス会社名 |
| `line_name` | 路線名 | — |

## 既知の制約

- **道路ネットワーク**: 車道中心線ベースのため、歩道専用路・公園内通路等は対象外
- **バス運行本数**: 本数が極端に少ない停留所も「バス停あり」として扱う（GTFSデータ未使用）
- **S12 乗降客数**: 2024年時点。廃線後のデータ更新ラグが生じる可能性がある
- **一方通行**: 道路ネットワークは双方向として処理（一方通行未考慮）

## 今後の拡張案

- バスGTFSデータによる運行本数フィルタリング
- 鉄道運行本数データの活用（[gtfs-gis.jp/railway_honsu/](https://gtfs-gis.jp/railway_honsu/)）
- 経年変化分析（S12の複数年版比較で廃線影響を可視化）
- タクシー・ライドシェア到達可能エリアの統合（国交省2024年通達：配車30分以内を空白解消の指標とする）

## ライセンス

本スクリプトはMITライセンス。

使用データのライセンス:
- 国土数値情報（S12・P11・N13）: [国土数値情報利用約款](https://nlftp.mlit.go.jp/ksj/other/yakkan.html)
- e-Stat（国勢調査）: [統計データ利用規約](https://www.e-stat.go.jp/terms-of-use)
