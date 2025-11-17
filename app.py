from flask import (
    Flask, render_template, session, redirect,
    url_for, request, flash, jsonify, abort
)
import json, os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dhruba_secret_key_production_safe"

# -------------------- FILE PATHS --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")

ADMIN_USERNAME = "dhruba"
ADMIN_PASSWORD = "00000000"

# -------------------- JSON HELPERS --------------------
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


# -------------------- INITIAL DEFAULTS --------------------
DEFAULT_USERS = [
    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "is_admin": True, "wishlist": []}
]

DEFAULT_ORDERS = []

# If your products.json already has the big list, it will load it automatically.
DEFAULT_PRODUCTS = []

products = load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
users = load_json(USERS_FILE, DEFAULT_USERS)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)


def sync_products():
    save_json(PRODUCTS_FILE, products)


def sync_users():
    save_json(USERS_FILE, users)


def sync_orders():
    save_json(ORDERS_FILE, orders)


# -------------------- HELPERS --------------------
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


def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get("username"):
            flash("Login required.", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        uname = session.get("username")
        usr = find_user(uname)
        if not usr or not usr.get("is_admin"):
            flash("Admin access only.", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrap


# -------------------- GLOBAL TEMPLATE VARIABLES --------------------
@app.context_processor
def inject_global_data():
    categories = sorted({p.get("category", "Other") for p in products})
    return {
        "categories": categories,
        "dark_mode": session.get("dark_mode", False),
        "current_user": session.get("username")
    }


# -------------------- HOME --------------------
@app.route("/")
def home():
    q = request.args.get("q", "").lower().strip()
    cat = request.args.get("category", "")
    featured = request.args.get("featured", "") == "1"

    out = []

    for p in products:
        ok = True

        if q and (q not in p["name"].lower() and q not in p["category"].lower()):
            ok = False

        if ok and cat and p["category"] != cat:
            ok = False

        if ok and featured and not p.get("featured", False):
            ok = False

        if ok:
            r = p.get("ratings", [])
            avg = sum(r) / len(r) if r else None
            pp = p.copy()
            pp["avg_rating"] = avg
            out.append(pp)

    return render_template("home.html", products=out)


# -------------------- PRODUCT PAGE --------------------
@app.route("/product/<int:pid>", methods=["GET", "POST"])
def product_view(pid):
    product = find_product(pid)
    if not product:
        abort(404)

    if request.method == "POST":
        try:
            rating = int(request.form.get("rating"))
            if 1 <= rating <= 5:
                product.setdefault("ratings", []).append(rating)
                sync_products()
                flash("Thanks for the rating!", "success")
        except:
            flash("Invalid rating.", "warning")

        return redirect(url_for("product_view", pid=pid))

    return render_template("product.html", product=product)


# -------------------- CART --------------------
@app.route("/add/<int:pid>")
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True

    # if guest → redirect to login first
    if not session.get("username"):
        flash("Login required to use Cart.", "warning")
        return redirect(url_for("login"))

    flash("Added to cart!", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart")
@login_required
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0

    for pid_str, qty in cart.items():
        p = find_product(int(pid_str))
        if not p:
            continue
        item = p.copy()
        item["qty"] = qty
        item["subtotal"] = qty * p["price"]
        items.append(item)
        total += item["subtotal"]

    return render_template("cart.html", items=items, total=total)


@app.route("/cart/increase/<int:pid>")
@login_required
def increase(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/cart/decrease/<int:pid>")
@login_required
def decrease(pid):
    cart = session.get("cart", {})
    if str(pid) in cart:
        cart[str(pid)] -= 1
        if cart[str(pid)] <= 0:
            cart.pop(str(pid))
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/remove/<int:pid>")
@login_required
def remove(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    if request.method == "POST":
        cart = session.get("cart", {})
        if not cart:
            flash("Cart empty!", "warning")
            return redirect(url_for("cart"))

        total = 0
        for pid, qty in cart.items():
            p = find_product(int(pid))
            if p:
                total += p["price"] * qty

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


# -------------------- WISHLIST --------------------
@app.route("/wishlist")
@login_required
def wishlist_view():
    u = find_user(session["username"])
    w = u.get("wishlist", []) if u else []
    items = [find_product(pid) for pid in w if find_product(pid)]
    return render_template("wishlist.html", items=items)


@app.route("/wishlist/add/<int:pid>")
@login_required
def wishlist_add(pid):
    u = find_user(session["username"])
    if u:
        if pid not in u["wishlist"]:
            u["wishlist"].append(pid)
            sync_users()
    flash("Added to wishlist!", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/wishlist/remove/<int:pid>")
@login_required
def wishlist_remove(pid):
    u = find_user(session["username"])
    if u:
        u["wishlist"] = [x for x in u["wishlist"] if x != pid]
        sync_users()
    flash("Removed from wishlist.", "info")
    return redirect(url_for("wishlist_view"))


# -------------------- AUTH --------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        uname = request.form.get("username").strip()
        pwd = request.form.get("password")

        if not uname or not pwd:
            flash("Enter all fields.", "warning")
            return redirect(url_for("signup"))

        if find_user(uname):
            flash("Username already exists.", "danger")
            return redirect(url_for("signup"))

        users.append({
            "username": uname,
            "password": pwd,
            "is_admin": False,
            "wishlist": []
        })

        sync_users()
        session["username"] = uname
        flash("Signup success.", "success")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username").strip()
        pwd = request.form.get("password")

        user = find_user(uname)
        if user and user["password"] == pwd:
            session["username"] = uname
            flash("Logged in.", "success")
            return redirect(request.args.get("next") or url_for("home"))

        flash("Invalid credentials.", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out.", "info")
    return redirect(url_for("home"))


# -------------------- ADMIN --------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", products=products)


@app.route("/admin/add", methods=["GET", "POST"])
@admin_required
def admin_add():
    if request.method == "POST":
        name = request.form.get("name")
        price = int(request.form.get("price"))
        img = request.form.get("img")
        category = request.form.get("category")
        featured = request.form.get("featured") == "on"

        new_id = max([p["id"] for p in products] or [0]) + 1

        p = {
            "id": new_id,
            "name": name,
            "price": price,
            "img": img,
            "category": category,
            "ratings": [],
            "featured": featured
        }

        products.append(p)
        sync_products()
        flash("Product added!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_add.html")


@app.route("/admin/edit/<int:pid>", methods=["GET", "POST"])
@admin_required
def admin_edit(pid):
    p = find_product(pid)
    if not p:
        flash("Product not found.", "danger")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        p["name"] = request.form.get("name")
        p["price"] = int(request.form.get("price"))
        p["img"] = request.form.get("img")
        p["category"] = request.form.get("category")
        p["featured"] = request.form.get("featured") == "on"

        sync_products()
        flash("Product updated.", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_edit.html", product=p)


@app.route("/admin/delete/<int:pid>")
@admin_required
def admin_delete(pid):
    global products
    products = [p for p in products if p["id"] != pid]
    sync_products()
    flash("Deleted.", "info")
    return redirect(url_for("admin_dashboard"))


# -------------------- DARK MODE --------------------
@app.route("/toggle-dark")
def toggle_dark():
    session["dark_mode"] = not session.get("dark_mode", False)
    session.modified = True
    return redirect(request.referrer or url_for("home"))


# -------------------- RUN --------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)
