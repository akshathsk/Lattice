"""
MongoDB seed — unstructured contract & legal documents.

Collections:
  emails          — internal and external email threads related to contracts
  memos           — legal memos and internal opinions
  notes           — negotiation notes, meeting minutes, call summaries
  amendments      — amendment requests and redlines
  correspondence  — formal vendor/party correspondence
  compliance      — compliance reports, audit findings, breach notifications
"""

from datetime import datetime, timezone


def utc(year, month, day) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


# ─── emails ───────────────────────────────────────────────────────────────────

EMAILS = [
    {
        "type": "email",
        "subject": "Re: Acme Corp MSA — Liability Cap Concern",
        "from": "jane.ceo@ourcompany.com",
        "to": ["legal@acme.com", "clo@ourcompany.com"],
        "date": utc(2022, 2, 14),
        "related_contract": "Master Services Agreement — Acme Corp",
        "related_party": "Acme Corp",
        "thread_id": "acme-msa-2022-001",
        "body": """Hi David,

Following our call yesterday, I want to confirm our position on the liability clause.

We cannot accept unlimited liability under Section 8.3. Our standard position is liability
capped at the total fees paid in the prior 12 months. Given our annual retainer of $120,000,
this represents meaningful coverage for both parties.

We are, however, willing to carve out unlimited liability for:
  - Gross negligence or willful misconduct
  - Death or personal injury caused by negligence
  - Any breach of our confidentiality obligations

Please review the redline I've attached and let me know if Acme's legal team can accept
this position. We'd like to execute by end of February to keep the March 1 effective date.

Best,
Jane"""
    },
    {
        "type": "email",
        "subject": "IBM Watson SaaS Renewal — Action Required",
        "from": "bob.cto@ourcompany.com",
        "to": ["clo@ourcompany.com", "finance@ourcompany.com"],
        "date": utc(2024, 3, 15),
        "related_contract": "SaaS Subscription — IBM Watson",
        "related_party": "IBM Corporation",
        "thread_id": "ibm-saas-renewal-2024",
        "body": """Hi team,

Urgent: our IBM Watson SaaS agreement (contract ID: 3) expires June 1, 2024.
It auto-renews unless we give 60 days written notice — that deadline is April 2.

We are 17 days away from the point of no return.

I've been evaluating alternatives (OpenAI, Anthropic, Cohere) and I believe we should
NOT renew at the current $84,000/year rate. IBM has declined to negotiate pricing
despite our 18-month relationship and increased usage.

If we want to avoid renewal, legal needs to send formal written notice by April 2.
If we miss the window, we're locked in for another $84,000.

Please advise urgently.

Bob (CTO)"""
    },
    {
        "type": "email",
        "subject": "DataSafe GmbH — GDPR Breach Notification Received",
        "from": "compliance@ourcompany.com",
        "to": ["clo@ourcompany.com", "cto@ourcompany.com", "ceo@ourcompany.com"],
        "date": utc(2024, 1, 9),
        "related_contract": "Data Processing Agreement — DataSafe GmbH",
        "related_party": "DataSafe GmbH",
        "thread_id": "datasafe-breach-jan-2024",
        "body": """URGENT — Data Breach Notification

We received formal notification from DataSafe GmbH at 08:42 UTC today.

Summary:
  - Breach type: Unauthorised access to encrypted backup storage
  - Data affected: ~2,300 customer records (name, email, hashed password)
  - Discovery date: January 8, 2024 (yesterday)
  - Notification to us: January 9, 2024 — within the 72-hour window required by our DPA

Under our Data Processing Agreement (Section 6.2) and GDPR Article 33, DataSafe has
met their notification obligation. We now have our own obligations:

OUR OBLIGATIONS (72-hour clock started January 8):
  1. Notify relevant supervisory authority (deadline: January 11, 2024)
  2. Assess whether affected individuals must be notified
  3. Document the breach in our internal breach register

IMMEDIATE ACTIONS:
  - CLO to file ICO notification by COB January 11
  - CTO to assess scope of affected data
  - PR team on standby for potential customer communication

This is time-critical. Please respond today.

Compliance Team"""
    },
    {
        "type": "email",
        "subject": "LexTech Partnership — Q4 Revenue Share Dispute",
        "from": "finance@ourcompany.com",
        "to": ["clo@ourcompany.com", "partnerships@ourcompany.com"],
        "date": utc(2024, 4, 3),
        "related_contract": "Partnership Agreement — LexTech Solutions",
        "related_party": "LexTech Solutions",
        "thread_id": "lextech-revshare-q4",
        "body": """Hi,

We have a dispute with LexTech regarding Q4 2023 revenue share.

Our calculation: 3 referred deals closed, total value $220,000 → 15% = $33,000 owed to LexTech
LexTech's calculation: They claim 4 referred deals, total value $290,000 → 15% = $43,500

The disagreement is over one deal — the Meridian Group contract ($70,000).
LexTech claims they introduced us to Meridian at the Austin legal tech conference in October.
Our records show our sales team had already contacted Meridian independently in August.

Under Section 5.1 of the Partnership Agreement, a referral is only valid if the partner
makes the initial introduction AND we had no prior contact with the prospect.

I need legal to review Section 5.1 and confirm our interpretation. If we're right, we owe
$33,000. If LexTech is right, we owe $43,500. Payment was due March 30 — we're already late.

Can legal review and advise within 48 hours?

Finance"""
    },
    {
        "type": "email",
        "subject": "James Okafor Non-Compete — Competitor Approach",
        "from": "hr@ourcompany.com",
        "to": ["clo@ourcompany.com"],
        "date": utc(2024, 2, 20),
        "related_contract": "Employment Contract — James Okafor",
        "related_party": "James Okafor",
        "thread_id": "okafor-noncompete-2024",
        "body": """Hi,

Sensitive matter — please treat this as strictly confidential.

James Okafor (Senior Counsel) has informed HR that he has received a job offer from
LegalAI Inc, a legal technology firm that directly competes with our LexTech partnership.

James would like to accept the offer and has asked whether his non-compete clause
applies to this opportunity.

His employment contract (signed November 2022) includes the following:
  "Employee agrees not to engage with any competing firm within the legal sector
   for 12 months following termination of employment."

Key questions for legal:
  1. Is LegalAI Inc a "competing firm within the legal sector" under this definition?
  2. Is this clause enforceable in New York (where James is based)?
  3. What are our options if he proceeds?

Note: New York recently passed legislation (Effective Jan 2024) significantly limiting
the enforceability of non-compete agreements for most employees.

Please advise before we respond to James.

HR"""
    },
]

