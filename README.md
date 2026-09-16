# 🚀 InstaPulse Scraper

> **High-speed Instagram Reel lead extractor & buyer-intent detector.**  
> Automatically turn Instagram Reel comments into enriched, actionable sales leads with 1-click Excel export.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

---

## ✨ Features

- 🎯 **Smart Intent Scoring**: Automatically detects high-intent buyer inquiries (e.g. price questions, purchase intent, product inquiries).
- ⚡ **Profile Enrichment**: Pulls bios, business categories, contact emails, phone numbers, website links, follower counts, and verification badges in parallel.
- 🛡️ **Anti-Ban Protection**: Built-in human-like pacing and rate limiting to keep your Instagram session safe.
- 📊 **1-Click Excel Export**: Formats leads directly into clean, structured `.xlsx` spreadsheets ready for CRM imports.
- 💻 **Dual Mode Interface**:
  - **Modern Web Dashboard**: Real-time progress tracking, interactive tables, and live lead filtering.
  - **High-Speed Terminal CLI**: Lightweight, keyboard-driven scraping right inside your terminal.

---

## 🛠️ Tech Stack

- **Backend**: Python, FastAPI, Uvicorn, Instagrapi, Pandas, OpenPyXL
- **Frontend**: HTML5, Modern CSS (Glassmorphism & Dark UI), Vanilla JS
- **CLI**: Interactive Python Console with live progress meters

---

## 🚀 Quick Start

### 1. Clone the Repository
```bash
git clone https://github.com/murugavel03/insta-pulse-scraper.git
cd insta-pulse-scraper
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Application

#### 🌐 Web Dashboard
Double-click `start.bat` or run:
```bash
python backend/main.py
```
Then open your browser at **`http://localhost:8000`**.

#### 💻 Terminal CLI Mode
Double-click `run_cli.bat` or run:
```bash
python cli.py
```

---

## 🔑 Authentication

This tool uses session-based authentication via your Instagram `sessionid` cookie for safe, fast, and 2FA-compatible login:
1. Open Instagram in your browser and log in.
2. Open Developer Tools (`F12` or right-click -> *Inspect*).
3. Navigate to **Application** (or **Storage**) > **Cookies** > `https://www.instagram.com`.
4. Copy the value of the `sessionid` cookie.
5. Paste it into the Web UI or CLI prompt when asked.

---

## 📁 Project Structure

```
insta-pulse-scraper/
├── backend/
│   ├── detector.py      # Lead & buyer intent classification engine
│   ├── exporter.py      # Excel (.xlsx) export utility
│   ├── main.py          # FastAPI application & REST endpoints
│   └── scraper.py       # Instagram API scraper & profile enricher
├── frontend/
│   └── index.html       # Glassmorphic web dashboard
├── cli.py               # Interactive terminal CLI scraper
├── requirements.txt     # Python dependencies
├── run_cli.bat          # 1-click CLI launcher
├── start.bat            # 1-click Web Dashboard launcher
└── README.md
```

---

## ⚠️ Disclaimer

This project is intended strictly for educational and legitimate business development purposes. Please respect Instagram's Terms of Service and rate limits.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
