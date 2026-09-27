"""
PocketSmart AI - Smart Budget & Recommendation Assistant
----------------------------------------------------------
A FastAPI application that generates budget-aware recommendations across
three domains: Home Interior, Party Planning, and Jewelry.

AI ENGINE:
By default this runs on a transparent, rule-based recommendation engine
(no API key required) so it works immediately for demos and grading.
If you set a GOOGLE_API_KEY environment variable and install
`google-generativeai`, the app automatically switches to using Gemini
for real generative recommendations - see `generate_with_ai()` below.
"""

import os
import re
import json
import hashlib
import secrets
import socket
import urllib.parse
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, Request, Form, File, UploadFile, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# --------------------------------------------------------------------------
# App setup
# --------------------------------------------------------------------------
app = FastAPI(title="PocketSmart AI - Budget Planner")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(BASE_DIR, "static", "uploads"), exist_ok=True)


def resolve_runtime_port(preferred: Optional[int] = None) -> int:
    """Return the preferred port, falling back to the next free one if needed."""
    if preferred is None:
        preferred = int(os.getenv("PORT", "8000"))
    if preferred <= 0:
        preferred = 8000

    for port in range(preferred, preferred + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("0.0.0.0", port))
                return port
            except OSError:
                continue

    raise RuntimeError("No free ports available in the expected range.")


app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# --------------------------------------------------------------------------
# Optional Gemini AI integration (falls back to rule-based engine if absent)
# --------------------------------------------------------------------------
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
AI_ENABLED = False
if GOOGLE_API_KEY:
    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        GEMINI_MODEL = genai.GenerativeModel("gemini-1.5-flash")
        AI_ENABLED = True
    except Exception:
        AI_ENABLED = False


