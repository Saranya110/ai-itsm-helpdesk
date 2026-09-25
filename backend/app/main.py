from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.55"))

ARTICLES = [
    {"id":"KB001","title":"VPN Troubleshooting","category":"Network","text":"If VPN authentication fails, verify your username and password, check that your account is not locked, confirm your device date and time, and reconnect to the approved VPN gateway. Restart the VPN client and collect the exact error. If sign-in still fails, contact Network Support. Never share your password."},
    {"id":"KB002","title":"Password Reset and Account Unlock","category":"Accounts","text":"Use the company password reset portal to change an expired password. After resetting, wait a few minutes and sign in again. If the account is locked, request an account unlock through the helpdesk. Do not send passwords over chat or email."},
    {"id":"KB003","title":"Outlook Synchronization","category":"Email","text":"For Outlook sync delays, check network connectivity and Outlook service status, then select Send/Receive > Update Folder. Restart Outlook. If the issue continues, capture the time and any error message and contact the Messaging team. Do not delete the mail profile without IT approval."},
    {"id":"KB004","title":"Corporate Wi-Fi Connection","category":"Network","text":"Select the approved corporate Wi-Fi network and sign in with your company account. Forget and rejoin the network if authentication fails. Check that airplane mode is off. Persistent failures should be escalated to Network Support with your device name and location."},
    {"id":"KB005","title":"Laptop Performance","category":"Hardware","text":"Restart the laptop, close applications you are not using, and check available disk space. Install operating system updates only through company-managed update tools. If performance remains poor, report the device name and when the slowdown occurs to Desktop Support."},
    {"id":"KB006","title":"Software Installation","category":"Software","text":"Request approved software through the employee software catalogue. Include the software name and business purpose. IT will review the request and provision it through managed device tools. Local administrator access is not required."},
    {"id":"KB007","title":"Application Access","category":"Access","text":"Request access through the service portal, naming the application and required role. Your manager may need to approve access. If access was recently granted, sign out and back in. Do not share another employee's account."},
]

