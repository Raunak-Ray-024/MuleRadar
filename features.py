import pandas as pd

def build_features(df):
    df = df.assign(cross=(df.from_bank != df.to_bank).astype(int))
    out = df.groupby("sender").agg(
        sent_count=("amount","size"), sent_total=("amount","sum"),
        sent_mean=("amount","mean"), sent_max=("amount","max"),
        n_receivers=("receiver","nunique"), cross_bank_share=("cross","mean"),
        n_formats=("fmt","nunique"), n_currencies=("cur_paid","nunique"),
        first_sent=("ts","min"), last_sent=("ts","max"))
    inn = df.groupby("receiver").agg(
        recv_count=("amount","size"), recv_total=("amount","sum"),
        recv_mean=("amount","mean"), recv_max=("amount","max"),
        n_senders=("sender","nunique"),
        first_recv=("ts","min"), last_recv=("ts","max"))
    f = out.join(inn, how="outer")
    first = f[["first_sent","first_recv"]].min(axis=1)
    last = f[["last_sent","last_recv"]].max(axis=1)
    f["active_hours"] = (last - first).dt.total_seconds() / 3600
    f = f.drop(columns=["first_sent","last_sent","first_recv","last_recv"]).fillna(0)
    f["pass_through"] = f.sent_total / (f.recv_total + 1)
    f["fan_ratio"] = f.n_senders / (f.n_receivers + 1)
    f["txn_rate"] = (f.sent_count + f.recv_count) / (f.active_hours + 1)
    f.index.name = "account"
    return f.reset_index()