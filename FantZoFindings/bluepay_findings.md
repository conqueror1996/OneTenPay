# BluePay (blue-pay.vip) — Full Recon Findings
**Date**: 2026-09-24 02:17 IST

## 🔴 CRITICAL: Druid DB Monitor OPEN
**URL**: `https://api.blue-pay.vip/druid`
- No authentication required
- Full SQL query history exposed
- Database connection string leaked
- Table schema fully visible

## Database Credentials
| Field | Value |
|---|---|
| **Type** | MySQL |
| **Host** | `172.31.0.190:3306` (AWS internal, ap-south-1) |
| **Database** | `pay` |
| **Username** | `root` |
| **SSL** | Disabled (`useSSL=false`) |
| **Total Queries** | 25M+ |

## Infrastructure
| Service | URL | Status |
|---|---|---|
| **Payment API** | `api.blue-pay.vip` | ✅ Live (Cloudflare) |
| **Admin Panel** | `admin.blue-pay.vip` | ✅ Live (RuoYi, captcha) |
| **Merchant Panel** | `merchant.blue-pay.vip` | ✅ Live (Spring Security + Google 2FA) |
| **Main Site** | `blue-pay.vip` | Default Landing |
| **Druid** | `api.blue-pay.vip/druid` | 🔴 OPEN |
| **IP** | `15.206.9.197` (AWS Mumbai) | — |
| **Server** | nginx + Spring Boot | — |

## Database Schema (19 Tables)

### Core Tables
| Table | SELECT | INSERT | UPDATE | Purpose |
|---|---|---|---|---|
| `pay_order` | 229K | 61K | 574 | Payin orders |
| `payout_order` | 1.1M | 60K | 2.1M | Payout orders |
| `pay_channel_info` | 444K | 0 | 0 | Channel configs |
| `pay_user` | 349K | 0 | 0 | Merchant users |
| `pay_cash_flow` | 0 | 1M | 0 | Cash flow log |
| `pay_bank_statement` | 1M | 0 | 0 | Bank statements |
| `pay_bank_list` | 375K | 0 | 0 | Bank/UPI list |
| `pay_channel_request` | 79K | 1M | 1M | Channel requests |
| `pay_channel_response` | 90 | 80K | 0 | Channel responses |
| `pay_channel_group` | 349K | 0 | 0 | Channel groups |
| `payout_order_split` | 3.9K | 1.3K | 7.5K | Split payouts |
| `payout_order_fake` | 78K | 0 | 0 | Fake/test payouts |
| `payout_order_sending` | 0 | 2.7K | 0 | Sending queue |
| `sys_config` | 174K | 0 | 0 | System config |
| `im_order_payin` | 96K | 0 | 0 | IM payin orders |
| `im_app_client` | 5.8K | 0 | 0 | App clients |
| `im_app_version` | 5.8K | 0 | 0 | App versions |
| `im_member_tool_statement` | 110K | 0 | 0 | Member statements |
| `payout_ifsc` | 1 | 0 | 0 | IFSC codes |

### Key Column Exposures

#### `pay_user` (Merchant Users)
```
id, secret_key, pay_fee1, pay_fee2, out_fee1, out_fee2,
ip, pay_channel, out_channel, payout_limit, user_type,
stat, min_in_amount, max_in_amount, min_out_amount,
max_out_amount, upi, ret_utr, test, api_notify,
pay_notify_url, out_notify_url, payin_ip, payout_ip,
pay_domain, pay_domain2, rate_limit, out_split
```

#### `pay_channel_info` (Channel Credentials)
```
id, type, login_account, account_key, account_secret,
stat, min_in_amount, max_in_amount, min_out_amount,
max_out_amount, pay_fee1, pay_fee2, out_fee1, out_fee2,
template_id, group_stat, third_config, upi, third_stat,
channel_name
```

#### `payout_order` (Payout with Bank Details)
```
id, order_id, user_order_id, user_id, channel_id,
amount, out_type, pay_fee1, pay_fee2, notify_url,
account_number, ifsc, account_holder, stat, create_time,
utr, push_count, upi, split_need, split_count,
card_number, card_holder, wallet_email, phone_no, profit
```

## API Endpoints (Live)
| Endpoint | Requests | IP Check | Notes |
|---|---|---|---|
| `/api/payment/createOrder` | 1.7M+ | ❌ No | Needs sign |
| `/api/payout/createOrder` | 491K+ | ✅ Yes | IP whitelisted |
| `/api/payout/status` | 747K+ | ✅ Yes | — |
| `/api/payout/balance` | 704K+ | ✅ Yes | — |
| `/api/payment/queryUpi` | 176K+ | — | — |
| `/api/payment/uploadUtr` | 171K+ | — | — |
| `/api/payment/queryUtr` | 169K+ | — | — |
| `/api/payment/status` | 24K+ | — | — |

## Merchant Enumeration
**250+ active merchants** (IDs 2-500+)
- Valid IDs: 2, 3, 4, 88, 100-104, 201-500 (mostly sequential)
- All return "IP error" on payout endpoints
- Payment createOrder for some merchants returns "notifyUrl error" (bypasses IP check)

## 64 Active Payout Channels
```
104, 213, 214, 216, 228, 230, 233, 236, 252, 259, 276, 297, 309, 312,
314, 327, 338, 402, 420, 421, 441, 442, 449, 464, 470, 475, 476, 478,
480, 489, 503, 506, 521, 524, 527, 548, 573, 589, 607, 609, 611, 668,
700, 702, 716, 761, 776, 778, 786, 790, 791, 792, 802, 810, 821, 824,
829, 833, 852, 857, 867, 868, 871, 874
```

## SQL Injection Attempts Found in Blacklist
Someone already tried SQLi against this system:
```sql
-- SLEEP injection (user_id=470):
WHERE order_id='X' AND SLEEP(4)-- -' and user_id=470

-- Boolean injection:
WHERE order_id='X'||(SELECT 1)||'' and user_id=470
```

## Leaked UPI IDs (from SQL errors)
- `he's.payu@axisbank`
- `saimi2323@naviaxis`
- `9366199113-1@mbkns`
- `9207570159@ptyes`
- `Completed-907204681210@boi`
- `MedicosGoogleYou'vewon@1`
- `Paidf'26091850-1@ypbiz`

## Admin Panel (admin.blue-pay.vip)
- Framework: **RuoYi** (Chinese admin framework)
- Base URL: `/prod-api`
- Captcha: **Enabled** (base64 image)
- `/prod-api/captchaImage` — returns captcha + UUID
- Login: POST `/prod-api/login` with `{username, password, code, uuid}`
- Google Authenticator: Required on merchant panel

## Merchant Panel (merchant.blue-pay.vip)
- Framework: Spring MVC + jQuery EasyUI
- Login: POST `/admin/login` with `{username, password, captcha, googleCode, lang}`
- Session: JSESSIONID
- Features: Lending platform with IFSC, bank account, UPI support
- Language: Chinese (zh_CN) + English
