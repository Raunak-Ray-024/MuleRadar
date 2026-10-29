import sqlite3, pandas as pd

CSV = r"C:\Users\sanja\.cache\kagglehub\datasets\ealtman2019\ibm-transactions-for-anti-money-laundering-aml\versions\8\HI-Small_Trans.csv"

cols = ["ts","from_bank","sender","to_bank","receiver",
        "amt_recv","cur_recv","amount","cur_paid","fmt","is_laundering"]
use = ["ts","from_bank","sender","to_bank","receiver","amount","cur_paid","fmt"]

con = sqlite3.connect("muleradar.db")
con.execute("DROP TABLE IF EXISTS transactions")
con.execute("""CREATE TABLE transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT, from_bank INTEGER, sender TEXT, to_bank INTEGER,
    receiver TEXT, amount REAL, cur_paid TEXT, fmt TEXT)""")

total = 0
for chunk in pd.read_csv(CSV, header=0, names=cols, usecols=use,
                         parse_dates=["ts"], chunksize=500_000):
    chunk["ts"] = chunk["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    chunk[use].to_sql("transactions", con, if_exists="append", index=False)
    total += len(chunk)
    print(total, "rows saved")

con.execute("CREATE INDEX idx_sender ON transactions(sender)")
con.execute("CREATE INDEX idx_receiver ON transactions(receiver)")
con.commit(); con.close()
print("done")