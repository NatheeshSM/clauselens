"""Step 4: deterministic policy engine. No LLM here: every flag is plain, explainable code."""
from dataclasses import dataclass, asdict

DEFAULT_POLICY = {
    "max_payment_days": 30,
    "allow_auto_renewal": False,
    "max_renewal_notice_days": 30,
    "require_liability_cap": True,
    "allowed_jurisdictions": ["India"],
}

PRESETS = {
    "Freelancer (strict)": DEFAULT_POLICY,
    "Small vendor (relaxed)": {**DEFAULT_POLICY, "max_payment_days": 45, "allow_auto_renewal": True,
                               "max_renewal_notice_days": 60, "allowed_jurisdictions": ["India", "Singapore"]},
}

VAGUE_PHRASES = [
    "reasonable efforts",
    "best efforts",
    "as soon as practicable",
    "in a timely manner",
    "promptly",
    "commercially reasonable",
    "mutually agreeable",
    "subject to approval",
    "to the extent practicable",
]


@dataclass
class Flag:
    kind: str            # CONFLICT | MISSING | WARNING
    rule: str
    message: str
    severity: str        # High | Medium | Low
    suggestion: str
    quote: str = ""
    chunk_id: str = ""
    page: int = 0
    section: str = ""
    category: str = ""
    rule_value: str | None = None
    contract_value: str | None = None

    def to_dict(self):
        return asdict(self)


def infer_policy_from_example(findings):
    """Create a baseline policy from a single example contract. This is useful for demos."""
    policy = dict(DEFAULT_POLICY)
    payment = [f for f in findings if f["type"] == "payment"]
    if payment:
        policy["max_payment_days"] = max(int(f["value"].get("days", 0) or 0) for f in payment)
    renewal = [f for f in findings if f["type"] == "renewal" and f["value"].get("renews")]
    if renewal:
        policy["allow_auto_renewal"] = True
        policy["max_renewal_notice_days"] = max(int(f["value"].get("notice_days", 0) or 0) for f in renewal)
    liability = [f for f in findings if f["type"] == "liability"]
    if liability:
        policy["require_liability_cap"] = any(f["value"].get("capped") is False for f in liability)
    jurisdictions = [f["value"].get("location") for f in findings if f["type"] == "jurisdiction"]
    if jurisdictions:
        policy["allowed_jurisdictions"] = list(dict.fromkeys([j.strip() for j in jurisdictions if j]))
    return policy


def vague_language_hits(text):
    text = (text or "").lower()
    return [phrase for phrase in VAGUE_PHRASES if phrase in text]


def evaluate(findings, policy):
    """findings: verified findings, each already carrying page/section."""
    flags = []
    by = lambda t: [f for f in findings if f["type"] == t]
    loc = lambda f: dict(quote=f["quote"], chunk_id=f["chunk_id"], page=f["page"], section=f["section"])

    pay = by("payment")
    if not pay:
        flags.append(Flag("MISSING", "Payment terms", "No payment deadline found in the contract.", "High",
                          f"Add: 'Client shall pay each invoice within {policy['max_payment_days']} days of the invoice date.'"))
    for f in pay:
        d = f["value"]["days"]
        if d > policy["max_payment_days"]:
            flags.append(Flag("CONFLICT", f"Max payment delay = {policy['max_payment_days']} days",
                              f"Payment due in {d} days, over your {policy['max_payment_days']}-day limit.", "High",
                              f"Replace with: 'within {policy['max_payment_days']} days of the invoice date.'", **loc(f)))
        if f["value"].get("clock_starts") in ("approval", "receipt"):
            flags.append(Flag("WARNING", "Payment clock start",
                              f"Payment clock starts at {f['value']['clock_starts']}, not invoice date, so the real delay can be longer.",
                              "Medium", "Ask for the clock to start on the invoice date.", **loc(f)))

    ren = by("renewal")
    for f in ren:
        v = f["value"]
        if v.get("renews") and not policy["allow_auto_renewal"]:
            flags.append(Flag("CONFLICT", "No auto-renewal", "Contract renews automatically; your policy forbids it.", "High",
                              "Make renewal opt-in by written agreement of both parties.", **loc(f)))
        elif v.get("renews") and (v.get("notice_days") or 0) > policy["max_renewal_notice_days"]:
            flags.append(Flag("CONFLICT", f"Max cancel notice = {policy['max_renewal_notice_days']} days",
                              f"Cancellation needs {v['notice_days']} days' notice, over your {policy['max_renewal_notice_days']}-day limit.",
                              "Medium", f"Reduce notice to {policy['max_renewal_notice_days']} days.", **loc(f)))

    liab = by("liability")
    if policy["require_liability_cap"]:
        if not liab:
            flags.append(Flag("MISSING", "Liability cap", "No liability limit found.", "High",
                              "Add a cap, e.g. total fees paid in the last 12 months."))
        for f in liab:
            if not f["value"].get("capped"):
                flags.append(Flag("CONFLICT", "Liability must be capped",
                                  "Your liability is uncapped (unlimited or broad indemnity).", "High",
                                  "Cap total liability at fees paid under this contract.", **loc(f)))
        if liab and any(f["value"].get("capped") for f in liab) and any(not f["value"].get("capped") for f in liab):
            flags.append(Flag("WARNING", "Contradictory liability clauses",
                              "One clause caps liability while another leaves it uncapped; the uncapped one may override.",
                              "High", "Clarify that the cap applies to indemnities too."))

    jur = by("jurisdiction")
    allowed = [a.lower() for a in policy["allowed_jurisdictions"]]
    if not jur:
        flags.append(Flag("MISSING", "Governing law", "No governing law or jurisdiction found.", "Medium",
                          f"Add: 'This agreement is governed by the laws of {policy['allowed_jurisdictions'][0]}.'"))
    for f in jur:
        if f["value"]["location"].lower() not in allowed:
            flags.append(Flag("CONFLICT", "Allowed jurisdictions",
                              f"Disputes governed by {f['value']['location']}, not in your list ({', '.join(policy['allowed_jurisdictions'])}).",
                              "Medium", f"Request {policy['allowed_jurisdictions'][0]} law and courts.", **loc(f)))
    seen, uniq = set(), []
    for f in flags:  # same rule + same message = duplicate (e.g. law and courts both say Delaware)
        if (f.rule, f.message) not in seen:
            seen.add((f.rule, f.message)); uniq.append(f)
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(uniq, key=lambda x: order[x.severity])