from flask import (
    Flask, render_template, session, redirect, url_for,
    request, flash, jsonify, abort
)
import json, os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dhruba_secret_key_changeThis!"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")

ADMIN_USERNAME = "dhruba"
ADMIN_PASSWORD = "00000000"

# ----------------------------
# JSON helpers
# ----------------------------
def load_json(path, default):
    # create file if missing
    if not os.path.exists(path):
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)
        except Exception:
            pass
    # read safely
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # return default on parse error
        return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ----------------------------
# Defaults
# ----------------------------
DEFAULT_PRODUCTS = [
  {"id":1,"name":"Laptop","price":249999,"img":"https://m.media-amazon.com/images/I/51PLKwik5fL._AC_UF1000,1000_QL80_.jpg","category":"Computers","ratings":[],"featured":True},
  {"id":2,"name":"Mouse","price":500,"img":"https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSsosymxQez36xdfSK09thwVFBpiLX4whdG3g&s","category":"Accessories","ratings":[],"featured":False},
  {"id":3,"name":"Keyboard","price":1500,"img":"https://www.bbassets.com/media/uploads/p/l/40195886_2-dell-kb216-multimedia-keyboard-wired.jpg","category":"Accessories","ratings":[],"featured":False},
  {"id":4,"name":"Headphones","price":9999,"img":"https://rukminim2.flixcart.com/image/480/640/xif0q/headphone/4/5/f/ace-sonos-original-imah4zanv4kphh6k.jpeg?q=90","category":"Audio","ratings":[],"featured":False}
]

DEFAULT_USERS = [
    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "is_admin": True, "wishlist": []}
]

DEFAULT_ORDERS = []

# ----------------------------
# Load or create JSON files
# ----------------------------
products = load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
users = load_json(USERS_FILE, DEFAULT_USERS)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)

def sync_products():
    save_json(PRODUCTS_FILE, products)

def sync_users():
    save_json(USERS_FILE, users)

def sync_orders():
    save_json(ORDERS_FILE, orders)

# ----------------------------
# Helpers
# ----------------------------
def find_product(pid):
    """Return product dict or None. Accepts int or str id."""
    try:
        target = int(pid)
    except Exception:
        return None
    for p in products:
        try:
            if int(p.get("id")) == target:
                return p
        except Exception:
            continue
    return None

def find_user(username):
    if not username:
        return None
    for u in users:
        if u.get("username") == username:
            return u
    return None

# ----------------------------
# Decorators
# ----------------------------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            flash("Please login first", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        username = session.get("username")
        user = find_user(username)
        if not user or not user.get("is_admin"):
            flash("Admin access required", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrapped

# ----------------------------
# Template globals
# ----------------------------
@app.context_processor
def inject_globals():
    cats = sorted(list({p.get("category", "Other") for p in products}))
    username = session.get("username")
    user_obj = find_user(username) if username else None
    return {
        "categories": cats,
        "dark_mode": session.get("dark_mode", False),
        "current_user": username,
        "is_admin": bool(user_obj and user_obj.get("is_admin"))
    }

# ----------------------------
# Routes
# ----------------------------
@app.route("/")
def home():
    q = (request.args.get("q") or "").strip().lower()
    cat = request.args.get("category") or ""
    only_featured = request.args.get("featured") == "1"

    filtered = []
    for p in products:
        ok = True
        if q:
            ok = q in (p.get("name","").lower()) or q in (p.get("category","").lower())
        if ok and cat:
            ok = (p.get("category","") == cat)
        if ok and only_featured:
            ok = bool(p.get("featured", False))
        if ok:
            pi = p.copy()
            rlist = [int(x) for x in p.get("ratings", []) if str(x).isdigit()]
            pi["avg_rating"] = (sum(rlist)/len(rlist)) if rlist else None
            filtered.append(pi)
    return render_template("home.html", products=filtered)

@app.route("/product/<pid>", methods=["GET", "POST"])
def product_view(pid):
    product = find_product(pid)
    if not product:
        abort(404)
    if request.method == "POST":
        # Rating submission
        try:
            r = int(request.form.get("rating", 0))
            if 1 <= r <= 5:
                product.setdefault("ratings", []).append(r)
                sync_products()
                flash("Thanks for rating!", "success")
            else:
                flash("Rating must be 1-5", "warning")
        except Exception:
            flash("Invalid rating", "warning")
        return redirect(url_for("product_view", pid=pid))
    return render_template("product.html", product=product)

# ----------------------------
# Cart actions
# ----------------------------
@app.route("/add/<int:pid>")
def add_to_cart(pid):
    prod = find_product(pid)
    if not prod:
        flash("Product not found", "warning")
        return redirect(url_for("home"))
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True
    flash("Added to cart", "success")
    return redirect(request.referrer or url_for("home"))

@app.route("/cart")
def cart():
    cart = session.get("cart", {}) or {}
    items = []
    total = 0
    for pid_str, qty in cart.items():
        p = find_product(pid_str)
        if p:
            item = p.copy()
            item["qty"] = qty
            item["subtotal"] = int(p.get("price", 0)) * qty
            items.append(item)
            total += item["subtotal"]
    return render_template("cart.html", items=items, total=total)

@app.route("/cart/increase/<int:pid>")
def increase(pid):
    cart = session.get("cart", {}) or {}
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))

@app.route("/cart/decrease/<int:pid>")
def decrease(pid):
    cart = session.get("cart", {}) or {}
    if str(pid) in cart:
        cart[str(pid)] -= 1
        if cart[str(pid)] <= 0:
            cart.pop(str(pid), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))

