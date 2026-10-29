# import json, sqlite3, hashlib, joblib, pandas as pd
# from datetime import datetime
# from typing import Optional
# from fastapi import FastAPI, HTTPException, Depends, Security
# from fastapi.security import APIKeyHeader
# from pydantic import BaseModel
# from features import build_features

# app = FastAPI(title="MuleRadar")

# saved = joblib.load("mule_model.joblib")
# model, FEATURES = saved["model"], saved["features"]
# THRESHOLD = json.load(open("threshold.json"))["threshold"]
# DB = "muleradar.db"


# # ---------------------------------------------------------------- RBAC

# api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# def init_auth():
#     con = sqlite3.connect(DB)
#     con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT, key_hash TEXT)")
#     con.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
#                 "ts TEXT, username TEXT, action TEXT, detail TEXT)")
#     con.commit(); con.close()

# init_auth()


# def current_user(key: Optional[str] = Security(api_key_header)):
#     if not key:
#         raise HTTPException(status_code=401, detail="API key chahiye (X-API-Key)")
#     con = sqlite3.connect(DB)
#     row = con.execute("SELECT username, role FROM users WHERE key_hash = ?",
#                       (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
#     con.close()
#     if row is None:
#         raise HTTPException(status_code=401, detail="API key galat hai")
#     return {"username": row[0], "role": row[1]}


# def require(*roles):
#     def checker(user=Depends(current_user)):
#         if user["role"] not in roles:
#             raise HTTPException(status_code=403, detail=f"{user['role']} ko iski ijazat nahi")
#         return user
#     return checker


# def audit(username, action, detail=""):
#     con = sqlite3.connect(DB)
#     con.execute("INSERT INTO audit_log (ts, username, action, detail) VALUES (?,?,?,?)",
#                 (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action, detail))
#     con.commit(); con.close()


# # ---------------------------------------------------------------- scoring

# def account_row(account):
#     """Is account ke saare transactions database se uthao aur uske features banao."""
#     con = sqlite3.connect(DB)
#     d = pd.read_sql(
#         "SELECT ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt "
#         "FROM transactions WHERE sender = ? OR receiver = ?",
#         con, params=(account, account), parse_dates=["ts"])
#     con.close()
#     if d.empty:
#         return None
#     f = build_features(d)
#     return f[f.account == account]


# def score_account(account):
#     row = account_row(account)
#     if row is None:
#         return None
#     s = float(model.predict_proba(row[FEATURES])[0, 1])
#     return {
#         "account": account,
#         "score": round(s, 4),
#         "is_suspicious": s >= THRESHOLD,
#         "threshold": round(THRESHOLD, 4),
#         "transactions_seen": int(row.sent_count.iloc[0] + row.recv_count.iloc[0]),
#     }


# class TxIn(BaseModel):
#     sender: str
#     receiver: str
#     amount: float
#     from_bank: int = 0
#     to_bank: int = 0
#     cur_paid: str = "US Dollar"
#     fmt: str = "ACH"
#     ts: Optional[datetime] = None


# class LabelIn(BaseModel):
#     account: str
#     is_mule: int          # 1 = mule, 0 = normal


# # ---------------------------------------------------------------- endpoints

# @app.get("/")
# def home():
#     con = sqlite3.connect(DB)
#     n = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
#     con.close()
#     return {"status": "ok", "transactions_in_db": n}


# @app.get("/score/{account}")
# def score(account: str, user=Depends(require("analyst", "admin"))):
#     r = score_account(account)
#     if r is None:
#         raise HTTPException(status_code=404, detail="Account data me nahi mila")
#     return r


