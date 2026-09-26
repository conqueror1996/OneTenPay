# EarnPe — "Mangrove" Casino Platform
## ⚠️ CRITICAL — Full GraphQL Schema Exposed, Unauthenticated Config Dump

## Infrastructure

| Asset | URL | Stack |
|-------|-----|-------|
| Cashier | cashier.earnpe.vip | Next.js (React) + Cloudflare |
| API | api.earnpe.vip | Node.js + GraphQL (Apollo) + Cloudflare |
| Admin Panel | console.earnpe.vip | UmiJS + Ant Design Pro ("Mangrove") |
| App Distribution | earnpe.vip | Next.js |
| Captcha Service | behavior-validator.notic185.com | Go-Captcha (slide) |
| Sister Platform | notic185.com | Same Mangrove stack |

**SSL:** Google Trust Services (WE1), wildcard `*.earnpe.vip`  
**Backend:** `/opt/mangrove/branch/` (leaked in stacktraces)  
**Error Reporting:** Sentry (DSN key: `9ce50bc588a1fc521ab2a099f10dca29`)  
**Health:** ORM ✅, RPC ✅, Cache ✅

---

## Category: GraphQL Introspection (CRITICAL)

### Full Schema Exposed — No Authentication
```
POST https://api.earnpe.vip/v1/graphql
{"query":"{ __schema { types { name kind fields { name } } } }"}
```
**Response:** Full schema with 50+ types, all mutations, all queries.

### Key Mutations (require auth)
| Mutation | Fields | Impact |
|----------|--------|--------|
| MutableOrder | update, delete | Modify/delete payment orders |
| MutableUserWallet | create, update, delete | Manipulate user wallets |
| MutableMerchantOrder | create, update, delete, clearMerchantWalletCaches | Create fake merchant orders |
| MutableUser | create, update, delete, loginByPassword, registerByPassword | User management |
| MutableUserCredential | create, update, delete, generateAccessKey | API key generation |
| MutableVerificationOrder | create, update, delete | Verification bypass |

### Key Queries (require auth)
| Query | Fields |
|-------|--------|
| ImmutableOrder | retrieve, summarizeQuantity/Status/Amount/AmountTrend/StatusRatio |
| ImmutableUserWallet | retrieve, retrievePortal, retrievePriorityOnes, summarizeStatus |
| ImmutableMerchantOrder | explainCreationProcess, retrieve, retrieveCreationFilter |

---

## Category: Unauthenticated Data Exfiltration (CRITICAL)

### Settings Dump — 20 Platform Configs Leaked
```
POST https://api.earnpe.vip/v1/graphql
{"query":"{ palmier { setting { retrieve(action: {}) { total data { key value name description } } } } }"}
```

| Key | Value | Impact |
|-----|-------|--------|
| check.options.baseURL | `https://behavior-validator.notic185.com` | Captcha validation endpoint |
| check.options.id | `slide-default` | Captcha configuration |
| redirectLinks | `https://t.me/+xdU9X0UuqR9kYzI1` | Internal Telegram group |
| fillAndSave.value | `107` | USDT-to-INR exchange rate |
| changeStatus.rebate | `0.004\|0.001` | 2-level MLM rebate rates |
| calculateIntegralAmount.value | `1.04` | INR to points conversion |
| paymentTip | "❗DO NOT USE POCKET UPI❗ ✅ Use Freecharge, Mobikwik or Freo" | Payment instructions |
| USDT rebates | `[{key:[50,99],value:200},{key:[100,199],value:450}...]` | Deposit reward tiers |
| INR rebates | `[{key:[10000,50000],value:25},{key:[20000,29999],value:50}...]` | INR reward tiers |
| availableGames | `[{id:11,name:"1",cover:"1"}]` | Active casino games |

---

## Category: Authentication Weaknesses

### Login Without Captcha ✅ CONFIRMED
```graphql
mutation {
  palmier {
    user {
      loginByPassword(action: {
        name: "root"
        password: "..."
      }) {
        accessToken
        refreshToken
      }
    }
  }
}
```
The `captcha` field in `LoginByPasswordAction` is **nullable** (not NON_NULL). Login can be attempted without solving the captcha.

### User Enumeration ✅ CONFIRMED
- `root` → "Password entered incorrectly" (EXISTS)
- `admin`, `test`, `demo`, `operator`, `agent`, `merchant` → "Please log in with username, not phone number" (treated as phone — these are **short enough to pass as phone numbers**)
- Rate limiting: "Password entered incorrectly multiple times, Contact your agent to remove the restriction. Account not frozen."

### Registration Disabled
```
"Register is disabled"
```

