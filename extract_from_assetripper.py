import os, sys, json, yaml, re
ADDR = os.path.expanduser("~/mnt/Assets/Addressables")
OUTDIR = os.path.expanduser("~/ba_json"); os.makedirs(OUTDIR, exist_ok=True)
DROP = {"m_ObjectHideFlags","m_CorrespondingSourceObject","m_PrefabInstance","m_PrefabAsset",
        "m_GameObject","m_Enabled","m_EditorHideFlags","m_Script","m_EditorClassIdentifier"}
def parse(path):
    txt = open(path, encoding="utf-8", errors="replace").read()
    lines = [l for l in txt.splitlines() if not l.startswith("%")]
    lines = ["---" if l.startswith("--- !u!") else l for l in lines]
    try:
        d = yaml.safe_load("\n".join(lines))
    except Exception as e:
        print("PARSE FAIL", path, e); return None
    if not isinstance(d, dict) or "MonoBehaviour" not in d: return None
    mb = d["MonoBehaviour"]
    return {k: v for k, v in mb.items() if k not in DROP}
SECTIONS = {
  "items": ("Items", True),
  "business_types": ("BusinessTypes", False),
  "recipes": ("Factories/Recipes", False),
  "buildings": ("Buildings", True),
  "building_types": ("BuildingTypes", False),
  "building_sizes": ("BuildingSizes", False),
  "job_demands": ("JobDemands", False),
  "ai_business_defaults": ("AiBusinessDefaults", True),
}
for name in sys.argv[1:]:
    sub, rec = SECTIONS[name]
    folder = os.path.join(ADDR, sub)
    out = []
    for root, dirs, files in os.walk(folder):
        if not rec and root != folder: continue
        for fn in sorted(files):
            if fn.endswith(".asset"):
                o = parse(os.path.join(root, fn))
                if o is not None: out.append(o)
    json.dump(out, open(os.path.join(OUTDIR, name + ".json"), "w"), ensure_ascii=False)
    print(name, len(out))
