"""
detector.py — Business/Company detection and contact extraction logic.
Extracts phone numbers, WhatsApp contacts, emails, and websites from comments & Instagram profiles.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ─── Regex Patterns ───────────────────────────────────────────────────────────

# Comprehensive phone patterns matching Indian (+91, 0, 10-digit) and International numbers
PHONE_PATTERNS = [
    # Explicit WhatsApp / Call context prefixes followed by numbers
    r'(?:wa\.me/|whatsapp\.com/send\?phone=)(\+?\d{10,15})',
    r'(?:call|mob|ph|phone|whatsapp|wa|wsp|contact|tel|num|no)[\s:\-\.]*(\+?\d[\d\s\-\.]{8,15}\d)',
    # Indian mobile format with +91 or 0 prefix: +91 98765 43210, +91-9876543210, 09876543210
    r'(?:\+91[\s\-]?)?(?:0)?[6-9]\d{4}[\s\-]?\d{5}\b',
    r'(?:\+91[\s\-]?)?(?:0)?[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}\b',
    r'(?:\+91[\s\-]?)?(?:0)?[6-9]\d{9}\b',
    # International standard format: +1-234-567-8901, +44 7911 123456, +971 50 123 4567
    r'\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{4}\b',
]

URL_PATTERNS = [
    r'https?://[^\s\)\]\>\"\']+',
    r'www\.[a-zA-Z0-9\-]+\.[a-zA-Z]{2,}(?:/[^\s\)\]\>\"\']*)?',
    r'\b(?:wa\.me|wa\.link|linktr\.ee)/[a-zA-Z0-9_\-\.\+]+',
    r'\b[a-zA-Z0-9\-]+\.(?:com|in|co\.in|net|org|io|biz|info|store|shop|online|co|me|app|site|club|tech)(?:/[^\s\)\]\>\"\']*)?',
]

EMAIL_PATTERN = r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}'

# Broad business and high-intent buyer/seller keywords
BUSINESS_KEYWORDS = [
    # Corporate / Business Structure
    'pvt ltd', 'pvt. ltd', 'private limited', 'ltd', 'llp', 'inc', 'corp',
    'enterprises', 'enterprise', 'solutions', 'services', 'industries',
    'group', 'associates', 'consultancy', 'consulting', 'agency', 'studio',
    'technologies', 'tech', 'systems', 'exports', 'imports', 'traders',
    'trading', 'suppliers', 'manufacturer', 'manufacturing', 'distributor',
    'dealer', 'factory', 'boutique', 'creations', 'jewels', 'jewellers',
    'apparel', 'couture', 'textiles', 'handloom', 'mart', 'store', 'shop',
    # Sales, Orders & Wholesale Intent
    'wholesale', 'retail', 'bulk order', 'bulk quantity', 'reseller',
    'order now', 'book now', 'get quote', 'free quote', 'quotation',
    'price please', 'send price', 'how much', 'cost', 'rate', 'price details',
    'catalog', 'catalogue', 'product details', 'moq', 'minimum order',
    'dispatch', 'shipping available', 'all india delivery', 'worldwide shipping',
    'cod available', 'ready stock', 'dm for order', 'dm for price',
    'our product', 'our service', 'our brand', 'visit our', 'check our',
    # Contact Calls
    'contact us', 'call us', 'whatsapp us', 'dm us', 'reach us', 'reach out',
    'ping us', 'connect with us', 'enquire', 'inquiry', 'enquiry',
    'link in bio', 'check bio', 'whatsapp on', 'call on', 'dm for collaboration',
    # Tax / Registration
    'gst', 'gstin', 'pan no', 'cin no', 'reg no',
    # Emojis commonly used by businesses
    '📞', '📱', '☎️', '📧', '🌐', '💼', '🏢', '🏬', '🛒', '🛍️', '📦', '🏷️', '✨', '💎'
]

_NOISE_DOMAINS = {
    'instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'youtube.com',
    'tiktok.com', 'youtu.be', 'linkedin.com',
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
    source_url: str = ""
    category: str = ""


def _clean_phones(raw: List[str]) -> List[str]:
    seen = set()
    result = []
    for m in raw:
        # Strip extraneous text, keep leading + and digits
        digits = re.sub(r'[^\d+]', '', m)
        # Standardize Indian 10-digit / 12-digit numbers
        clean_num = digits
        if digits.startswith('+91') and len(digits) == 13:
            clean_num = '+91 ' + digits[3:]
        elif digits.startswith('91') and len(digits) == 12 and not digits.startswith('+'):
            clean_num = '+91 ' + digits[2:]
        elif len(digits) == 10 and digits[0] in '6789':
            clean_num = '+91 ' + digits
        elif digits.startswith('0') and len(digits) == 11 and digits[1] in '6789':
            clean_num = '+91 ' + digits[1:]

        # Filter out trivial sequences or short numbers
        num_digits = re.sub(r'\D', '', clean_num)
        if len(num_digits) >= 10 and clean_num not in seen:
            seen.add(clean_num)
            result.append(clean_num)
    return result


def _normalise_url(url: str) -> str:
    u = url.lower().strip('.,;:)\'"')
    u = re.sub(r'^https?://', '', u)
    u = re.sub(r'^www\.', '', u)
    return u.rstrip('/')


def _clean_urls(raw: List[str]) -> List[str]:
    seen_norm = set()
    result = []
    for url in raw:
        url = url.strip('.,;:)\'"')
        if any(nd in url.lower() for nd in _NOISE_DOMAINS):
            continue
        norm = _normalise_url(url)
        if norm and norm not in seen_norm:
            seen_norm.add(norm)
            result.append(url)
    return result


def extract_phones(text: str) -> List[str]:
    found = []
    for pat in PHONE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            # If pattern has capturing group, use it, else whole match
            val = m.group(1) if m.lastindex else m.group(0)
            found.append(val)
    return _clean_phones(found)


def extract_emails(text: str) -> List[str]:
    matches = re.findall(EMAIL_PATTERN, text, re.IGNORECASE)
    seen = set()
    result = []
    for email in matches:
        e_lower = email.lower().strip('.,;')
        if e_lower not in seen:
            seen.add(e_lower)
            result.append(e_lower)
    return result


def extract_websites(text: str) -> List[str]:
    found = []
    for pat in URL_PATTERNS:
        found.extend(re.findall(pat, text, re.IGNORECASE))
    return _clean_urls(found)


def analyze_comment(
    comment_text: str,
    username: str,
    full_name: str,
    biography: Optional[str] = None,
    external_url: Optional[str] = None,
    public_email: Optional[str] = None,
    public_phone: Optional[str] = None,
    source_url: str = "",
    category: Optional[str] = None,
    is_business_profile: bool = False,
) -> ExtractedLead:
    """
    Extracts leads and calculates business confidence score.
    """
    bio = (biography or "").strip()
    comment = (comment_text or "").strip()
    u_name = (username or "").strip()
    f_name = (full_name or "").strip()

    all_text = f"{comment} {bio} {u_name} {f_name}"

    # 1. Extract contact details
    phones = extract_phones(all_text)
    if public_phone:
        for p in _clean_phones([public_phone]):
            if p not in phones:
                phones.append(p)

    emails = extract_emails(all_text)
    if public_email:
        pe = public_email.lower().strip()
        if pe and pe not in emails:
            emails.append(pe)

    websites = extract_websites(all_text)
    if external_url:
        ext = external_url.strip()
        if ext and not any(nd in ext.lower() for nd in _NOISE_DOMAINS):
            if ext not in websites:
                websites.insert(0, ext)

    # 2. Score business likelihood
    score = 0
    reasons = []
    check_text = all_text.lower()

    if phones:
        score += 45
        reasons.append(f"📞 Phone: {', '.join(phones[:2])}")

    if emails:
        score += 35
        reasons.append(f"📧 Email: {', '.join(emails[:2])}")

    if websites:
        score += 30
        reasons.append(f"🌐 Website: {', '.join(websites[:2])}")

    if public_email or public_phone:
        score += 25
        reasons.append("✅ Verified business contact info")

    if external_url and "Website" not in " ".join(reasons):
        score += 20
        reasons.append("🌐 Profile website link")

    if category:
        score += 35
        reasons.append(f"🏢 Category: {category}")

    if is_business_profile:
        score += 30
        if "Category" not in " ".join(reasons):
            reasons.append("🏢 Verified Business Account")

    # Keyword scoring
    kw_found = [kw for kw in BUSINESS_KEYWORDS if kw in check_text]
    if kw_found:
        kw_score = min(len(kw_found) * 8, 30)
        score += kw_score
        reasons.append(f"💼 Keywords: {', '.join(kw_found[:4])}")

    # Username hints
    biz_hints = ['official', 'store', 'shop', 'pvt', 'ltd', 'india', 'group',
                 'brand', 'corp', 'enterprise', 'biz', 'co', 'hub', 'mart',
                 'creations', 'jewels', 'boutique', 'fashion', 'studio', 'agency',
                 'trading', 'solutions', 'apparel', 'couture']
    for hint in biz_hints:
        if hint in u_name.lower():
            score += 15
            reasons.append(f"🏷️ Business handle (@{u_name})")
            break

    # Business bio style
    if bio and any(kw in bio.lower() for kw in ['📞', '📱', '📧', '🌐', 'contact', 'call', 'dm', 'order', 'shipping', 'wholesale']):
        score += 15
        reasons.append("📋 Business profile bio")

    score = min(score, 100)

    # Lead determination: considered a lead if score >= 25, contacts found, or official business profile
    is_lead = (score >= 25) or bool(phones) or bool(emails) or bool(websites) or bool(category) or is_business_profile

    return ExtractedLead(
        instagram_handle=f"@{u_name}",
        commenter_name=f_name or u_name,
        comment_text=comment[:300],
        phones=phones,
        emails=emails,
        websites=websites,
        confidence_score=score,
        detection_reasons=reasons,
        is_business=is_lead,
        source_url=source_url,
        category=category or "",
    )
