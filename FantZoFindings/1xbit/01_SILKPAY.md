# SilkPay / SavingsLand / IndianPay Ecosystem

## Infrastructure

| Asset | IP | Notes |
|-------|----|-------|
| admin.silkpay.ai | 43.205.35.52 | PROD — Spring Boot admin panel |
| admin.dev.silkpay.ai | 3.0.59.226 | DEV — same codebase |
| uu.indianpay.net | 43.205.35.52 | User-facing registration |
| savings-land.com | Cloudflare | Same backend as uu.indianpay.net |
| uu.savingslandweb.com | same | Alias domain |
| ityem.club | related | Merchant/backend entity |

**Admin panel branding:** "Didapay" (from JS)  
**Framework:** Spring Boot + Vue.js SPA + Element UI  

---

## Category: Authentication

### OTP Bypass — uu.indianpay.net
- **Endpoint:** `POST /api/auth/sendOtp?mobile=&purpose=register&otpToken=`
- **Finding:** OTP token accepted ANY 6-digit code on test number ranges (`8600000XXX`)
- **Status:** Rate-limited after repeated attempts (403)
- **OTP token format:** `eyJhbGciOiJIUzUxMiJ9...` JWT — contains OTP ID in `info` claim
- **OTP IDs observed:** 15602–15604 (low counter, low usage)

### Registration Flow
- Endpoint: `POST /api/auth/register`
- Params: `mobile`, `password` (SHA256), `otp`, `otpToken`, `invitationCode`
- **Blocker:** `invitationCode` must be a phone number of an existing registered user
- `checkReferNo` returns 405 on GET — POST only
- savings-land `checkReferNo` uses param name `invitationCode` (not `referNo`)
- All codes return `{exist: false}` — no valid codes found

### Password Transmission
- Admin login passes password in URL query string: `POST /auth/login?mobile=X&password=Y`
- Plain-text over HTTPS but logged in nginx access logs

### Client-Side Role Hardcoding
- `getInfo` function in `app.af526109.js` hardcodes `roles: ["admin"]`
- Client-side authorization bypass possible if token obtained

### JWT / Token
- Auth token format: `Authorization: Bearer <JWT>`
- Token cookie name: varies by panel
- HS512 signing algorithm — secret not cracked

---

## Category: API Surface

### Confirmed Endpoints (uu.indianpay.net)
```
POST /api/auth/sendOtp
POST /api/auth/register
POST /api/auth/login
POST /api/auth/login/otp
POST /api/auth/checkReferNo
GET  /api/user/info         (401)
GET  /api/user/home         (401)
GET  /api/user/balance      (401)
GET  /api/p2p/home          (401)
GET  /api/p2p/myOrders      (401)
```

### Admin Panel (admin.silkpay.ai) — Swagger Extracted
- 44 payment API endpoints (full Swagger at `/v2/api-docs`)
- 164 admin panel endpoints mapped from frontend JS
- 150+ payment channel names leaked from enums

---

## Category: Information Disclosure

- **Heapdump:** `3.0.59.226` (DEV) — actuator endpoint accessible via direct IP
- **Payment channels:** Full list of 150+ UPI/bank channel names from `/api/index/enums`
- **Merchant:** `merchantNo=1000` confirmed on both DEV and PROD
- **Error format:** Spring Boot Whitelabel errors leak package paths

---

## Category: HPP / Logic

- **HTTP Parameter Pollution:** Form-encoded body overrides URL query params at `/auth/login`
- **Password reset:** Returns 500 NPE — reset flow broken, exploitable
- **savings-land captcha:** Hardcoded dummy Turnstile key in frontend

---

## Blockers / Dead Ends

| Path | Why Blocked |
|------|-------------|
| JWT secret cracking | HS512 — not in common wordlists |
| Admin login bypass | Needs valid merchantNo=1000 password |
| Payment API signing | Needs merchant signing key |
| Callback endpoint | nginx IP-whitelisted |
| Registration | Rate limited + invitation code needed |
