@regression
Feature: Script Service – video script generation

  Generates structured video scripts for a POI using its data + assets.

  Background:
    * url scriptBaseUrl

  Scenario: Generate a script for a published POI and verify structure
    # ── Pre-requisite: create + publish a POI ──
    Given url poiBaseUrl + '/pois'
    And request { "name": "Script Test Villa", "description": "Beautiful villa", "lat": 43.6, "lon": 3.9, "poi_type": "villa" }
    When method post
    Then status 201
    * def poiId = response.id

    Given url poiBaseUrl + '/pois/' + poiId + '/validate'
    When method post
    Then status 200

    Given url poiBaseUrl + '/pois/' + poiId + '/publish'
    When method post
    Then status 200

    # ── Pre-requisite: add an asset ──
    Given url assetBaseUrl + '/assets'
    And request { "poi_id": "#(poiId)", "name": "main.jpg", "asset_type": "photo", "file_path": "/data/main.jpg" }
    When method post
    Then status 201

    # ── Generate script ──
    Given url scriptBaseUrl + '/scripts/generate'
    And param poi_id = poiId
    When method post
    Then status 201
    And match response.id == '#uuid'
    And match response.poi_id == poiId
    And match response.title == '#string'
    And match response.scenes == '#array'
    And match response.scenes == '#[_ > 0]'
    And match response.total_duration_seconds == '#number'
    * def scriptId = response.id

    # ── Verify scenes have required fields ──
    And match each response.scenes contains
      """
      {
        "scene_number": '#number',
        "description": '#string',
        "duration_seconds": '#number'
      }
      """

    # ── List scripts by poi_id ──
    Given url scriptBaseUrl + '/scripts'
    And param poi_id = poiId
    When method get
    Then status 200
    And match response.items == '#[_ > 0]'

    # ── Get script by ID ──
    Given url scriptBaseUrl + '/scripts/' + scriptId
    When method get
    Then status 200
    And match response.id == scriptId
    And match response.poi_id == poiId

