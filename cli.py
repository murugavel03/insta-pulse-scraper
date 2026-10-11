"""
cli.py — High-Performance, Anti-Ban Instagram Lead Scraper for Terminal.
Features:
- Bulk Reel URL processing (enter multiple links or supply a text file)
- Multi-Account Session Pool & Auto-Rotation (Burner Accounts)
- Anti-Ban Safety Engine (Ultra-Safe, Balanced, Turbo)
- Automatic Excel Export with Source Reel tracking
"""

import os
import sys
import time
from datetime import datetime
from typing import List

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from detector import ExtractedLead
from exporter import export_to_excel
from scraper import InstagramScraper


def main():
    print("=" * 65)
    print(" 🚀 INSTAGRAM BULK LEAD SCRAPER (Anti-Ban Terminal Edition)")
    print("=" * 65)
    print()

    scraper = InstagramScraper()

    # Step 1: Session ID(s)
    session_file = os.path.join(os.path.dirname(__file__), ".ig_session")
    saved_session = ""
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                saved_session = f.read().strip()
        except Exception:
            pass

    session_list: List[str] = []
    if saved_session:
        use_saved = input(f"Use saved Instagram session(s)? (Y/n): ").strip().lower()
        if use_saved not in ["n", "no"]:
            session_list = [s.strip() for s in saved_session.replace(",", "\n").split("\n") if s.strip()]
        else:
            print("💡 Paste your Instagram 'sessionid' cookie(s). (Separate multiple accounts with commas)")
            raw = input("Instagram sessionid: ").strip()
            session_list = [s.strip() for s in raw.replace(",", "\n").split("\n") if s.strip()]
    else:
        print("💡 Paste your Instagram 'sessionid' cookie(s).")
        print("   (Tip: You can paste multiple sessionids separated by commas for account rotation!)")
        raw = input("Instagram sessionid: ").strip()
        session_list = [s.strip() for s in raw.replace(",", "\n").split("\n") if s.strip()]

    if not session_list:
        print("❌ Error: No session ID provided.")
        return

    # Optional Proxy
    proxy_in = input("🌐 Proxy (optional, e.g. http://user:pass@host:port, or press Enter to skip): ").strip()
    proxy = proxy_in if proxy_in else None

    print("\n🔌 Connecting to Instagram account(s)…")
    login_res = scraper.login_by_sessions(session_list, proxy=proxy)
    if not login_res["success"]:
        print(f"❌ Login failed: {login_res['message']}")
        return

    print(f"✅ {login_res['message']}\n")

    # Save sessions for convenience
    try:
        with open(session_file, "w") as f:
            f.write("\n".join(session_list))
    except Exception:
        pass

    # Step 2: Reel URLs (Single or Bulk)
    print("📎 Enter Instagram Reel URLs:")
    print("   • Paste single link")
    print("   • OR paste multiple links separated by commas/spaces")
    print("   • OR type path to a .txt file containing links")
    reel_input = input("\nReel link(s) or file: ").strip()

    urls_to_scrape: List[str] = []
    if os.path.isfile(reel_input):
        try:
            with open(reel_input, "r") as f:
                urls_to_scrape = [line.strip() for line in f if line.strip()]
            print(f"📄 Loaded {len(urls_to_scrape)} URLs from {reel_input}")
        except Exception as e:
            print(f"❌ Error reading file: {e}")
            return
    else:
        # Split by comma or whitespace
        parts = reel_input.replace(",", "\n").split()
        urls_to_scrape = [p.strip() for p in parts if p.strip()]

    if not urls_to_scrape:
        print("❌ Error: No URLs provided.")
        return

    print(f"🎯 Target: {len(urls_to_scrape)} Reel(s) queued for scraping.")

    # Max comments & min confidence
    max_comments_in = input("\n📊 Max comments per Reel [default 0 = ALL comments (100%), or type 500/1000]: ").strip()
    max_comments = int(max_comments_in) if max_comments_in.isdigit() else 0

    min_conf_in = input("🎯 Minimum confidence score (0-100) [default 25]: ").strip()
    min_confidence = int(min_conf_in) if min_conf_in.isdigit() else 25

    # Anti-Ban Safety Mode
    print("\n🛡️ Anti-Ban Safety Presets:")
    print("   [1] 🛡️ Ultra-Safe (Recommended — stealth human delays, 20s inter-reel cooldown, 0% ban risk)")
    print("   [2] ⚖️ Balanced (Standard human delays, 10s cooldown)")
    print("   [3] ⚡ Turbo (Fast extraction — recommended only with rotating proxy)")
    mode_pick = input("Select Safety Mode [1/2/3, default 1]: ").strip()
    safety_mode = "ultra" if mode_pick in ["", "1"] else "balanced" if mode_pick == "2" else "turbo"

    # Deep mode
    deep_pick = input("\n🔍 Deep Profile Mode (Scrape bio, category, phone, email & website of ALL business commenters)? (Y/n): ").strip().lower()
    deep_mode = deep_pick not in ["n", "no"]

    print("\n" + "=" * 65)
    print(f"🚀 Starting Extraction: {len(urls_to_scrape)} Reel(s) | Mode: {safety_mode.upper()} | Deep Profiles: {deep_mode}")
    print("=" * 65)

    last_pct = [0]
    def cli_progress(msg: str, pct: int):
        last_pct[0] = pct
        bar_len = 25
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r[{bar}] {pct:3d}% — {msg[:60]:<60}")
        sys.stdout.flush()

    start_time = time.time()
    result = scraper.scrape_bulk_reels(
        reel_urls=urls_to_scrape,
        max_comments=max_comments,
        min_confidence=min_confidence,
        deep_mode=deep_mode,
        safety_mode=safety_mode,
        progress_callback=cli_progress,
    )
    elapsed = time.time() - start_time
    print()  # Newline after progress

    if not result["success"]:
        print(f"\n❌ Scraping aborted: {result['message']}")
        return

    leads_raw = result.get("leads", [])
    total_comments = result.get("total_comments", 0)
    total_reels = result.get("total_reels", len(urls_to_scrape))
    print("\n" + "=" * 65)
    print(f"✨ DONE in {elapsed:.1f}s! Scanned {total_comments} comments across {total_reels} Reel(s) → Found {len(leads_raw)} leads.")
    print("=" * 65)

    if not leads_raw:
        print("⚠️ No business leads detected matching the score threshold.")
        return

    # Convert to ExtractedLead objects
    leads = [
        ExtractedLead(
            instagram_handle=d["instagram_handle"],
            commenter_name=d["commenter_name"],
            comment_text=d["comment_text"],
            phones=d["phones"],
            emails=d["emails"],
            websites=d["websites"],
            confidence_score=d["confidence_score"],
            detection_reasons=d["detection_reasons"],
            is_business=d["is_business"],
            source_url=d.get("source_url", ""),
            category=d.get("category", ""),
        )
        for d in leads_raw
    ]

    # Automatic Excel Export
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"IG_Bulk_Leads_{timestamp}.xlsx"
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))

    xlsx_bytes = export_to_excel(leads, f"Bulk ({len(urls_to_scrape)} Reels)")
    with open(out_path, "wb") as f:
        f.write(xlsx_bytes)

    print(f"\n📥 [AUTOMATIC DOWNLOAD] Excel sheet saved successfully!")
    print(f"📁 File location: {out_path}\n")

    # Display Top Leads Summary Table
    print(f"{'#':<3} {'Handle':<20} {'Phone(s)':<18} {'Email':<22} {'Score':<6}")
    print("-" * 75)
    for i, lead in enumerate(leads[:15], 1):
        phone_str = ", ".join(lead.phones) if lead.phones else "—"
        email_str = ", ".join(lead.emails) if lead.emails else "—"
        if len(phone_str) > 16:
            phone_str = phone_str[:14] + "…"
        if len(email_str) > 20:
            email_str = email_str[:18] + "…"
        handle_str = f"@{lead.instagram_handle.replace('@','')}"[:18]
        print(f"{i:<3} {handle_str:<20} {phone_str:<18} {email_str:<22} {lead.confidence_score}%")

    if len(leads) > 15:
        print(f"... and {len(leads) - 15} more leads included in the Excel file.")

    print("\n✅ All contacts & leads saved with Source Reel links.")
    print("=" * 65)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️ Scraper stopped by user.")