# @app.post("/transactions")
# def add_transaction(t: TxIn, user=Depends(require("analyst", "admin"))):
#     ts = (t.ts or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
#     con = sqlite3.connect(DB)
#     con.execute(
#         "INSERT INTO transactions (ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt) "
#         "VALUES (?,?,?,?,?,?,?,?)",
#         (ts, t.from_bank, t.sender, t.to_bank, t.receiver, t.amount, t.cur_paid, t.fmt))
#     con.commit(); con.close()
#     return {"saved": True, "sender": score_account(t.sender), "receiver": score_account(t.receiver)}


# @app.post("/label")
# def add_label(l: LabelIn, user=Depends(require("admin"))):
#     if l.is_mule not in (0, 1):
#         raise HTTPException(status_code=400, detail="is_mule sirf 0 ya 1 ho sakta hai")
#     con = sqlite3.connect(DB)
#     con.execute(
#         "INSERT INTO labels (account, is_mule, source) VALUES (?, ?, 'admin') "
#         "ON CONFLICT(account) DO UPDATE SET is_mule = excluded.is_mule, source = 'admin'",
#         (l.account, l.is_mule))
#     con.commit(); con.close()
#     audit(user["username"], "LABEL", f"{l.account}={l.is_mule}")
#     return {"saved": True, "account": l.account, "is_mule": l.is_mule}


# @app.get("/rings")
# def get_rings(min_size: int = 3, user=Depends(require("analyst", "admin"))):
#     try:
#         data = json.load(open("rings.json"))
#     except FileNotFoundError:
#         raise HTTPException(status_code=404, detail="Pehle python rings.py chalao")
#     return [r for r in data if r["size"] >= min_size]


# def init_cases():
#     con = sqlite3.connect(DB)
#     con.execute("""CREATE TABLE IF NOT EXISTS cases (
#         id INTEGER PRIMARY KEY AUTOINCREMENT, ring_id INTEGER, accounts TEXT,
#         report TEXT, status TEXT DEFAULT 'PENDING', created_at TEXT)""")
#     con.commit(); con.close()

# init_cases()


# @app.post("/cases/generate/{ring_id}")
# def generate_case(ring_id: int, user=Depends(require("analyst", "admin"))):
#     from agent import write_case_report
#     rings = json.load(open("rings.json"))
#     ring = next((r for r in rings if r["ring_id"] == ring_id), None)
#     if ring is None:
#         raise HTTPException(status_code=404, detail="ring_id nahi mila")
#     key = ",".join(ring["accounts"])
#     con = sqlite3.connect(DB)
#     old = con.execute("SELECT id, status FROM cases WHERE accounts = ?", (key,)).fetchone()
#     if old:
#         con.close()
#         return {"case_id": old[0], "status": old[1], "note": "is ring ka case pehle se hai"}
#     report = write_case_report(ring)
#     cur = con.execute("INSERT INTO cases (ring_id, accounts, report, created_at) VALUES (?,?,?,?)",
#                       (ring_id, key, report, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
#     con.commit(); cid = cur.lastrowid; con.close()
#     audit(user["username"], "GENERATE", f"ring {ring_id} -> case {cid}")
#     return {"case_id": cid, "status": "PENDING", "report": report}


# @app.get("/cases")
# def list_cases(status: str = "PENDING", user=Depends(require("analyst", "admin"))):
#     con = sqlite3.connect(DB)
#     rows = con.execute("SELECT id, ring_id, accounts, report, status, created_at FROM cases WHERE status = ?",
#                        (status,)).fetchall()
#     con.close()
#     return [{"case_id": r[0], "ring_id": r[1], "accounts": r[2].split(","), "report": r[3],
#              "status": r[4], "created_at": r[5]} for r in rows]


