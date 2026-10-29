import sqlite3, pandas as pd

lab = pd.read_csv("labels.csv")
lab["source"] = "ibm"

con = sqlite3.connect("muleradar.db")
con.execute("DROP TABLE IF EXISTS labels")
con.execute("CREATE TABLE labels (account TEXT PRIMARY KEY, is_mule INTEGER, source TEXT)")
lab.to_sql("labels", con, if_exists="append", index=False)
con.commit()
print(con.execute("SELECT is_mule, COUNT(*) FROM labels GROUP BY is_mule").fetchall())
con.close()