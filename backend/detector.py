"""
detector.py — Business/Company detection logic.
Extracts phones, emails, websites from comment text AND Instagram profile bio.
"""

import re
from dataclasses import dataclass, field
from typing import Optional


# ─── Regex Patterns ───────────────────────────────────────────────────────────

PHONE_PATTERNS = [
    r'(?:\+91[\-\s]?)?(?:0)?[6-9]\d{9}',
    r'\b(?:\+91[\s\-]?)?\d{5}[\s\-]?\d{5}\b',
    r'\b(?:\+91[\s\-]?)?\d{4}[\s\-]?\d{3}[\s\-]?\d{3}\b',
    r'\b(?:\+\d{1,3}[\s\-]?)?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{4}\b',
    r'(?:call|mob|ph|phone|whatsapp|wa|contact)[\s:\-\.]*(\+?[\d\s\-]{10,})',
]

URL_PATTERNS = [
    r'https?://[^\s\)\]\>\"\']+',
    r'www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s\)\]\>\"\']*)?',
    r'\b[a-zA-Z0-9\-]+\.(?:com|in|co\.in|net|org|io|biz|info|store|shop|online|co|me|app)(?:/[^\s\)\]\>\"\']*)?',
]

EMAIL_PATTERN = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'

BUSINESS_KEYWORDS = [
    'pvt ltd', 'pvt. ltd', 'private limited', 'ltd', 'llp', 'inc', 'corp',
    'enterprises', 'enterprise', 'solutions', 'services', 'industries',
    'group', 'associates', 'consultancy', 'consulting', 'agency', 'studio',
    'technologies', 'tech', 'systems', 'exports', 'imports', 'traders',
    'trading', 'suppliers', 'manufacturer', 'distributor', 'dealer',
    'contact us', 'call us', 'whatsapp us', 'dm for', 'dm us',
    'reach us', 'reach out', 'enquire', 'inquiry', 'enquiry',
    'order now', 'book now', 'get quote', 'free quote', 'bulk order',
    'wholesale', 'retail', 'our product', 'our service', 'our brand',
    'visit our', 'check our', 'shop now', 'buy now', 'link in bio',
    'gst', 'gstin', 'pan no', 'cin no', 'reg no',
    '📞', '📱', '☎️', '📧', '🌐', '💼', '🏢', '🏬', '🛒', '🛍️',
]

# Noise domains to skip
_NOISE_DOMAINS = {
    'instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'youtube.com',
    'tiktok.com', 'linktr.ee', 'bit.ly', 'youtu.be', 'linkedin.com',
}


@dataclass
class ExtractedLead:
    instagram_handle: str
    commenter_name: str
    comment_text: str
    phones: list = field(default_factory=list)
    emails: list = field(default_factory=list)
    websites: list = field(default_factory=list)
    confidence_score: int = 0
    detection_reasons: list = field(default_factory=list)
    is_business: bool = False


def _clean_phones(raw: list[str]) -> list[str]:
    seen, result = set(), []
    for m in raw:
        digits = re.sub(r'[^\d+]', '', m)
        if len(digits.lstrip('+')) >= 10 and digits not in seen:
            seen.add(digits)
            result.append(digits)
    return result


def _normalise_url(url: str) -> str:
    """Normalise URL for deduplication (lowercase, strip scheme and www)."""
    u = url.lower().strip('.,;:)\'"')
    u = re.sub(r'^https?://', '', u)
    u = re.sub(r'^www\.', '', u)
    return u.rstrip('/')


def _clean_urls(raw: list[str]) -> list[str]:
    seen_norm, result = set(), []
    for url in raw:
        url = url.strip('.,;:)\'"')
        if any(nd in url.lower() for nd in _NOISE_DOMAINS):
            continue
        norm = _normalise_url(url)
        if url and norm not in seen_norm:
            seen_norm.add(norm)
            result.append(url)
    return result


def extract_phones(text: str) -> list[str]:
    found = []
    for pat in PHONE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            found.append(m.group(0))
    return _clean_phones(found)


def extract_emails(text: str) -> list[str]:
    return list(dict.fromkeys(re.findall(EMAIL_PATTERN, text, re.IGNORECASE)))


def extract_websites(text: str) -> list[str]:
    found = []
    for pat in URL_PATTERNS:
        found.extend(re.findall(pat, text, re.IGNORECASE))
    return _clean_urls(found)


def analyze_comment(
    comment_text: str,
    username: str,
    full_name: str,
    biography: Optional[str] = None,
    external_url: Optional[str] = None,   # Instagram's profile website field
    public_email: Optional[str] = None,   # Business account public email
    public_phone: Optional[str] = None,   # Business account public phone
) -> ExtractedLead:
    """
    Full analysis of a commenter.
    Pulls data from: comment text, bio, external URL, public email, public phone.
    """
    bio = biography or ""
    # Combine all text sources for extraction
    all_text = f"{comment_text} {bio} {username} {full_name}"

    # ── Extract phones ──
    phones = extract_phones(all_text)
    # Add the direct public_phone if present
    if public_phone:
        cleaned = _clean_phones([public_phone])
        for p in cleaned:
            if p not in phones:
                phones.append(p)

    # ── Extract emails ──
    emails = extract_emails(all_text)
    if public_email and public_email not in emails:
        emails.append(public_email)

    # ── Extract websites ──
    websites = extract_websites(all_text)
    # The external_url field is Instagram's dedicated "website" field in the bio
    if external_url:
        ext = external_url.strip()
        if ext and not any(nd in ext.lower() for nd in _NOISE_DOMAINS):
            if ext not in websites:
                websites.insert(0, ext)  # Put profile website first

    # ── Score business likelihood ──
    score = 0
    reasons = []
    check_text = all_text.lower()

    if phones:
        score += 40
        reasons.append(f"📞 Phone: {', '.join(phones[:2])}")

    if emails:
        score += 35
        reasons.append(f"📧 Email: {', '.join(emails[:2])}")

    if websites:
        score += 35
        reasons.append(f"🌐 Website: {', '.join(websites[:2])}")

    if public_email or public_phone:
        score += 20
        reasons.append("✅ Verified business account info")

    if external_url:
        score += 15
        if "Website in profile" not in " ".join(reasons):
            reasons.append("🌐 Website in profile")

    kw_found = [kw for kw in BUSINESS_KEYWORDS if kw in check_text]
    if kw_found:
        score += min(len(kw_found) * 6, 25)
        reasons.append(f"💼 Keywords: {', '.join(kw_found[:4])}")

    biz_hints = ['official', 'store', 'shop', 'pvt', 'ltd', 'india', 'group',
                 'brand', 'corp', 'enterprise', 'biz', 'co', 'hub', 'mart']
    for hint in biz_hints:
        if hint in username.lower():
            score += 10
            reasons.append(f"🏷️ Business username (@{username})")
            break

    # Bio looks like a business bio (has contact info structure)
    if bio and any(kw in bio.lower() for kw in ['📞', '📱', '📧', '🌐', 'contact', 'call', 'dm', 'order']):
        score += 10
        reasons.append("📋 Business-style bio")

    score = min(score, 100)

    return ExtractedLead(
        instagram_handle=f"@{username}",
        commenter_name=full_name or username,
        comment_text=comment_text[:300],
        phones=phones,
        emails=emails,
        websites=websites,
        confidence_score=score,
        detection_reasons=reasons,
        is_business=(score >= 25),
    )