# def decide(case_id: int, status: str, label: int, username: str):
#     con = sqlite3.connect(DB)
#     row = con.execute("SELECT accounts, status FROM cases WHERE id = ?", (case_id,)).fetchone()
#     if row is None:
#         con.close(); raise HTTPException(status_code=404, detail="case nahi mila")
#     if row[1] != "PENDING":
#         con.close(); raise HTTPException(status_code=400, detail=f"case pehle se {row[1]} hai")
#     accs = row[0].split(",")
#     con.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
#     con.executemany(
#         "INSERT INTO labels (account, is_mule, source) VALUES (?, ?, 'admin') "
#         "ON CONFLICT(account) DO UPDATE SET is_mule = excluded.is_mule, source = 'admin'",
#         [(a, label) for a in accs])
#     con.commit(); con.close()
#     audit(username, status, f"case {case_id}: {len(accs)} accounts, is_mule={label}")
#     return {"case_id": case_id, "status": status, "accounts_labelled": len(accs)}


# @app.post("/cases/{case_id}/approve")
# def approve_case(case_id: int, user=Depends(require("admin"))):
#     return decide(case_id, "APPROVED", 1, user["username"])


# @app.post("/cases/{case_id}/reject")
# def reject_case(case_id: int, user=Depends(require("admin"))):
#     return decide(case_id, "REJECTED", 0, user["username"])


# @app.post("/reload-model")
# def reload_model(user=Depends(require("admin"))):
#     global model, FEATURES, THRESHOLD
#     saved = joblib.load("mule_model.joblib")
#     model, FEATURES = saved["model"], saved["features"]
#     THRESHOLD = json.load(open("threshold.json"))["threshold"]
#     audit(user["username"], "RELOAD_MODEL", f"threshold={round(THRESHOLD, 4)}")
#     return {"reloaded": True, "threshold": round(THRESHOLD, 4)}


# @app.get("/audit")
# def get_audit(limit: int = 50, user=Depends(require("admin"))):
#     con = sqlite3.connect(DB)
#     rows = con.execute("SELECT ts, username, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
#                        (limit,)).fetchall()
#     con.close()
#     return [{"ts": r[0], "user": r[1], "action": r[2], "detail": r[3]} for r in rows]







import os, sys, json, sqlite3, hashlib, subprocess, threading, joblib, pandas as pd
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from features import build_features

app = FastAPI(title="MuleRadar")
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
from fastapi.responses import FileResponse
from public import build_router

saved = joblib.load("mule_model.joblib")
model, FEATURES = saved["model"], saved["features"]
THRESHOLD = json.load(open("threshold.json"))["threshold"]
DB = "muleradar.db"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------- RBAC

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def init_auth():
    con = sqlite3.connect(DB)
    con.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, role TEXT, key_hash TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS audit_log (id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "ts TEXT, username TEXT, action TEXT, detail TEXT)")
    con.commit(); con.close()

init_auth()


def current_user(key: Optional[str] = Security(api_key_header)):
    if not key:
        raise HTTPException(status_code=401, detail="API key chahiye (X-API-Key)")
    con = sqlite3.connect(DB)
    row = con.execute("SELECT username, role FROM users WHERE key_hash = ?",
                      (hashlib.sha256(key.encode()).hexdigest(),)).fetchone()
    con.close()
    if row is None:
        raise HTTPException(status_code=401, detail="API key galat hai")
    return {"username": row[0], "role": row[1]}


def require(*roles):
    def checker(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"{user['role']} ko iski ijazat nahi")
        return user
    return checker


