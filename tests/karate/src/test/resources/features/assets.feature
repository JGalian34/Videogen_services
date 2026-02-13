@regression
Feature: Asset Service – CRUD linked to POI

  Assets are files (photos, plans, videos) associated with a POI.

  Background:
    * url assetBaseUrl
    * def poiUrl = poiBaseUrl

  Scenario: Create 2 assets for a POI and list them
    # ── Pre-requisite: create a POI via poi-service ──
    Given url poiUrl + '/pois'
    And request { "name": "Asset Test POI", "lat": 48.8, "lon": 2.3 }
    When method post
    Then status 201
    * def poiId = response.id

    # ── 1. Create first asset (photo) ──
    Given url assetBaseUrl + '/assets'
    And request
      """
      {
        "poi_id": "#(poiId)",
        "name": "front_photo.jpg",
        "asset_type": "photo",
        "file_path": "/data/assets/front_photo.jpg",
        "mime_type": "image/jpeg",
        "file_size": 204800,
        "metadata": { "resolution": "1920x1080" }
      }
      """
    When method post
    Then status 201
    And match response.id == '#uuid'
    And match response.poi_id == poiId
    And match response.asset_type == 'photo'
    * def assetId1 = response.id

    # ── 2. Create second asset (floor plan) ──
    Given url assetBaseUrl + '/assets'
    And request
      """
      {
        "poi_id": "#(poiId)",
        "name": "floor_plan.pdf",
        "asset_type": "plan",
        "file_path": "/data/assets/floor_plan.pdf",
        "mime_type": "application/pdf",
        "file_size": 512000,
        "metadata": { "pages": 2 }
      }
      """
    When method post
    Then status 201
    * def assetId2 = response.id

    # ── 3. List assets by poi_id ──
    Given url assetBaseUrl + '/assets'
    And param poi_id = poiId
    When method get
    Then status 200
    And match response.items == '#[2]'
    And match each response.items contains { poi_id: '#(poiId)' }

    # ── 4. Get single asset by ID ──
    Given url assetBaseUrl + '/assets/' + assetId1
    When method get
    Then status 200
    And match response.name == 'front_photo.jpg'
    And match response.mime_type == 'image/jpeg'
    And match response.file_size == 204800

  Scenario: Update asset metadata
    # Create POI + asset
    Given url poiUrl + '/pois'
    And request { "name": "Update Test", "lat": 48.0, "lon": 2.0 }
    When method post
    Then status 201
    * def poiId = response.id

    Given url assetBaseUrl + '/assets'
    And request { "poi_id": "#(poiId)", "name": "old.jpg", "asset_type": "photo", "file_path": "/old.jpg" }
    When method post
    Then status 201
    * def assetId = response.id

    # Update
    Given url assetBaseUrl + '/assets/' + assetId
    And request { "name": "updated.jpg", "metadata": { "color_profile": "sRGB" } }
    When method patch
    Then status 200
    And match response.name == 'updated.jpg'
    And match response.version == 2