### Stacktrace Disclosure ✅ CONFIRMED
All errors include full Node.js stacktraces with file paths:
```
at MutableUserResolver.loginByPassword (/opt/mangrove/branch/dist/application/user/resolver.js:1672)
at OperationAuditInterceptor.intercept (...)
```

---

## Category: Sister Platform — notic185.com

| Asset | URL | Status |
|-------|-----|--------|
| Console | console.notic185.com | ✅ "Mangrove" admin panel |
| API | api.notic185.com/v1/graphql | ✅ GraphQL introspection open |
| App | notic185.com | ✅ "Application distribution" |

Same Mangrove platform, different configuration:
- Has game "Mines" (ID 100)
- Different Telegram: `tg://join?invite=8l8t5vOxuUA2N2Nl`
- Different rebate rates: 0.3% (level 1), 0.001% (level 2)

---

## Category: Business Intelligence

### Platform Type
Crypto + INR casino/gaming platform with:
- UPI payment collection (INR)
- USDT deposits (crypto)
- 2-level MLM referral system
- Casino games integration
- Phone mule wallet network (INR collection)
- Merchant order processing

### Connected Domains
- earnpe.vip — primary platform
- notic185.com — sister platform (same code)
- behavior-validator.notic185.com — shared captcha service

---

## Category: Unauthenticated Server Crash (HIGH)

### describeExchangeToken — Crashes Without Auth
```
POST https://api.earnpe.vip/v1/graphql
{"query":"{ palmier { user { describeExchangeToken } } }"}
```
**Response:**
```json
{"errors":[{"message":"Cannot read properties of undefined (reading 'totpSecret')"}]}
```
The server attempts to read `totpSecret` from the user context **before checking authentication**. This is a code-level bug — the resolver runs without auth and crashes when it can't find the user object. A crafted payload could potentially trigger further exploitable behavior.

---

## Category: Dual GraphQL Root (HIGH)

Two separate mutation/query roots exist:

| Root | Mutation Type | Query Type | Purpose |
|------|--------------|------------|----------|
| **palmier** | MutablePalmier | ImmutablePalmier | Core platform (users, settings, auth, credentials) |
| **mangrove** | MutableMangrove | ImmutableMangrove | Business entities (orders, wallets, games, merchants) |

### MutableMangrove Entities (30+)
```
article, autoRebate, autoRebateHistory, game, gameAccount, history,
merchantOrder, order, orderCallback, orderHistory, orderTransaction,
promotion, promotionGroup, resource, setting, user, userIntegralHistory,
userIntegralHistoryAttribute, userWalletHistory, userWalletPayHistory,
userOrder, userOrderPartition, userOrderTransaction, userPromotion,
userWallet, userWalletAttribute, verificationOrder, wallet,
inrCollectionOrderPackage, inrCollectionOrderPackageTemplate
```

### Key Observation
- `mangrove.order` has only `update` and `delete` — NO `create`
- `mangrove.user` (MutableMangroveUser) has only `update` — NO `create`
- This means orders are created through **merchant API integrations**, not the admin panel

---

## Category: Framework Intelligence (MEDIUM)

| Component | Version/Detail |
|-----------|----------------|
| **Runtime** | Node.js |
| **Framework** | NestJS 11.1.1 |
| **Auth Library** | @element/helium@2.6.2 |
| **Auth Interceptor** | OperationAuditInterceptor |
| **GraphQL** | Apollo Server 5.5.1 + graphql@16.14.0 |
| **ORM** | TypeORM (confirmed via /health) |
| **Server Path** | `/opt/mangrove/branch/dist/application/` |
| **Frontend (Cashier)** | Next.js + React |
| **Frontend (Console)** | UmiJS + Ant Design Pro |
| **Frontend (App)** | Next.js + next-auth |
| **Proxy** | Cloudflare |
| **Monitoring** | Sentry |

### /health (Unauthenticated)
```json
{"status":"ok","info":{"object-relational-mapping":{"status":"up"},"remote-procedure-call":{"status":"up"},"cache":{"status":"up"}}}
```

---

## Category: User Data Model (from Schema)

### PartialMangroveUser (Input — shows all user fields)
```
id, uuid, name, description, type, logStatus, workStatus,
integral, pin, lastSeenAt, status, sex, nickName,
email, phone, password, disablePasswordLogin,
inrPurchaseLimitExempt, totpSecret, enableAt
```

**Notable:** `totpSecret` field is directly in the user model — TOTP secrets are stored alongside user data, not in a separate auth service.

---

## Full Schema Reference
Saved to: `FantZoFindings/1xbit/earnpe_schema.json`