def audit(username, action, detail=""):
    con = sqlite3.connect(DB)
    con.execute("INSERT INTO audit_log (ts, username, action, detail) VALUES (?,?,?,?)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, action, detail))
    con.commit(); con.close()


# ---------------------------------------------------------------- scoring

def account_row(account):
    """Is account ke saare transactions database se uthao aur uske features banao."""
    con = sqlite3.connect(DB)
    d = pd.read_sql(
        "SELECT ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt "
        "FROM transactions WHERE sender = ? OR receiver = ?",
        con, params=(account, account), parse_dates=["ts"])
    con.close()
    if d.empty:
        return None
    f = build_features(d)
    return f[f.account == account]


def score_account(account):
    row = account_row(account)
    if row is None:
        return None
    s = float(model.predict_proba(row[FEATURES])[0, 1])
    return {
        "account": account,
        "score": round(s, 4),
        "is_suspicious": s >= THRESHOLD,
        "threshold": round(THRESHOLD, 4),
        "transactions_seen": int(row.sent_count.iloc[0] + row.recv_count.iloc[0]),
    }


class TxIn(BaseModel):
    sender: str
    receiver: str
    amount: float
    from_bank: int = 0
    to_bank: int = 0
    cur_paid: str = "US Dollar"
    fmt: str = "ACH"
    ts: Optional[datetime] = None


class LabelIn(BaseModel):
    account: str
    is_mule: int          # 1 = mule, 0 = normal


# ---------------------------------------------------------------- endpoints

@app.get("/")
def home():
    con = sqlite3.connect(DB)
    n = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
    con.close()
    return {"status": "ok", "transactions_in_db": n}


@app.get("/score/{account}")
def score(account: str, user=Depends(require("analyst", "admin"))):
    r = score_account(account)
    if r is None:
        raise HTTPException(status_code=404, detail="Account data me nahi mila")
    return r


@app.post("/transactions")
def add_transaction(t: TxIn, user=Depends(require("analyst", "admin"))):
    ts = (t.ts or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO transactions (ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (ts, t.from_bank, t.sender, t.to_bank, t.receiver, t.amount, t.cur_paid, t.fmt))
    con.commit(); con.close()
    return {"saved": True, "sender": score_account(t.sender), "receiver": score_account(t.receiver)}


@app.post("/label")
def add_label(l: LabelIn, user=Depends(require("admin"))):
    if l.is_mule not in (0, 1):
        raise HTTPException(status_code=400, detail="is_mule sirf 0 ya 1 ho sakta hai")
    con = sqlite3.connect(DB)
    con.execute(
        "INSERT INTO labels (account, is_mule, source) VALUES (?, ?, 'admin') "
        "ON CONFLICT(account) DO UPDATE SET is_mule = excluded.is_mule, source = 'admin'",
        (l.account, l.is_mule))
    con.commit(); con.close()
    audit(user["username"], "LABEL", f"{l.account}={l.is_mule}")
    return {"saved": True, "account": l.account, "is_mule": l.is_mule}


@app.get("/rings")
def get_rings(min_size: int = 3, user=Depends(require("analyst", "admin"))):
    try:
        data = json.load(open("rings.json"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Pehle python rings.py chalao")
    return [r for r in data if r["size"] >= min_size]


def init_cases():
    con = sqlite3.connect(DB)
    con.execute("""CREATE TABLE IF NOT EXISTS cases (
        id INTEGER PRIMARY KEY AUTOINCREMENT, ring_id INTEGER, accounts TEXT,
        report TEXT, status TEXT DEFAULT 'PENDING', created_at TEXT)""")
    con.commit(); con.close()

init_cases()


@app.post("/cases/generate/{ring_id}")
def generate_case(ring_id: int, user=Depends(require("analyst", "admin"))):
    from agent import write_case_report
    rings = json.load(open("rings.json"))
    ring = next((r for r in rings if r["ring_id"] == ring_id), None)
    if ring is None:
        raise HTTPException(status_code=404, detail="ring_id nahi mila")
    key = ",".join(ring["accounts"])
    con = sqlite3.connect(DB)
    old = con.execute("SELECT id, status FROM cases WHERE accounts = ?", (key,)).fetchone()
    if old:
        con.close()
        return {"case_id": old[0], "status": old[1], "note": "is ring ka case pehle se hai"}
    report = write_case_report(ring)
    cur = con.execute("INSERT INTO cases (ring_id, accounts, report, created_at) VALUES (?,?,?,?)",
                      (ring_id, key, report, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    con.commit(); cid = cur.lastrowid; con.close()
    audit(user["username"], "GENERATE", f"ring {ring_id} -> case {cid}")
    return {"case_id": cid, "status": "PENDING", "report": report}


@app.get("/cases")
def list_cases(status: str = "PENDING", user=Depends(require("analyst", "admin"))):
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT id, ring_id, accounts, report, status, created_at FROM cases WHERE status = ?",
                       (status,)).fetchall()
    con.close()
    return [{"case_id": r[0], "ring_id": r[1], "accounts": r[2].split(","), "report": r[3],
             "status": r[4], "created_at": r[5]} for r in rows]


def decide(case_id: int, status: str, label: int, username: str):
    con = sqlite3.connect(DB)
    row = con.execute("SELECT accounts, status FROM cases WHERE id = ?", (case_id,)).fetchone()
    if row is None:
        con.close(); raise HTTPException(status_code=404, detail="case nahi mila")
    if row[1] != "PENDING":
        con.close(); raise HTTPException(status_code=400, detail=f"case pehle se {row[1]} hai")
    accs = row[0].split(",")
    con.execute("UPDATE cases SET status = ? WHERE id = ?", (status, case_id))
    con.executemany(
        "INSERT INTO labels (account, is_mule, source) VALUES (?, ?, 'admin') "
        "ON CONFLICT(account) DO UPDATE SET is_mule = excluded.is_mule, source = 'admin'",
        [(a, label) for a in accs])
    con.commit(); con.close()
    audit(username, status, f"case {case_id}: {len(accs)} accounts, is_mule={label}")
    return {"case_id": case_id, "status": status, "accounts_labelled": len(accs)}


@app.post("/cases/{case_id}/approve")
def approve_case(case_id: int, user=Depends(require("admin"))):
    return decide(case_id, "APPROVED", 1, user["username"])


@app.post("/cases/{case_id}/reject")
def reject_case(case_id: int, user=Depends(require("admin"))):
    return decide(case_id, "REJECTED", 0, user["username"])


def _load_model():
    """mule_model.joblib aur threshold.json dobara padho (server band kiye bina)."""
    global model, FEATURES, THRESHOLD
    saved = joblib.load(os.path.join(BASE_DIR, "mule_model.joblib"))
    model, FEATURES = saved["model"], saved["features"]
    THRESHOLD = json.load(open(os.path.join(BASE_DIR, "threshold.json")))["threshold"]


@app.post("/reload-model")
def reload_model(user=Depends(require("admin"))):
    _load_model()
    audit(user["username"], "RELOAD_MODEL", f"threshold={round(THRESHOLD, 4)}")
    return {"reloaded": True, "threshold": round(THRESHOLD, 4)}


# ---------------------------------------------------------------- background jobs
# rings.py aur retrain.py bhaari hain (kuch second se kuch minute), isliye unhe alag
# process mein chalate hain. API atakti nahi, aur ek samay mein sirf ek job chalti hai.

JOBS = {"rings": {"state": "idle"}, "retrain": {"state": "idle"}}
JOB_LOCK = threading.Lock()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _run_job(name, cmd, username):
    try:
        p = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=3600)
        out = (p.stdout or "") + "\n" + (p.stderr or "")
        ok = p.returncode == 0
    except Exception as e:
        out, ok = f"job chal nahi payi: {e}", False

    replaced = False
    if name == "retrain" and ok and "model REPLACED" in out:
        try:
            _load_model()
            replaced = True
        except Exception as e:
            out += f"\nnaya model load nahi hua: {e}"

    lines = [l for l in out.strip().splitlines() if l.strip()]
    JOBS[name] = {**JOBS[name], "state": "done" if ok else "failed", "finished": _now(),
                  "model_replaced": replaced, "output_tail": "\n".join(lines[-12:])}
    audit(username, f"{name.upper()}_{'DONE' if ok else 'FAILED'}", f"model_replaced={replaced}")


def _start_job(name, cmd, user):
    with JOB_LOCK:
        if any(j.get("state") == "running" for j in JOBS.values()):
            raise HTTPException(status_code=409, detail="Ek job pehle se chal rahi hai, khatam hone do")
        JOBS[name] = {"state": "running", "started": _now(), "by": user["username"]}
    audit(user["username"], f"{name.upper()}_START", " ".join(cmd[1:]))
    threading.Thread(target=_run_job, args=(name, cmd, user["username"]), daemon=True).start()
    return {"started": True, "job": name, "check": "GET /jobs"}


@app.post("/rings/refresh", status_code=202)
def refresh_rings(rebuild_features: bool = False, user=Depends(require("admin"))):
    """rings.py chalata hai. rebuild_features=true: pehle database se saare features dobara banata hai
    (naye transactions bhi rings mein aate hain, par 1-2 minute aur kaafi RAM lagti hai)."""
    cmd = [sys.executable, "rings.py"] + (["--rebuild"] if rebuild_features else [])
    return _start_job("rings", cmd, user)


@app.post("/retrain", status_code=202)
def retrain_model(user=Depends(require("admin"))):
    """retrain.py chalata hai. Naya model theek laga to apne aap replace aur reload ho jaata hai."""
    return _start_job("retrain", [sys.executable, "retrain.py"], user)


@app.get("/jobs")
def job_status(user=Depends(require("admin"))):
    return JOBS


@app.get("/audit")
def get_audit(limit: int = 50, user=Depends(require("admin"))):
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT ts, username, action, detail FROM audit_log ORDER BY id DESC LIMIT ?",
                       (limit,)).fetchall()
    con.close()
    return [{"ts": r[0], "user": r[1], "action": r[2], "detail": r[3]} for r in rows]


class UserIn(BaseModel):
    username: str
    role: str   # "analyst" or "admin"

import secrets
@app.post("/users")
def create_user(u: UserIn, user=Depends(require("admin"))):
    if u.role not in ("analyst", "admin"):
        raise HTTPException(status_code=400, detail="role sirf analyst ya admin ho sakta hai")
    key = secrets.token_urlsafe(32)
    con = sqlite3.connect(DB)
    try:
        con.execute("INSERT INTO users (username, role, key_hash) VALUES (?,?,?)",
                    (u.username, u.role, hashlib.sha256(key.encode()).hexdigest()))
        con.commit()
    except sqlite3.IntegrityError:
        con.close()
        raise HTTPException(status_code=409, detail="username pehle se hai")
    con.close()
    audit(user["username"], "CREATE_USER", f"{u.username} ({u.role})")
    return {"username": u.username, "role": u.role, "api_key": key}  # shown only once

@app.get("/users")
def list_users(user=Depends(require("admin"))):
    con = sqlite3.connect(DB)
    rows = con.execute("SELECT username, role FROM users ORDER BY username").fetchall()
    con.close()
    return [{"username": r[0], "role": r[1]} for r in rows]


@app.delete("/users/{username}")
def delete_user(username: str, user=Depends(require("admin"))):
    if username == user["username"]:
        raise HTTPException(status_code=400, detail="Apne aap ko delete nahi kar sakte")
    con = sqlite3.connect(DB)
    row = con.execute("SELECT role FROM users WHERE username = ?", (username,)).fetchone()
    if row is None:
        con.close()
        raise HTTPException(status_code=404, detail="user nahi mila")
    con.execute("DELETE FROM users WHERE username = ?", (username,))
    con.commit(); con.close()
    audit(user["username"], "DELETE_USER", f"{username} ({row[0]})")
    return {"deleted": True, "username": username}


@app.get("/app", include_in_schema=False)
def frontend():
    return FileResponse(os.path.join(BASE_DIR, "muleradar.html"))



# after your audit() function is defined:
app.include_router(build_router(require, audit, DB))

@app.get("/app", include_in_schema=False)
def frontend():
    return FileResponse(os.path.join(BASE_DIR, "muleradar.html"))