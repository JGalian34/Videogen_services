#!/usr/bin/env bash
# seed.sh – Create 1 POI + 2 assets + generate a script
set -euo pipefail

API_KEY="dev-api-key"
BASE="http://localhost"

echo "=== Seeding platform ==="

# 1) Create POI
echo "-> Creating POI..."
POI=$(curl -sf -X POST "$BASE:8001/pois" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{
    "name": "Villa Méditerranée – Montpellier",
    "description": "Superbe villa contemporaine de 250m² avec piscine, jardin paysager et vue sur les toits de Montpellier. 5 chambres, 3 salles de bain.",
    "address": "42 Rue Foch, 34000 Montpellier, France",
    "lat": 43.6108,
    "lon": 3.8767,
    "poi_type": "villa",
    "tags": ["luxury", "pool", "garden", "city-view"],
    "metadata": {"surface_m2": 250, "rooms": 5, "price_eur": 890000}
  }')
POI_ID=$(echo "$POI" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   POI created: $POI_ID"

# 2) Validate POI
echo "-> Validating POI..."
curl -sf -X POST "$BASE:8001/pois/$POI_ID/validate" \
  -H "X-API-Key: $API_KEY" > /dev/null
echo "   POI validated"

# 3) Publish POI
echo "-> Publishing POI..."
curl -sf -X POST "$BASE:8001/pois/$POI_ID/publish" \
  -H "X-API-Key: $API_KEY" > /dev/null
echo "   POI published"

# 4) Create assets
echo "-> Creating assets..."
ASSET1=$(curl -sf -X POST "$BASE:8002/assets" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"poi_id\": \"$POI_ID\",
    \"name\": \"facade-principale.jpg\",
    \"asset_type\": \"photo\",
    \"description\": \"Photo de la façade principale de la villa\",
    \"file_path\": \"/data/assets/facade-principale.jpg\",
    \"mime_type\": \"image/jpeg\",
    \"file_size\": 2048000
  }")
ASSET1_ID=$(echo "$ASSET1" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   Asset 1 created: $ASSET1_ID"

ASSET2=$(curl -sf -X POST "$BASE:8002/assets" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d "{
    \"poi_id\": \"$POI_ID\",
    \"name\": \"visite-drone.mp4\",
    \"asset_type\": \"raw_video\",
    \"description\": \"Vidéo brute de survol drone\",
    \"file_path\": \"/data/assets/visite-drone.mp4\",
    \"mime_type\": \"video/mp4\",
    \"file_size\": 52428800
  }")
ASSET2_ID=$(echo "$ASSET2" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   Asset 2 created: $ASSET2_ID"

# 5) Generate script
echo "-> Generating video script..."
SCRIPT=$(curl -sf -X POST "$BASE:8003/scripts/generate?poi_id=$POI_ID" \
  -H "X-API-Key: $API_KEY")
SCRIPT_ID=$(echo "$SCRIPT" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   Script generated: $SCRIPT_ID"

# 6) Start transcription
echo "-> Starting transcription..."
TRANS=$(curl -sf -X POST "$BASE:8004/transcriptions/start?poi_id=$POI_ID&asset_video_id=$ASSET2_ID" \
  -H "X-API-Key: $API_KEY")
TRANS_ID=$(echo "$TRANS" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "   Transcription started: $TRANS_ID"

echo ""
echo "=== Seed complete ==="
echo "POI:            $POI_ID"
echo "Asset (photo):  $ASSET1_ID"
echo "Asset (video):  $ASSET2_ID"
echo "Script:         $SCRIPT_ID"
echo "Transcription:  $TRANS_ID"
echo ""
echo "Try: curl -H 'X-API-Key: dev-api-key' http://localhost:8001/pois/$POI_ID"

