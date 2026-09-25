"""/scan failure-mode matrix. Run: python3 tests/test_scan_matrix.py"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import base64, json
from fastapi.testclient import TestClient
from insidelabel.api.main import app
c = TestClient(app)

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
BOTH = {"back": ("back.png", PNG, "image/png"), "front": ("front.png", PNG, "image/png")}
BACK_ONLY = {"back": ("back.png", PNG, "image/png")}

def mk(**kw):
    base = {"front_status":"read","back_status":"read","ingredients_status":"read",
      "product":{"brand":"Britannia","name":"NutriChoice","variant":"Diabetic Friendly",
                 "net_quantity":"100 g","veg_mark":"veg"},
      "product_match":{"status":"match","evidence":["same pack artwork on both faces"]},
      "front_identity":{"brand":"Britannia","name":"NutriChoice","manufacturer":None},
      "back_identity":{"brand":"Britannia","name":None,"manufacturer":"Britannia Industries","fssai_licence":None},
      "ingredient_lines":["Almonds, Dough Conditioner (INS 223), Emulsifiers (INS 322,","INS 471, INS 472e), Maltodextrin, Soya Protein Isolate,","Sweeteners (INS 965, INS 955), Iodised Salt."],
      "ingredient_count":7,
      "ingredients":["Almonds","Dough Conditioner (INS 223)","Emulsifiers (INS 322, INS 471, INS 472e)",
                     "Maltodextrin","Soya Protein Isolate","Sweeteners (INS 965, INS 955)","Iodised Salt"],
      "allergen_statement":"CONTAINS MILK, WHEAT, SOYA.",
      "front_claims":["SUGAR FREE*","Made with Real Almonds","NO PRESERVATIVES"],
      "front_claim_footnotes":["*No added sucrose"],
      "extraction_notes":[], "confidence":{"ingredients":0.93,"front_claims":0.9,"product_identity":0.95}}
    base.update(kw); return json.dumps(base)

def post(files, **kw):
    return c.post("/scan", files=files, data={"replay": mk(**kw)})

print("A. front+back, happy path")
j = post(BOTH).json()
print("   product:", j["product"]["brand"], j["product"]["name"], "|", j["product"]["variant"])
print("   verdict:", j["verdict"]["binary"], j["verdict"]["grade"], j["verdict"]["score"], "| display:", j["display"])
for ch in j["claim_check"]["checked"]:
    print(f'   {"X" if ch["contradicted"] else "."} "{ch["claim"]}"',
          [f["fact"] for f in ch["contradicted_by"]] or "")

print("\nB. back only, but model claims it read a front")
j = post(BACK_ONLY).json()
print("   corrections:", j["reliability"]["client_corrections"])
print("   claim_check:", j["claim_check"]["status"], "/", j["claim_check"]["reason"])

print("\nC. status 'read' but empty ingredient array")
r = post(BOTH, ingredients=[], ingredient_lines=[], ingredient_count=0); print("   HTTP", r.status_code, "|", r.json()["reliability"]["error"])
print("   corrections:", r.json()["reliability"]["client_corrections"])

print("\nD. partial read that would otherwise be CLEAN")
j = post(BOTH, ingredients_status="partial", ingredients=["Peanuts","Salt"], ingredient_lines=["Peanuts, Salt"], ingredient_count=2).json()
print("   engine binary:", j["verdict"]["binary"], "score", j["verdict"]["score"], "-> display:", j["display"])
print("   caveats:", [x["code"] for x in j["reliability"]["caveats"]])

print("\nE. partial read that is ultra-processed")
j = post(BOTH, ingredients_status="partial").json()
print("   engine binary:", j["verdict"]["binary"], "-> display:", j["display"])

print("\nF. back unreadable")
r = post(BOTH, back_status="unreadable"); print("   HTTP", r.status_code, "|", r.json()["reliability"]["error"])

print("\nG. low confidence")
j = post(BOTH, confidence={"ingredients":0.31,"front_claims":0.9,"product_identity":0.8}).json()
print("   caveats:", [x["code"] for x in j["reliability"]["caveats"]])

print("\nH. model returns prose instead of JSON")
r = c.post("/scan", files=BOTH, data={"replay": "Sure! Here you go:\n```json\n{\"a\":1}\n```"})
print("   HTTP", r.status_code, "|", r.json()["error"], "->", r.json()["detail"][:60])

print("\nI. no images at all")
r = c.post("/scan", data={})
print("   HTTP", r.status_code, "|", r.json()["error"])
