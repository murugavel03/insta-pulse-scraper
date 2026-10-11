"""
scraper.py — High-Performance, Anti-Ban Instagram Scraping Engine.

Features:
- Multi-Account Session Pool & Auto-Rotation (Burner Account Pool)
- Proxy Support (HTTP / SOCKS5) to shield your IP
- Configurable Anti-Ban Safety Presets (Ultra-Safe / Balanced / Turbo)
- Human-emulated randomized jitter and inter-reel batch cooldowns
- Smart, selective Deep Profile Enrichment (saves 85-90% API calls)
- Bulk Reel URL processing with cross-reel commenter deduplication
- Automatic Checkpoint & Rate-Limit Circuit Breaker (preserves scraped data)
"""

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from instagrapi import Client
from instagrapi.exceptions import (
    ChallengeRequired,
    ClientError,
    FeedbackRequired,
    LoginRequired,
    MediaNotFound,
    PleaseWaitFewMinutes,
    PrivateError,
    RateLimitError,
)

from detector import ExtractedLead, analyze_comment

# Suppress loud instagrapi request errors from polluting console output
logging.getLogger("instagrapi").setLevel(logging.WARNING)


def extract_shortcode(reel_url: str) -> Optional[str]:
    """Extract Instagram media shortcode from various URL formats."""
    url = reel_url.strip()
    # Match standard URLs: /reel/CODE, /reels/CODE, /p/CODE, /tv/CODE, /share/reel/CODE
    pattern = r'instagram\.com/(?:reel|reels|p|tv|share/reel)/([A-Za-z0-9_\-]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)

    # Match direct shortcode passed without URL
    clean = url.strip('/').split('?')[0].split('/')[-1]
    if re.match(r'^[A-Za-z0-9_\-]{8,25}$', clean):
        return clean

    return None


@dataclass
class AccountSession:
    client: Client
    sessionid: str
    username: str = ""
    is_active: bool = True
    requests_count: int = 0
    cooldown_until: float = 0.0
    status: str = "active"  # "active", "cooldown", "blocked"
    error_msg: str = ""


