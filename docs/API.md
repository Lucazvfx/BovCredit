# Livestock Intelligence API

Versioned B2B API for the livestock intelligence pipeline.

## Authentication

Send one of these headers with every request:

- `X-API-Key: lii_<prefix>.<secret>`
- `Authorization: Bearer lii_<prefix>.<secret>`

The API key is hashed at rest and scoped to one organization. Revoked keys are rejected.

## Idempotency

`POST /api/v1/full-analysis` accepts an `Idempotency-Key` header. Reusing the same key inside the same organization returns the original response. Reusing the same key with a different payload returns `409 Conflict`.

## Scopes

Typical scopes used by the API:

- `herd:analyze`
- `production:project`
- `cashflow:project`
- `payment-capacity:analyze`
- `stress:analyze`
- `analysis:write`
- `analysis:read`
- `report:read`

An API key without explicit scopes is treated as unrestricted.

## Error envelope

All v1 errors use the same shape:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Field 'valores' must contain exactly 10 numbers.",
    "details": {
      "field": "valores"
    }
  },
  "trace_id": "8-character-id"
}
```

## Endpoints

### POST /api/v1/herd/analyze

Analyzes herd structure from the 10-value vector.

Example body:

```json
{
  "valores": [120, 90, 80, 60, 50, 40, 30, 20, 10, 5],
  "bois_vendidos": 2,
  "bezerros_vendidos": 3
}
```

### POST /api/v1/production/project

Projects production from herd values and a production system.

Required fields:

- `valores`
- `system`

### POST /api/v1/cashflow/project

Projects monthly cashflow from an annual projection and debt schedule.

Required fields:

- `annual_projection`
- `debt_schedule`

### POST /api/v1/payment-capacity

Computes DSCR / payment capacity from cashflow and debt request payloads.

Required fields:

- `cashflow`
- `debt_request`

### POST /api/v1/stress-test

Runs stress scenarios against a base analysis payload.

Required fields:

- `base_analysis`

### POST /api/v1/full-analysis

Runs the complete pipeline, persists a snapshot, and returns the stored analysis id.

Headers:

- `Idempotency-Key: <unique key>`

### GET /api/v1/analysis/<id>

Returns the stored machine analysis for the organization attached to the API key.

### GET /api/v1/report/<id>

Returns a machine-readable report wrapper derived from the stored analysis.

### GET /api/docs

Returns the OpenAPI 3.1 JSON document for the API.

## Compatibility

The legacy Flask routes remain available unchanged. This API is additive.
