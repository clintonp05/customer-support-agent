"""
ingest_noon_knowledge.py

Ingest real noon policies (UAE, KSA, Egypt) into Qdrant using hierarchical
chunking (summary → section → rule) with rich metadata per chunk.

Chunking strategy:
  Level 0 — summary:  one per policy × region  (~300 tokens)
  Level 1 — section:  sub-topic within a policy (~150 tokens)
  Level 2 — rule:     atomic fact or condition  (~50 tokens)

  Each Level-2 chunk carries parent_id → Level-1 id.
  Each Level-1 chunk carries parent_id → Level-0 id.
  Retrieval returns rule-level chunks; their parent section is
  injected as context to the LLM for coherence.

Qdrant payload indexes (KEYWORD + BOOL) are created in retriever.py on startup.

Run:
    python .claude/ingest_noon_knowledge.py
    python .claude/ingest_noon_knowledge.py --verify
    python .claude/ingest_noon_knowledge.py --region UAE
    python .claude/ingest_noon_knowledge.py --dry-run
"""
import asyncio
import argparse
import sys
import os
from datetime import date
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.rag.retriever import get_retriever
from src.observability.logger import setup_logging, get_logger

setup_logging()
logger = get_logger()

# ─────────────────────────────────────────────────────────────────────────────
# GLOBAL METADATA DEFAULTS
# ─────────────────────────────────────────────────────────────────────────────

VERSION = "2025.1"
LAST_UPDATED = str(date.today())

# Synthetic uploader pool (simulates a multi-user CMS scenario)
UPLOADERS = [
    {"uploaded_by": "usr_policybot_7f3a", "uploader_role": "system"},
    {"uploaded_by": "usr_rania_al_k",     "uploader_role": "policy_admin"},
    {"uploaded_by": "usr_omar_h92",       "uploader_role": "content_manager"},
    {"uploaded_by": "usr_priya_nair",     "uploader_role": "policy_admin"},
    {"uploaded_by": "usr_sys_ingest",     "uploader_role": "system"},
]


def _uploader(seed: int) -> Dict[str, str]:
    return UPLOADERS[seed % len(UPLOADERS)]


def _base_meta(
    region: str,
    entity: str,
    currency: str,
    category: str,
    sub_category: str,
    intent_tags: List[str],
    web_source: str,
    citation: str,
    access_level: str = "public",
    uploader_seed: int = 0,
    language: str = "en",
) -> Dict[str, Any]:
    return {
        "region":        region,
        "entity":        entity,
        "currency":      currency,
        "category":      category,
        "sub_category":  sub_category,
        "intent_tags":   intent_tags,
        "web_source":    web_source,
        "citation":      citation,
        "language":      language,
        "access_level":  access_level,
        "version":       VERSION,
        "is_active":     True,
        "verified":      True,
        "effective_date": "2025-01-01",
        "expiry_date":   None,
        "last_updated":  LAST_UPDATED,
        **_uploader(uploader_seed),
    }


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT CORPUS
# Each entry = one logical document; expanded into 3-level chunks at ingest.
# Structure:  { id, content, meta, sections: [{ id, content, meta, rules: [...] }] }
# ─────────────────────────────────────────────────────────────────────────────

KNOWLEDGE_TREE: List[Dict[str, Any]] = []