@app.route("/remove/<int:pid>")
def remove(pid):
    cart = session.get("cart", {}) or {}
    cart.pop(str(pid), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "POST":
        cart = session.get("cart", {}) or {}
        if not cart:
            flash("Cart is empty", "warning")
            return redirect(url_for("cart"))
        total = 0
        for pid_str, qty in cart.items():
            p = find_product(pid_str)
            if p:
                total += int(p.get("price", 0)) * qty
        order = {
            "id": len(orders) + 1,
            "user": session.get("username"),
            "items": cart,
            "total": total,
            "created_at": datetime.utcnow().isoformat()
        }
        orders.append(order)
        sync_orders()
        session.pop("cart", None)
        session.modified = True
        flash("Order placed, thank you!", "success")
        return redirect(url_for("home"))
    return render_template("checkout.html")

# ----------------------------
# Wishlist
# ----------------------------
@app.route("/wishlist")
def wishlist_view():
    if session.get("username"):
        user = find_user(session.get("username"))
        wished = user.get("wishlist", []) if user else []
    else:
        wished = session.get("wishlist", []) or []
    items = [find_product(pid) for pid in wished if find_product(pid)]
    return render_template("wishlist.html", items=items)

@app.route("/wishlist/add/<int:pid>")
def wishlist_add(pid):
    prod = find_product(pid)
    if not prod:
        flash("Product not found", "warning")
        return redirect(url_for("home"))
    if session.get("username"):
        user = find_user(session.get("username"))
        if user:
            user.setdefault("wishlist", [])
            if pid not in user["wishlist"]:
                user["wishlist"].append(pid)
                sync_users()
    else:
        w = session.get("wishlist", []) or []
        if pid not in w:
            w.append(pid)
        session["wishlist"] = w
        session.modified = True
    flash("Added to wishlist", "success")
    return redirect(request.referrer or url_for("home"))

@app.route("/wishlist/remove/<int:pid>")
def wishlist_remove(pid):
    if session.get("username"):
        user = find_user(session.get("username"))
        if user:
            user["wishlist"] = [x for x in user.get("wishlist", []) if x != pid]
            sync_users()
    else:
        w = session.get("wishlist", []) or []
        session["wishlist"] = [x for x in w if x != pid]
        session.modified = True
    flash("Removed from wishlist", "info")
    return redirect(request.referrer or url_for("wishlist_view"))

# ----------------------------
# Auth
# ----------------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        uname = (request.form.get("username") or "").strip()
        pwd = request.form.get("password") or ""
        if not uname or not pwd:
            flash("Enter username and password", "warning")
            return redirect(url_for("signup"))
        if find_user(uname):
            flash("Username taken", "warning")
            return redirect(url_for("signup"))
        new = {"username": uname, "password": pwd, "is_admin": False, "wishlist": []}
        users.append(new)
        sync_users()
        session["username"] = uname
        session.modified = True
        flash("Signup success. Logged in.", "success")
        return redirect(url_for("home"))
    return render_template("signup.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = (request.form.get("username") or "").strip()
        pwd = request.form.get("password") or ""
        user = find_user(uname)
        if user and user.get("password") == pwd:
            session["username"] = uname
            session.modified = True
            flash("Logged in", "success")
            return redirect(request.args.get("next") or url_for("home"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    session.modified = True
    flash("Logged out", "info")
    return redirect(url_for("home"))

# ----------------------------
# Admin
# ----------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", products=products)

@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    if request.method == "POST":
        try:
            new_id = max([p.get("id", 0) for p in products] or [0]) + 1
        except Exception:
            new_id = 1
        products.append({
            "id": new_id,
            "name": request.form.get("name") or "Untitled",
            "price": int(request.form.get("price") or 0),
            "img": request.form.get("img") or "",
            "category": request.form.get("category") or "Other",
            "ratings": [],
            "featured": request.form.get("featured") == "on"
        })
        sync_products()
        flash("Product added", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_add.html")

@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    p = find_product(pid)
    if not p:
        flash("Not found", "danger")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        p["name"] = request.form.get("name") or p.get("name")
        p["price"] = int(request.form.get("price") or p.get("price", 0))
        p["img"] = request.form.get("img") or p.get("img", "")
        p["category"] = request.form.get("category") or p.get("category", "Other")
        p["featured"] = request.form.get("featured") == "on"
        sync_products()
        flash("Product updated", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", product=p)

@app.route("/admin/delete/<int:pid>")
@admin_required
def admin_delete(pid):
    global products
    products = [p for p in products if p.get("id") != pid]
    sync_products()
    flash("Deleted", "info")
    return redirect(url_for("admin_dashboard"))

# ----------------------------
# Toggle dark
# ----------------------------
@app.route("/toggle-dark")
def toggle_dark():
    session["dark_mode"] = not session.get("dark_mode", False)
    session.modified = True
    return redirect(request.referrer or url_for("home"))

# ----------------------------
# API rating (ajax)
# ----------------------------
@app.route("/api/rate/<int:pid>", methods=["POST"])
def api_rate(pid):
    p = find_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404
    try:
        r = int(request.json.get("rating", 0))
        if 1 <= r <= 5:
            p.setdefault("ratings", []).append(r)
            sync_products()
            avg = sum([int(x) for x in p.get("ratings", [])]) / len(p.get("ratings", []))
            return jsonify({"ok": True, "avg": avg})
    except Exception:
        pass
    return jsonify({"error": "invalid"}), 400

# ----------------------------
# Run
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
