@smoke
Feature: Health checks – all 5 services

  All microservices must expose /healthz (liveness) and /readyz (readiness).

  Scenario Outline: <service> /healthz returns 200
    Given url '<baseUrl>/healthz'
    And header X-API-Key = ''
    When method get
    Then status 200
    And match response.status == 'ok'

    Examples:
      | service               | baseUrl                        |
      | poi-service           | #(poiBaseUrl)                  |
      | asset-service         | #(assetBaseUrl)                |
      | script-service        | #(scriptBaseUrl)               |
      | transcription-service | #(transcriptionBaseUrl)        |
      | render-service        | #(renderBaseUrl)               |

  Scenario Outline: <service> /readyz returns 200
    Given url '<baseUrl>/readyz'
    And header X-API-Key = ''
    When method get
    Then status 200
    And match response.status == 'ready'

    Examples:
      | service               | baseUrl                        |
      | poi-service           | #(poiBaseUrl)                  |
      | asset-service         | #(assetBaseUrl)                |
      | script-service        | #(scriptBaseUrl)               |
      | transcription-service | #(transcriptionBaseUrl)        |
      | render-service        | #(renderBaseUrl)               |

