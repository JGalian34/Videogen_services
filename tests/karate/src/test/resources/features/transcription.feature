@regression
Feature: Transcription Service – stub pipeline

  Simulates transcription of a raw video asset.
  Uses a stub worker so results appear quickly.

  Background:
    * url transcriptionBaseUrl

  Scenario: Start a transcription job and verify completion
    # ── Pre-requisite: create POI ──
    Given url poiBaseUrl + '/pois'
    And request { "name": "Transcription POI", "lat": 48.8, "lon": 2.3 }
    When method post
    Then status 201
    * def poiId = response.id

    # ── Pre-requisite: create a video asset ──
    Given url assetBaseUrl + '/assets'
    And request
      """
      {
        "poi_id": "#(poiId)",
        "name": "walkthrough.mp4",
        "asset_type": "video",
        "file_path": "/data/assets/walkthrough.mp4",
        "mime_type": "video/mp4",
        "file_size": 5242880
      }
      """
    When method post
    Then status 201
    * def assetVideoId = response.id

    # ── Start transcription ──
    Given url transcriptionBaseUrl + '/transcriptions/start'
    And param poi_id = poiId
    And param asset_video_id = assetVideoId
    When method post
    Then status 201
    And match response.id == '#uuid'
    And match response.poi_id == poiId
    And match response.asset_video_id == assetVideoId
    And match response.status == '#string'
    * def transcriptionId = response.id

    # ── Poll until completed (stub finishes instantly or within seconds) ──
    * configure retry = { count: '#(pollRetryCount)', interval: '#(pollIntervalMs)' }
    Given url transcriptionBaseUrl + '/transcriptions/' + transcriptionId
    And retry until responseStatus == 200 && response.status == 'completed'
    When method get
    Then status 200
    And match response.status == 'completed'
    And match response.result == '#present'

    # ── List transcriptions by poi_id ──
    Given url transcriptionBaseUrl + '/transcriptions'
    And param poi_id = poiId
    When method get
    Then status 200
    And match response.items == '#[_ > 0]'

