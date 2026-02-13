@regression
Feature: Render Service – video rendering jobs

  Manages scene-by-scene rendering triggered by script.generated events.
  In stub mode, render jobs complete almost instantly.

  Background:
    * url renderBaseUrl

  Scenario: List renders (may be empty initially)
    Given path '/renders'
    When method get
    Then status 200
    And match response.items == '#array'

  Scenario: Trigger render via script generation and verify result
    # ── 1. Create + publish POI ──
    Given url poiBaseUrl + '/pois'
    And request { "name": "Render Test POI", "lat": 43.7, "lon": 7.26, "poi_type": "villa" }
    When method post
    Then status 201
    * def poiId = response.id

    Given url poiBaseUrl + '/pois/' + poiId + '/validate'
    When method post
    Then status 200

    Given url poiBaseUrl + '/pois/' + poiId + '/publish'
    When method post
    Then status 200

    # ── 2. Add asset ──
    Given url assetBaseUrl + '/assets'
    And request { "poi_id": "#(poiId)", "name": "aerial.jpg", "asset_type": "photo", "file_path": "/data/aerial.jpg" }
    When method post
    Then status 201

    # ── 3. Generate script (publishes script.generated → render-service consumes it) ──
    Given url scriptBaseUrl + '/scripts/generate'
    And param poi_id = poiId
    When method post
    Then status 201
    * def scriptId = response.id

    # ── 4. Poll render-service for a render linked to this POI ──
    * configure retry = { count: '#(pollRetryCount)', interval: '#(pollIntervalMs)' }
    Given url renderBaseUrl + '/renders'
    And param poi_id = poiId
    And retry until responseStatus == 200 && response.items.length > 0
    When method get
    Then status 200
    And match response.items[0].poi_id == poiId
    And match response.items[0].status == '#string'
    * def renderId = response.items[0].id

    # ── 5. Get render details ──
    Given url renderBaseUrl + '/renders/' + renderId
    When method get
    Then status 200
    And match response.id == renderId
    And match response.scenes == '#array'

