"""Risk report: one row per target clause with your rule vs the contract's value, plus the final outcome line."""

CATEGORIES = [("payment", "Payment"), ("renewal", "Auto-renewal"), ("liability", "Liability"),
              ("jurisdiction", "Jurisdiction")]


def _rule_text(key, p):
    return {"payment": f"≤ {p['max_payment_days']} days",
            "renewal": "No auto-renewal" if not p["allow_auto_renewal"] else f"Cancel notice ≤ {p['max_renewal_notice_days']} days",
            "liability": "Must be capped" if p["require_liability_cap"] else "No requirement",
            "jurisdiction": ", ".join(p["allowed_jurisdictions"])}[key]


def _contract_text(key, items):
    if key == "renewal":
        r = [i for i in items if i["value"].get("renews")]
        if not r:
            return "No auto-renewal clause found"
        n = r[0]["value"].get("notice_days")
        return "Auto-renews" + (f", {n} days' notice" if n else "")
    if not items:
        return "Not found"
    if key == "payment":
        return " / ".join(dict.fromkeys(f"{i['value']['days']} days" for i in items))
    if key == "liability":
        return "Unlimited / uncapped" if any(not i["value"].get("capped") for i in items) else "Capped"
    return ", ".join(dict.fromkeys(i["value"]["location"] for i in items))


def build_checks(findings, flags, policy):
    rows = []
    category_map = {"payment": "Payment", "renewal": "Auto-renewal", "liability": "Liability", "jurisdiction": "Jurisdiction"}
    for key, label in CATEGORIES:
        for f in flags:
            if getattr(f, "category", "") == label:
                continue
            if key in ("payment", "renewal", "liability", "jurisdiction") and (
                ("payment" in getattr(f, "rule", "").lower() and key == "payment") or
                ("auto" in getattr(f, "rule", "").lower() and key == "renewal") or
                ("liability" in getattr(f, "rule", "").lower() and key == "liability") or
                ("jurisdiction" in getattr(f, "rule", "").lower() and key == "jurisdiction")
            ):
                f.category = label
        items = [f for f in findings if f["type"] == key]
        fl = [f for f in flags if getattr(f, "category", "") == label]
        if not fl and key in category_map:
            fl = [f for f in flags if category_map[key] in getattr(f, "rule", "") or (key == "renewal" and "auto" in getattr(f, "rule", "").lower())]
        status = "FAIL" if any(f.kind in ("CONFLICT", "MISSING") for f in fl) else "WARN" if fl else "PASS"
        rows.append({"category": label, "rule": _rule_text(key, policy), "contract": _contract_text(key, items),
                     "status": status, "flags": len(fl)})
    return rows


def summarize(checks):
    n = sum(c["status"] != "PASS" for c in checks)
    return f"{n} of {len(checks)} clause types need action before signing" if n else "All clause types pass your rules"