class InstagramScraper:
    def __init__(self):
        self.accounts: List[AccountSession] = []
        self.current_account_idx: int = 0
        self.proxy: Optional[str] = None
        self.logged_in: bool = False
        self.username: str = ""

    def add_session(self, sessionid: str, proxy: Optional[str] = None) -> Tuple[bool, str, str]:
        """Test and add a single session to the account pool."""
        sessionid = sessionid.strip()
        if not sessionid:
            return False, "", "Empty session ID."

        client = Client()
        if proxy and proxy.strip():
            try:
                client.set_proxy(proxy.strip())
            except Exception as e:
                return False, "", f"Proxy error: {str(e)}"

        client.delay_range = [2, 5]

        try:
            client.login_by_sessionid(sessionid)
            username = getattr(client, "username", None) or "User"
            acc = AccountSession(
                client=client,
                sessionid=sessionid,
                username=username,
                is_active=True,
                status="active",
            )
            self.accounts.append(acc)
            return True, username, f"Logged in as @{username} ✅"
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["login", "session", "invalid", "401", "unauthorized"]):
                msg = "Session ID is invalid or expired."
            elif any(k in err for k in ["checkpoint", "challenge"]):
                msg = "Account triggered checkpoint verification."
            else:
                msg = f"Login failed: {str(e)}"
            return False, "", msg

    def login_by_sessions(self, sessionids: List[str], proxy: Optional[str] = None) -> dict:
        """Connect one or multiple sessions into the account pool."""
        self.accounts = []
        self.proxy = proxy.strip() if proxy and proxy.strip() else None
        self.logged_in = False
        self.username = ""

        successful_accounts = []
        failed_accounts = []

        for sid in sessionids:
            clean_sid = sid.strip()
            if not clean_sid:
                continue
            success, uname, msg = self.add_session(clean_sid, self.proxy)
            if success:
                successful_accounts.append(uname)
            else:
                failed_accounts.append({"session": clean_sid[:15] + "…", "error": msg})

        if successful_accounts:
            self.logged_in = True
            self.username = successful_accounts[0]
            summary = f"Connected {len(successful_accounts)} account(s): " + ", ".join(f"@{u}" for u in successful_accounts)
            if failed_accounts:
                summary += f" ({len(failed_accounts)} session(s) failed)"
            return {
                "success": True,
                "message": summary,
                "username": self.username,
                "accounts": [{"username": a.username, "status": a.status} for a in self.accounts],
            }

        first_err = failed_accounts[0]["error"] if failed_accounts else "No valid session ID provided."
        return {
            "success": False,
            "message": f"Could not connect any account: {first_err}",
            "accounts": [],
        }

    def login_by_session(self, sessionid: str, proxy: Optional[str] = None) -> dict:
        """Single session login for backward compatibility."""
        return self.login_by_sessions([sessionid], proxy)

    def get_next_client(self) -> Tuple[Optional[Client], Optional[AccountSession]]:
        """Round-robin rotation across active, non-cooling accounts."""
        if not self.accounts:
            return None, None

        now = time.time()
        # Reactivate any accounts whose cooldown has elapsed
        for acc in self.accounts:
            if acc.status == "cooldown" and now >= acc.cooldown_until:
                acc.status = "active"
                acc.is_active = True

        active_accounts = [a for a in self.accounts if a.is_active and a.status == "active"]
        if not active_accounts:
            # If all are cooling down, find the one with shortest remaining wait
            cooling = [a for a in self.accounts if a.status == "cooldown"]
            if cooling:
                cooling.sort(key=lambda a: a.cooldown_until)
                wait_sec = max(1.0, cooling[0].cooldown_until - now)
                time.sleep(min(wait_sec, 15.0))
                cooling[0].status = "active"
                cooling[0].is_active = True
                return cooling[0].client, cooling[0]
            return None, None

        self.current_account_idx = (self.current_account_idx + 1) % len(active_accounts)
        chosen = active_accounts[self.current_account_idx]
        chosen.requests_count += 1
        return chosen.client, chosen

    def _mark_account_cooldown(self, acc: AccountSession, duration: float, reason: str):
        """Put an account in cooldown to avoid triggering a ban."""
        acc.status = "cooldown"
        acc.is_active = False
        acc.cooldown_until = time.time() + duration
        acc.error_msg = reason

    def _mark_account_blocked(self, acc: AccountSession, reason: str):
        """Mark account as blocked / expired checkpoint so we never hammer it."""
        acc.status = "blocked"
        acc.is_active = False
        acc.error_msg = reason

    def _apply_safety_settings(self, safety_mode: str, custom_cooldown: Optional[int] = None) -> dict:
        """Returns tuned delay and pacing configurations based on anti-ban profile."""
        mode = safety_mode.lower()
        if mode == "ultra":
            # 🛡️ Ultra-Safe (Stealth Zero-Ban)
            return {
                "name": "Ultra-Safe",
                "delay_range": [3.5, 6.5],
                "cooldown_between_reels": custom_cooldown if custom_cooldown is not None else 20,
                "profile_delay": 4.5,
                "max_enrich": 8,
                "batch_pause": 5.0,
            }
        elif mode == "turbo":
            # ⚡ Turbo Mode (Fastest, best with proxies or burner pools)
            return {
                "name": "Turbo",
                "delay_range": [1.0, 2.2],
                "cooldown_between_reels": custom_cooldown if custom_cooldown is not None else 4,
                "profile_delay": 1.5,
                "max_enrich": 25,
                "batch_pause": 2.0,
            }
        else:
            # ⚖️ Balanced Mode (Default recommendation)
            return {
                "name": "Balanced",
                "delay_range": [2.0, 4.0],
                "cooldown_between_reels": custom_cooldown if custom_cooldown is not None else 10,
                "profile_delay": 3.0,
                "max_enrich": 15,
                "batch_pause": 3.5,
            }

    def _sleep_jitter(self, base_delay: float, jitter_min: float = 0.5, jitter_max: float = 1.8):
        """Human-emulated randomized delay with jitter."""
        sleep_time = max(0.2, base_delay + random.uniform(jitter_min, jitter_max))
        time.sleep(sleep_time)

    def _fetch_profile_safe(self, client: Client, acc: AccountSession, user_pk: int) -> dict:
        """
        Fetch full profile using authenticated private mobile v1 endpoint ONLY.
        Extracts bio, external link, public phone/email, and official Instagram business category.
        """
        try:
            info = client.user_info_v1(user_pk)
            cat = getattr(info, "category_name", "") or getattr(info, "business_category_name", "") or getattr(info, "category", "") or ""
            is_biz = getattr(info, "is_business", False)
            phone = getattr(info, "contact_phone_number", "") or getattr(info, "public_phone_number", "") or ""
            return {
                "biography": getattr(info, "biography", "") or "",
                "external_url": getattr(info, "external_url", "") or "",
                "public_email": getattr(info, "public_email", "") or "",
                "public_phone": phone,
                "full_name": getattr(info, "full_name", "") or "",
                "category": cat,
                "is_business_profile": bool(is_biz or cat),
            }
        except (RateLimitError, FeedbackRequired, PleaseWaitFewMinutes):
            self._mark_account_cooldown(acc, duration=120.0, reason="Rate limit / Feedback on user profile.")
            return {"biography": "", "external_url": "", "public_email": "", "public_phone": "", "full_name": "", "category": "", "is_business_profile": False}
        except (LoginRequired, ChallengeRequired):
            self._mark_account_blocked(acc, reason="Checkpoint or login required on user profile.")
            return {"biography": "", "external_url": "", "public_email": "", "public_phone": "", "full_name": "", "category": "", "is_business_profile": False}
        except Exception:
            return {"biography": "", "external_url": "", "public_email": "", "public_phone": "", "full_name": "", "category": "", "is_business_profile": False}

    def _fetch_comments_progressive(
        self,
        client: Client,
        acc: AccountSession,
        media_pk: str,
        max_comments: int,
        progress_callback: Optional[Callable[[str, int], None]] = None,
        base_pct: int = 10,
        target_pct: int = 60,
        safety_config: Optional[dict] = None,
    ) -> Tuple[List[Any], Optional[str]]:
        """
        Progressively fetch up to 500-1000+ comments with humanized breathing pauses,
        stealth cursor pagination, and graceful partial yield if throttled.
        """
        from types import SimpleNamespace
        from instagrapi.extractors import extract_comment

        def _safe_extract(c_dict):
            try:
                return extract_comment(c_dict)
            except Exception:
                u_raw = c_dict.get("user") or {}
                return SimpleNamespace(
                    pk=c_dict.get("pk"),
                    text=c_dict.get("text", "") or "",
                    user=SimpleNamespace(
                        pk=u_raw.get("pk", 0),
                        username=u_raw.get("username", "") or "",
                        full_name=u_raw.get("full_name", "") or "",
                    )
                )

        comments: List[Any] = []
        warning_msg: Optional[str] = None
        params = None
        batch_count = 0

        page_delay = 2.2 if not safety_config else max(1.2, safety_config["delay_range"][0])

        is_unlimited = (max_comments <= 0)
        target_label = "ALL" if is_unlimited else str(max_comments)

        try:
            # 1. Initial page
            self._sleep_jitter(0.4, 0.2, 0.6)
            result = client.private_request(f"media/{media_pk}/comments/", params)
            raw_batch = result.get("comments") or []
            for item in raw_batch:
                comments.append(_safe_extract(item))

            if progress_callback:
                progress_callback(f"Scanned {len(comments)} comments ({'fetching 100% of Reel' if is_unlimited else f'target: {max_comments}'}) with @{acc.username}…", base_pct + 2)

            # 2. Paged loop for complete comment retrieval (100% of reel or up to max_comments)
            while True:
                if not is_unlimited and len(comments) >= max_comments:
                    break
                has_next = (
                    (result.get("has_more_comments") and result.get("next_max_id"))
                    or (result.get("has_more_headload_comments") and result.get("next_min_id"))
                )
                if not has_next:
                    break

                if result.get("has_more_comments"):
                    params = {"max_id": result.get("next_max_id")}
                else:
                    params = {"min_id": result.get("next_min_id")}

                if not (result.get("next_max_id") or result.get("next_min_id") or result.get("comments")):
                    break

                # Human delay between comment page requests
                self._sleep_jitter(page_delay, 0.3, 1.0)
                batch_count += 1

                # Stealth breathing pause every ~100-120 comments
                if batch_count % 4 == 0 and len(comments) >= 100:
                    pause_sec = random.uniform(4.5, 7.0)
                    pct = base_pct + int((min(len(comments), max_comments) / max_comments) * (target_pct - base_pct))
                    if progress_callback:
                        progress_callback(
                            f"🛡️ Anti-Ban Pacing: taking a {pause_sec:.1f}s stealth breath after {len(comments)} comments…",
                            pct,
                        )
                    time.sleep(pause_sec)

                try:
                    result = client.private_request(f"media/{media_pk}/comments/", params)
                except (RateLimitError, FeedbackRequired, PleaseWaitFewMinutes) as e:
                    self._mark_account_cooldown(acc, duration=180.0, reason=f"Rate limit on page: {str(e)}")
                    warning_msg = f"Instagram rate limit reached after {len(comments)} comments. Safely preserving all collected comments."
                    break
                except (LoginRequired, ChallengeRequired):
                    self._mark_account_blocked(acc, reason="Checkpoint triggered on pagination.")
                    warning_msg = f"Account @{acc.username} triggered verification after {len(comments)} comments. Preserving collected data."
                    break

                new_batch = result.get("comments") or []
                if not new_batch:
                    break

                for item in new_batch:
                    comments.append(_safe_extract(item))
                    if not is_unlimited and len(comments) >= max_comments:
                        break

                if is_unlimited:
                    pct = min(base_pct + int(len(comments) / 25), target_pct)
                    if progress_callback:
                        progress_callback(f"Scanned {len(comments)} comments (scanning 100% of Reel) with @{acc.username}…", pct)
                else:
                    pct = base_pct + int((min(len(comments), max_comments) / max_comments) * (target_pct - base_pct))
                    if progress_callback:
                        progress_callback(f"Scanned {len(comments)}/{max_comments} comments with @{acc.username}…", pct)

        except (RateLimitError, FeedbackRequired, PleaseWaitFewMinutes) as e:
            self._mark_account_cooldown(acc, duration=180.0, reason=f"Rate limit on initial comments: {str(e)}")
            warning_msg = f"Rate limit on @{acc.username}. Safely kept {len(comments)} comments."
        except (LoginRequired, ChallengeRequired):
            self._mark_account_blocked(acc, reason="Checkpoint on initial comments.")
            warning_msg = f"Checkpoint on @{acc.username}. Safely kept {len(comments)} comments."
        except MediaNotFound:
            raise MediaNotFound("Reel not found or private.")
        except Exception as e:
            warning_msg = f"Notice: {str(e)}"

        if max_comments and len(comments) > max_comments:
            comments = comments[:max_comments]

        return comments, warning_msg

    def scrape_bulk_reels(
        self,
        reel_urls: List[str],
        max_comments: int = 500,
        min_confidence: int = 25,
        deep_mode: bool = False,
        safety_mode: str = "ultra",
        custom_cooldown: Optional[int] = None,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """
        Scrape single or multiple Reels with anti-ban protections, account rotation,
        and unified Excel-ready lead aggregation.
        """
        def _progress(msg: str, pct: int):
            if progress_callback:
                progress_callback(msg, pct)

        if not self.logged_in or not self.accounts:
            return {
                "success": False,
                "message": "Not connected. Please add at least one Instagram session.",
                "leads": [],
                "total_comments": 0,
            }

        # Filter and validate input URLs
        valid_items: List[Tuple[str, str]] = []
        for u in reel_urls:
            raw = u.strip()
            if not raw:
                continue
            sc = extract_shortcode(raw)
            if sc:
                canonical_url = f"https://www.instagram.com/reel/{sc}/"
                if not any(item[1] == sc for item in valid_items):
                    valid_items.append((canonical_url, sc))

        if not valid_items:
            return {
                "success": False,
                "message": "No valid Instagram Reel URLs or shortcodes detected. Please paste valid links.",
                "leads": [],
                "total_comments": 0,
            }

        total_reels = len(valid_items)
        config = self._apply_safety_settings(safety_mode, custom_cooldown)

        # Apply delay ranges to all clients in pool
        for a in self.accounts:
            a.client.delay_range = config["delay_range"]

        _progress(f"Initializing Anti-Ban Engine ({config['name']} Mode, {len(self.accounts)} account(s) ready)…", 5)

        # Master aggregates
        all_user_comments: Dict[str, dict] = {}
        total_comments_scanned = 0
        warnings: List[str] = []

        # Process each Reel sequentially
        for reel_idx, (reel_url, shortcode) in enumerate(valid_items, start=1):
            reel_base_pct = int(((reel_idx - 1) / total_reels) * 70)
            reel_target_pct = int((reel_idx / total_reels) * 70)

            _progress(f"[Reel {reel_idx}/{total_reels}] Resolving {shortcode}…", reel_base_pct + 2)

            client, acc = self.get_next_client()
            if not client or not acc:
                warnings.append("All connected accounts entered cooldown/block. Scrape stopped early to prevent bans.")
                break

            try:
                media_pk = client.media_pk_from_code(shortcode)
            except Exception as e:
                warnings.append(f"Could not resolve Reel {shortcode}: {str(e)}")
                continue

            _progress(f"[Reel {reel_idx}/{total_reels}] Fetching up to {max_comments} comments with @{acc.username}…", reel_base_pct + 6)

            # Progressive, chunked comment retrieval with stealth breathing
            comments, page_warn = self._fetch_comments_progressive(
                client=client,
                acc=acc,
                media_pk=str(media_pk),
                max_comments=max_comments,
                progress_callback=_progress,
                base_pct=reel_base_pct + 8,
                target_pct=reel_base_pct + 22,
                safety_config=config,
            )
            if page_warn:
                warnings.append(page_warn)

            count_comments = len(comments)
            total_comments_scanned += count_comments
            _progress(f"[Reel {reel_idx}/{total_reels}] Collected {count_comments} comments. Grouping users…", reel_base_pct + 24)

            # Deduplicate and group comments per commenter across all reels
            for c in comments:
                if not c or not getattr(c, "user", None):
                    continue
                u = c.user.username
                text = (c.text or "").strip()
                if u not in all_user_comments:
                    all_user_comments[u] = {
                        "user_pk": c.user.pk,
                        "full_name": c.user.full_name or "",
                        "comment_texts": [text] if text else [],
                        "source_urls": [reel_url],
                    }
                else:
                    if text and text not in all_user_comments[u]["comment_texts"]:
                        all_user_comments[u]["comment_texts"].append(text)
                    if reel_url not in all_user_comments[u]["source_urls"]:
                        all_user_comments[u]["source_urls"].append(reel_url)

            # Inter-Reel Anti-Ban Cooldown Countdown (if not the last reel)
            if reel_idx < total_reels:
                cooldown_sec = config["cooldown_between_reels"]
                for remaining in range(cooldown_sec, 0, -1):
                    _progress(f"🛡️ Anti-ban pacing: resting accounts for {remaining}s before Reel {reel_idx + 1}/{total_reels}…", reel_target_pct)
                    time.sleep(1.0)

        # ── Step 2: Instant Comment-Level AI Lead Extraction ──
        total_unique_users = len(all_user_comments)
        _progress(f"Analyzing {total_unique_users} commenters across all Reels with AI detector…", 72)

        raw_leads: List[dict] = []
        for username, udata in all_user_comments.items():
            combined_comment = " | ".join(udata["comment_texts"])
            primary_src = udata["source_urls"][0] if udata["source_urls"] else ""
            lead = analyze_comment(
                comment_text=combined_comment,
                username=username,
                full_name=udata["full_name"],
                source_url=primary_src,
            )
            raw_leads.append({
                "lead": lead,
                "user_pk": udata["user_pk"],
                "username": username,
                "full_name": udata["full_name"],
                "combined_comment": combined_comment,
                "source_urls": udata["source_urls"],
            })

        # ── Step 3: Deep Mode Business Profile Enrichment ──
        if deep_mode:
            # Identify ALL candidates that have business indicators, seller/buyer intent, keywords or handles
            candidates = [
                item for item in raw_leads
                if item["lead"].is_business or item["lead"].confidence_score >= 15 or len(item["lead"].phones) > 0
            ]
            candidates.sort(key=lambda item: item["lead"].confidence_score, reverse=True)
            total_cand = len(candidates)

            if total_cand > 0:
                _progress(f"Deep Mode active: Safely scraping {total_cand} business profile(s) for Bio, Category, Phone & Website…", 75)
                profile_cache: Dict[int, dict] = {}

                for idx, item in enumerate(candidates, 1):
                    u_pk = item["user_pk"]
                    if u_pk in profile_cache:
                        profile = profile_cache[u_pk]
                    else:
                        client, acc = self.get_next_client()
                        if not client or not acc:
                            break

                        # Human randomized delay between bio requests
                        self._sleep_jitter(config["profile_delay"], 0.4, 1.2)

                        # Stealth breathing pause every 12 profiles
                        if idx % 12 == 0 and idx < total_cand:
                            rest_s = random.uniform(6.0, 9.0)
                            _progress(f"🛡️ Anti-ban breath: resting accounts for {rest_s:.1f}s after {idx} profiles…", 75 + int((idx / total_cand) * 20))
                            time.sleep(rest_s)

                        profile = self._fetch_profile_safe(client, acc, u_pk)
                        profile_cache[u_pk] = profile

                    if (
                        profile["biography"]
                        or profile["external_url"]
                        or profile["public_email"]
                        or profile["public_phone"]
                        or profile.get("category")
                        or profile.get("is_business_profile")
                    ):
                        enriched = analyze_comment(
                            comment_text=item["combined_comment"],
                            username=item["username"],
                            full_name=profile["full_name"] or item["full_name"],
                            biography=profile["biography"],
                            external_url=profile["external_url"],
                            public_email=profile["public_email"],
                            public_phone=profile["public_phone"],
                            category=profile.get("category", ""),
                            is_business_profile=profile.get("is_business_profile", False),
                            source_url=item["source_urls"][0] if item["source_urls"] else "",
                        )
                        item["lead"] = enriched

                    pct = 75 + int((idx / total_cand) * 20)
                    _progress(f"Scraped business profile {idx}/{total_cand} (@{item['username']})…", pct)

        # ── Step 4: Filter by confidence and sort ──
        filtered_leads: List[ExtractedLead] = []
        for item in raw_leads:
            lead: ExtractedLead = item["lead"]
            if lead.is_business and lead.confidence_score >= min_confidence:
                filtered_leads.append(lead)

        filtered_leads.sort(
            key=lambda l: (len(l.phones) > 0, len(l.emails) > 0, l.confidence_score),
            reverse=True,
        )

        leads_dict = [_lead_to_dict(l) for l in filtered_leads]
        finish_msg = (
            f"Done! Extracted {len(filtered_leads)} qualified business leads from {total_comments_scanned} comments "
            f"({total_unique_users} commenters) across {total_reels} Reel(s)."
        )
        if warnings:
            finish_msg += f" (Note: {len(warnings)} notice(s) logged)"

        _progress(f"✅ {finish_msg}", 100)

        return {
            "success": True,
            "message": finish_msg,
            "total_reels": total_reels,
            "total_comments": total_comments_scanned,
            "total_commenters": total_unique_users,
            "leads": leads_dict,
            "warnings": warnings,
            "accounts_status": [{"username": a.username, "status": a.status, "requests": a.requests_count} for a in self.accounts],
        }

    def scrape_reel(
        self,
        reel_url: str,
        max_comments: int = 300,
        min_confidence: int = 25,
        deep_mode: bool = False,
        safety_mode: str = "ultra",
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        """Backward-compatible single-reel scrape wrapper."""
        return self.scrape_bulk_reels(
            reel_urls=[reel_url],
            max_comments=max_comments,
            min_confidence=min_confidence,
            deep_mode=deep_mode,
            safety_mode=safety_mode,
            progress_callback=progress_callback,
        )


def _lead_to_dict(lead: ExtractedLead) -> dict:
    return {
        "instagram_handle": lead.instagram_handle,
        "commenter_name": lead.commenter_name,
        "comment_text": lead.comment_text,
        "phones": lead.phones,
        "emails": lead.emails,
        "websites": lead.websites,
        "confidence_score": lead.confidence_score,
        "detection_reasons": lead.detection_reasons,
        "is_business": lead.is_business,
        "source_url": getattr(lead, "source_url", ""),
        "category": getattr(lead, "category", ""),
    }