# ─── memos ────────────────────────────────────────────────────────────────────

MEMOS = [
    {
        "type": "memo",
        "title": "Legal Opinion: Enforceability of Non-Compete Clauses in New York (2024)",
        "author": "Office of the CLO",
        "date": utc(2024, 2, 22),
        "related_contract": "Employment Contract — James Okafor",
        "related_party": "James Okafor",
        "classification": "privileged",
        "body": """PRIVILEGED AND CONFIDENTIAL — ATTORNEY-CLIENT COMMUNICATION

TO: HR Department
FROM: Office of the CLO
RE: Non-Compete Enforceability — James Okafor / New York

SUMMARY
Effective September 4, 2023, New York Executive Law § 340 was amended to prohibit
non-compete agreements for most workers earning under $250,000 per annum.
As James Okafor's total compensation is $185,000, his non-compete clause is likely
unenforceable under current New York law.

ANALYSIS

1. STATUTORY PROHIBITION
The amended statute prohibits employers from seeking, requiring, demanding, or accepting
a non-compete agreement from a "covered individual." A covered individual is defined
broadly and includes senior counsel roles.

2. APPLICABILITY TO EXISTING AGREEMENTS
The statute applies prospectively to agreements entered into on or after September 4, 2023.
James's employment contract was signed November 1, 2022 — predating the amendment.
However, the statute's legislative intent and recent NLRB guidance suggest that
enforcement of pre-existing agreements may face significant challenges.

3. RECOMMENDATION
We recommend NOT attempting to enforce the non-compete against James Okafor.
Enforcement risk: high. Reputational risk: high. Legal cost: significant.

We should, however, ensure that James is reminded of his ongoing confidentiality
obligations, which survive termination and are not affected by the 2023 amendment.

Prepared by: Office of the CLO
Date: February 22, 2024"""
    },
    {
        "type": "memo",
        "title": "Contract Risk Assessment — Auto-Renewing Agreements Q1 2024",
        "author": "Legal Operations",
        "date": utc(2024, 1, 15),
        "classification": "internal",
        "body": """CONTRACT RISK ASSESSMENT — AUTO-RENEWING AGREEMENTS
Quarter: Q1 2024

EXECUTIVE SUMMARY
Three contracts in our portfolio contain auto-renewal clauses with notice windows
expiring in Q1 and Q2 2024. This memo identifies required actions and deadlines.

HIGH PRIORITY — IMMEDIATE ACTION REQUIRED

1. IBM Watson SaaS Subscription (Contract #3)
   Auto-renews: June 1, 2024
   Notice required: 60 days prior
   Deadline to cancel: April 2, 2024 ← CRITICAL
   Annual value: $84,000
   Recommendation: Evaluate alternatives. Do not auto-renew without renegotiating price.

MEDIUM PRIORITY — MONITOR

2. Acme Corp MSA (Contract #1)
   Auto-renews: March 1, 2025
   Notice required: 30 days prior
   Deadline to cancel: February 1, 2025
   Annual value: $120,000
   Recommendation: Relationship is strategic. Likely to renew. Begin renewal discussion Q3 2024.

3. LexTech Partnership Agreement (Contract #5)
   Auto-renews: January 1, 2028
   Notice required: 90 days prior (unusual — flag for renegotiation)
   Annual value: $200,000 (revenue share model)
   Recommendation: Revenue share dispute must be resolved before next renewal discussion.

ACTION ITEMS
[ ] CTO to provide IBM Watson usage and satisfaction report by Jan 31
[ ] Finance to model cost of IBM non-renewal vs renewal
[ ] Legal to calendar all renewal deadlines in contract management system
[ ] Partnership team to resolve LexTech Q4 revenue share dispute

Prepared by: Legal Operations
Reviewed by: CLO"""
    },
    {
        "type": "memo",
        "title": "GDPR Compliance Status — DataSafe GmbH DPA",
        "author": "Data Protection Officer",
        "date": utc(2024, 1, 12),
        "related_contract": "Data Processing Agreement — DataSafe GmbH",
        "related_party": "DataSafe GmbH",
        "classification": "confidential",
        "body": """DATA PROTECTION MEMO

TO: Legal, Compliance, CTO
FROM: Data Protection Officer (DPO)
RE: GDPR Compliance Status Following DataSafe Breach — January 2024

STATUS: NOTIFIED — ICO filing completed January 11, 2024

TIMELINE OF EVENTS
Jan 8, 2024: DataSafe detects breach at 06:00 UTC
Jan 9, 2024: DataSafe notifies us at 08:42 UTC (within 72-hour contractual window)
Jan 11, 2024: We filed breach notification with ICO (reference: ICO-2024-0089)

BREACH SCOPE (CONFIRMED)
- 2,847 customer records affected (revised upward from initial 2,300 estimate)
- Data elements: full name, email address, encrypted password hash
- No financial data, no sensitive personal data (GDPR special categories) affected
- Encryption was in place; risk of actual harm assessed as LOW

INDIVIDUAL NOTIFICATION DECISION
Under GDPR Article 34, notification to individuals is required only if the breach is
"likely to result in a high risk to their rights and freedoms."

Given the low-risk assessment and encryption controls in place, we have determined
that individual notification is NOT required at this time. This decision is documented
in our breach register (BR-2024-001).

REMEDIATION REQUIRED FROM DATASAFE
Under DPA Section 7.4:
  1. Full incident report due: February 9, 2024
  2. Penetration test results due: March 9, 2024
  3. Remediation confirmation due: April 9, 2024

Failure to deliver these within contractual timelines may constitute a material breach.

DPO"""
    },
]

