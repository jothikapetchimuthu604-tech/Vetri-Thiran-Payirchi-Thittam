# PocketSmart AI — Smart Budget & Recommendation Assistant

A full-stack budget-planning web app that generates personalized recommendations
across three domains — **Home Interior**, **Party Planning**, and **Jewelry** —
built with **FastAPI** + **Jinja2**, with an optional **Gemini AI** integration.

Built as a college capstone / Naan Mudhalvan-style project.

---

## 1. Features

- User registration & login (session-cookie based)
- Three budget planners: Home Interior, Party, Jewelry (with image upload)
- Automatic budget allocation across categories with per-item pricing
- Shopping links generated per item (Amazon, Flipkart, IKEA, Swiggy, Zomato, OYO,
  Tanishq, CaratLane, BlueStone, Myntra)
- Recommendation history log per user
- Dashboard with recent activity
- Works immediately with **no API key** (rule-based engine) — or plug in a real
  Gemini key to switch to true generative recommendations

## 2. Why this architecture

The original brief for this class of project (PocketSmart AI) called for a
Gemini-only recommendation engine. This build makes that engine **swappable**:

- `generate_with_ai()` in `app.py` calls Gemini **only if** `GOOGLE_API_KEY` is
  set and `google-generativeai` is installed.
- If that call fails or isn't configured, every route falls back to a
  transparent **rule-based engine** (`rule_based_home`, `rule_based_party`,
  `rule_based_jewelry`) that allocates budget by category weights and returns
  the exact same JSON shape the AI would.

This means:
1. The app **runs and demos reliably** without depending on API quota/keys
   during a viva or grading session.
2. You can **honestly describe both paths** in your report/demo — "rule-based
   by default, real GenAI when configured" — rather than presenting mocked
   API calls as if they were live.

## 3. Project structure

```
pocketsmart_ai/
├── app.py                  # FastAPI app: routes, auth, recommendation engine
├── requirements.txt
├── .env.example
├── static/
│   ├── style.css
│   └── uploads/             # uploaded outfit images land here
└── templates/
    ├── base.html            # shared layout + nav
    ├── index.html           # landing page
    ├── login.html / register.html
    ├── dashboard.html
    ├── home_planner.html
    ├── party_planner.html
    ├── jewelry_planner.html
    ├── _results.html        # shared results-rendering partial
    └── history.html
```

## 4. Setup & run

```bash
cd pocketsmart_ai
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

python app.py
# or: uvicorn app:app --reload
```

Open **http://127.0.0.1:8000** — register an account, then try any of the
three planners from the dashboard.

## 5. Enabling real Gemini AI (optional)

1. Get an API key from [Google AI Studio](https://aistudio.google.com/).
2. `pip install google-generativeai`
3. Copy `.env.example` to `.env` and set `GOOGLE_API_KEY=your_key`, or export
   it directly: `export GOOGLE_API_KEY=your_key`
4. Restart the app — the startup log will print `AI engine: Gemini` instead
   of `rule-based fallback`.

No other code changes are needed — the prompts are already built into each
route handler.

## 6. Known limitations (be upfront about these in your report/viva)

- **Shopping links are search-URL redirects**, not live product API calls —
  there's no real Amazon/Flipkart/IKEA product-catalog integration. This
  mirrors how most student projects in this space work, but say so plainly
  rather than implying live scraping.
- **In-memory storage** — users and history reset when the server restarts.
  Swap in SQLite/PostgreSQL for a persistent version (see "Next steps").
- **Password hashing** uses SHA-256 for simplicity; use `bcrypt`/`passlib` with
  salting before treating this as production-ready.
- **No rate limiting / cost tracking** on the optional Gemini calls — add this
  before using a paid key at scale.

## 7. Suggested "next steps" section for your report

- Swap in-memory dicts for SQLite via SQLAlchemy
- Replace search-URL links with a real product API (e.g., a free-tier
  affiliate API) for at least one category
- Add automated tests (pytest + httpx) for each planner route
- Add budget-adherence validation (flag if AI-suggested totals exceed budget)
- Deploy (Render/Railway/Fly.io) and add a live demo link to your submission

## 8. Tech stack summary (for your report table)

| Layer | Technology |
|---|---|
| Backend | FastAPI (Python) |
| Templating | Jinja2 |
| AI (optional) | Google Gemini 1.5 Flash |
| Styling | Vanilla CSS (no framework) |
| Auth | Cookie-based sessions, in-memory store |
| Storage | In-memory (swap for SQLite/Postgres in production) |
