"""Step 4: deterministic policy engine. No LLM here: every flag is plain, explainable code."""
import re
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
        pay_vals = [int(f["value"].get("days") or 30) for f in payment if f.get("value", {}).get("days") is not None]
        policy["max_payment_days"] = max(pay_vals, default=30)
    renewal = [f for f in findings if f["type"] == "renewal"]
    if renewal:
        policy["allow_auto_renewal"] = any(bool(f.get("value", {}).get("renews")) for f in renewal)
        notice_days = [int(f["value"].get("notice_days")) for f in renewal if f.get("value", {}).get("notice_days")]
        if notice_days:
            policy["max_renewal_notice_days"] = max(notice_days)
    policy["require_liability_cap"] = True
    jurisdictions = [f.get("value", {}).get("location") for f in findings if f["type"] == "jurisdiction"]
    if jurisdictions:
        policy["allowed_jurisdictions"] = list(dict.fromkeys([str(j).strip() for j in jurisdictions if j]))
    return policy


def parse_user_defined_policy(text: str, base_policy=None) -> dict:
    """Parses free-form natural language requirements or rule specifications into a validated policy dict."""
    if not base_policy:
        base_policy = dict(DEFAULT_POLICY)
    policy = dict(base_policy)
    if not text or not str(text).strip():
        return policy

    low = str(text).lower()

    # 1. Max payment days (e.g., 'within 45 days', 'net 15', 'pay 60 days', '2 months')
    pay_m = (
        re.search(r"(?:payment|pay|invoice|within|net|delay|terms?)\s*[:=]?\s*(?:within\s*)?(\d+)\s*(days?|months?)?", low)
        or re.search(r"\b(\d+)\s*(days?|months?)\s*(?:payment|delay|invoice)?", low)
    )
    if pay_m:
        val = int(pay_m.group(1))
        unit = pay_m.group(2) or "days"
        if "month" in unit:
            val = val * 30
        policy["max_payment_days"] = val

    # 2. Auto-renewal
    if re.search(r"\b(?:no\s+auto-?renewal|forbid\s+auto-?renewal|disallow\s+auto-?renewal|prevent\s+auto-?renewal|without\s+auto-?renewal|no\s+renewal)\b", low):
        policy["allow_auto_renewal"] = False
    elif re.search(r"\b(?:allow\s+auto-?renewal|permit\s+auto-?renewal|accept\s+auto-?renewal|auto-?renewal\s+allowed|allow\s+renewal)\b", low):
        policy["allow_auto_renewal"] = True

    # 3. Cancellation notice days
    notice_m = (
        re.search(r"(?:notice|cancellation|cancel)\s*(?:period|window|days)?\s*[:=]?\s*(?:within\s*)?(\d+)\s*days?", low)
        or re.search(r"\b(\d+)\s*days?\s*(?:cancellation\s+|cancel\s+)?notice", low)
    )
    if notice_m:
        policy["max_renewal_notice_days"] = int(notice_m.group(1))

    # 4. Liability cap
    if re.search(r"\b(?:no\s+liability\s+cap|uncapped\s+liability|unlimited\s+liability|without\s+cap)\b", low):
        policy["require_liability_cap"] = False
    elif re.search(r"\b(?:require\s+liability\s+cap|capped\s+liability|must\s+be\s+capped|require\s+cap|cap\s+liability|capped)\b", low):
        policy["require_liability_cap"] = True

    # 5. Allowed jurisdictions
    known_jurisdictions = [
        "India", "Singapore", "United States", "USA", "US", "United Kingdom", "UK",
        "England", "Delaware", "New York", "California", "Germany", "France",
        "Australia", "Canada", "Dubai", "UAE", "Hong Kong", "Chennai", "Bangalore", "Mumbai"
    ]
    jur_m = re.search(r"(?:jurisdictions?|governing\s+law|courts?|location)\s*[:=]\s*([^\n;.]+)", text, re.I)
    if jur_m:
        raw_jurs = [j.strip() for j in re.split(r"[,/|;]|\band\b", jur_m.group(1)) if j.strip()]
        if raw_jurs:
            policy["allowed_jurisdictions"] = raw_jurs
    else:
        found_j = []
        for kj in known_jurisdictions:
            if re.search(r"\b" + re.escape(kj.lower()) + r"\b", low):
                found_j.append(kj)
        if found_j:
            policy["allowed_jurisdictions"] = found_j

    # 6. Advanced sensors (IP, non-compete, termination)
    if re.search(r"\b(?:ip|intellectual\s+property|moral\s+rights|non-?compete|exclusivity|termination|convenience)\b", low):
        policy["check_advanced_risks"] = True

    return policy


def vague_language_hits(text: str):
    low = text.lower()
    return [phrase for phrase in VAGUE_PHRASES if phrase in low]


