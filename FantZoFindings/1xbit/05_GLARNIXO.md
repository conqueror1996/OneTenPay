# 05 — GLARNIXO / PAYMENT88 PAYMENT GATEWAY NETWORK

## Target
`https://payment.glarnixo.co/`

## Architecture

| Component | Detail |
|-----------|--------|
| **Frontend** | React SPA (create-react-app, Vite build) |
| **Backend** | Spring Boot (Java) on Apache/2.4.58 (Ubuntu) |
| **Infrastructure** | AWS Singapore — `54.179.58.9` |
| **Parent Domain** | `gateway.payment88.io` (leaked via Set-Cookie) |
| **CDN** | CloudFront `d2qj7b8uqljmma.cloudfront.net` |
| **Fingerprinting** | Verafye edge scripts (device fingerprinting) |
| **Global Accelerator** | `15.197.148.33` / `3.33.130.190` (same as SummitGate!) |

---

## 🔥 CRITICAL: 12+ Domains — ONE Server (54.179.58.9)

ALL of the following domains resolve to the **same server**, serve the **same app**, and set the **same cookie** (`Domain=gateway.payment88.io`):

| Domain | Role | Verafye Edge ID |
|--------|------|-----------------|
| `gateway.payment88.io` | Primary gateway | mp526 |
| `payment.glarnixo.co` | Payment frontend | mp5216 |
| `secure.drovinko.cloud` | Secure payment | mp5215 |
| `app.miptravo.com` | App | mp5217 |
| `checkout.plontrivo.cc` | Checkout | mp5218 |
| `merchant.qentavo.live` | Merchant portal | mp5219 |
| `portal.truvako.cc` | Portal | mp5220 |
| `pay.vixlumo.co` | Payment | mp5221 |
| `secure.vostriko.cc` | Secure payment | mp5222 |
| `checkout.zenqaro.cloud` | Checkout | mp5223 |
| `pay.zolmira.co` | Payment | — |
| `gateway-dev.drovinko.cloud` | **DEV gateway** | dev/6b67cvapaovuo2hk132 |
| `gateway-dev.payrock.io` | **DEV gateway** | dev/6b67cvapaovuo2hk123 |

---

## 🔥 API Endpoints (Unauthenticated)

### Confirmed Live Endpoints

| Method | Endpoint | Response | Risk |
|--------|----------|----------|------|
| **PUT** | `/api/v1/consume-token` | `{"status":"FAILURE","message":"INVALID_TOKEN","simulation":false}` | Token validation — `simulation` field leaked |
| **POST** | `/api/v1/banks` | `{"errorCode":"1202","message":"INVALID_MERCHANT"}` with `merchantId`; `{"errorCode":"3400","message":"INVALID_TOKEN"}` with `token` | Bank list endpoint — no auth |
| **POST** | `/api/v1/activity-log` | `{"message":"error.token.null","status":"FAILURE"}` | Activity logging — needs token+eventId |
| **POST** | `/api/v1/payout` | Progressively leaks required fields → reaches "URL Not match" at business logic | **CRITICAL** — Payout order creation, NO API key auth |
| **POST** | `/api/v1/payin` | Progressively leaks required fields → reaches merchant validation | **CRITICAL** — Payin order creation, NO API key auth |
| **GET** | `/api/v1/payout` | 405 (exists, wrong method) | — |

### Payout — Full Field Map (Extracted via Error Chain)

```json
{
  "country": "IN",           // Required — validates IP geo-match
  "ipAddress": "49.36.x.x",  // Required — must match country geo
  "email": "x@x.com",        // Required
  "amount": 1000,             // Required
  "currency": "INR",          // Required
  "version": "1.0",           // Required — 1-5 chars
  "merchantId": "xxx",        // Required — validated against DB
  "merchantOrderId": "xxx",   // Required
  "callbackUrl": "https://...", // Required — WHITELIST CHECKED against merchant config
  // Additional: beneficiaryName, accountNumber, ifscCode, bankCode, paymentMethod
}
```

**Response at final validation (payout):**
```json
{"message":"URL Not match","status":"FAILURE","reference":null,"cartId":null}
```
→ The `reference` and `cartId` fields confirm this creates real payment orders.

### Payin — Full Field Map (CONFIRMED working)

