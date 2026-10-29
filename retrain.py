import json, sqlite3, joblib, pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import average_precision_score, precision_recall_curve
from xgboost import XGBClassifier
from features import build_features

FEATURES = joblib.load("mule_model.joblib")["features"]

con = sqlite3.connect("muleradar.db")
tx = pd.read_sql("SELECT ts, from_bank, sender, to_bank, receiver, amount, cur_paid, fmt "
                 "FROM transactions", con, parse_dates=["ts"])
labels = pd.read_sql("SELECT account, is_mule, source FROM labels", con)
con.close()
for c in ("fmt", "cur_paid"):
    tx[c] = tx[c].astype("category")

print("transactions:", len(tx), "| labels:", len(labels),
      "| admin labels:", int((labels.source == "admin").sum()))

df = build_features(tx).merge(labels[["account", "is_mule"]], on="account")   # sirf label wale accounts
print("training accounts:", len(df), "| mules:", int(df.is_mule.sum()))

train_df, test_df = train_test_split(df, test_size=0.25, stratify=df.is_mule, random_state=1)
pos_w = (train_df.is_mule == 0).sum() / train_df.is_mule.sum()

model = XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05, subsample=0.8,
                      colsample_bytree=0.8, scale_pos_weight=pos_w, eval_metric="aucpr", n_jobs=-1)
model.fit(train_df[FEATURES], train_df.is_mule)

s = model.predict_proba(test_df[FEATURES])[:, 1]
print("PR-AUC:", average_precision_score(test_df.is_mule, s))

p, r, t = precision_recall_curve(test_df.is_mule, s)
f1 = 2 * p * r / (p + r + 1e-9)
thr = float(t[f1[:-1].argmax()])

# joblib.dump({"model": model, "features": FEATURES}, "mule_model_new.joblib")
# json.dump({"threshold": thr}, open("threshold_new.json", "w"))
# print("saved: mule_model_new.joblib + threshold_new.json | new threshold:", round(thr, 4))
import shutil, time

pr_new = average_precision_score(test_df.is_mule, s)
old = joblib.load("mule_model.joblib")
pr_old = average_precision_score(test_df.is_mule, old["model"].predict_proba(test_df[FEATURES])[:, 1])
print(f"PR-AUC old: {pr_old:.4f} | new: {pr_new:.4f}")

if pr_new >= pr_old - 0.02:        # thoda farak chalta hai, bada girna nahi
    stamp = time.strftime("%Y%m%d_%H%M")
    shutil.copy("mule_model.joblib", f"backup_model_{stamp}.joblib")
    shutil.copy("threshold.json", f"backup_threshold_{stamp}.json")
    joblib.dump({"model": model, "features": FEATURES}, "mule_model.joblib")
    json.dump({"threshold": thr}, open("threshold.json", "w"))
    print("model REPLACED")
else:
    print("Weak model , old one kept")