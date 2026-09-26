# MandiPay — Internal Infrastructure Map

> **Source**: Spring Boot Actuator at `52.221.140.71:40000/actuator/gateway/routes`  
> **Pulled**: 2026-09-27 02:49 IST  
> **Network**: `172.16.0.8` (internal host) + `172.16.1.170` (sbnk connector)

## Full Microservice Architecture

| Route ID | Internal URL | Path Pattern |
|----------|-------------|-------------|
| **auth-service** | `http://172.16.0.8:40001` | `/auth/**` |
| **upi-payin-service** | `http://172.16.0.8:40300` | `/api/v1/upi/payin/**` |
| **upi-payout-service** | `http://172.16.0.8:50300` | `/api/v1/upi/payout/**` |
| **upi-merchant-service** | `http://172.16.0.8:40100` | `/api/v1/upi/merchant/**` |
| **upi-wallet-service** | `http://172.16.0.8:40101` | `/api/v1/upi/merchant/wallet/**` |
| **upi-account-manager** | `http://172.16.0.8:40200` | `/api/v1/upi/account/**` |
| **upi-account-manager-utility** | `http://172.16.0.8:40201` | `/api/v1/upi/utility/**` |
| **upi-statement-utility** | `http://172.16.0.8:40201` | `/api/v1/upi/statement/history/**` |
| **upi-transaction-query** | `http://172.16.0.8:40500` | `/api/v1/upi/q/payin/**` |
| **upi-sms-processor** | `http://172.16.0.8:40600` | `/api/v1/upi/sms/**` |
| **upi-ticket-mgmt** | `http://172.16.0.8:40700` | `/api/v1/upi/ticket/**` |
| **upi-payout-query** | `http://172.16.0.8:40800` | `/api/v1/upi/q/payout/**` |
| **upi-misc-service** | `http://172.16.0.8:44044` | `/api/v1/upi/config/**` |
| **upi-reporting-service** | `http://172.16.0.8:44444` | `/api/v1/upi/reporting/**` |
| **upi-supplier-service** | `http://172.16.0.8:49100` | `/api/v1/upi/supplier/**` |
| **upi-api-connector** | `http://172.16.0.8:51234` | `/api/v1/upi/api/**` ← **statement/manual lives here** |
| **upi-google** | `http://172.16.0.8:56789` | `/google/**` |

## Bank Connectors (SMS Scraper Utilities)

| Bank | Internal URL | Path |
|------|-------------|------|
| SBI | `http://172.16.0.8:50001` | `/api/v1/upi/sbi/**` |
| IOB | `http://172.16.0.8:50002` | `/api/v1/upi/iob/**` |
| UCO | `http://172.16.0.8:50003` | `/api/v1/upi/uco/**` |
| CBI | `http://172.16.0.8:50004` | `/api/v1/upi/cbi/**` |
| BOB | `http://172.16.0.8:50005` | `/api/v1/upi/bob/**` |
| IDBI | `http://172.16.0.8:50006` | `/api/v1/upi/idbi/**` |
| BOM | `http://172.16.0.8:50007` | `/api/v1/upi/bom/**` |
| Canara | `http://172.16.0.8:50008` | `/api/v1/upi/canara/**` |
| IDIB | `http://172.16.0.8:50010` | `/api/v1/upi/idib/**` |

## External Connectors

| Connector | Internal URL | Callback Path |
|-----------|-------------|---------------|
| WizPay | `http://172.16.0.8:50200` | `/api/v1/upi/connector/payin/wiz/callback` |
| PayerIn | `http://172.16.0.8:52300` | `/api/v1/upi/connector/payin/payer/callback` |
| SabPaisa | `http://172.16.0.8:50800` | `/api/v1/upi/connector/payin/sabpaisa/**` |
| SabPaisa H2H | `http://172.16.0.8:50801` | `/api/v1/upi/connector/payin/sabpaisa-h2h/**` |
| SBNK | `http://172.16.1.170:50100` | `/api/v1/upi/connector/payin/sbnk/**` |
| File Payout | `http://172.16.0.8:50999` | `/api/v1/upi/connector/payout/file/**` |

## Key Discovery: SMS Processor

The SMS processor at `http://172.16.0.8:40600` handles:
- `/api/v1/upi/sms/process` — Process incoming bank SMS
- `/api/v1/upi/sms/push` — Push SMS data into the system
- `/api/v1/upi/sms/log` — SMS logs

Currently **DOWN** on production (`failed to resolve 'upi-sms-processor'`), but route exists on UAT.

## UAT Gateway Users (41 total, with bcrypt hashes)

| Username | Role | Status |
|----------|------|--------|
| `superadmin@upi` | ROLE_SUPERADMIN | Active |
| `godmode@gmail.com` | ROLE_SUPERADMIN | Active |
| `deepaktest@paytom` | ROLE_SUPERADMIN | Active |
| `dev@uat.com` | ROLE_SUPERADMIN | Active |
| `dana@uat.com` | ROLE_SUPERADMIN | Active |
| `jimmy@gmail.com` | ROLE_SUPERADMIN | Active |
| `testertestington` | ROLE_SUPERADMIN | Active |
| `newsuperadmin123` | ROLE_SUPERADMIN | Active |
| `hitman@wizpay` | ROLE_DISTRIBUTOR_ADMIN | Active |

## Callback URLs (where confirmed payments are sent)

```
DEFAULT → https://agentpay.leopay.live
NETL    → https://agentpay.netl.com
MEX     → https://agent.texmex.org
FINOVEX → https://agent.FINOVEX.org
```

## SMS Forward URL
```
https://api.qrbonpay.com/api/v1/upi/sms/forward
```

## Default Passwords
From config: `DEFAULT_PASSWORD`, `741909`, `20050418`