def evaluate(findings, policy=DEFAULT_POLICY):
    """findings: verified findings, each already carrying page/section."""
    flags = []
    by = lambda t: [f for f in findings if f["type"] == t]
    loc = lambda f: dict(quote=f["quote"], chunk_id=f["chunk_id"], page=f["page"], section=f["section"])

    # 1. Payment checks
    pay = by("payment")
    try:
        max_pay = int(policy.get("max_payment_days", 30) or 30)
    except (ValueError, TypeError):
        max_pay = 30

    if not pay:
        flags.append(Flag(
            "MISSING",
            "Payment terms",
            "No payment deadline found in the contract.",
            "High",
            f"Add: 'Client shall pay each invoice within {max_pay} days of the invoice date.'",
            category="Payment",
            rule_value=f"≤ {max_pay} days",
            contract_value="Not found",
        ))
    for f in pay:
        val = f.get("value", {})
        raw_d = val.get("days")
        try:
            d = int(raw_d) if raw_d is not None else None
        except (ValueError, TypeError):
            d = None

        if d is not None and d > max_pay:
            flags.append(Flag(
                "CONFLICT",
                f"Max payment delay = {max_pay} days",
                f"Payment due in {d} days, over your {max_pay}-day limit.",
                "High",
                f"Replace with: 'within {max_pay} days of the invoice date.'",
                category="Payment",
                rule_value=f"≤ {max_pay} days",
                contract_value=f"{d} days",
                **loc(f),
            ))
        elif d is None:
            flags.append(Flag(
                "WARNING",
                "Indefinite payment deadline",
                "Payment clause does not specify an exact number of calendar days.",
                "Medium",
                f"Add: 'within {max_pay} days of the invoice date.'",
                category="Payment",
                rule_value=f"≤ {max_pay} days",
                contract_value="Not specified",
                **loc(f),
            ))
        if val.get("clock_starts") in ("approval", "receipt"):
            clock = val["clock_starts"]
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
    allow_renew = bool(policy.get("allow_auto_renewal", False))
    try:
        max_notice = int(policy.get("max_renewal_notice_days", 30) or 30)
    except (ValueError, TypeError):
        max_notice = 30

    for f in ren:
        v = f.get("value", {})
        raw_notice = v.get("notice_days")
        try:
            notice = int(raw_notice) if raw_notice is not None else None
        except (ValueError, TypeError):
            notice = None

        if v.get("renews") and not allow_renew:
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
        elif v.get("renews") and notice is not None and notice > max_notice:
            flags.append(Flag(
                "CONFLICT",
                f"Max cancel notice = {max_notice} days",
                f"Cancellation needs {notice} days' notice, over your {max_notice}-day limit.",
                "Medium",
                f"Reduce notice to {max_notice} days.",
                category="Auto-renewal",
                rule_value=f"≤ {max_notice} days",
                contract_value=f"{notice} days",
                **loc(f),
            ))

    # 3. Liability checks
    liab = by("liability")
    req_cap = bool(policy.get("require_liability_cap", True))
    if req_cap:
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
            if not f.get("value", {}).get("capped"):
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
        has_capped = any(bool(f.get("value", {}).get("capped")) for f in liab)
        has_uncapped = any(not bool(f.get("value", {}).get("capped")) for f in liab)
        if has_capped and has_uncapped:
            first_uncapped = next(f for f in liab if not bool(f.get("value", {}).get("capped")))
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
    raw_allowed = policy.get("allowed_jurisdictions", ["India"])
    if isinstance(raw_allowed, str):
        raw_allowed = [j.strip() for j in raw_allowed.split(",") if j.strip()]
    elif not isinstance(raw_allowed, list):
        raw_allowed = [str(raw_allowed)]
    allowed = [str(a).lower().strip() for a in raw_allowed if str(a).strip()]
    pref_jur = raw_allowed[0] if raw_allowed else "India"

    if not jur:
        flags.append(Flag(
            "MISSING",
            "Governing law",
            "No governing law or jurisdiction found.",
            "Medium",
            f"Add: 'This agreement shall be governed by the laws of {pref_jur}.'",
            category="Jurisdiction",
            rule_value=", ".join(raw_allowed) if raw_allowed else "India",
            contract_value="Not found",
        ))
    for f in jur:
        loc_str = str(f.get("value", {}).get("location", "")).strip()
        loc_low = loc_str.lower()
        if not any(a in loc_low for a in allowed):
            flags.append(Flag(
                "CONFLICT",
                "Allowed jurisdictions",
                f"Disputes governed by {loc_str}, not your preferred jurisdictions ({', '.join(raw_allowed)}).",
                "Medium",
                f"Request {pref_jur} law and courts.",
                category="Jurisdiction",
                rule_value=", ".join(raw_allowed) if raw_allowed else "India",
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