def extract_json_from_response(text: str) -> dict:
    """Pull a JSON object out of a raw LLM text response."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON object found in AI response")


def generate_with_ai(prompt: str) -> Optional[dict]:
    """Call Gemini if configured; return None on any failure so callers
    can gracefully fall back to the rule-based engine."""
    if not AI_ENABLED:
        return None
    try:
        response = GEMINI_MODEL.generate_content(prompt)
        return extract_json_from_response(response.text)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Fake in-memory "database" (swap for a real DB in production)
# --------------------------------------------------------------------------
users_db: Dict[str, Dict[str, Any]] = {}          # username -> {password_hash, email}
sessions: Dict[str, str] = {}                      # token -> username
history_db: Dict[str, List[Dict[str, Any]]] = {}   # username -> list of records


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def get_current_user(request: Request) -> Optional[str]:
    token = request.cookies.get("session_token")
    if token and token in sessions:
        return sessions[token]
    return None


def require_login(request: Request) -> str:
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=status.HTTP_303_SEE_OTHER, headers={"Location": "/login"})
    return user


def save_to_history(username: str, rec_type: str, input_summary: str, result: dict):
    history_db.setdefault(username, []).insert(0, {
        "id": secrets.token_hex(6),
        "type": rec_type,
        "timestamp": datetime.now().strftime("%b %d, %Y %I:%M %p"),
        "input_summary": input_summary,
        "result": result,
    })


# --------------------------------------------------------------------------
# Shopping link helper (search-URL based - swap for real product APIs later)
# --------------------------------------------------------------------------
PLATFORM_URLS = {
    "amazon": "https://www.amazon.in/s?k={q}",
    "flipkart": "https://www.flipkart.com/search?q={q}",
    "ikea": "https://www.ikea.com/in/en/search/?q={q}",
    "myntra": "https://www.myntra.com/{q}",
    "swiggy": "https://www.swiggy.com/search?query={q}",
    "zomato": "https://www.zomato.com/search?q={q}",
    "oyorooms": "https://www.oyorooms.com/search/?location={q}",
    "bluestone": "https://www.bluestone.com/search.html?query={q}",
    "tanishq": "https://www.tanishq.co.in/search?q={q}",
    "caratlane": "https://www.caratlane.com/search?q={q}",
}


def shopping_links(item_name: str, platforms: List[str]) -> Dict[str, str]:
    q = urllib.parse.quote_plus(item_name)
    return {p: PLATFORM_URLS[p].format(q=q) for p in platforms if p in PLATFORM_URLS}


def inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


# --------------------------------------------------------------------------
# Rule-based recommendation engine (default, no API key needed)
# --------------------------------------------------------------------------
def rule_based_home(total_budget, num_lights, num_fans, num_furniture, num_dining_tables, rooms, notes):
    weights = {
        "Lighting": (0.15, num_lights, ["LED Ceiling Light", "Pendant Lamp", "Warm White Bulb Set"], ["amazon", "flipkart", "ikea"]),
        "Ceiling Fans": (0.20, num_fans, ["Standard Ceiling Fan", "Premium BLDC Ceiling Fan"], ["amazon", "flipkart"]),
        "Furniture": (0.40, num_furniture, ["Accent Chair", "2-Seater Sofa", "Compact Wardrobe", "Bookshelf"], ["amazon", "flipkart", "ikea", "myntra"]),
        "Dining Tables": (0.25, num_dining_tables, ["4-Seater Dining Table", "6-Seater Dining Set"], ["amazon", "ikea"]),
    }
    active = {k: v for k, v in weights.items() if v[1] and v[1] > 0}
    total_weight = sum(v[0] for v in active.values()) or 1
    breakdown = []
    calc_table = []
    for cat, (w, qty, names, platforms) in active.items():
        allocation = round(total_budget * (w / total_weight), 2)
        per_item = round(allocation / qty, 2) if qty else 0
        tier_idx = min(len(names) - 1, int(per_item // max(1, (allocation / max(qty, 1)) / len(names))) if names else 0)
        item_name = names[min(len(names) - 1, qty % len(names))]
        item = {
            "name": item_name,
            "description": f"Recommended {cat.lower()} option sized to your budget for {qty} unit(s).",
            "estimated_price": per_item,
            "quantity": qty,
            "shopping_links": shopping_links(item_name, platforms),
        }
        breakdown.append({"category": cat, "allocation": allocation, "products": [item]})
        calc_table.append({"category": cat, "items_count": qty, "total_cost": allocation,
                            "percentage_of_budget": round(allocation / total_budget * 100, 1) if total_budget else 0})

    allocated = sum(c["allocation"] for c in breakdown)
    return {
        "total_budget": total_budget,
        "budget_breakdown": breakdown,
        "calculation_table": calc_table,
        "remaining_budget": round(total_budget - allocated, 2),
        "additional_suggestions": [
            "Consider second-hand or open-box furniture for further savings.",
            "Watch for seasonal sales (Republic Day, Diwali) on IKEA and Amazon.",
            "Prioritize the rooms you use most before splurging on secondary spaces.",
        ] + ([f"Notes considered: {notes}"] if notes else []),
    }


def rule_based_party(total_budget, num_guests, party_type, venue_type, needs_catering, needs_decoration, needs_entertainment, notes):
    cats = {}
    if needs_catering:
        cats["Catering"] = (0.55, ["swiggy", "zomato"])
    if needs_decoration:
        cats["Decoration"] = (0.25, ["amazon", "flipkart"])
    if needs_entertainment:
        cats["Entertainment"] = (0.20, ["amazon", "flipkart"])
    if not cats:
        cats["Miscellaneous"] = (1.0, ["amazon"])
    if venue_type and venue_type.lower() not in ("home", "own home", "n/a", ""):
        cats["Venue"] = (0.0, ["oyorooms"])  # informational, priced separately below

    total_weight = sum(w for w, _ in cats.values()) or 1
    breakdown = []
    calc_table = []
    venue_cost = round(total_budget * 0.20, 2) if "Venue" in cats else 0
    remaining_for_split = total_budget - venue_cost

    for cat, (w, platforms) in cats.items():
        if cat == "Venue":
            allocation = venue_cost
            item_name = f"{party_type or 'Event'} venue for {num_guests} guests"
        else:
            allocation = round(remaining_for_split * (w / total_weight), 2)
            per_guest = round(allocation / max(num_guests, 1), 2)
            item_name = f"{cat} package for {party_type or 'event'} ({num_guests} guests, ~{inr(per_guest)}/guest)"
        item = {
            "name": item_name,
            "description": f"{cat} option tailored to a {party_type or 'general'} event with {num_guests} guests.",
            "estimated_price": allocation,
            "shopping_links": shopping_links(item_name, platforms),
        }
        breakdown.append({"category": cat, "allocation": allocation, "products": [item]})
        calc_table.append({"category": cat, "items_count": 1, "total_cost": allocation,
                            "percentage_of_budget": round(allocation / total_budget * 100, 1) if total_budget else 0})

    allocated = sum(c["allocation"] for c in breakdown)
    return {
        "total_budget": total_budget,
        "budget_breakdown": breakdown,
        "calculation_table": calc_table,
        "remaining_budget": round(total_budget - allocated, 2),
        "additional_suggestions": [
            "Get at least two catering quotes before booking.",
            "Potluck-style catering can cut costs by 20-30% for informal gatherings.",
            "Book venues 3-4 weeks ahead for better rates.",
        ] + ([f"Notes considered: {notes}"] if notes else []),
    }


def rule_based_jewelry(total_budget, occasion, preferences, has_image):
    cats = {
        "Necklace/Bracelet": (0.45, ["amazon", "flipkart", "bluestone", "caratlane"]),
        "Earrings": (0.30, ["amazon", "flipkart", "tanishq", "caratlane"]),
        "Ring": (0.25, ["amazon", "flipkart", "bluestone", "tanishq"]),
    }
    style = "elegant"
    if preferences:
        low = preferences.lower()
        if "minimal" in low:
            style = "minimalist"
        elif "gold" in low or "traditional" in low:
            style = "traditional gold-toned"
        elif "silver" in low or "modern" in low:
            style = "modern silver-toned"

    breakdown = []
    calc_table = []
    for cat, (w, platforms) in cats.items():
        allocation = round(total_budget * w, 2)
        item_name = f"{style.title()} {cat.split('/')[0]} for {occasion or 'the occasion'}"
        item = {
            "name": item_name,
            "description": f"A {style} {cat.split('/')[0].lower()} suited to a {occasion or 'general'} occasion"
                            + (" and coordinated with your uploaded outfit." if has_image else "."),
            "estimated_price": allocation,
            "style": style,
            "shopping_links": shopping_links(item_name, platforms),
        }
        breakdown.append({"category": cat, "allocation": allocation, "products": [item]})
        calc_table.append({"category": cat, "items_count": 1, "total_cost": allocation,
                            "percentage_of_budget": round(w * 100, 1)})

    allocated = sum(c["allocation"] for c in breakdown)
    return {
        "total_budget": total_budget,
        "outfit_analysis": {"style": style, "formality": "special occasion" if occasion else "everyday",
                             "image_provided": has_image},
        "budget_breakdown": breakdown,
        "calculation_table": calc_table,
        "remaining_budget": round(total_budget - allocated, 2),
        "additional_suggestions": [
            "Keep metal tones consistent across pieces (all gold or all silver).",
            "For formal occasions, let one statement piece lead and keep the rest minimal.",
        ] + ([f"Style notes: {preferences}"] if preferences else []),
    }


# --------------------------------------------------------------------------
# Routes: static pages
# --------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"user": get_current_user(request)})


# --------------------------------------------------------------------------
# Routes: auth
# --------------------------------------------------------------------------
@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html", {"user": None, "error": None})


@app.post("/register", response_class=HTMLResponse)
async def register(request: Request, username: str = Form(...), email: str = Form(...),
                    password: str = Form(...), confirm_password: str = Form(...)):
    if password != confirm_password:
        return templates.TemplateResponse(request, "register.html", {"user": None,
                                                              "error": "Passwords do not match."})
    if username in users_db:
        return templates.TemplateResponse(request, "register.html", {"user": None,
                                                              "error": "Username already taken."})
    users_db[username] = {"password_hash": hash_password(password), "email": email}
    history_db[username] = []
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {"user": None, "error": None})


@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    user = users_db.get(username)
    if not user or user["password_hash"] != hash_password(password):
        return templates.TemplateResponse(request, "login.html", {"user": None,
                                                           "error": "Invalid username or password."})
    token = secrets.token_hex(16)
    sessions[token] = username
    response = RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax")
    return response


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("session_token")
    if token in sessions:
        del sessions[token]
    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie("session_token")
    return response


# --------------------------------------------------------------------------
# Routes: dashboard & history
# --------------------------------------------------------------------------
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    recent = history_db.get(user, [])[:5]
    return templates.TemplateResponse(request, "dashboard.html", {"user": user, "recent": recent})


@app.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    records = history_db.get(user, [])
    return templates.TemplateResponse(request, "history.html", {"user": user, "records": records})


# --------------------------------------------------------------------------
# Routes: Home Interior Planner
# --------------------------------------------------------------------------
@app.get("/home-planner", response_class=HTMLResponse)
async def home_planner_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "home_planner.html", {"user": user, "result": None})


@app.post("/home-planner", response_class=HTMLResponse)
async def home_planner_submit(
    request: Request,
    total_budget: float = Form(...),
    num_lights: int = Form(0),
    num_fans: int = Form(0),
    num_furniture: int = Form(0),
    num_dining_tables: int = Form(0),
    rooms: List[str] = Form([]),
    notes: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    ai_prompt = (
        f"I need interior design product recommendations for a home in India with a total budget of "
        f"₹{total_budget:.2f}. Requirements: {num_lights} lights, {num_fans} ceiling fans, "
        f"{num_furniture} furniture pieces, {num_dining_tables} dining tables. Rooms: {', '.join(rooms)}. "
        f"Additional notes: {notes or 'None'}. Respond ONLY as JSON with keys: total_budget, "
        f"budget_breakdown (list of {{category, allocation, products: [{{name, description, estimated_price, quantity}}]}}), "
        f"remaining_budget, additional_suggestions (list of strings)."
    )
    result = generate_with_ai(ai_prompt) or rule_based_home(
        total_budget, num_lights, num_fans, num_furniture, num_dining_tables, rooms, notes
    )

    save_to_history(user, "Home Interior", f"Budget ₹{total_budget:.0f} · Rooms: {', '.join(rooms) or 'N/A'}", result)
    return templates.TemplateResponse(request, "home_planner.html", {"user": user, "result": result})


# --------------------------------------------------------------------------
# Routes: Party Planner
# --------------------------------------------------------------------------
@app.get("/party-planner", response_class=HTMLResponse)
async def party_planner_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "party_planner.html", {"user": user, "result": None})


@app.post("/party-planner", response_class=HTMLResponse)
async def party_planner_submit(
    request: Request,
    total_budget: float = Form(...),
    num_guests: int = Form(...),
    party_type: str = Form(""),
    venue_type: str = Form(""),
    needs_catering: Optional[str] = Form(None),
    needs_decoration: Optional[str] = Form(None),
    needs_entertainment: Optional[str] = Form(None),
    notes: str = Form(""),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    ai_prompt = (
        f"I need party planning recommendations for India with a total budget of ₹{total_budget:.2f}. "
        f"Party type: {party_type}, Guests: {num_guests}, Venue type: {venue_type or 'not specified'}. "
        f"Catering needed: {bool(needs_catering)}, Decoration needed: {bool(needs_decoration)}, "
        f"Entertainment needed: {bool(needs_entertainment)}. Notes: {notes or 'None'}. "
        f"Respond ONLY as JSON with keys: total_budget, budget_breakdown (list of {{category, allocation, "
        f"products: [{{name, description, estimated_price}}]}}), remaining_budget, additional_suggestions."
    )
    result = generate_with_ai(ai_prompt) or rule_based_party(
        total_budget, num_guests, party_type, venue_type,
        bool(needs_catering), bool(needs_decoration), bool(needs_entertainment), notes
    )

    save_to_history(user, "Party Planning",
                     f"Budget ₹{total_budget:.0f} · {party_type or 'Event'} · {num_guests} guests", result)
    return templates.TemplateResponse(request, "party_planner.html", {"user": user, "result": result})


# --------------------------------------------------------------------------
# Routes: Jewelry Planner
# --------------------------------------------------------------------------
@app.get("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner_form(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "jewelry_planner.html", {"user": user, "result": None})


@app.post("/jewelry-planner", response_class=HTMLResponse)
async def jewelry_planner_submit(
    request: Request,
    total_budget: float = Form(...),
    occasion: str = Form(""),
    preferences: str = Form(""),
    outfit_image: Optional[UploadFile] = File(None),
):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    has_image = bool(outfit_image and outfit_image.filename)
    if has_image:
        upload_dir = os.path.join(BASE_DIR, "static", "uploads")
        safe_name = f"{secrets.token_hex(6)}_{outfit_image.filename}"
        with open(os.path.join(upload_dir, safe_name), "wb") as f:
            f.write(await outfit_image.read())

    ai_prompt = (
        f"I need jewelry recommendations for India with a total budget of ₹{total_budget:.2f}. "
        f"Occasion: {occasion or 'not specified'}. Style preferences: {preferences or 'not specified'}. "
        f"Respond ONLY as JSON with keys: total_budget, outfit_analysis, budget_breakdown (list of "
        f"{{category, allocation, products: [{{name, description, estimated_price, style}}]}}), "
        f"remaining_budget, additional_suggestions."
    )
    result = generate_with_ai(ai_prompt) or rule_based_jewelry(total_budget, occasion, preferences, has_image)

    save_to_history(user, "Jewelry", f"Budget ₹{total_budget:.0f} · {occasion or 'General'}", result)
    return templates.TemplateResponse(request, "jewelry_planner.html", {"user": user, "result": result})


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("HOST", "127.0.0.1")
    port = resolve_runtime_port()
    print(f"Starting PocketSmart AI on http://{host}:{port}  (AI engine: {'Gemini' if AI_ENABLED else 'rule-based fallback'})")
    uvicorn.run(app, host=host, port=port)
