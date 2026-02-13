@regression
Feature: POI Service – CRUD + workflow

  Tests the full POI lifecycle: create → validate → publish → archive.

  Background:
    * url poiBaseUrl

  Scenario: Create a POI and verify defaults
    Given path '/pois'
    And request
      """
      {
        "name": "Karate Test Villa",
        "description": "E2E test property created by Karate",
        "address": "10 Rue de la Paix, 75002 Paris",
        "lat": 48.8698,
        "lon": 2.3308,
        "poi_type": "villa",
        "tags": ["karate", "e2e", "test"]
      }
      """
    When method post
    Then status 201
    And match response.name == 'Karate Test Villa'
    And match response.status == 'draft'
    And match response.version == 1
    And match response.id == '#uuid'
    And match response.tags == ['karate', 'e2e', 'test']
    * def poiId = response.id

  Scenario: Full workflow – create → validate → publish → archive
    # ── 1. Create ──
    Given path '/pois'
    And request { "name": "Workflow POI", "lat": 43.61, "lon": 3.87, "poi_type": "apartment" }
    When method post
    Then status 201
    * def poiId = response.id
    And match response.status == 'draft'

    # ── 2. Validate ──
    Given path '/pois/' + poiId + '/validate'
    When method post
    Then status 200
    And match response.status == 'validated'

    # ── 3. Publish ──
    Given path '/pois/' + poiId + '/publish'
    When method post
    Then status 200
    And match response.status == 'published'

    # ── 4. Get by ID ──
    Given path '/pois/' + poiId
    When method get
    Then status 200
    And match response.id == poiId
    And match response.status == 'published'

    # ── 5. Archive ──
    Given path '/pois/' + poiId + '/archive'
    When method post
    Then status 200
    And match response.status == 'archived'

  Scenario: Cannot publish a draft POI (must validate first)
    Given path '/pois'
    And request { "name": "Skip Validate", "lat": 48.0, "lon": 2.0 }
    When method post
    Then status 201
    * def poiId = response.id

    Given path '/pois/' + poiId + '/publish'
    When method post
    Then status 409
    And match response.error == 'workflow_error'

  Scenario: List POIs with filters
    # Create 2 POIs
    Given path '/pois'
    And request { "name": "Filter Test A", "lat": 48.0, "lon": 2.0, "poi_type": "villa" }
    When method post
    Then status 201

    Given path '/pois'
    And request { "name": "Filter Test B", "lat": 49.0, "lon": 3.0, "poi_type": "apartment" }
    When method post
    Then status 201

    # List with type filter
    Given path '/pois'
    And param poi_type = 'villa'
    When method get
    Then status 200
    And match response.items == '#[_ > 0]'

  Scenario: Update POI bumps version when published
    Given path '/pois'
    And request { "name": "Version Test", "lat": 48.0, "lon": 2.0 }
    When method post
    Then status 201
    * def poiId = response.id

    Given path '/pois/' + poiId + '/validate'
    When method post
    Then status 200

    Given path '/pois/' + poiId + '/publish'
    When method post
    Then status 200
    And match response.version == 1

    Given path '/pois/' + poiId
    And request { "name": "Version Test Updated" }
    When method patch
    Then status 200
    And match response.version == 2

