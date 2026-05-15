#!/bin/bash
tippecanoe \
  -Z 4 -z 13 \
  -l transit_desert \
  --no-tile-size-limit \
  --no-feature-limit \
  --coalesce-densest-as-needed \
  --force \
  -P \
  -o /mnt/c/Users/yshiw/Documents/GIS/ksj/ksj-roadcenterline-route-search/09_transit-desert-analysis-250/output/transit_desert_250m.pmtiles \
  /mnt/c/Users/yshiw/Documents/GIS/ksj/ksj-roadcenterline-route-search/09_transit-desert-analysis-250/output/transit_desert_web_250m.geojson
