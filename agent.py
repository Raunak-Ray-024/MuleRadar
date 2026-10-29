import sqlite3, pandas as pd
from typing import TypedDict
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import os

load_dotenv()
RULES = [r.strip() for r in open("rules.txt", encoding="utf-8").read().split("\n\n") if r.strip()]
vec = TfidfVectorizer().fit(RULES)
RULE_M = vec.transform(RULES)
llm = ChatGroq(model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"), temperature=0)


def build_evidence(ring):
    accs = ring["accounts"]
    ph = ",".join("?" * len(accs))
    con = sqlite3.connect("muleradar.db")
    d = pd.read_sql(
        f"SELECT ts, sender, receiver, amount, cur_paid, fmt FROM transactions "
        f"WHERE sender IN ({ph}) AND receiver IN ({ph}) AND sender != receiver",
        con, params=accs + accs, parse_dates=["ts"])
    con.close()

    indeg = d.groupby("receiver").sender.nunique()
    outdeg = d.groupby("sender").receiver.nunique()
    hints = []
    if len(indeg) and indeg.max() >= 3: hints.append("fan-in (one account receives from many senders)")
    if len(outdeg) and outdeg.max() >= 3: hints.append("fan-out (one account sends to many receivers)")
    if not hints: hints.append("chain pass-through (funds move account to account)")

    span = (d.ts.max() - d.ts.min()).total_seconds() / 3600 if len(d) else 0
    return (
        f"Accounts in group: {len(accs)} (examples: {', '.join(accs[:6])})\n"
        f"Average model risk score: {ring['avg_score']}\n"
        f"Transactions among these accounts: {len(d)}\n"
        f"Time span: {span:.1f} hours\n"
        f"Payment formats used: {d.fmt.value_counts().to_dict()}\n"
        f"Currencies used: {d.cur_paid.value_counts().to_dict()}\n"
        f"Pattern observed: {'; '.join(hints)}"
    )


class State(TypedDict, total=False):
    evidence: str
    rules: str
    report: str


def retrieve(s: State):
    sims = cosine_similarity(vec.transform([s["evidence"]]), RULE_M)[0]
    top = [RULES[i] for i in sims.argsort()[::-1][:3]]
    if RULES[-1] not in top:
        top.append(RULES[-1])                     # human-review rule hamesha shamil
    return {"rules": "\n\n".join(top)}


def write(s: State):
    prompt = f"""You are a fraud analyst writing a short case note for a human officer.
Use ONLY the evidence and rules below. Cite rules like [Rule 2]. Say "suspected", never "guilty".
Do not invent amounts, names or facts. Write under 180 words with these headings:
Summary, Key evidence, Rules matched, Recommended action.
Recommended action must say: escalate for human review; do not freeze accounts without approval.
Do not mention account balances, total amounts or anything not listed in EVIDENCE.

EVIDENCE:
{s['evidence']}

RULES:
{s['rules']}"""
    return {"report": llm.invoke(prompt).content}


g = StateGraph(State)
g.add_node("retrieve", retrieve)
g.add_node("write", write)
g.set_entry_point("retrieve")
g.add_edge("retrieve", "write")
g.add_edge("write", END)
graph = g.compile()


def write_case_report(ring):
    return graph.invoke({"evidence": build_evidence(ring)})["report"]