# FantZo Findings — 1xBit Payment Ecosystem
**Session Date:** 2026-09-25  
**Scope:** Payment gateway infrastructure serving online gambling/forex platforms

---

## Targets Investigated

| File | Target | Status |
|------|--------|--------|
| [01_SILKPAY.md](01_SILKPAY.md) | silkpay.ai / savings-land.com / indianpay.net | Partially Mapped |
| [02_PAYNQUICK.md](02_PAYNQUICK.md) | aws-bridge.paynquick.com / bridge.paynquick.com | Gateway Fingerprinted |
| [03_SUMMITGATE.md](03_SUMMITGATE.md) | summitgateglobal.com / fastsecurepay.asia | PHP Endpoints Found |
| [04_HTPSY.md](04_HTPSY.md) | web.htpsy5364.vip | **CRITICAL — Unauth RCE Surface** |
| [05_GLARNIXO.md](05_GLARNIXO.md) | payment.glarnixo.co / gateway.payment88.io (12+ domains) | **CRITICAL — Unauth Payin/Payout API** |

---

## Priority
1. **`05_GLARNIXO.md`** — 12+ domains, ONE server. Payin/Payout APIs exposed without auth. Full field map extracted. `ip` vs `ipAddress` field bug. With valid merchantCode → creates real orders.
2. **`04_HTPSY.md`** — confirmed unauth DB writes, full API map, Druid monitor exposed.