# ─── negotiation notes ────────────────────────────────────────────────────────

NOTES = [
    {
        "type": "note",
        "title": "Meeting Notes — Acme Corp MSA Negotiation (Final Round)",
        "author": "Jane CEO",
        "date": utc(2022, 2, 25),
        "related_contract": "Master Services Agreement — Acme Corp",
        "related_party": "Acme Corp",
        "body": """MEETING NOTES — Acme Corp MSA Negotiation
Date: February 25, 2022 | Attendees: Jane (CEO), CLO, David Acme, Acme Legal

AGREED TERMS (final):
- Liability cap: 12 months of fees paid (our position accepted)
- Unlimited liability carve-outs: gross negligence, willful misconduct, confidentiality breach
- Payment terms: Net 30 (we wanted Net 15, Acme wanted Net 45 — compromised)
- Termination for convenience: 30 days notice (reduced from their initial 60-day ask)
- Auto-renewal: Yes, with 30-day notice to cancel
- Governing law: California (our preference, accepted)

OPEN ITEMS AT SIGNING:
- SOW #1 pricing to be agreed separately (target: $15K/month)
- SLA schedule to be attached as Exhibit A (draft due March 15)

INTERNAL NOTE (do not share):
David mentioned Acme is considering expanding operations into EMEA next year.
This could significantly increase contract value. Flag for relationship review in Q4 2022.

Next steps:
- CLO to circulate execution copy by Feb 28
- DocuSign routing: Jane → David Acme
- File executed MSA in contract management system"""
    },
    {
        "type": "note",
        "title": "Call Notes — LexTech Revenue Share Q4 Dispute",
        "author": "Partnerships Team",
        "date": utc(2024, 4, 10),
        "related_contract": "Partnership Agreement — LexTech Solutions",
        "related_party": "LexTech Solutions",
        "body": """CALL NOTES — LexTech Revenue Share Dispute Resolution
Date: April 10, 2024 | Duration: 45 mins
Attendees: Our partnerships lead + CLO vs LexTech CEO + LexTech legal

BACKGROUND:
Disputed deal: Meridian Group ($70,000 contract)
Our position: We contacted Meridian independently in August, before Austin conference
LexTech position: They made the introduction at the Austin Legal Tech conference in October

DISCUSSION:
- LexTech presented an email from Meridian's CEO stating they first heard of us through
  LexTech's booth at Austin conference in October 2023
- We presented CRM records showing a cold outreach email to Meridian on August 14, 2023
- Meridian's CEO email contradicts our CRM records — unclear which is accurate
- LexTech's legal noted that our CRM record shows NO RESPONSE to the August email,
  suggesting Meridian may not have taken notice until the conference

OUTCOME — NEGOTIATED SETTLEMENT:
Rather than litigate, parties agreed to split the disputed commission:
  - LexTech receives 50% of the disputed commission: $70,000 × 15% × 50% = $5,250
  - Total payment to LexTech: $33,000 (undisputed) + $5,250 = $38,250
  - Payment due: April 30, 2024

AGREED PROCESS CHANGE:
Section 5.1 to be amended at next renewal to require LexTech to register referrals
in our CRM within 5 business days of introduction (prevents future disputes).

ACTION:
- Finance to pay $38,250 to LexTech by April 30
- Legal to draft Section 5.1 amendment for next renewal"""
    },
    {
        "type": "note",
        "title": "Vendor Risk Assessment — Stripe Inc NDA Context",
        "author": "Legal Operations",
        "date": utc(2023, 1, 10),
        "related_contract": "NDA — Stripe Inc",
        "related_party": "Stripe Inc",
        "body": """VENDOR RISK ASSESSMENT NOTE — Stripe Inc

Purpose of NDA:
We are in early-stage discussions with Stripe about potentially integrating their
payment infrastructure into our legal contract management platform. The NDA was
executed to allow sharing of technical architecture details and pricing models.

Scope of discussions:
- Stripe Connect integration for contract milestone payment processing
- Potential embedded finance features for our platform clients
- Data sharing: We would share volume projections and client industry data

Risk Assessment:
LOW — Stripe is a well-capitalised, highly regulated financial institution with
strong compliance posture (PCI-DSS Level 1, SOC 2 Type II).

Confidentiality obligations (mutual, 3 years):
- We must not disclose Stripe's pricing model or technical integration specs
- Stripe must not disclose our platform architecture or client pipeline

Note: If discussions progress to a commercial agreement, we will need to execute
a separate DPA given the personal data involved in payment processing.
Stripe's standard DPA is GDPR-compliant (EU Standard Contractual Clauses in place).

Status: Discussions on hold pending internal product decision on payment features (Q3 2023)."""
    },
]

