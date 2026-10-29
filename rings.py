# import json, sqlite3, joblib, pandas as pd, networkx as nx

# saved = joblib.load("mule_model.joblib")
# model, FEATURES = saved["model"], saved["features"]
# THRESHOLD = json.load(open("threshold.json"))["threshold"]

# # 1. sab accounts ka score, aur jo threshold ke upar hain wo "flagged"
# feats = pd.read_pickle("account_features.pkl")
# feats["score"] = model.predict_proba(feats[FEATURES])[:, 1]
# flagged = feats[feats.score >= THRESHOLD][["account", "score"]]
# score_of = dict(zip(flagged.account, flagged.score))
# print("flagged accounts:", len(flagged))

# # 2. database se sirf wo transactions jo flagged accounts ke beech hue
# con = sqlite3.connect("muleradar.db")
# con.execute("CREATE TEMP TABLE flagged (account TEXT PRIMARY KEY)")
# con.executemany("INSERT INTO flagged VALUES (?)", [(a,) for a in flagged.account])
# edges = pd.read_sql(
#     "SELECT t.sender, t.receiver FROM transactions t "
#     "JOIN flagged s ON t.sender = s.account "
#     "JOIN flagged r ON t.receiver = r.account "
#     "WHERE t.sender != t.receiver", con)          # self-transfer hata diye
# labels = pd.read_sql("SELECT account, is_mule FROM labels", con)
# con.close()
# label_of = dict(zip(labels.account, labels.is_mule))
# print("transactions between flagged accounts:", len(edges))

# # 3. jude hue accounts ke groups (rings)
# g = nx.Graph()
# g.add_edges_from(zip(edges.sender, edges.receiver))

# rings = []
# for comp in nx.connected_components(g):
#     if len(comp) < 3:
#         continue
#     accs = sorted(comp, key=lambda a: -score_of[a])
#     n_tx = int((edges.sender.isin(comp) & edges.receiver.isin(comp)).sum())
#     rings.append({
#         "size": len(accs),
#         "accounts": accs,
#         "avg_score": round(sum(score_of[a] for a in accs) / len(accs), 4),
#         "transactions": n_tx,
#         "known_mules": int(sum(label_of.get(a, 0) for a in accs)),
#     })

# rings.sort(key=lambda r: (-r["avg_score"], -r["size"]))
# for i, r in enumerate(rings, 1):
#     r["ring_id"] = i

# json.dump(rings, open("rings.json", "w"), indent=2)
# print(len(rings), "rings found")
# for r in rings[:5]:
#     print(f"ring {r['ring_id']}: {r['size']} accounts | avg score {r['avg_score']} | "
#           f"known mules {r['known_mules']}/{r['size']} | {r['transactions']} transactions")






import json, sqlite3, sys, joblib, pandas as pd, networkx as nx

saved = joblib.load("mule_model.joblib")
model, FEATURES = saved["model"], saved["features"]
THRESHOLD = json.load(open("threshold.json"))["threshold"]

# --rebuild: database ke SAARE transactions se features dobara banao (naye transactions bhi aayenge).
# 1-2 minute lagta hai aur kaafi RAM chahiye.
if "--rebuild" in sys.argv:
    from features import build_features
    con = sqlite3.connect("muleradar.db")
    tx = pd.read_sql("SELECT ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt "
                     "FROM transactions", con, parse_dates=["ts"])
    con.close()
    for c in ("fmt", "cur_paid"):
        tx[c] = tx[c].astype("category")
    build_features(tx).to_pickle("account_features.pkl")
    print("features rebuilt from", len(tx), "transactions")
    del tx

# 1. sab accounts ka score, aur jo threshold ke upar hain wo "flagged"
feats = pd.read_pickle("account_features.pkl")
feats["score"] = model.predict_proba(feats[FEATURES])[:, 1]
flagged = feats[feats.score >= THRESHOLD][["account", "score"]]
score_of = dict(zip(flagged.account, flagged.score))
print("flagged accounts:", len(flagged))

# 2. database se sirf wo transactions jo flagged accounts ke beech hue
con = sqlite3.connect("muleradar.db")
con.execute("CREATE TEMP TABLE flagged (account TEXT PRIMARY KEY)")
con.executemany("INSERT INTO flagged VALUES (?)", [(a,) for a in flagged.account])
edges = pd.read_sql(
    "SELECT t.sender, t.receiver FROM transactions t "
    "JOIN flagged s ON t.sender = s.account "
    "JOIN flagged r ON t.receiver = r.account "
    "WHERE t.sender != t.receiver", con)          # self-transfer hata diye
labels = pd.read_sql("SELECT account, is_mule FROM labels", con)
con.close()
label_of = dict(zip(labels.account, labels.is_mule))
print("transactions between flagged accounts:", len(edges))

# 3. jude hue accounts ke groups (rings)
g = nx.Graph()
g.add_edges_from(zip(edges.sender, edges.receiver))

rings = []
for comp in nx.connected_components(g):
    if len(comp) < 3:
        continue
    accs = sorted(comp, key=lambda a: -score_of[a])
    n_tx = int((edges.sender.isin(comp) & edges.receiver.isin(comp)).sum())
    rings.append({
        "size": len(accs),
        "accounts": accs,
        "avg_score": round(sum(score_of[a] for a in accs) / len(accs), 4),
        "transactions": n_tx,
        "known_mules": int(sum(label_of.get(a, 0) for a in accs)),
    })

rings.sort(key=lambda r: (-r["avg_score"], -r["size"]))
for i, r in enumerate(rings, 1):
    r["ring_id"] = i

json.dump(rings, open("rings.json", "w"), indent=2)
print(len(rings), "rings found")
for r in rings[:5]:
    print(f"ring {r['ring_id']}: {r['size']} accounts | avg score {r['avg_score']} | "
          f"known mules {r['known_mules']}/{r['size']} | {r['transactions']} transactions")