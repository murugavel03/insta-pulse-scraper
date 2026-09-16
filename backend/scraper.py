"""
scraper.py — Instagram scraping using instagrapi.
Fetches FULL profile (bio, website, email, phone) for every commenter.
"""

import re
import time
from typing import List, Optional, Callable

from instagrapi import Client
from instagrapi.exceptions import LoginRequired, MediaNotFound

from detector import analyze_comment, ExtractedLead


def extract_shortcode(reel_url: str) -> Optional[str]:
    pattern = r'instagram\.com/(?:reel|p|tv)/([A-Za-z0-9_\-]+)'
    match = re.search(pattern, reel_url)
    return match.group(1) if match else None


class InstagramScraper:
    def __init__(self):
        self.client = Client()
        self.client.delay_range = [1, 2]
        self.logged_in = False

    def login_by_session(self, sessionid: str) -> dict:
        sessionid = sessionid.strip()
        if not sessionid:
            return {"success": False, "message": "Session ID cannot be empty."}
        try:
            self.client.login_by_sessionid(sessionid)
            self.logged_in = True
            me = self.client.account_info()
            return {"success": True, "message": f"Logged in as @{me.username} ✅", "username": me.username}
        except Exception as e:
            err = str(e).lower()
            if any(k in err for k in ["login", "session", "invalid", "401", "unauthorized"]):
                return {"success": False, "message": "Session ID is invalid or expired. Please copy it again from your browser."}
            return {"success": False, "message": f"Login failed: {str(e)}"}

    def _fetch_profile(self, user_pk) -> dict:
        """
        Fetch full profile for a user with error and challenge safety.
        Returns dict with: biography, external_url, public_email, public_phone, full_name
        """
        try:
            info = self.client.user_info(user_pk)
            return {
                "biography":    getattr(info, "biography", "") or "",
                "external_url": getattr(info, "external_url", "") or "",
                "public_email": getattr(info, "public_email", "") or "",
                "public_phone": getattr(info, "public_phone_number", "") or "",
                "full_name":    getattr(info, "full_name", "") or "",
            }
        except Exception:
            return {"biography": "", "external_url": "", "public_email": "", "public_phone": "", "full_name": ""}

    def scrape_reel(
        self,
        reel_url: str,
        max_comments: int = 100,
        min_confidence: int = 25,
        safe_mode: bool = True,
        progress_callback: Optional[Callable[[str, int], None]] = None,
    ) -> dict:
        import random
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        def _progress(msg, pct):
            if progress_callback:
                progress_callback(msg, pct)

        if not self.logged_in:
            return {"success": False, "message": "Not logged in.", "leads": [], "total_comments": 0}

        shortcode = extract_shortcode(reel_url)
        if not shortcode:
            return {"success": False, "message": "Could not parse the Instagram URL. Please paste a valid Reel link.", "leads": [], "total_comments": 0}

        _progress("Fetching reel info…", 5)
        try:
            media_pk = self.client.media_pk_from_code(shortcode)
        except MediaNotFound:
            return {"success": False, "message": "Reel not found. It may be private or deleted.", "leads": [], "total_comments": 0}
        except Exception as e:
            return {"success": False, "message": f"Error fetching reel: {str(e)}", "leads": [], "total_comments": 0}

        _progress("Fetching comments…", 10)
        try:
            comments = self.client.media_comments(media_pk, amount=max_comments)
        except LoginRequired:
            return {"success": False, "message": "Session expired or checkpoint triggered. Please re-login with a fresh session.", "leads": [], "total_comments": 0}
        except Exception as e:
            return {"success": False, "message": f"Error fetching comments: {str(e)}", "leads": [], "total_comments": 0}

        total_comments = len(comments)
        if total_comments == 0:
            _progress("No comments found on this Reel.", 100)
            return {"success": True, "message": "No comments found on this Reel.", "total_comments": 0, "leads": []}

        # Deduplicate commenters first to avoid redundant API requests
        user_comments = {}
        for comment in comments:
            u = comment.user.username
            if u not in user_comments:
                user_comments[u] = {
                    "user_pk": comment.user.pk,
                    "full_name": comment.user.full_name or "",
                    "comment_texts": [comment.text or ""],
                }
            else:
                user_comments[u]["comment_texts"].append(comment.text or "")

        unique_users = list(user_comments.items())
        total_unique = len(unique_users)
        _progress(f"Found {total_comments} comments ({total_unique} unique users). Scanning safely…", 15)

        leads: List[ExtractedLead] = []
        lock = threading.Lock()
        completed_count = 0
        rate_limited = False

        # Safe mode uses 2 workers with random pauses; standard mode uses 4 workers
        max_workers = 2 if safe_mode else 4

        def process_user(item):
            nonlocal completed_count, rate_limited
            if rate_limited:
                return

            username, udata = item
            user_pk = udata["user_pk"]
            full_name = udata["full_name"]
            combined_comment = " | ".join(udata["comment_texts"])

            try:
                # Add human-like random pause to avoid triggering Instagram spam detection
                if safe_mode:
                    time.sleep(random.uniform(1.5, 3.0))

                profile = self._fetch_profile(user_pk)
                biography = profile["biography"]
                external_url = profile["external_url"]
                public_email = profile["public_email"]
                public_phone = profile["public_phone"]
                if profile["full_name"]:
                    full_name = profile["full_name"]

                lead = analyze_comment(
                    comment_text=combined_comment,
                    username=username,
                    full_name=full_name,
                    biography=biography,
                    external_url=external_url,
                    public_email=public_email,
                    public_phone=public_phone,
                )

                with lock:
                    completed_count += 1
                    if lead.is_business and lead.confidence_score >= min_confidence:
                        leads.append(lead)

                    pct = 15 + int((completed_count / max(total_unique, 1)) * 80)
                    if completed_count % 2 == 0 or completed_count == total_unique:
                        _progress(
                            f"Scanned {completed_count}/{total_unique} profiles · Found {len(leads)} leads…",
                            pct,
                        )
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "feedback" in err_str or "checkpoint" in err_str:
                    rate_limited = True
                with lock:
                    completed_count += 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(process_user, item) for item in unique_users]
            for future in as_completed(futures):
                pass

        leads.sort(key=lambda l: l.confidence_score, reverse=True)
        msg = f"Finished! Found {len(leads)} business leads from {total_comments} comments."
        if rate_limited:
            msg += " (Paused early to prevent rate limits)."

        _progress(f"✅ {msg}", 100)

        return {
            "success": True,
            "message": msg,
            "total_comments": total_comments,
            "leads": [_lead_to_dict(l) for l in leads],
        }


def _lead_to_dict(lead: ExtractedLead) -> dict:
    return {
        "instagram_handle":  lead.instagram_handle,
        "commenter_name":    lead.commenter_name,
        "comment_text":      lead.comment_text,
        "phones":            lead.phones,
        "emails":            lead.emails,
        "websites":          lead.websites,
        "confidence_score":  lead.confidence_score,
        "detection_reasons": lead.detection_reasons,
        "is_business":       lead.is_business,
    }
