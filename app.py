from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify, abort
import json, os
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dhruba_secret_key_change_this"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_FILE = os.path.join(BASE_DIR, "products.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
ORDERS_FILE = os.path.join(BASE_DIR, "orders.json")

# Admin login
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


# -------------------- DEFAULT DATA --------------------
DEFAULT_PRODUCTS = [
    # keep your 30-item big product list unchanged
]

DEFAULT_USERS = [
    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "is_admin": True, "wishlist": []}
]

DEFAULT_ORDERS = []

products = load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
users = load_json(USERS_FILE, DEFAULT_USERS)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)


# -------------------- SYNC HELPERS --------------------
def sync_products(): save_json(PRODUCTS_FILE, products)
def sync_users(): save_json(USERS_FILE, users)
def sync_orders(): save_json(ORDERS_FILE, orders)


# -------------------- FINDERS --------------------
def find_product(pid):
    pid = int(pid)
    for p in products:
        if int(p["id"]) == pid:
            return p
    return None


def find_user(username):
    for u in users:
        if u["username"] == username:
            return u
    return None


# -------------------- GLOBALS TO JINJA --------------------
@app.context_processor
def inject_globals():
    categories = sorted({p.get("category", "Other") for p in products})
    return {
        "categories": categories,
        "dark_mode": session.get("dark_mode", False),
        "current_user": session.get("username"),
        "find_user": find_user,            # FIXED
        "find_product": find_product       # FIXED
    }


# -------------------- AUTH DECORATORS --------------------
def login_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if not session.get("username"):
            flash("Login required", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrap


def admin_required(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        user = find_user(session.get("username"))
        if not user or not user.get("is_admin"):
            flash("Admin access only", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrap


# -------------------- ROUTES --------------------

@app.route("/")
def home():
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("category", "")
    featured = request.args.get("featured") == "1"

    filtered = []

    for p in products:
        ok = True

        if q:
            ok = q in p["name"].lower() or q in p["category"].lower()

        if ok and cat:
            ok = p["category"] == cat

        if ok and featured:
            ok = p.get("featured", False) is True

        if ok:
            ratings = p.get("ratings", [])
            avg = sum(ratings) / len(ratings) if ratings else None
            copy_p = p.copy()
            copy_p["avg_rating"] = avg
            filtered.append(copy_p)

    return render_template("home.html", products=filtered)


@app.route("/product/<int:pid>", methods=["GET", "POST"])
def product_view(pid):
    product = find_product(pid)
    if not product:
        abort(404)

    if request.method == "POST":
        rating = int(request.form.get("rating", 0))
        if 1 <= rating <= 5:
            product.setdefault("ratings", []).append(rating)
            sync_products()
            flash("Thanks for rating!", "success")
        return redirect(url_for('product_view', pid=pid))

    return render_template("product.html", product=product)


@app.route("/add/<int:pid>")
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True
    flash("Added to cart", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    items = []
    total = 0

    for pid, qty in cart.items():
        product = find_product(pid)
        if product:
            item = product.copy()
            item["qty"] = qty
            item["subtotal"] = qty * product["price"]
            items.append(item)
            total += item["subtotal"]

    return render_template("cart.html", items=items, total=total)


@app.route("/cart/increase/<int:pid>")
def increase(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/cart/decrease/<int:pid>")
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
def remove(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    session.modified = True
    return redirect(url_for("cart"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "POST":
        cart = session.get("cart", {})
        if not cart:
            flash("Your cart is empty.", "warning")
            return redirect(url_for("cart"))

        total = 0
        for pid, qty in cart.items():
            p = find_product(pid)
            if p:
                total += p["price"] * qty

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
        flash("Order placed successfully!", "success")
        return redirect(url_for("home"))

    return render_template("checkout.html")


# -------------------- WISHLIST --------------------

@app.route("/wishlist")
def wishlist_view():
    wishlist_items = []

    if session.get("username"):
        user = find_user(session["username"])
        plist = user.get("wishlist", [])
    else:
        plist = session.get("wishlist", [])

    wishlist_items = [find_product(pid) for pid in plist if find_product(pid)]

    return render_template("wishlist.html", items=wishlist_items)


@app.route("/wishlist/add/<int:pid>")
def wishlist_add(pid):
    if session.get("username"):
        user = find_user(session["username"])
        if pid not in user["wishlist"]:
            user["wishlist"].append(pid)
            sync_users()
    else:
        w = session.get("wishlist", [])
        if pid not in w:
            w.append(pid)
        session["wishlist"] = w
    flash("Added to wishlist!", "success")
    return redirect(request.referrer or url_for("home"))


@app.route("/wishlist/remove/<int:pid>")
def wishlist_remove(pid):
    if session.get("username"):
        user = find_user(session["username"])
        user["wishlist"] = [x for x in user["wishlist"] if x != pid]
        sync_users()
    else:
        w = session.get("wishlist", [])
        session["wishlist"] = [x for x in w if x != pid]
    flash("Removed!", "info")
    return redirect(request.referrer or url_for("wishlist_view"))


# -------------------- USER AUTH --------------------

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        u = request.form.get("username").strip()
        p = request.form.get("password")

        if not u or not p:
            flash("Enter username & password.", "warning")
            return redirect(url_for("signup"))

        if find_user(u):
            flash("Username already exists.", "warning")
            return redirect(url_for("signup"))

        users.append({"username": u, "password": p, "is_admin": False, "wishlist": []})
        sync_users()

        session["username"] = u
        flash("Signup successful!", "success")
        return redirect(url_for("home"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form.get("username")
        p = request.form.get("password")

        user = find_user(u)
        if user and user["password"] == p:
            session["username"] = u
            flash("Logged in!", "success")
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
        name = request.form["name"]
        price = int(request.form["price"])
        img = request.form["img"]
        cat = request.form["category"]
        featured = request.form.get("featured") == "on"

        new_id = max([p["id"] for p in products] or [0]) + 1

        products.append({
            "id": new_id,
            "name": name,
            "price": price,
            "img": img,
            "category": cat,
            "ratings": [],
            "featured": featured
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

        flash("Updated!", "success")
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


# -------------------- DARK MODE --------------------

@app.route("/toggle-dark")
def toggle_dark():
    session["dark_mode"] = not session.get("dark_mode", False)
    session.modified = True
    return redirect(request.referrer or url_for("home"))


# -------------------- API --------------------

@app.route("/api/rate/<int:pid>", methods=["POST"])
def api_rate(pid):
    p = find_product(pid)
    if not p:
        return jsonify({"error": "not found"}), 404

    try:
        rating = int(request.json.get("rating"))
        if 1 <= rating <= 5:
            p.setdefault("ratings", []).append(rating)
            sync_products()
            return jsonify({"ok": True})
    except:
        pass

    return jsonify({"error": "invalid"}), 400


# -------------------- RUN --------------------

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