app = FastAPI(title="Sorim AI ITSM Helpdesk", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Optional MongoDB Atlas persistence; local demo remains usable without credentials.
mongo = None
try:
    if os.getenv("MONGODB_URI"):
        from pymongo import MongoClient
        mongo = MongoClient(os.environ["MONGODB_URI"], serverSelectionTimeoutMS=1800)[os.getenv("MONGODB_DATABASE", "itsm_helpdesk")]
        mongo.command("ping")
except Exception as exc:
    print(f"MongoDB unavailable; using local demo storage ({exc.__class__.__name__})")

# Chroma + open embeddings are selected when installed. Lexical fallback keeps first-run demo fast.
collection = None
try:
    import chromadb
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
    ef = SentenceTransformerEmbeddingFunction(model_name=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
    client = chromadb.PersistentClient(path=str(DATA_DIR / "chroma"))
    collection = client.get_or_create_collection("itsm_knowledge", embedding_function=ef)
    if collection.count() == 0:
        collection.add(ids=[a["id"] for a in ARTICLES], documents=[a["text"] for a in ARTICLES], metadatas=[{"title":a["title"],"category":a["category"]} for a in ARTICLES])
except Exception as exc:
    print(f"Vector model unavailable; using local lexical retrieval ({exc.__class__.__name__})")

def now() -> str:
    return datetime.now(timezone.utc).isoformat()

def save(name: str, record: dict[str, Any]) -> None:
    if mongo is not None:
        mongo[name].insert_one(record.copy())
    else:
        path = DATA_DIR / f"{name}.jsonl"
        with path.open("a", encoding="utf-8") as stream:
            import json
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")

def records(name: str) -> list[dict[str, Any]]:
    if mongo is not None:
        return list(mongo[name].find({}, {"_id": 0}).sort("created_at", -1).limit(100))
    path = DATA_DIR / f"{name}.jsonl"
    if not path.exists(): return []
    import json
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line][-100:][::-1]

def retrieve(query: str) -> list[dict[str, Any]]:
    if collection is not None:
        result = collection.query(query_texts=[query], n_results=3, include=["documents", "metadatas", "distances"])
        out=[]
        for i, doc in enumerate(result["documents"][0]):
            distance=result["distances"][0][i]
            out.append({"id": result["ids"][0][i], "title": result["metadatas"][0][i]["title"], "category": result["metadatas"][0][i]["category"], "text": doc, "score": round(max(0, 1-distance), 3)})
        return out
    stop_words={"a","an","and","are","as","at","be","can","do","does","for","how","i","in","is","it","me","my","of","on","or","please","the","to","what","when","where","with"}
    terms=set(re.findall(r"[a-z0-9]+", query.lower()))-stop_words
    scored=[]
    for article in ARTICLES:
        words=set(re.findall(r"[a-z0-9]+", article["title"]+" "+article["text"].lower()))
        score=len(terms & words)/max(1,len(terms))
        scored.append((score, article))
    scored.sort(key=lambda x:x[0], reverse=True)
    return [{**a,"score":round(s,3)} for s,a in scored[:3] if s>=0.2]

def analyze(text: str) -> dict[str, Any]:
    t=text.lower()
    if any(k in t for k in ["install", "provision", "software catalogue", "software catalog"]):
        intent, category, sub, summary, group = "Service Request", "Software", "Provisioning", "Software provisioning request", "Software Support"
        priority="P3"; kind="software"
    elif any(k in t for k in ["password", "unlock", "locked out", "expired"]):
        intent, category, sub, summary, group = "Automatable Issue", "Account", "Password / Account Access", "Password reset or account unlock", "Identity Support"
        priority="P3"; kind="password"
    elif any(k in t for k in ["vpn", "wi-fi", "wifi", "network", "internet"]):
        intent, category, sub, summary, group = "Incident", "Network", "VPN" if "vpn" in t else "Connectivity", "VPN authentication failure" if "vpn" in t else "Network connectivity issue", "Network Support"
        priority="P2"; kind="incident"
    elif any(k in t for k in ["outlook", "email", "mail sync"]):
        intent, category, sub, summary, group = "Incident", "Email", "Synchronization", "Outlook synchronization issue", "Messaging Support"
        priority="P3"; kind="incident"
    elif any(k in t for k in ["slow", "performance", "laptop"]):
        intent, category, sub, summary, group = "Incident", "Hardware", "Performance", "Laptop performance issue", "Desktop Support"
        priority="P3"; kind="incident"
    else:
        intent, category, sub, summary, group = "Knowledge Question", "General", "Unknown", "Helpdesk assistance requested", "Service Desk"
        priority="P3"; kind="unknown"
    conf=0.91 if kind != "unknown" else 0.31
    return {"intent":intent,"category":category,"subcategory":sub,"priority":priority,"impact":"Individual","urgency":"High" if priority=="P2" else "Medium","summary":summary,"assignment_group":group,"confidence":conf,"kind":kind}

def create_ticket(text: str, ai: dict[str, Any], state="Open") -> dict[str, Any]:
    ticket={"number":"INC"+str(100000+uuid.uuid4().int%899999),"description":text,"state":state,"created_at":now(), **ai}
    ticket.pop("kind", None); save("tickets", ticket); return ticket

class Ask(BaseModel):
    message: str = Field(min_length=2, max_length=2000)

@app.get("/api/health")
def health():
    return {"status":"ok","database":"MongoDB Atlas" if mongo is not None else "local demo JSON","vector_db":"Chroma + sentence-transformers" if collection is not None else "local lexical fallback","servicenow":"mock"}

@app.get("/api/dashboard")
def dashboard():
    tickets=records("tickets"); actions=records("audit"); reqs=records("requests")
    return {"total":len(tickets),"open":sum(t.get("state")=="Open" for t in tickets),"resolved":sum(t.get("state")=="Resolved" for t in tickets),"escalated":sum(t.get("state")=="Escalated" for t in tickets),"automation_actions":len(actions),"requests":len(reqs),"tickets":tickets[:8],"recent_actions":actions[:8],"requests_list":reqs[:8]}

@app.get("/api/knowledge")
def knowledge(): return ARTICLES

@app.post("/api/ask")
def ask(req: Ask):
    ai=analyze(req.message); hits=retrieve(req.message)
    grounded=hits and hits[0]["score"] >= (0.22 if collection is not None else 0.2)
    if grounded:
        answer=f"Based on {hits[0]['title']}: {hits[0]['text']}"
    else:
        answer="I couldn't find an approved knowledge article that answers this. I can create a helpdesk ticket for a person to review it."
    result={"analysis":ai,"sources":[{"id":h["id"],"title":h["title"],"category":h["category"],"score":h["score"]} for h in hits if h["score"]>0],"answer":answer,"grounded":bool(grounded),"needs_escalation":ai["confidence"]<THRESHOLD or not grounded}
    if ai["kind"]=="password":
        result["automation"]={"status":"ready","steps":["Identity check passed (demo)","Password reset action executed (mock)","Sign-in validation passed (mock)"],"action":"password_reset"}
    elif ai["kind"]=="software":
        match=re.search(r"(?:install|need|request)\s+(?:to\s+install\s+)?(.+?)(?:\s+on\s+my\s+laptop)?[.!?]*$",req.message,re.I)
        result["software_name"]=(match.group(1).strip() if match else "Requested software").replace("my ", "")
        result["software_name"]=re.sub(r"\s+(?:installed|installing|on my laptop|on my computer).*$", "", result["software_name"], flags=re.I).strip(" .?!")
    return result

@app.post("/api/tickets")
def ticket(req: Ask):
    ai=analyze(req.message); ai["kind"]="unknown" if ai["confidence"]<THRESHOLD else ai["kind"]
    t=create_ticket(req.message, ai, "Escalated" if ai["kind"]=="unknown" else "Open")
    t["servicenow"]="mock" if not os.getenv("SERVICENOW_INSTANCE_URL") else "configured"
    return t

@app.post("/api/automate")
def automate(req: Ask):
    ai=analyze(req.message)
    if ai["kind"]!="password": raise HTTPException(400,"This safe demo action supports password reset or account unlock requests only.")
    t=create_ticket(req.message, ai, "Resolved")
    action={"id":"ACT"+uuid.uuid4().hex[:8].upper(),"action":"password_reset","status":"Validated","target":"Current demo user","ticket":t["number"],"created_at":now(),"detail":"Mock reset executed after simulated identity check; sign-in validation succeeded."}
    save("audit",action)
    return {"ticket":t,"action":action}

@app.post("/api/requests")
def software_request(req: Ask):
    ai=analyze(req.message)
    if ai["kind"]!="software": raise HTTPException(400,"Please describe a software installation or provisioning request.")
    result=ask(req); name=result.get("software_name","Requested software")
    request={"number":"REQ"+str(100000+uuid.uuid4().int%899999),"software":name,"status":"Provisioning","created_at":now(),"servicenow":"mock" if not os.getenv("SERVICENOW_INSTANCE_URL") else "configured"}
    save("requests",request)
    action={"id":"ACT"+uuid.uuid4().hex[:8].upper(),"action":"software_provisioning","status":"Provisioning","target":name,"ticket":request["number"],"created_at":now(),"detail":"Mock provisioning request queued; no software is installed."}
    save("audit",action)
    return {"request":request,"action":action}