# ─── amendments ───────────────────────────────────────────────────────────────

AMENDMENTS = [
    {
        "type": "amendment",
        "title": "Amendment Request — Acme Corp MSA: IP Ownership Clarification",
        "author": "Acme Legal",
        "date": utc(2023, 8, 1),
        "related_contract": "Master Services Agreement — Acme Corp",
        "related_party": "Acme Corp",
        "status": "under_review",
        "body": """AMENDMENT REQUEST — Master Services Agreement (Acme Corp)
Requested by: David Acme / Acme Legal
Date: August 1, 2023

SECTION PROPOSED FOR AMENDMENT: Section 9 (Intellectual Property)

CURRENT TEXT:
"All work product, deliverables, and developments created by Acme Corp in the
performance of Services under this Agreement shall be owned by Our Company Inc
upon full payment of the applicable SOW fees."

PROPOSED AMENDMENT:
"All work product and deliverables created specifically for Our Company Inc under
a SOW shall be owned by Our Company Inc upon full payment. However, Acme Corp
retains ownership of all pre-existing IP, general methodologies, tools, frameworks,
and know-how used in delivery ('Background IP'). Acme Corp grants Our Company Inc
a perpetual, non-exclusive licence to use Background IP embedded in the deliverables."

ACME'S RATIONALE:
The current clause is overly broad and would transfer ownership of Acme's proprietary
development framework (AcmeBuild™) which is used across all client engagements.
This was not the intent of either party at signing.

OUR INITIAL ASSESSMENT:
The request is reasonable. The current language is indeed broader than intended.
The proposed Background IP carve-out is standard market practice.
Recommend accepting with minor modification: add list of specific Background IP
assets to a schedule to avoid future disputes.

STATUS: Under internal legal review — response due September 1, 2023"""
    },
]