# ══════════════════════════════════════════════════════════════════════════════
# RETURNS
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-returns-uae",
    "content": (
        "noon UAE Return Policy summary: Most products can be returned within 14 days of delivery. "
        "Mobiles have a 15-day window. Items must be in original condition with original packaging, "
        "all accessories, and intact tamper-proof seal. Manufacturing defects qualify for return "
        "regardless of condition. Non-returnable categories include perishables, hygiene items, "
        "personalized goods, and digital products. noon's 2× Refund policy covers counterfeit items "
        "from noon Supermall — claim within 48 hours."
    ),
    "meta": {
        **_base_meta("UAE", "noon.com/uae-en", "AED", "returns", "summary",
                     ["refund_request", "return_request", "cancel_order"],
                     "https://www.noon.com/uae-en/return-policy/",
                     "noon UAE Return Policy — Overview", uploader_seed=1),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-returns-uae-window",
            "content": (
                "noon UAE return window: Standard products — 14 days from delivery date. "
                "Mobile phones — 15 days from delivery date. "
                "Installed items — 7 days post-installation (excludes non-returnable products). "
                "Products received over 14 days ago are not eligible unless faulty or not as described."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "returns", "eligibility",
                             ["refund_request", "return_request"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Return Policy — Return Window", uploader_seed=1),
                "chunk_level": "section", "parent_id": "sum-returns-uae",
            },
            "rules": [
                {"id": "rl-returns-uae-window-01",
                 "content": "Standard noon UAE return window is 14 days from the date of delivery."},
                {"id": "rl-returns-uae-window-02",
                 "content": "noon UAE mobile phones have a 15-day return window from delivery date."},
                {"id": "rl-returns-uae-window-03",
                 "content": "Installed items can be returned within 7 days of installation on noon UAE, excluding non-returnable products."},
                {"id": "rl-returns-uae-window-04",
                 "content": "Items received more than 14 days ago are not eligible for return, exchange, or refund unless faulty or not as described."},
            ],
        },
        {
            "id": "sec-returns-uae-conditions",
            "content": (
                "noon UAE return conditions: Product must be in original condition. "
                "All original packaging, labels, and accessories must be intact. "
                "Tamper-proof seal must be unbroken. Product must not have been assembled, used, "
                "altered, or installed. If opened or repackaged, noon may decline the return "
                "unless there is a manufacturing defect."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "returns", "eligibility",
                             ["return_request"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Return Policy — Return Conditions", uploader_seed=1),
                "chunk_level": "section", "parent_id": "sum-returns-uae",
            },
            "rules": [
                {"id": "rl-returns-uae-cond-01",
                 "content": "noon UAE return requires original packaging, labels, and all accessories to be intact."},
                {"id": "rl-returns-uae-cond-02",
                 "content": "The tamper-proof seal must be unbroken for a noon UAE return to be accepted."},
                {"id": "rl-returns-uae-cond-03",
                 "content": "Product must not have been assembled, used, altered, or installed to qualify for return on noon UAE."},
                {"id": "rl-returns-uae-cond-04",
                 "content": "Manufacturing defects qualify for return on noon UAE regardless of whether the product has been opened."},
            ],
        },
        {
            "id": "sec-returns-uae-nonreturnable",
            "content": (
                "Non-returnable items on noon UAE: perishable goods, grocery, and food items; "
                "products received over 14 days ago; items not in original condition; "
                "opened or unsealed products (unless faulty); hygiene items such as unwrapped "
                "bedding, pillows, mattresses, towels; personalized or custom-made items; "
                "digital goods and gift cards; used consumables; customer-damaged items."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "returns", "exclusions",
                             ["return_request", "refund_request"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Return Policy — Non-Returnable Items", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-returns-uae",
            },
            "rules": [
                {"id": "rl-returns-uae-nonret-01",
                 "content": "Perishables, grocery, and food items are not eligible for return on noon UAE."},
                {"id": "rl-returns-uae-nonret-02",
                 "content": "Hygiene items (unwrapped bedding, pillows, mattresses, towels) cannot be returned on noon UAE."},
                {"id": "rl-returns-uae-nonret-03",
                 "content": "Digital goods and gift cards are non-returnable on noon UAE."},
                {"id": "rl-returns-uae-nonret-04",
                 "content": "Personalized or custom-made items cannot be returned on noon UAE."},
            ],
        },
        {
            "id": "sec-returns-uae-counterfeit",
            "content": (
                "noon UAE 2× Refund Policy for counterfeit products from noon Supermall: "
                "If you receive a counterfeit item, you receive a refund equal to the amount paid "
                "PLUS noon credits worth the product value (up to AED 200). "
                "Claim must be submitted within 48 hours of receiving the product. "
                "Product must be returned unused in original noon packaging."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "returns", "exceptions",
                             ["refund_request", "return_request"],
                             "https://www.noon.com/uae-en/2x-refund-faq/",
                             "noon UAE 2× Refund Policy — Counterfeit Protection", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-returns-uae",
            },
            "rules": [
                {"id": "rl-returns-uae-counterfeit-01",
                 "content": "noon UAE 2× Refund gives you refund + noon credits up to AED 200 if you receive a counterfeit from noon Supermall."},
                {"id": "rl-returns-uae-counterfeit-02",
                 "content": "noon UAE counterfeit claim must be submitted within 48 hours of receiving the product."},
                {"id": "rl-returns-uae-counterfeit-03",
                 "content": "The counterfeit product must be returned unused in original noon packaging for the 2× Refund to be processed."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-returns-ksa",
    "content": (
        "noon KSA (Saudi Arabia) Return Policy summary: Products can be returned within 14 days "
        "of delivery in original condition with original packaging, labels, and accessories. "
        "Shipping fees and COD fees are non-refundable once the item is delivered. "
        "Refund processing: up to 2 business days at fulfillment center, then 7–14 business days "
        "to credit card or noon wallet. Manufacturing defects qualify regardless of condition."
    ),
    "meta": {
        **_base_meta("KSA", "noon.com/saudi-en", "SAR", "returns", "summary",
                     ["refund_request", "return_request"],
                     "https://www.noon.com/saudi-en/return-policy/",
                     "noon KSA Return Policy — Overview", uploader_seed=3),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-returns-ksa-window",
            "content": (
                "noon KSA return window: 14 days from delivery date for standard products. "
                "After 14 days, items are not eligible unless faulty. "
                "Shipping and COD fees are non-refundable once the item is delivered to you."
            ),
            "meta": {
                **_base_meta("KSA", "noon.com/saudi-en", "SAR", "returns", "eligibility",
                             ["refund_request", "return_request"],
                             "https://www.noon.com/saudi-en/return-policy/",
                             "noon KSA Return Policy — Return Window", uploader_seed=3),
                "chunk_level": "section", "parent_id": "sum-returns-ksa",
            },
            "rules": [
                {"id": "rl-returns-ksa-window-01",
                 "content": "noon KSA return window is 14 days from delivery date."},
                {"id": "rl-returns-ksa-window-02",
                 "content": "Shipping fee and COD fee are non-refundable once the item is delivered on noon KSA."},
                {"id": "rl-returns-ksa-window-03",
                 "content": "noon KSA refund processing takes up to 2 business days at the fulfillment center, then 7–14 business days to reflect on card or wallet."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-returns-egypt",
    "content": (
        "noon Egypt Return Policy summary: Products can be returned within 15 days of delivery. "
        "Eligible categories: Electronics, Mobiles, Beauty & Health, Home & Kitchen, Sports, "
        "Toys & Games, Baby Products, Automotive, Tools, Pet Supplies, Stationery & Office. "
        "Credit/debit card refunds processed within 30 days of noon receiving the item. "
        "Wallet refunds are immediate after inspection. Shipping and COD fees non-refundable."
    ),
    "meta": {
        **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "returns", "summary",
                     ["refund_request", "return_request"],
                     "https://www.noon.com/egypt-en/return-policy/",
                     "noon Egypt Return Policy — Overview", uploader_seed=4),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-returns-egypt-window",
            "content": (
                "noon Egypt return window is 15 days from delivery date. "
                "Eligible product categories: Electronics, Mobiles, Beauty & Health, "
                "Home & Kitchen, Sports & Outdoor, Toys & Games, Baby Products, "
                "Automotive, Tools & Home Improvement, Pet Supplies, Stationery & Office Supplies."
            ),
            "meta": {
                **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "returns", "eligibility",
                             ["return_request", "refund_request"],
                             "https://www.noon.com/egypt-en/return-policy/",
                             "noon Egypt Return Policy — Return Window & Categories", uploader_seed=4),
                "chunk_level": "section", "parent_id": "sum-returns-egypt",
            },
            "rules": [
                {"id": "rl-returns-egypt-window-01",
                 "content": "noon Egypt return window is 15 days from delivery date."},
                {"id": "rl-returns-egypt-window-02",
                 "content": "noon Egypt eligible return categories include Electronics, Mobiles, Beauty, Home, Sports, Toys, Baby Products, Auto, Tools, Pet Supplies, Stationery."},
                {"id": "rl-returns-egypt-refund-01",
                 "content": "noon Egypt credit/debit card refunds are processed within 30 days of noon receiving the returned item."},
                {"id": "rl-returns-egypt-refund-02",
                 "content": "noon Egypt wallet refunds are immediate after product inspection at the fulfillment center."},
                {"id": "rl-returns-egypt-refund-03",
                 "content": "noon Egypt refunds appear as noon credits first for 24 hours, then auto-transfer to source account within 14 days."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# REFUNDS
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-refunds-uae",
    "content": (
        "noon UAE Refund Policy summary: Refunds are processed after the returned product is "
        "received and inspected at noon's fulfillment center. Card refunds: 7 days after receipt. "
        "COD refunds: credited to noon wallet (noon credits) immediately. Pre-shipment cancellations "
        "are refunded automatically. EMI orders: refund to card but installment plan continues "
        "until bank reversal. Counterfeit 2× refund: refund + noon credits up to AED 200."
    ),
    "meta": {
        **_base_meta("UAE", "noon.com/uae-en", "AED", "refunds", "summary",
                     ["refund_request"],
                     "https://www.noon.com/uae-en/return-policy/",
                     "noon UAE Refund Policy — Overview", uploader_seed=1),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-refunds-uae-timeline",
            "content": (
                "noon UAE refund timelines by payment method: "
                "Credit/debit card — up to 7 calendar days after noon receives the item at the fulfillment center. "
                "Cash on Delivery (COD) — refunded immediately to noon wallet as noon credits. "
                "Noon wallet/credits — refunded instantly on return confirmation. "
                "Pre-shipment cancellation — automatic immediate refund to original payment method. "
                "It may take up to one week for a product to reach noon, then 5–7 business days "
                "for the refund to reflect on your card or wallet."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "refunds", "timeline",
                             ["refund_request", "payment_issue"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Refund Policy — Refund Timelines", uploader_seed=1),
                "chunk_level": "section", "parent_id": "sum-refunds-uae",
            },
            "rules": [
                {"id": "rl-refunds-uae-timeline-01",
                 "content": "noon UAE card refund is issued within 7 calendar days after noon receives the returned item at the fulfillment center."},
                {"id": "rl-refunds-uae-timeline-02",
                 "content": "noon UAE COD (Cash on Delivery) refunds are credited to the noon wallet as noon credits immediately upon return confirmation."},
                {"id": "rl-refunds-uae-timeline-03",
                 "content": "noon UAE pre-shipment order cancellation triggers an automatic immediate refund to the original payment method."},
                {"id": "rl-refunds-uae-timeline-04",
                 "content": "Total noon UAE refund timeline: up to 1 week for item to arrive at noon, then 5–7 business days to reflect on card or wallet."},
            ],
        },
        {
            "id": "sec-refunds-uae-cod",
            "content": (
                "noon UAE COD refund handling: Cash on Delivery refunds go to noon wallet as noon credits. "
                "Noon credits can be used for future purchases and do not expire. "
                "To transfer noon credits to a bank account: go to noon Pay → Transfer to Bank. "
                "Bank transfer takes an additional 3–5 business days. "
                "COD refund cannot be returned as cash — it is credited to the wallet only."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "refunds", "process",
                             ["refund_request", "payment_issue"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Refund Policy — COD Refunds", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-refunds-uae",
            },
            "rules": [
                {"id": "rl-refunds-uae-cod-01",
                 "content": "noon UAE COD refunds are issued as noon wallet credits (noon credits), not as cash."},
                {"id": "rl-refunds-uae-cod-02",
                 "content": "noon credits (UAE) do not expire and can be used for future noon purchases."},
                {"id": "rl-refunds-uae-cod-03",
                 "content": "To convert noon UAE credits to a bank transfer, use noon Pay → Transfer to Bank; takes 3–5 additional business days."},
            ],
        },
        {
            "id": "sec-refunds-uae-emi",
            "content": (
                "noon UAE EMI (Easy Installments) refund rules: If you return an EMI order, "
                "a full refund is processed to your card or as noon credits. "
                "However, you must continue paying monthly installments as per your bank's terms "
                "until the bank processes the reversal — the EMI plan itself cannot be cancelled by noon. "
                "Contact your bank directly for EMI reversal. "
                "Gift cards and coupon discounts are not included in the refund amount."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "refunds", "exceptions",
                             ["refund_request", "payment_issue"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Refund Policy — EMI Refunds", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-refunds-uae",
            },
            "rules": [
                {"id": "rl-refunds-uae-emi-01",
                 "content": "noon UAE EMI order return triggers a full refund to card or noon credits, but installment payments must continue until the bank processes the reversal."},
                {"id": "rl-refunds-uae-emi-02",
                 "content": "The noon UAE EMI plan cannot be cancelled by noon — contact your bank directly for installment reversal."},
                {"id": "rl-refunds-uae-emi-03",
                 "content": "noon UAE gift card and coupon discounts are not included in refund amounts."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# WARRANTY
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-warranty-uae",
    "content": (
        "noon UAE Warranty Policy summary: noon provides 12 months warranty on selected electronics "
        "where noon is the seller. Electronic accessories (non-Apple) have 6-month warranty; "
        "Apple accessories have 12-month warranty. Warranty starts from delivery date. "
        "Covered: manufacturing defects in materials, design, workmanship. "
        "Not covered: physical damage, liquid damage, unauthorized repair, accidents, commercial use. "
        "Repair period: up to 25 working days. If unrepairable, replacement or refund at noon's discretion."
    ),
    "meta": {
        **_base_meta("UAE", "noon.com/uae-en", "AED", "warranty", "summary",
                     ["warranty_claim"],
                     "https://www.noon.com/uae-en/warranty-policy/",
                     "noon UAE Warranty Policy — Overview", uploader_seed=2),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-warranty-uae-coverage",
            "content": (
                "noon UAE warranty coverage: noon-sold electronics — 12 months from delivery date. "
                "Electronic accessories (excluding Apple) — 6 months from delivery date. "
                "Apple accessories — 12 months from delivery date. "
                "Third-party seller items: seller's warranty terms apply. "
                "Warranty covers defects in materials, design, and workmanship only."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "warranty", "coverage",
                             ["warranty_claim"],
                             "https://www.noon.com/uae-en/warranty-policy/",
                             "noon UAE Warranty Policy — Coverage Duration", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-warranty-uae",
            },
            "rules": [
                {"id": "rl-warranty-uae-cov-01",
                 "content": "noon UAE electronics sold by noon carry a 12-month warranty from the delivery date."},
                {"id": "rl-warranty-uae-cov-02",
                 "content": "noon UAE electronic accessories (non-Apple) have a 6-month warranty from delivery date."},
                {"id": "rl-warranty-uae-cov-03",
                 "content": "Apple accessories purchased on noon UAE carry a 12-month (1-year) warranty from delivery date."},
                {"id": "rl-warranty-uae-cov-04",
                 "content": "For noon UAE third-party seller products, the seller's own warranty terms apply — not noon's warranty."},
            ],
        },
        {
            "id": "sec-warranty-uae-exclusions",
            "content": (
                "noon UAE warranty does NOT cover: physical damage (broken screens, dents, bends); "
                "liquid damage (water contact or submersion); repairs by unauthorized service centers; "
                "original software modification or alteration; accessories not supplied by noon; "
                "damage from accidents, abuse, or misuse; products used commercially (not domestically); "
                "items repaired or modified outside noon-authorized service centers."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "warranty", "exclusions",
                             ["warranty_claim"],
                             "https://www.noon.com/uae-en/warranty-policy/",
                             "noon UAE Warranty Policy — Exclusions", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-warranty-uae",
            },
            "rules": [
                {"id": "rl-warranty-uae-excl-01",
                 "content": "Physical damage (broken screens, heavy dents, bent products) is NOT covered by noon UAE warranty."},
                {"id": "rl-warranty-uae-excl-02",
                 "content": "Liquid damage (water contact or submersion) is NOT covered by noon UAE warranty."},
                {"id": "rl-warranty-uae-excl-03",
                 "content": "Repairs by unauthorized service centers void the noon UAE warranty."},
                {"id": "rl-warranty-uae-excl-04",
                 "content": "Products used commercially (not for domestic use) are not covered by noon UAE warranty."},
                {"id": "rl-warranty-uae-excl-05",
                 "content": "Software modification or alteration of the original OS voids the noon UAE warranty."},
            ],
        },
        {
            "id": "sec-warranty-uae-process",
            "content": (
                "noon UAE warranty claim process: Go to 'My Orders', select the order, tap 'Warranty Claim'. "
                "Provide original invoice and warranty card (if supplied). Serial number must match invoice. "
                "noon arranges pickup and drop-off where available. "
                "Repair period: up to 25 working days. "
                "If unrepairable, noon or brand service provider may offer replacement or refund. "
                "Warranty repair does not extend or renew the original warranty period. "
                "If a customer refuses to collect after repair, noon stores the item for 30 calendar days "
                "then may dispose without compensation."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "warranty", "process",
                             ["warranty_claim"],
                             "https://www.noon.com/uae-en/warranty-policy/",
                             "noon UAE Warranty Policy — Claim Process", uploader_seed=3),
                "chunk_level": "section", "parent_id": "sum-warranty-uae",
            },
            "rules": [
                {"id": "rl-warranty-uae-proc-01",
                 "content": "noon UAE warranty repair takes up to 25 working days from claim submission."},
                {"id": "rl-warranty-uae-proc-02",
                 "content": "If a noon UAE warranty item cannot be repaired, noon may offer a replacement or refund at their discretion."},
                {"id": "rl-warranty-uae-proc-03",
                 "content": "Warranty repair on noon UAE does not extend or renew the original warranty period."},
                {"id": "rl-warranty-uae-proc-04",
                 "content": "Original invoice and serial number are required to initiate a warranty claim on noon UAE."},
                {"id": "rl-warranty-uae-proc-05",
                 "content": "noon UAE stores repaired items for 30 calendar days after repair; uncollected items may be disposed of."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-warranty-ksa",
    "content": (
        "noon KSA (Saudi Arabia) Warranty Policy summary: All electronic devices sold on noon KSA "
        "have a 2-year manufacturer or seller warranty (except accessories). "
        "Warranty is provided by brand-authorized service centers. "
        "Same exclusions as UAE: no physical damage, liquid damage, unauthorized repair, commercial use."
    ),
    "meta": {
        **_base_meta("KSA", "noon.com/saudi-en", "SAR", "warranty", "summary",
                     ["warranty_claim"],
                     "https://www.noon.com/saudi-en/warranty-policy/",
                     "noon KSA Warranty Policy — Overview", uploader_seed=3),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-warranty-ksa-coverage",
            "content": (
                "noon KSA warranty coverage: All electronic devices sold on noon KSA — 2-year "
                "manufacturer or seller warranty from delivery date. Accessories are not covered "
                "under the 2-year policy. Warranty is serviced through brand-authorized service centers. "
                "Warranty obligations are limited to repair, replacement of defective part, "
                "or refund at the paid/sold price."
            ),
            "meta": {
                **_base_meta("KSA", "noon.com/saudi-en", "SAR", "warranty", "coverage",
                             ["warranty_claim"],
                             "https://www.noon.com/saudi-en/warranty-policy/",
                             "noon KSA Warranty Policy — Coverage", uploader_seed=3),
                "chunk_level": "section", "parent_id": "sum-warranty-ksa",
            },
            "rules": [
                {"id": "rl-warranty-ksa-cov-01",
                 "content": "noon KSA electronic devices have a 2-year manufacturer or seller warranty from delivery date."},
                {"id": "rl-warranty-ksa-cov-02",
                 "content": "noon KSA warranty accessories are not covered under the 2-year electronics warranty."},
                {"id": "rl-warranty-ksa-cov-03",
                 "content": "noon KSA warranty is fulfilled through brand-authorized service centers."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# DELIVERY
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-delivery-uae",
    "content": (
        "noon UAE Delivery summary: Multiple delivery tiers available. "
        "Standard: 2–5 business days across UAE. Express: 2-day on selected products. "
        "Rocket: 45-minute delivery in Dubai and major UAE cities on selected items. "
        "Minutes: 15-minute delivery for groceries and essentials in Dubai, Abu Dhabi, Sharjah — "
        "over 5,000 products, Monday–Sunday. Drone delivery coming soon. "
        "Carriers: Fetchr, Aramex, DHL, and noon's own logistics fleet for Rocket and Minutes. "
        "Failed delivery: reattempted; after multiple failures, order returned and refund issued."
    ),
    "meta": {
        **_base_meta("UAE", "noon.com/uae-en", "AED", "delivery", "summary",
                     ["delivery_tracking", "order_status"],
                     "https://www.noon.com/uae-en/rocket-fastest-delivery/",
                     "noon UAE Delivery Options — Overview", uploader_seed=0),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-delivery-uae-options",
            "content": (
                "noon UAE delivery tiers: "
                "Standard — 2–5 business days, available across all UAE emirates. "
                "Express — 2-day delivery on selected products. "
                "noon Rocket — 45-minute delivery on selected products in Dubai and major UAE cities; "
                "covers food, fashion, homeware, appliances, electronics, beauty. "
                "noon Minutes — 15-minute delivery in Dubai, Abu Dhabi, Sharjah; "
                "5,000+ products including groceries; Mon–Fri 10AM–11PM, Sat–Sun 10AM–12AM. "
                "Drone delivery: launching soon with real-time tracking in noon app."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "delivery", "eligibility",
                             ["delivery_tracking", "order_status"],
                             "https://www.noon.com/uae-en/rocket-fastest-delivery/",
                             "noon UAE Delivery — Service Tiers & SLAs", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-delivery-uae",
            },
            "rules": [
                {"id": "rl-delivery-uae-std-01",
                 "content": "noon UAE standard delivery takes 2–5 business days across all UAE emirates."},
                {"id": "rl-delivery-uae-rocket-01",
                 "content": "noon Rocket delivers selected products in 45 minutes in Dubai and major UAE cities."},
                {"id": "rl-delivery-uae-minutes-01",
                 "content": "noon Minutes delivers groceries and essentials in 15 minutes in Dubai, Abu Dhabi, and Sharjah."},
                {"id": "rl-delivery-uae-minutes-02",
                 "content": "noon Minutes operating hours: Monday–Friday 10AM–11PM, Saturday–Sunday 10AM–12AM (UAE)."},
                {"id": "rl-delivery-uae-carriers-01",
                 "content": "noon UAE delivery carriers include Fetchr, Aramex, DHL, and noon's own fleet for Rocket and Minutes."},
            ],
        },
        {
            "id": "sec-delivery-uae-failed",
            "content": (
                "noon UAE failed delivery (NDR — Non-Delivered Return): Delivery attempted but not completed "
                "due to no one available, restricted access, or incorrect address. "
                "noon will reattempt delivery. After multiple failed attempts, the order is returned "
                "to the warehouse and a refund is issued automatically. "
                "Update delivery address or contact details via 'My Account' to prevent NDR."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "delivery", "exceptions",
                             ["delivery_tracking", "order_status"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Delivery — Failed Delivery (NDR)", uploader_seed=4),
                "chunk_level": "section", "parent_id": "sum-delivery-uae",
            },
            "rules": [
                {"id": "rl-delivery-uae-ndr-01",
                 "content": "noon UAE Non-Delivered Returns (NDR) occur when delivery cannot be completed — noon reattempts."},
                {"id": "rl-delivery-uae-ndr-02",
                 "content": "After multiple failed delivery attempts on noon UAE, the order is returned to warehouse and a refund is issued automatically."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-delivery-ksa",
    "content": (
        "noon KSA (Saudi Arabia) Delivery summary: Standard delivery across KSA cities including "
        "Riyadh, Jeddah, Dammam. DirectShip Express available on selected products. "
        "noon One membership provides enhanced shipping benefits. "
        "Contact 800-116-0210 for delivery issues."
    ),
    "meta": {
        **_base_meta("KSA", "noon.com/saudi-en", "SAR", "delivery", "summary",
                     ["delivery_tracking", "order_status"],
                     "https://www.noon.com/saudi-en/",
                     "noon KSA Delivery — Overview", uploader_seed=3),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-delivery-ksa-options",
            "content": (
                "noon KSA delivery options: Standard delivery to all KSA regions (Riyadh, Jeddah, "
                "Dammam, Mecca, Medina, and other cities). DirectShip Express on selected products. "
                "noon One membership provides priority shipping and free delivery benefits. "
                "Track orders via 'My Orders' in the noon app — shows Confirmed, Packed, Shipped, "
                "Out for Delivery, Delivered status."
            ),
            "meta": {
                **_base_meta("KSA", "noon.com/saudi-en", "SAR", "delivery", "eligibility",
                             ["delivery_tracking", "order_status"],
                             "https://www.noon.com/saudi-en/",
                             "noon KSA Delivery — Options", uploader_seed=3),
                "chunk_level": "section", "parent_id": "sum-delivery-ksa",
            },
            "rules": [
                {"id": "rl-delivery-ksa-opt-01",
                 "content": "noon KSA offers standard delivery to all KSA regions including Riyadh, Jeddah, and Dammam."},
                {"id": "rl-delivery-ksa-opt-02",
                 "content": "noon KSA DirectShip Express provides faster delivery on selected products."},
                {"id": "rl-delivery-ksa-opt-03",
                 "content": "noon One membership in KSA provides priority shipping and free delivery perks."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-delivery-egypt",
    "content": (
        "noon Egypt Delivery summary: Delivers to Cairo, Giza, and all other cities across Egypt. "
        "Free shipping available on orders above a minimum threshold. "
        "Multiple delivery speed options available in major cities. "
        "Contact helpegypt.noon.com for delivery support."
    ),
    "meta": {
        **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "delivery", "summary",
                     ["delivery_tracking", "order_status"],
                     "https://www.noon.com/egypt-en/",
                     "noon Egypt Delivery — Overview", uploader_seed=4),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-delivery-egypt-options",
            "content": (
                "noon Egypt delivery covers Cairo, Giza, and all other Egyptian cities. "
                "Free shipping is available on orders above the minimum order threshold. "
                "Track orders via the noon Egypt app or website under 'My Orders'. "
                "For delivery inquiries contact helpegypt.noon.com or noon Egypt customer care."
            ),
            "meta": {
                **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "delivery", "eligibility",
                             ["delivery_tracking", "order_status"],
                             "https://www.noon.com/egypt-en/",
                             "noon Egypt Delivery — Coverage & Options", uploader_seed=4),
                "chunk_level": "section", "parent_id": "sum-delivery-egypt",
            },
            "rules": [
                {"id": "rl-delivery-egypt-opt-01",
                 "content": "noon Egypt delivers to Cairo, Giza, and all other cities across Egypt."},
                {"id": "rl-delivery-egypt-opt-02",
                 "content": "Free shipping on noon Egypt is available when the order exceeds the minimum threshold."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-payments-uae",
    "content": (
        "noon UAE Payment Methods summary: Credit/debit cards (Visa, Mastercard), Cash on Delivery (COD), "
        "noon Pay (digital wallet), noon credits, Easy Installments (EMI) for orders above AED 500 "
        "in 3 or 6-month tenures at 0% interest (bank processing fee may apply), "
        "Buy Now Pay Later via partner providers, and Mashreq noon co-branded card with 3.5% cashback. "
        "noon does not charge interest on EMI — bank may apply a fee. EMI not available with COD."
    ),
    "meta": {
        **_base_meta("UAE", "noon.com/uae-en", "AED", "payments", "summary",
                     ["payment_issue"],
                     "https://help.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know",
                     "noon UAE Payment Methods — Overview", uploader_seed=2),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-payments-uae-methods",
            "content": (
                "noon UAE accepted payment methods: "
                "Credit cards (Visa, Mastercard); Debit cards (Visa, Mastercard); "
                "Cash on Delivery (COD) — pay cash at door; "
                "noon Pay (digital wallet — top up via linked debit/credit card); "
                "noon credits (wallet balance from refunds or promotions); "
                "Easy Installments (EMI) via partner banks for orders above AED 500; "
                "Buy Now Pay Later (BNPL) via partner providers; "
                "Mashreq noon co-branded credit card — up to 3.5% cashback on noon purchases."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "payments", "eligibility",
                             ["payment_issue"],
                             "https://help.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know",
                             "noon UAE Payments — Accepted Methods", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-payments-uae",
            },
            "rules": [
                {"id": "rl-payments-uae-meth-01",
                 "content": "noon UAE accepts Visa and Mastercard credit and debit cards."},
                {"id": "rl-payments-uae-meth-02",
                 "content": "noon UAE Cash on Delivery (COD): customer pays in cash to the delivery agent at the door."},
                {"id": "rl-payments-uae-meth-03",
                 "content": "noon Pay is noon UAE's digital wallet; top up via linked debit or credit card."},
                {"id": "rl-payments-uae-meth-04",
                 "content": "Mashreq noon co-branded credit card earns up to 3.5% cashback on noon UAE purchases."},
            ],
        },
        {
            "id": "sec-payments-uae-emi",
            "content": (
                "noon UAE Easy Installments (EMI): Available for orders above AED 500. "
                "Tenure: 3 or 6 months via eligible partner bank credit cards. "
                "noon charges 0% interest; your bank may apply a processing fee. "
                "Select 'Easy Installments' at checkout. Processing time: 3–5 business days to reflect. "
                "EMI is not available with Cash on Delivery. "
                "If you return an EMI order, refund goes to card but installments continue until bank reversal."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "payments", "process",
                             ["payment_issue"],
                             "https://help.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know",
                             "noon UAE Payments — Easy Installments (EMI)", uploader_seed=2),
                "chunk_level": "section", "parent_id": "sum-payments-uae",
            },
            "rules": [
                {"id": "rl-payments-uae-emi-01",
                 "content": "noon UAE EMI (Easy Installments) requires a minimum order of AED 500."},
                {"id": "rl-payments-uae-emi-02",
                 "content": "noon UAE EMI tenures are 3 or 6 months; noon charges 0% interest (bank may apply a fee)."},
                {"id": "rl-payments-uae-emi-03",
                 "content": "noon UAE EMI is not available with Cash on Delivery (COD) as the payment method."},
                {"id": "rl-payments-uae-emi-04",
                 "content": "noon UAE EMI takes 3–5 business days to reflect on your credit card statement."},
            ],
        },
        {
            "id": "sec-payments-uae-cod-rules",
            "content": (
                "noon UAE COD rules: Some items require prepaid payment and are not COD-eligible. "
                "Customers with too many open undelivered orders may be restricted from COD. "
                "COD may not be available for high-value items or during major sale events. "
                "Confirm COD availability at checkout. "
                "For failed payment: check card details, ensure sufficient funds, verify 3D Secure/OTP. "
                "Try a different payment method or contact your bank."
            ),
            "meta": {
                **_base_meta("UAE", "noon.com/uae-en", "AED", "payments", "eligibility",
                             ["payment_issue"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon UAE Payments — COD Rules & Payment Failures", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-payments-uae",
            },
            "rules": [
                {"id": "rl-payments-uae-cod-01",
                 "content": "noon UAE COD may not be available for high-value items, items requiring prepaid payment, or during major sale events."},
                {"id": "rl-payments-uae-cod-02",
                 "content": "Customers with excessive open undelivered noon UAE orders may be restricted from using COD."},
                {"id": "rl-payments-uae-cod-03",
                 "content": "noon UAE payment failure: check card details, sufficient funds, and complete 3D Secure OTP verification."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-payments-ksa",
    "content": (
        "noon KSA Payment Methods summary: Credit/debit cards (Visa, Mastercard), COD, noon Pay P2P, "
        "noon credits. Easy Installments available for orders above SAR 1,000 in 3 or 6-month tenures "
        "(Saudi Investment Bank offers up to 12 months). 0% interest from noon; bank fee may apply. "
        "noon Pay P2P supports peer-to-peer transfers within KSA."
    ),
    "meta": {
        **_base_meta("KSA", "noon.com/saudi-en", "SAR", "payments", "summary",
                     ["payment_issue"],
                     "https://help.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know",
                     "noon KSA Payment Methods — Overview", uploader_seed=3),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-payments-ksa-emi",
            "content": (
                "noon KSA Easy Installments (EMI): Available for orders above SAR 1,000. "
                "Tenures: 3 or 6 months (Saudi Investment Bank offers 3, 6, or 12 months). "
                "noon charges 0% interest; bank may apply a processing fee. "
                "Select 'Easy Installments' at checkout with an eligible KSA bank credit card."
            ),
            "meta": {
                **_base_meta("KSA", "noon.com/saudi-en", "SAR", "payments", "process",
                             ["payment_issue"],
                             "https://help.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know",
                             "noon KSA Payments — Easy Installments (EMI)", uploader_seed=3),
                "chunk_level": "section", "parent_id": "sum-payments-ksa",
            },
            "rules": [
                {"id": "rl-payments-ksa-emi-01",
                 "content": "noon KSA EMI requires a minimum order of SAR 1,000."},
                {"id": "rl-payments-ksa-emi-02",
                 "content": "noon KSA EMI tenures are 3 or 6 months; Saudi Investment Bank offers up to 12 months."},
            ],
        },
    ],
})

KNOWLEDGE_TREE.append({
    "id": "sum-payments-egypt",
    "content": (
        "noon Egypt Payment Methods summary: COD, Visa/Mastercard credit and debit cards, "
        "Easy Installments up to 36 months via Egyptian partner banks (NBE, CIB, Banque Misr, "
        "HSBC Egypt, Emirates NBD Egypt), 0% interest with Emirates NBD up to 12 months. "
        "valU Buy Now Pay Later. Minimum EMI order: EGP 500. "
        "noon Payments gateway available for checkout."
    ),
    "meta": {
        **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "payments", "summary",
                     ["payment_issue"],
                     "https://helpegypt.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know-6-3-2024",
                     "noon Egypt Payment Methods — Overview", uploader_seed=4),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-payments-egypt-emi",
            "content": (
                "noon Egypt Easy Installments (EMI): Available for orders above EGP 500. "
                "Installment tenures up to 36 months via partner banks: "
                "National Bank of Egypt (NBE), CIB, Banque Misr, HSBC Egypt, Emirates NBD Egypt. "
                "Emirates NBD Egypt offers 0% interest for up to 12 months. "
                "valU BNPL (Buy Now Pay Later) also available. "
                "COD is not available with EMI."
            ),
            "meta": {
                **_base_meta("Egypt", "noon.com/egypt-en", "EGP", "payments", "process",
                             ["payment_issue"],
                             "https://helpegypt.noon.com/portal/en/kb/articles/easy-installments-everything-you-need-to-know-6-3-2024",
                             "noon Egypt Payments — Easy Installments (EMI)", uploader_seed=4),
                "chunk_level": "section", "parent_id": "sum-payments-egypt",
            },
            "rules": [
                {"id": "rl-payments-egypt-emi-01",
                 "content": "noon Egypt EMI requires a minimum order of EGP 500."},
                {"id": "rl-payments-egypt-emi-02",
                 "content": "noon Egypt EMI partner banks: NBE, CIB, Banque Misr, HSBC Egypt, Emirates NBD Egypt — tenures up to 36 months."},
                {"id": "rl-payments-egypt-emi-03",
                 "content": "Emirates NBD Egypt offers 0% interest installments for up to 12 months on noon Egypt."},
                {"id": "rl-payments-egypt-emi-04",
                 "content": "valU Buy Now Pay Later (BNPL) is available on noon Egypt."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# ORDERS
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-orders-all",
    "content": (
        "noon Order Management summary (all regions): Track orders via 'My Orders' in app or website. "
        "Order statuses: Confirmed → Packed → Shipped → Out for Delivery → Delivered / Cancelled. "
        "Cancel before packing via app for automatic full refund. After packing/shipping, "
        "cancel by refusing at door or returning after delivery. "
        "Change delivery address only before packing — contact customer care after shipment."
    ),
    "meta": {
        **_base_meta("ALL", "noon.com", "AED", "orders", "summary",
                     ["order_status", "cancel_order", "change_delivery_address"],
                     "https://www.noon.com/uae-en/return-policy/",
                     "noon Order Management — Overview", uploader_seed=0),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-orders-statuses",
            "content": (
                "noon order status definitions: "
                "Confirmed — order placed and being processed by noon. "
                "Packed — items prepared for dispatch at the warehouse. "
                "Shipped — order handed to delivery carrier. "
                "Out for Delivery — driver is en route to your address. "
                "Delivered — order successfully completed. "
                "Cancelled — order cancelled before dispatch."
            ),
            "meta": {
                **_base_meta("ALL", "noon.com", "AED", "orders", "process",
                             ["order_status"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon Orders — Status Definitions", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-orders-all",
            },
            "rules": [
                {"id": "rl-orders-status-01",
                 "content": "noon order status 'Confirmed' means the order is placed and being processed."},
                {"id": "rl-orders-status-02",
                 "content": "noon order status 'Out for Delivery' means the driver is en route to your address."},
                {"id": "rl-orders-status-03",
                 "content": "noon order status 'Cancelled' means the order was cancelled before dispatch."},
            ],
        },
        {
            "id": "sec-orders-cancellation",
            "content": (
                "noon order cancellation: Cancel via 'My Orders' → 'Cancel Order' before packing/shipping "
                "for an automatic full refund. Once packed or shipped, cancellation is not possible online. "
                "You can refuse delivery at the door or initiate a return after delivery. "
                "COD orders cancelled before delivery: no charge. "
                "For non-FBN (third-party seller) items, seller-specific cancellation terms may apply."
            ),
            "meta": {
                **_base_meta("ALL", "noon.com", "AED", "orders", "process",
                             ["cancel_order", "order_status"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon Orders — Cancellation Policy", uploader_seed=1),
                "chunk_level": "section", "parent_id": "sum-orders-all",
            },
            "rules": [
                {"id": "rl-orders-cancel-01",
                 "content": "noon orders can be cancelled online before packing for an automatic full refund."},
                {"id": "rl-orders-cancel-02",
                 "content": "Once a noon order is packed or shipped, it cannot be cancelled online — refuse at door or return after delivery."},
                {"id": "rl-orders-cancel-03",
                 "content": "COD noon orders cancelled before delivery incur no charges to the customer."},
            ],
        },
        {
            "id": "sec-orders-address",
            "content": (
                "noon delivery address change: You can change the delivery address before an order is packed. "
                "Go to 'My Orders' → select order → 'Edit Address'. "
                "Once packed or shipped, delivery address cannot be changed. "
                "Contact noon customer care immediately at 800-NOON (800-6666) UAE if shipment already dispatched — "
                "changes subject to carrier availability."
            ),
            "meta": {
                **_base_meta("ALL", "noon.com", "AED", "orders", "process",
                             ["change_delivery_address", "order_status"],
                             "https://www.noon.com/uae-en/return-policy/",
                             "noon Orders — Change Delivery Address", uploader_seed=1),
                "chunk_level": "section", "parent_id": "sum-orders-all",
            },
            "rules": [
                {"id": "rl-orders-addr-01",
                 "content": "noon delivery address can only be changed before the order is packed."},
                {"id": "rl-orders-addr-02",
                 "content": "After a noon order is shipped, address change requires calling 800-NOON (800-6666) and is subject to carrier availability."},
            ],
        },
    ],
})

# ══════════════════════════════════════════════════════════════════════════════
# PRODUCTS
# ══════════════════════════════════════════════════════════════════════════════

KNOWLEDGE_TREE.append({
    "id": "sum-products-all",
    "content": (
        "noon Product Catalogue summary (all regions): noon sells across Electronics, Mobiles, "
        "Laptops, TVs, Cameras, Men's/Women's/Kids Fashion, Home & Kitchen, Beauty & Fragrance, "
        "Sports, Grocery, and more. Products are sold by noon directly (FBN — Fulfilled by Noon) "
        "or by third-party marketplace sellers. FBN items are warehoused and shipped by noon. "
        "Top electronics brands: Samsung, Apple, Sony, LG, Huawei, Xiaomi, HP, Dell, Lenovo, Hisense. "
        "Warranty and return terms differ between noon-sold and seller products."
    ),
    "meta": {
        **_base_meta("ALL", "noon.com", "AED", "products", "summary",
                     ["product_inquiry"],
                     "https://www.noon.com/uae-en/",
                     "noon Product Catalogue — Overview", uploader_seed=0),
        "chunk_level": "summary", "parent_id": None,
    },
    "sections": [
        {
            "id": "sec-products-fbn",
            "content": (
                "noon FBN (Fulfilled by Noon): Products labeled FBN are stored in noon's own warehouses "
                "and shipped using noon's logistics. FBN guarantees faster delivery, consistent quality checks, "
                "and noon's standard return and warranty terms. "
                "Non-FBN marketplace seller products may have different delivery times, "
                "return windows, and warranty coverage — check individual product listings."
            ),
            "meta": {
                **_base_meta("ALL", "noon.com", "AED", "products", "eligibility",
                             ["product_inquiry", "return_request"],
                             "https://www.noon.com/uae-en/",
                             "noon Products — FBN vs Marketplace Sellers", uploader_seed=0),
                "chunk_level": "section", "parent_id": "sum-products-all",
            },
            "rules": [
                {"id": "rl-products-fbn-01",
                 "content": "FBN (Fulfilled by Noon) products are stored in noon's warehouses and ship faster with noon's standard return policy."},
                {"id": "rl-products-fbn-02",
                 "content": "Third-party noon marketplace seller products may have different delivery times, return windows, and warranty terms than FBN items."},
            ],
        },
    ],
})


# ─────────────────────────────────────────────────────────────────────────────
# CHUNK FLATTENER
# Converts KNOWLEDGE_TREE into flat list of Qdrant-ready documents
# ─────────────────────────────────────────────────────────────────────────────

def flatten_to_chunks(tree: list, target_regions: list = None) -> tuple:
    """
    Returns (faq_docs, policy_docs) ready for Qdrant upsert.

    faq_docs    — section + rule level chunks → noon_faq collection
    policy_docs — summary + section level chunks → noon_policies collection
    """
    faq_docs = []
    policy_docs = []

    for doc in tree:
        region = doc["meta"].get("region", "ALL")
        if target_regions and region not in target_regions and region != "ALL":
            continue

        summary_id = doc["id"]
        summary_chunk = {
            "id": summary_id,
            "content": doc["content"],
            "chunk_id": summary_id,
            **doc["meta"],
        }
        policy_docs.append(summary_chunk)

        for section in doc.get("sections", []):
            section_id = section["id"]
            section_chunk = {
                "id": section_id,
                "content": section["content"],
                "chunk_id": section_id,
                **section["meta"],
            }
            # Sections go to both collections for cross-collection retrieval
            policy_docs.append(section_chunk)
            faq_docs.append(section_chunk)

            for rule in section.get("rules", []):
                rule_chunk = {
                    "id": rule["id"],
                    "content": rule["content"],
                    "chunk_id": rule["id"],
                    "parent_id": section_id,
                    "chunk_level": "rule",
                    # Inherit section metadata
                    **{k: v for k, v in section["meta"].items()
                       if k not in ("chunk_level", "parent_id")},
                }
                faq_docs.append(rule_chunk)

    return faq_docs, policy_docs


# ─────────────────────────────────────────────────────────────────────────────
# INGESTION
# ─────────────────────────────────────────────────────────────────────────────

async def ingest(target_regions: list = None, dry_run: bool = False):
    retriever = get_retriever()

    faq_docs, policy_docs = flatten_to_chunks(KNOWLEDGE_TREE, target_regions)

    region_label = "+".join(target_regions) if target_regions else "ALL"
    print(f"\n── Ingestion Plan ({'DRY RUN' if dry_run else 'LIVE'}) ──")
    print(f"  Target regions : {region_label}")
    print(f"  noon_faq chunks: {len(faq_docs)}  (sections + rules)")
    print(f"  noon_policies  : {len(policy_docs)}  (summaries + sections)")

    if dry_run:
        print("\n── Sample chunks (first 3 from each collection) ──")
        for d in faq_docs[:3]:
            print(f"  [faq   {d['chunk_level']:7s}] [{d['region']:6s}] {d['content'][:90]}")
        for d in policy_docs[:3]:
            print(f"  [policy {d['chunk_level']:7s}] [{d['region']:6s}] {d['content'][:90]}")
        print("\nDry run complete — no data written.")
        return

    logger.info("ingest.start", faq_count=len(faq_docs), policy_count=len(policy_docs),
                regions=region_label)

    await retriever.add_documents("noon_faq", faq_docs)
    print(f"  ✓ noon_faq:     {len(faq_docs)} chunks ingested")

    await retriever.add_documents("noon_policies", policy_docs)
    print(f"  ✓ noon_policies:{len(policy_docs)} chunks ingested")

    _print_breakdown(faq_docs + policy_docs)


def _print_breakdown(all_docs):
    from collections import Counter
    regions = Counter(d.get("region") for d in all_docs)
    categories = Counter(d.get("category") for d in all_docs)
    levels = Counter(d.get("chunk_level") for d in all_docs)
    print("\n── Breakdown ──────────────────────────────────────────")
    print("  By region:   ", dict(regions))
    print("  By category: ", dict(categories))
    print("  By level:    ", dict(levels))


# ─────────────────────────────────────────────────────────────────────────────
# RETRIEVAL VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

async def verify():
    retriever = get_retriever()

    test_cases = [
        # (query, collection, region, expected_category, expected_keyword_in_content)
        # More precise queries ensure the right atomic rule surfaces at top-1
        ("standard return window for noon UAE orders days",   "noon_faq",     "UAE",   "returns",  "14"),
        ("عندي مشكلة في الإرجاع كم يوم عندي",               "noon_faq",     "UAE",   "returns",  "14"),  # Arabic
        ("when will my refund arrive on my credit card",      "noon_faq",     "UAE",   "refunds",  "7"),
        ("noon UAE electronics warranty months coverage",     "noon_faq",     "UAE",   "warranty", "12"),
        ("warranty electronics KSA Saudi 2 years",           "noon_faq",     "KSA",   "warranty", "2-year"),
        ("can I pay with installments in Egypt EGP",         "noon_faq",     "Egypt", "payments", "EGP"),
        ("my order shows out for delivery status",           "noon_faq",     "UAE",   "orders",   "Delivery"),
        ("what is COD cash on delivery payment noon",        "noon_faq",     "UAE",   "payments", "cash"),
        ("return eligibility 14 day policy rules UAE",       "noon_policies","UAE",   "returns",  "14"),
        ("noon Rocket delivery time minutes UAE",            "noon_faq",     "UAE",   "delivery", "45"),
        ("how long does noon Egypt delivery take to Cairo",  "noon_faq",     "Egypt", "delivery", "Egypt"),
    ]

    print("\n── Retrieval Verification ────────────────────────────────────────")
    print(f"  {'QUERY':<48} {'REGION':<7} {'SCORE':>6}  STATUS")
    print("  " + "─" * 70)
    passed = failed = 0

    for query, collection, region, expected_cat, expected_kw in test_cases:
        results = await retriever.retrieve(
            query, collection, limit=1, region=region, active_only=True
        )
        if results:
            r = results[0]
            score = r["score"]
            content_lower = r["content"].lower()
            kw_found = expected_kw.lower() in content_lower
            cat_ok = r.get("category") == expected_cat
            ok = kw_found and score >= 0.4
            status = "PASS" if ok else "FAIL"
            if ok:
                passed += 1
            else:
                failed += 1
            q_short = query[:46]
            print(f"  {'✓' if ok else '✗'} {q_short:<48} {region:<7} {score:>6.3f}  {status}")
            if not ok:
                print(f"      → got cat={r.get('category')!r} kw_found={kw_found} content={r['content'][:80]!r}")
        else:
            failed += 1
            print(f"  ✗ {query[:46]:<48} {region:<7} {'N/A':>6}  FAIL (no results)")

    print("  " + "─" * 70)
    print(f"  Result: {passed}/{passed+failed} passed")
    if failed == 0:
        print("  ✓ All checks passed")
    else:
        print(f"  ✗ {failed} check(s) failed — review embedding threshold or chunk content")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest noon knowledge into Qdrant")
    parser.add_argument("--verify",    action="store_true", help="Run retrieval verification only")
    parser.add_argument("--dry-run",   action="store_true", help="Show chunk counts without writing")
    parser.add_argument("--region",    type=str, default=None,
                        help="Ingest specific region only: UAE | KSA | Egypt")
    args = parser.parse_args()

    regions = [args.region] if args.region else None

    if args.verify:
        asyncio.run(verify())
    elif args.dry_run:
        asyncio.run(ingest(regions, dry_run=True))
    else:
        asyncio.run(ingest(regions))
        asyncio.run(verify())
