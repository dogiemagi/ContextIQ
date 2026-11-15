# API Guide

## Authentication

All requests authenticate with a Bearer token in the Authorization header. Tokens are created under Settings, Developer.

## Rate limits

Rate limits depend on the plan: Starter allows 60 requests per minute, Pro allows 600 requests per minute and Enterprise allows 6000 requests per minute. When a limit is exceeded the API returns HTTP 429 with a Retry-After header.

## Webhooks

Failed webhook deliveries are retried 5 times with exponential backoff, starting at 30 seconds. After the fifth failure the endpoint is disabled and the workspace owner is notified by email.

## Pagination

List endpoints use cursor-based pagination. The maximum page size is 100 items.
