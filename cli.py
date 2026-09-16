"""
cli.py — High-speed Instagram Lead Scraper for Terminal.
Scrapes Reel comments, fetches full profiles (bio, website, phone, email) in parallel,
and automatically saves directly to an Excel file.
"""

import os
import sys
import time
from datetime import datetime

# Add backend directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from detector import ExtractedLead
from exporter import export_to_excel
from scraper import InstagramScraper


def main():
    print("=" * 60)
    print(" 🚀 INSTAGRAM REEL LEAD SCRAPER (High-Speed Terminal Mode)")
    print("=" * 60)
    print()

    scraper = InstagramScraper()

    # Step 1: Session ID
    session_file = os.path.join(os.path.dirname(__file__), ".ig_session")
    saved_session = ""
    if os.path.exists(session_file):
        try:
            with open(session_file, "r") as f:
                saved_session = f.read().strip()
        except Exception:
            pass

    if saved_session:
        use_saved = input(f"Use saved Instagram session ID? (Y/n): ").strip().lower()
        if use_saved not in ["n", "no"]:
            sessionid = saved_session
        else:
            sessionid = input("Enter your Instagram sessionid: ").strip()
    else:
        print("💡 Paste your Instagram 'sessionid' cookie value.")
        sessionid = input("Instagram sessionid: ").strip()

    if not sessionid:
        print("❌ Error: sessionid cannot be empty.")
        return

    print("\n🔌 Logging into Instagram…")
    login_res = scraper.login_by_session(sessionid)
    if not login_res["success"]:
        print(f"❌ Login failed: {login_res['message']}")
        return

    print(f"✅ {login_res['message']}\n")

    # Save session for convenience
    try:
        with open(session_file, "w") as f:
            f.write(sessionid)
    except Exception:
        pass

    # Step 2: Reel URL
    reel_url = input("📎 Paste Instagram Reel URL: ").strip()
    if not reel_url:
        print("❌ Reel URL cannot be empty.")
        return

    # Max comments & min confidence
    max_comments_in = input("📊 Max comments to scan [default 50, safe range: 30-100]: ").strip()
    max_comments = int(max_comments_in) if max_comments_in.isdigit() else 50

    min_conf_in = input("🎯 Minimum confidence score (0-100) [default 25]: ").strip()
    min_confidence = int(min_conf_in) if min_conf_in.isdigit() else 25

    print("\n" + "-" * 60)
    print("🛡️ Starting safe lead extraction (anti-ban delays active)…")
    print("-" * 60)

    last_pct = [0]
    def cli_progress(msg: str, pct: int):
        last_pct[0] = pct
        bar_len = 30
        filled = int((pct / 100) * bar_len)
        bar = "█" * filled + "░" * (bar_len - filled)
        sys.stdout.write(f"\r[{bar}] {pct:3d}% — {msg[:55]:<55}")
        sys.stdout.flush()

    start_time = time.time()
    result = scraper.scrape_reel(
        reel_url=reel_url,
        max_comments=max_comments,
        min_confidence=min_confidence,
        progress_callback=cli_progress,
    )
    elapsed = time.time() - start_time
    print()  # Newline after progress bar

    if not result["success"]:
        print(f"\n❌ Scraping failed: {result['message']}")
        return

    leads_raw = result.get("leads", [])
    total_comments = result.get("total_comments", 0)
    print("\n" + "=" * 60)
    print(f"✨ DONE in {elapsed:.1f}s! Scanned {total_comments} comments → Found {len(leads_raw)} business leads.")
    print("=" * 60)

    if not leads_raw:
        print("⚠️ No business leads found matching criteria.")
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
        )
        for d in leads_raw
    ]

    # Automatic Excel Export
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"IG_Leads_{timestamp}.xlsx"
    out_path = os.path.abspath(os.path.join(os.path.dirname(__file__), filename))

    xlsx_bytes = export_to_excel(leads, reel_url)
    with open(out_path, "wb") as f:
        f.write(xlsx_bytes)

    print(f"\n📥 [AUTOMATIC DOWNLOAD] Excel sheet saved successfully!")
    print(f"📁 File location: {out_path}\n")

    # Display Top Leads Summary Table
    print(f"{'#':<3} {'Handle':<22} {'Phone(s)':<20} {'Email':<25} {'Score':<6}")
    print("-" * 80)
    for i, lead in enumerate(leads[:15], 1):
        phone_str = ", ".join(lead.phones) if lead.phones else "—"
        email_str = ", ".join(lead.emails) if lead.emails else "—"
        if len(phone_str) > 18:
            phone_str = phone_str[:15] + "…"
        if len(email_str) > 23:
            email_str = email_str[:20] + "…"
        handle_str = f"@{lead.instagram_handle}"[:20]
        print(f"{i:<3} {handle_str:<22} {phone_str:<20} {email_str:<25} {lead.confidence_score}%")

    if len(leads) > 15:
        print(f"... and {len(leads) - 15} more leads included in the Excel file.")

    print("\n✅ All lead profiles, bios, contact numbers, websites & emails saved.")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️ Scraper stopped by user.")
