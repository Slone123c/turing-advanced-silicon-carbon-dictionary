"""把 rules/*.yaml 打包成 web/src/rules.json（React 词典 web/ 读取）。

用法：python build_site.py [--repo owner/name]
"""
import argparse
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent
FIELDS = ("aliases", "why", "suggest", "ok_when", "bad_when")


def collect():
    out = []
    for path in sorted((ROOT / "rules").glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        lang = data.get("lang", path.stem)
        for level, items in (data.get("rules") or {}).items():
            for item in items or []:
                entry = {"term": item["term"], "level": int(level), "lang": lang,
                         "file": f"rules/{path.name}"}
                entry.update({k: item[k] for k in FIELDS if item.get(k)})
                out.append(entry)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="Slone123c/turing-advanced-silicon-carbon-dictionary")
    args = ap.parse_args()
    payload = {"repo": args.repo, "rules": collect()}
    web_dest = ROOT / "web" / "src" / "rules.json"
    if web_dest.parent.exists():
        web_dest.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                            encoding="utf-8")
        print(f"{len(payload['rules'])} terms → {web_dest.relative_to(ROOT)}")
    worker_dest = ROOT / "worker" / "terms.json"
    if worker_dest.parent.exists():
        terms_by_lang = {}
        for entry in payload["rules"]:
            terms_by_lang.setdefault(entry["lang"], set()).add(entry["term"])
        worker_payload = {lang: sorted(terms) for lang, terms in sorted(terms_by_lang.items())}
        worker_dest.write_text(
            json.dumps(worker_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        total_terms = sum(len(terms) for terms in worker_payload.values())
        print(f"{total_terms} terms → {worker_dest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