# ─── compliance ───────────────────────────────────────────────────────────────

COMPLIANCE = [
    {
        "type": "compliance_report",
        "title": "Annual Contract Compliance Audit — FY2023",
        "author": "Legal Operations & External Auditor (Nexus Legal LLP)",
        "date": utc(2024, 1, 31),
        "classification": "confidential",
        "body": """ANNUAL CONTRACT COMPLIANCE AUDIT REPORT — FY2023
Prepared by: Legal Operations + Nexus Legal LLP
Review period: January 1 – December 31, 2023

SCOPE: All 8 active contracts in portfolio

FINDINGS SUMMARY
Overall compliance: SATISFACTORY with noted exceptions

─── COMPLIANT ───────────────────────────────────────────────
✓ Acme Corp MSA (Contract #1)
  Payment obligations met. All SOW deliverables accepted.
  No disputes. Auto-renewal tracked.

✓ Stripe NDA (Contract #2)
  Confidentiality obligations maintained.
  No disclosures identified. Note: commercial discussions inactive.

✓ Sarah Mitchell Employment (Contract #6)
  IP assignment clause operative. No IP disputes.
  All standard employment obligations met.

─── EXCEPTIONS NOTED ────────────────────────────────────────
⚠ IBM Watson SaaS (Contract #3) — ATTENTION REQUIRED
  Auto-renewal deadline April 2, 2024 not yet calendared.
  Recommend immediate action (see separate memo).

⚠ DataSafe GmbH DPA (Contract #4) — BREACH EVENT
  Personal data breach occurred December 31, 2023.
  Breach notification received January 9, 2024.
  ICO notified January 11, 2024. Remediation in progress.
  Annual GDPR audit report from DataSafe DUE September 2024 — must track.

⚠ LexTech Partnership (Contract #5) — PAYMENT DISPUTE
  Q4 revenue share payment overdue (due March 30).
  Dispute in progress. Resolution expected April 2024.

⚠ James Okafor Employment (Contract #7) — LEGAL RISK
  Non-compete clause likely unenforceable under NY 2023 amendments.
  Employee has received external offer. Risk of departure: HIGH.
  Confidentiality obligations must be reinforced.

─── RECOMMENDATIONS ─────────────────────────────────────────
1. Implement contract management calendar for all renewal deadlines
2. Conduct GDPR readiness review following DataSafe breach
3. Review and update all non-compete clauses for NY-based employees
4. Resolve LexTech revenue share dispute and implement referral registration process
5. Schedule IBM Watson renewal decision by February 28, 2024

NEXT AUDIT: January 2025
Auditor: Nexus Legal LLP | Reference: NL-AUDIT-2024-0012"""
    },
]


def seed(db):
    """Seed all collections. Idempotent — skips if data already present."""

    collections = {
        "emails":        EMAILS,
        "memos":         MEMOS,
        "notes":         NOTES,
        "amendments":    AMENDMENTS,
        "compliance":    COMPLIANCE,
    }

    results = {}
    for name, docs in collections.items():
        col = db[name]
        if col.count_documents({}) > 0:
            results[name] = {"skipped": True, "count": col.count_documents({})}
        else:
            col.insert_many(docs)
            results[name] = {"skipped": False, "count": col.count_documents({})}

    return results


if __name__ == "__main__":
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017/")
    db = client["contracts_docs"]
    results = seed(db)
    for col, r in results.items():
        status = "skipped (already seeded)" if r["skipped"] else "seeded"
        print(f"  ✓  {col}: {r['count']} docs — {status}")
