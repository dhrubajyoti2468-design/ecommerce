from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify, abort
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
# JSON LOAD / SAVE HELPERS
# ----------------------------
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ----------------------------
# DEFAULT DATA
# ----------------------------
DEFAULT_PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 249999,
     "img": "https://m.media-amazon.com/images/I/51PLKwik5fL._AC_UF1000,1000_QL80_.jpg",
     "category": "Computers", "ratings": []},
    {"id": 2, "name": "Mouse", "price": 500,
     "img": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSsosymxQez36xdfSK09thwVFBpiLX4whdG3g&s",
     "category": "Accessories", "ratings": []},
]

DEFAULT_USERS = [
    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD,
     "is_admin": True, "wishlist": []}
]

DEFAULT_ORDERS = []


# ----------------------------
# LOAD DATA
# ----------------------------
products = load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
users = load_json(USERS_FILE, DEFAULT_USERS)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)


def sync_products(): save_json(PRODUCTS_FILE, products)
def sync_users(): save_json(USERS_FILE, users)
def sync_orders(): save_json(ORDERS_FILE, orders)


# ----------------------------
# HELPERS
# ----------------------------
def find_product(pid):
    for p in products:
        if int(p["id"]) == int(pid):
            return p
    return None


def find_user(username):
    for u in users:
        if u["username"] == username:
            return u
    return None


# ----------------------------
# LOGIN REQUIRED WRAPPERS
# ----------------------------
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get("username"):
            flash("Login required", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        user = find_user(session.get("username"))
        if not user or not user.get("is_admin"):
            flash("Admin only", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrap


# ----------------------------
# GLOBAL TEMPLATE VARIABLES
# ----------------------------
@app.context_processor
def inject_globals():
    categories = sorted(list({p["category"] for p in products}))
    return {
        "categories": categories,
        "dark_mode": session.get("dark_mode", False),
        "current_user": session.get("username")
    }


# ----------------------------
# ROUTES
# ----------------------------
@app.route("/")
def home():
    q = request.args.get("q", "").lower()
    cat = request.args.get("category", "")
    only_featured = request.args.get("featured") == "1"

    filtered = []
    for p in products:
        ok = True

        if q:
            ok = q in p["name"].lower() or q in p["category"].lower()

        if ok and cat:
            ok = (p["category"] == cat)

        if ok and only_featured:
            ok = p.get("featured", False)

        if ok:
            pi = p.copy()
            ratings = p.get("ratings", [])
            pi["avg_rating"] = sum(ratings) / len(ratings) if ratings else None
            filtered.append(pi)

    return render_template("home.html", products=filtered)


@app.route("/product/<pid>", methods=["GET", "POST"])
def product_view(pid):
    product = find_product(pid)
    if not product:
        abort(404)

    if request.method == "POST":
        rating = int(request.form.get("rating"))
        if 1 <= rating <= 5:
            product["ratings"].append(rating)
            sync_products()
            flash("Thanks for rating!", "success")
        return redirect(url_for("product_view", pid=pid))

    return render_template("product.html", product=product)


# ----------------------------
# CART
# ----------------------------
@app.route("/add/<int:pid>")
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    flash("Added to cart", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    items, total = [], 0

    for pid, qty in cart.items():
        prod = find_product(pid)
        if prod:
            item = prod.copy()
            item["qty"] = qty
            item["subtotal"] = qty * prod["price"]
            total += item["subtotal"]
            items.append(item)

    return render_template("cart.html", items=items, total=total)


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if request.method == "POST":
        cart = session.get("cart", {})
        if not cart:
            flash("Your cart is empty", "warning")
            return redirect(url_for("cart"))

        total = 0
        for pid, qty in cart.items():
            prod = find_product(pid)
            if prod:
                total += prod["price"] * qty

        order = {
            "id": len(orders) + 1,
            "user": session["username"],
            "items": cart,
            "total": total,
            "created_at": datetime.utcnow().isoformat()
        }

        orders.append(order)
        sync_orders()
        session.pop("cart", None)
        flash("Order placed successfully!", "success")
        return redirect(url_for("home"))

    return render_template("checkout.html")


# ----------------------------
# WISHLIST
# ----------------------------
@app.route("/wishlist")
def wishlist_view():
    if not session.get("username"):
        wished = session.get("wishlist", [])
    else:
        user = find_user(session["username"])
        wished = user.get("wishlist", [])

    items = [find_product(pid) for pid in wished if find_product(pid)]
    return render_template("wishlist.html", items=items)


@app.route("/wishlist/add/<int:pid>")
def wishlist_add(pid):
    if session.get("username"):
        user = find_user(session["username"])
        user.setdefault("wishlist", [])
        if pid not in user["wishlist"]:
            user["wishlist"].append(pid)
        sync_users()
    else:
        w = session.get("wishlist", [])
        if pid not in w:
            w.append(pid)
        session["wishlist"] = w

    flash("Added to wishlist", "success")
    return redirect(request.referrer or url_for("home"))


# ----------------------------
# AUTH
# ----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = find_user(request.form["username"])
        if user and user["password"] == request.form["password"]:
            session["username"] = user["username"]
            flash("Logged in!", "success")
            return redirect(url_for("home"))
        flash("Invalid credentials", "danger")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        uname = request.form["username"]
        pwd = request.form["password"]

        if find_user(uname):
            flash("Username taken", "warning")
            return redirect(url_for("signup"))

        users.append({
            "username": uname,
            "password": pwd,
            "is_admin": False,
            "wishlist": []
        })

        sync_users()
        session["username"] = uname
        flash("Signup successful!", "success")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out!", "info")
    return redirect(url_for("home"))


# ----------------------------
# ADMIN PANEL
# ----------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", products=products)


@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    if request.method == "POST":
        new_id = max([p["id"] for p in products]) + 1
        products.append({
            "id": new_id,
            "name": request.form["name"],
            "price": int(request.form["price"]),
            "img": request.form["img"],
            "category": request.form["category"],
            "ratings": [],
            "featured": request.form.get("featured") == "on"
        })
        sync_products()
        flash("Product added!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add.html")


@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    p = find_product(pid)
    if not p:
        flash("Product not found", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        p["name"] = request.form["name"]
        p["price"] = int(request.form["price"])
        p["img"] = request.form["img"]
        p["category"] = request.form["category"]
        p["featured"] = request.form.get("featured") == "on"

        sync_products()
        flash("Product updated!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_edit.html", product=p)


@app.route("/admin/delete/<int:pid>")
@admin_required
def admin_delete(pid):
    global products
    products = [p for p in products if p["id"] != pid]
    sync_products()
    flash("Deleted!", "info")
    return redirect(url_for("admin_dashboard"))


# ----------------------------
# DARK MODE
# ----------------------------
@app.route("/toggle-dark")
def toggle_dark():
    session["dark_mode"] = not session.get("dark_mode", False)
    return redirect(request.referrer or url_for("home"))


# ----------------------------
# API
# ----------------------------
@app.route("/api/rate/<int:pid>", methods=["POST"])
def api_rate(pid):
    p = find_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404

    r = int(request.json.get("rating", 0))
    if 1 <= r <= 5:
        p["ratings"].append(r)
        sync_products()
        avg = sum(p["ratings"]) / len(p["ratings"])
        return jsonify({"ok": True, "avg": avg})

    return jsonify({"error": "invalid"}), 400


# ----------------------------
# RUN
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
