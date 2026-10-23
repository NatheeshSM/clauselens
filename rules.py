"""Step 4: deterministic policy engine. No LLM here: every flag is plain, explainable code."""
from dataclasses import dataclass, asdict

DEFAULT_POLICY = {
    "max_payment_days": 30,
    "allow_auto_renewal": False,
    "max_renewal_notice_days": 30,
    "require_liability_cap": True,
    "allowed_jurisdictions": ["India"],
    "check_advanced_risks": False,
}

PRESETS = {
    "Freelancer (strict)": DEFAULT_POLICY,
    "Small vendor (relaxed)": {
        **DEFAULT_POLICY,
        "max_payment_days": 45,
        "allow_auto_renewal": True,
        "max_renewal_notice_days": 60,
        "allowed_jurisdictions": ["India", "Singapore"],
    },
    "Enterprise agency": {
        **DEFAULT_POLICY,
        "max_payment_days": 15,
        "allow_auto_renewal": False,
        "max_renewal_notice_days": 15,
        "require_liability_cap": True,
        "allowed_jurisdictions": ["India", "United States", "United Kingdom", "Singapore"],
        "check_advanced_risks": True,
    },
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
    category: str = ""   # Payment | Auto-renewal | Liability | Jurisdiction | Clarity
    rule_value: str | None = None
    contract_value: str | None = None

    def to_dict(self):
        return asdict(self)


def infer_policy_from_example(findings):
    """Create a baseline policy from a single example contract. This is useful for demos."""
    policy = dict(DEFAULT_POLICY)
    payment = [f for f in findings if f["type"] == "payment"]
    if payment:
        policy["max_payment_days"] = max(f["value"].get("days", 30) for f in payment)
    renewal = [f for f in findings if f["type"] == "renewal"]
    if renewal:
        policy["allow_auto_renewal"] = any(f["value"].get("renews") for f in renewal)
        notice_days = [f["value"].get("notice_days") for f in renewal if f["value"].get("notice_days")]
        if notice_days:
            policy["max_renewal_notice_days"] = max(notice_days)
    policy["require_liability_cap"] = True
    jurisdictions = [f["value"].get("location") for f in findings if f["type"] == "jurisdiction"]
    if jurisdictions:
        policy["allowed_jurisdictions"] = list(dict.fromkeys([j.strip() for j in jurisdictions if j]))
    return policy


def vague_language_hits(text: str):
    low = text.lower()
    return [phrase for phrase in VAGUE_PHRASES if phrase in low]


def evaluate(findings, policy):
    """findings: verified findings, each already carrying page/section."""
    flags = []
    by = lambda t: [f for f in findings if f["type"] == t]
    loc = lambda f: dict(quote=f["quote"], chunk_id=f["chunk_id"], page=f["page"], section=f["section"])

    # 1. Payment checks
    pay = by("payment")
    if not pay:
        flags.append(Flag(
            "MISSING",
            "Payment terms",
            "No payment deadline found in the contract.",
            "High",
            f"Add: 'Client shall pay each invoice within {policy['max_payment_days']} days of the invoice date.'",
            category="Payment",
            rule_value=f"≤ {policy['max_payment_days']} days",
            contract_value="Not found",
        ))
    for f in pay:
        d = f["value"]["days"]
        if d > policy["max_payment_days"]:
            flags.append(Flag(
                "CONFLICT",
                f"Max payment delay = {policy['max_payment_days']} days",
                f"Payment due in {d} days, over your {policy['max_payment_days']}-day limit.",
                "High",
                f"Replace with: 'within {policy['max_payment_days']} days of the invoice date.'",
                category="Payment",
                rule_value=f"≤ {policy['max_payment_days']} days",
                contract_value=f"{d} days",
                **loc(f),
            ))
        if f["value"].get("clock_starts") in ("approval", "receipt"):
            clock = f["value"]["clock_starts"]
            flags.append(Flag(
                "WARNING",
                "Payment clock start",
                f"Payment clock starts at {clock}, not invoice date, so the real delay can be longer.",
                "Medium",
                "Ask for the clock to start on the invoice date.",
                category="Payment",
                rule_value="Invoice date",
                contract_value=f"{clock.capitalize()} of deliverables",
                **loc(f),
            ))

    # 2. Auto-renewal checks
    ren = by("renewal")
    for f in ren:
        v = f["value"]
        if v.get("renews") and not policy["allow_auto_renewal"]:
            flags.append(Flag(
                "CONFLICT",
                "No auto-renewal",
                "Contract renews automatically; your policy forbids it.",
                "High",
                "Make renewal opt-in by written agreement of both parties.",
                category="Auto-renewal",
                rule_value="No auto-renewal",
                contract_value="Auto-renews automatically",
                **loc(f),
            ))
        elif v.get("renews") and (v.get("notice_days") or 0) > policy["max_renewal_notice_days"]:
            notice = v.get("notice_days")
            flags.append(Flag(
                "CONFLICT",
                f"Max cancel notice = {policy['max_renewal_notice_days']} days",
                f"Cancellation needs {notice} days' notice, over your {policy['max_renewal_notice_days']}-day limit.",
                "Medium",
                f"Reduce notice to {policy['max_renewal_notice_days']} days.",
                category="Auto-renewal",
                rule_value=f"≤ {policy['max_renewal_notice_days']} days",
                contract_value=f"{notice} days",
                **loc(f),
            ))

    # 3. Liability checks
    liab = by("liability")
    if policy["require_liability_cap"]:
        if not liab:
            flags.append(Flag(
                "MISSING",
                "Liability cap",
                "No liability limit found.",
                "High",
                "Add a cap, e.g. total fees paid in the last 12 months.",
                category="Liability",
                rule_value="Must be capped",
                contract_value="Not found",
            ))
        for f in liab:
            if not f["value"].get("capped"):
                flags.append(Flag(
                    "CONFLICT",
                    "Liability must be capped",
                    "Liability is unlimited, or broad indemnity without a cap is required.",
                    "High",
                    "Cap liability at total fees paid under this agreement in the preceding 12 months.",
                    category="Liability",
                    rule_value="Must be capped",
                    contract_value="Unlimited / uncapped",
                    **loc(f),
                ))

        # Check for contradictory liability terms (both capped and uncapped)
        has_capped = any(f["value"].get("capped") for f in liab)
        has_uncapped = any(not f["value"].get("capped") for f in liab)
        if has_capped and has_uncapped:
            first_uncapped = next(f for f in liab if not f["value"].get("capped"))
            flags.append(Flag(
                "WARNING",
                "Contradictory liability terms",
                "Contract contains both a liability cap and an unlimited liability or indemnity clause.",
                "High",
                "Clarify that the liability cap applies notwithstanding any indemnity provision.",
                category="Liability",
                rule_value="Consistent cap",
                contract_value="Both capped and uncapped terms found",
                **loc(first_uncapped),
            ))

    # 4. Jurisdiction checks
    jur = by("jurisdiction")
    allowed = [a.lower().strip() for a in policy.get("allowed_jurisdictions", ["India"])]
    if not jur:
        pref = policy.get("allowed_jurisdictions", ["India"])[0]
        flags.append(Flag(
            "MISSING",
            "Governing law",
            "No governing law or jurisdiction found.",
            "Medium",
            f"Add: 'This agreement shall be governed by the laws of {pref}.'",
            category="Jurisdiction",
            rule_value=", ".join(policy.get("allowed_jurisdictions", ["India"])),
            contract_value="Not found",
        ))
    for f in jur:
        loc_str = str(f["value"].get("location", "")).strip()
        loc_low = loc_str.lower()
        if not any(a in loc_low for a in allowed):
            flags.append(Flag(
                "CONFLICT",
                "Allowed jurisdictions",
                f"Disputes governed by {loc_str}, not your preferred jurisdictions ({', '.join(policy['allowed_jurisdictions'])}).",
                "Medium",
                f"Request {policy['allowed_jurisdictions'][0]} law and courts.",
                category="Jurisdiction",
                rule_value=", ".join(policy["allowed_jurisdictions"]),
                contract_value=loc_str,
                **loc(f),
            ))

    # 5. Advanced Risk Sensors: IP Ownership, Non-Compete, Termination
    if policy.get("check_advanced_risks", False):
        for f in by("ip_ownership"):
            flags.append(Flag(
                "CONFLICT",
                "Broad IP & Moral Rights Transfer",
                "Contract claims full transfer of IP and moral rights without carveout for your pre-existing tools or portfolio display rights.",
                "High",
                "Add: 'Contractor retains full ownership of pre-existing tools, background IP, and the right to showcase the deliverables in contractor portfolio.'",
                category="IP Rights",
                rule_value="Retain tools & portfolio",
                contract_value="Full broad IP surrender",
                **loc(f),
            ))
        for f in by("non_compete"):
            flags.append(Flag(
                "CONFLICT",
                "Restrictive Non-Compete Covenant",
                "Contract restricts your freedom to provide services to other companies in your industry or domain.",
                "High",
                "Strike non-compete clause. Replace with standard confidentiality protecting trade secrets without restricting general freelance practice.",
                category="Non-Compete",
                rule_value="No client exclusivity",
                contract_value="Restrictive non-compete found",
                **loc(f),
            ))
        for f in by("termination"):
            flags.append(Flag(
                "WARNING",
                "Immediate Termination for Convenience",
                "Client may terminate immediately without cause. Work performed prior to termination may be unpaid.",
                "Medium",
                "Add: 'In the event of termination for convenience, Client shall pay Contractor for all services rendered to date, plus a 14-day notice transition fee.'",
                category="Termination",
                rule_value="14-day notice + payment for WIP",
                contract_value="Immediate unilateral termination",
                **loc(f),
            ))

    # Deduplicate flags: same rule + message + quote
    seen, uniq = set(), []
    for f in flags:
        key = (getattr(f, "rule", None), getattr(f, "message", None), getattr(f, "quote", None))
        if key not in seen:
            seen.add(key)
            uniq.append(f)

    return sorted(uniq, key=lambda x: {"High": 0, "Medium": 1, "Low": 2}.get(getattr(x, "severity", "Low"), 2))