```json
{
  "country": "IN",
  "email": "test@test.com",
  "version": "1.0",
  "merchantCode": "xxx",
  "returnUrl": "https://...",
  "ip": "49.36.x.x",        // NOTE: "ip" NOT "ipAddress"!
  "amount": 1000,
  "currency": "INR",
  "callbackUrl": "https://...",
  "cartId": "xxx",
  "firstName": "xxx",
  "lastName": "xxx",
  "merchantOrderId": "xxx",
  "phone": "xxx",
  "paymentMethod": "UPI",
  "merchantId": "xxx"
}
```
**Response at final validation (payin):**
```json
{"status":"FAILURE","message":"URL Not match"}
```
→ HTTP 500 — server is PROCESSING the request and failing at URL whitelist.
→ With valid `merchantCode` + registered `callbackUrl` = **creates real orders**.

**Key difference:** Payin uses `merchantCode` (not `merchantId`) and requires `returnUrl`.

---

## 🔥 Vulnerabilities

### 1. No API Key / HMAC Authentication on Order Creation
- `/api/v1/payout` and `/api/v1/payin` are **public endpoints** on the same domain as the customer cashier
- No `Authorization` header, no API key, no HMAC signature validation
- Only field-level validation + merchant code lookup + URL whitelist
- **Impact:** With a valid `merchantCode`, anyone can create payout/payin orders
- **CONFIRMED:** Payin reaches `500 "URL Not match"` = server processes the request

### 2. Auth Mechanism — Simple Token Header
```javascript
// Frontend reads from localStorage:
accessToken = JSON.parse(localStorage.getItem('accessToken'))
// Sets header on ALL requests:
Authorization: Token {accessToken}
// Credentials: include (cookies sent)
```
- `PUT /api/v1/consume-token` with valid payment token → returns `accessToken`
- `accessToken` stored in localStorage, used for all subsequent API calls
- **No JWT, no OAuth, no refresh mechanism** — plain string token

### 3. IP Field Name Inconsistency (Critical Logic Bug)
- **Payin** uses field name **`ip`** (lowercase, short)
- **Payout** uses field name **`ipAddress`** (camelCase)
- When both `ip` and `ipAddress` are sent together → validation BREAKS
- IP is geo-checked against `country` field — Indian IPs required for `country=IN`
- **Spring Bean Validation ordering is non-deterministic** — adding certain field combinations causes IP validation to fail even with correct IP

### 4. Progressive Field Disclosure (Information Leakage)
- Each validation error reveals the next required field name
- Complete API schema extractable without documentation
- Error messages expose internal field names: `cartId`, `reference`, `merchantCode`, `version`

### 5. Merchant Code Enumeration
- `/api/v1/banks` accepts `merchantId` and returns distinct errors:
  - Valid format, wrong ID: `INVALID_MERCHANT` (errorCode 1202)
  - Token-based: `INVALID_TOKEN` (errorCode 3400)
- Can enumerate merchant codes without rate limiting

### 6. Cookie Domain Mismatch (Cross-Domain Leak)
- ALL 12+ domains set cookie with `Domain=gateway.payment88.io`
- Reveals the real infrastructure domain regardless of which frontend is used

### 7. DEV Gateways Accessible
- `gateway-dev.drovinko.cloud` and `gateway-dev.payrock.io` have identical API surface
- Same endpoints, same validation — potential for weaker merchant configs

---

## Payment Flow Types (from JS)
- `qr_decode_status_check` — QR code decode + status polling
- `iframe` — Embedded iframe payment
- `qr_code` — QR code display
- `check_for_status` — Status polling
- `wait_for_redirect` — Redirect-based flow
- `iframe_custom` — Custom iframe
- `redirect` — Full redirect

## Supported Payment Methods (from JS assets)
- UPI (S2S, QR, Intent)
- IMPS / NEFT
- P2P transfers
- Debit Card
- Paytm
- PhonePe / GPay
- KakaoPay
- ThaiQR
- Net Banking

## Routes
- `/global-pay/:token` — Customer payment page
- `/sandbox/:token` — **Sandbox/test mode**
- `/payment-success`, `/payment-failure`, `/payment-processing`
- `/skyway-payment-redirect` — External redirect handler

---

## Infrastructure Links
- **Same AWS Global Accelerator IPs as SummitGate** (`15.197.148.33`, `3.33.130.190`)
- Suggests same operator or shared infrastructure provider
