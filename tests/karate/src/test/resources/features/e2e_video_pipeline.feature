@e2e
Feature: E2E Video Pipeline – full lifecycle regression

  Complete end-to-end scenario:
    POI creation → asset upload → script generation → transcription → render
  Uses controlled polling (retry until) instead of blind sleeps.

  Background:
    * configure retry = { count: 40, interval: 3000 }

  Scenario: Full video pipeline – POI to rendered video
    # ══════════════════════════════════════════════════════════════════
    #  STEP 1 – Create POI
    # ══════════════════════════════════════════════════════════════════
    Given url poiBaseUrl + '/pois'
    And request
      """
      {
        "name": "E2E Château de Test",
        "description": "Magnificent property for full pipeline E2E testing",
        "address": "42 Avenue des Champs-Élysées, 75008 Paris",
        "lat": 48.8698,
        "lon": 2.3075,
        "poi_type": "villa",
        "tags": ["e2e", "pipeline", "karate"]
      }
      """
    When method post
    Then status 201
    And match response.status == 'draft'
    * def poiId = response.id
    * karate.log('>>> POI created:', poiId)

    # ── Validate POI ──
    Given url poiBaseUrl + '/pois/' + poiId + '/validate'
    When method post
    Then status 200
    And match response.status == 'validated'

    # ── Publish POI ──
    Given url poiBaseUrl + '/pois/' + poiId + '/publish'
    When method post
    Then status 200
    And match response.status == 'published'
    * karate.log('>>> POI published:', poiId)

    # ══════════════════════════════════════════════════════════════════
    #  STEP 2 – Add assets
    # ══════════════════════════════════════════════════════════════════
    Given url assetBaseUrl + '/assets'
    And request
      """
      {
        "poi_id": "#(poiId)",
        "name": "facade_hd.jpg",
        "asset_type": "photo",
        "file_path": "/data/assets/facade_hd.jpg",
        "mime_type": "image/jpeg",
        "file_size": 3145728,
        "metadata": { "resolution": "4096x2160", "hdr": true }
      }
      """
    When method post
    Then status 201
    * def assetPhoto = response.id

    Given url assetBaseUrl + '/assets'
    And request
      """
      {
        "poi_id": "#(poiId)",
        "name": "walkthrough_raw.mp4",
        "asset_type": "video",
        "file_path": "/data/assets/walkthrough_raw.mp4",
        "mime_type": "video/mp4",
        "file_size": 52428800,
        "metadata": { "duration_seconds": 120, "codec": "h264" }
      }
      """
    When method post
    Then status 201
    * def assetVideo = response.id
    * karate.log('>>> Assets created – photo:', assetPhoto, '  video:', assetVideo)

    # ── Verify 2 assets exist ──
    Given url assetBaseUrl + '/assets'
    And param poi_id = poiId
    When method get
    Then status 200
    And match response.items == '#[2]'

    # ══════════════════════════════════════════════════════════════════
    #  STEP 3 – Generate video script
    # ══════════════════════════════════════════════════════════════════
    Given url scriptBaseUrl + '/scripts/generate'
    And param poi_id = poiId
    When method post
    Then status 201
    And match response.id == '#uuid'
    And match response.scenes == '#[_ > 0]'
    And match response.total_duration_seconds == '#number'
    * def scriptId = response.id
    * def sceneCount = response.scenes.length
    * karate.log('>>> Script generated:', scriptId, '– scenes:', sceneCount)

    # ── Verify script persisted ──
    Given url scriptBaseUrl + '/scripts/' + scriptId
    When method get
    Then status 200
    And match response.poi_id == poiId

    # ══════════════════════════════════════════════════════════════════
    #  STEP 4 – Start transcription (optional – enriches rendering)
    # ══════════════════════════════════════════════════════════════════
    Given url transcriptionBaseUrl + '/transcriptions/start'
    And param poi_id = poiId
    And param asset_video_id = assetVideo
    When method post
    Then status 201
    * def transcriptionId = response.id
    * karate.log('>>> Transcription started:', transcriptionId)

    # ── Poll transcription until completed ──
    Given url transcriptionBaseUrl + '/transcriptions/' + transcriptionId
    And retry until responseStatus == 200 && response.status == 'completed'
    When method get
    Then status 200
    And match response.status == 'completed'
    * karate.log('>>> Transcription completed')

    # ══════════════════════════════════════════════════════════════════
    #  STEP 5 – Wait for render-service (event-driven via Redpanda)
    #  The script.generated event triggers render-service to create
    #  a render job. We poll until the render appears.
    # ══════════════════════════════════════════════════════════════════
    Given url renderBaseUrl + '/renders'
    And param poi_id = poiId
    And retry until responseStatus == 200 && response.items.length > 0
    When method get
    Then status 200
    And match response.items == '#[_ > 0]'
    * def render = response.items[0]
    * def renderId = render.id
    * karate.log('>>> Render job found:', renderId, '– status:', render.status)

    # ── Verify render job details ──
    Given url renderBaseUrl + '/renders/' + renderId
    When method get
    Then status 200
    And match response.poi_id == poiId
    And match response.scenes == '#array'

    # ── Poll until render status is 'completed' or 'done' ──
    Given url renderBaseUrl + '/renders/' + renderId
    And retry until responseStatus == 200 && (response.status == 'completed' || response.status == 'done')
    When method get
    Then status 200
    And match response.status == '#? _ == "completed" || _ == "done"'
    And match response.scenes == '#[_ > 0]'
    * karate.log('>>> Render completed! Scenes:', response.scenes.length)

    # ══════════════════════════════════════════════════════════════════
    #  STEP 6 – Final cross-service consistency check
    # ══════════════════════════════════════════════════════════════════
    # POI still published
    Given url poiBaseUrl + '/pois/' + poiId
    When method get
    Then status 200
    And match response.status == 'published'

    # Assets still present
    Given url assetBaseUrl + '/assets'
    And param poi_id = poiId
    When method get
    Then status 200
    And match response.items == '#[2]'

    # Script still accessible
    Given url scriptBaseUrl + '/scripts/' + scriptId
    When method get
    Then status 200

    * karate.log('══════ E2E PIPELINE PASSED ══════')

