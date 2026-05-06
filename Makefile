.PHONY: all facilities analysis aggregate charts pmtiles clean

# 全処理一括実行
all: facilities analysis aggregate charts pmtiles

# Step 1: 施設データ準備
facilities:
	python3 scripts/01_prepare_facilities.py

# Step 2-3: 道路ネットワーク生成 + Dijkstra 分析
analysis:
	bash run_analysis.sh

# Step 4: 人口集計
aggregate:
	python3 scripts/03_aggregate.py

# Step 5: チャート生成
charts:
	python3 scripts/04_pref_ranking.py

# Step 6: GeoJSON → PMTiles 変換
pmtiles:
	python3 scripts/05_export_geojson.py
	bash output/make_pmtiles.sh

clean:
	rm -f output/*.parquet output/*.geojson output/*.pmtiles output/*.csv \
	       output/*.png output/make_pmtiles.sh
