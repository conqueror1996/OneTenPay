# PaynQuick / AWS Bridge

## Infrastructure

| Asset | IP | CDN | Notes |
|-------|----|-----|-------|
| aws-bridge.paynquick.com | 18.66.57.23 | AWS CloudFront (BOM78-P2) | Primary API gateway |
| bridge.paynquick.com | 104.26.9.134 | Cloudflare | Alternate domain, same backend |

Only `aws-bridge` and `bridge` subdomains resolve. `paynquick.com`, `api.`, `admin.` etc all NXDOMAIN.

---

## Category: Architecture

```
Client → CloudFront (BOM78) → nginx → Go backend app
                                         ↑
                                    /gateway/* routes only
```

- **Root `/`:** nginx 403 (CloudFront blocks — no origin config for root)
- **`/api/*`:** nginx 404 (backend not reachable via /api)
- **`/gateway/*`:** Go backend 404 `{"error":"Not Found"}` — **CORRECT PREFIX**
- All other paths: nginx 548-byte HTML 404

**Backend language:** Go (Gin/Echo/Fiber) — evidenced by `404 page not found` response, `{"error":"Not Found"}` JSON format

---

## Category: Information Disclosure — CORS Headers

`GET /gateway` leaks full auth scheme via CORS headers:
```
Access-Control-Allow-Credentials: true
Access-Control-Allow-Headers: Content-Type, Authorization, X-Requested-With, 
  X-Merchant-ID, X-Timestamp, X-Signature, X-Advertising-ID, X-Device-Fingerprint
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Origin: *
X-Trace-Id: 8dea1e53f700783d2eb0acb1dc550829
```

**Auth scheme:**
- `X-Merchant-ID` — merchant identifier
- `X-Timestamp` — request timestamp
- `X-Signature` — HMAC signature
- `X-Advertising-ID` — mobile ad tracking
- `X-Device-Fingerprint` — device fingerprint

**CORS: `*`** — any origin can call this API (no CORS restriction)

---

## Category: Route Discovery

- `OPTIONS /gateway` → 204 (backend alive)
- All `/gateway/{word}` paths return same Go 404 — strict route matching
- No routes discovered through wordlist (100+ tried)
- Routes likely use path parameters: `/gateway/:merchantId/pay` etc.
- No Swagger, no Druid, no actuator exposed

---

## Blockers

- Route names unknown — no frontend JS to extract from
- Auth requires HMAC signature with unknown secret
- No subdomains with admin panels
- Go app has strict route matching — wordlist approach ineffective
