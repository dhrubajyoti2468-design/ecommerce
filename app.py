from flask import Flask, render_template, session, redirect, url_for, request, flash, jsonify
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

def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

DEFAULT_PRODUCTS = [
    {"id": 1, "name": "Laptop", "price": 249999, "img": "https://m.media-amazon.com/images/I/51PLKwik5fL._AC_UF1000,1000_QL80_.jpg", "category": "Computers", "ratings": [], "featured": True},
    {"id": 2, "name": "Mouse", "price": 500, "img": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcSsosymxQez36xdfSK09thwVFBpiLX4whdG3g&s", "category": "Accessories", "ratings": [], "featured": False},
    {"id": 3, "name": "Keyboard", "price": 1500, "img": "https://www.bbassets.com/media/uploads/p/l/40195886_2-dell-kb216-multimedia-keyboard-wired.jpg", "category": "Accessories", "ratings": [], "featured": False},
    {"id": 4, "name": "Headphones", "price": 99999, "img": "https://images.unsplash.com/photo-1517336714731-489689fd1ca8", "category": "Audio", "ratings": [], "featured": False}
]

DEFAULT_USERS = [
    {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD, "is_admin": True, "wishlist": []}
]

DEFAULT_ORDERS = []

products = load_json(PRODUCTS_FILE, DEFAULT_PRODUCTS)
users = load_json(USERS_FILE, DEFAULT_USERS)
orders = load_json(ORDERS_FILE, DEFAULT_ORDERS)

def sync_products(): save_json(PRODUCTS_FILE, products)
def sync_users(): save_json(USERS_FILE, users)
def sync_orders(): save_json(ORDERS_FILE, orders)

def find_product(pid):
    for p in products:
        if int(p.get("id")) == int(pid):
            return p
    return None

def find_user(username):
    for u in users:
        if u.get("username") == username:
            return u
    return None

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            flash("Login required", "warning")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("username"):
            flash("Admin login required", "warning")
            return redirect(url_for("login"))
        user = find_user(session.get("username"))
        if not user or not user.get("is_admin"):
            flash("Admin required", "danger")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return wrapped

@app.context_processor
def inject_globals():
    cats = sorted(list({p.get("category","Other") for p in products}))
    return {"categories": cats, "dark_mode": session.get("dark_mode", False), "current_user": session.get("username")}

@app.route("/")
def home():
    q = request.args.get("q", "").strip().lower()
    cat = request.args.get("category", "")
    only_featured = request.args.get("featured", "") == "1"

    filtered = []
    for p in products:
        ok = True
        if q:
            ok = q in p.get("name","").lower() or q in p.get("category","").lower()
        if ok and cat:
            ok = p.get("category","") == cat
        if ok and only_featured:
            ok = p.get("featured", False) is True
        if ok:
            rlist = p.get("ratings", [])
            avg = (sum(rlist)/len(rlist)) if rlist else None
            pi = p.copy()
            pi["avg_rating"] = avg
            filtered.append(pi)
    return render_template("home.html", products=filtered)

@app.route("/product/<int:pid>", methods=["GET","POST"])
def product(pid):
    p = find_product(pid)
    if not p:
        flash("Product not found", "danger")
        return redirect(url_for("home"))
    if request.method == "POST":
        # rating
        try:
            rating = int(request.form.get("rating", 0))
            if 1 <= rating <= 5:
                p.setdefault("ratings", []).append(rating)
                sync_products()
                flash("Thanks for rating!", "success")
            else:
                flash("Rating must be 1-5", "warning")
        except Exception:
            flash("Invalid rating", "warning")
        return redirect(url_for("product", pid=pid))
    return render_template("product.html", product=p)

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
    for pid_str, qty in cart.items():
        p = find_product(int(pid_str))
        if p:
            item = p.copy()
            item["qty"] = qty
            item["subtotal"] = qty * int(p.get("price",0))
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
            cart.pop(str(pid), None)
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

@app.route("/checkout", methods=["GET","POST"])
def checkout():
    if request.method == "POST":
        cart = session.get("cart", {})
        if not cart:
            flash("Cart empty", "warning")
            return redirect(url_for("cart"))
        total = 0
        for pid, qty in cart.items():
            prod = find_product(int(pid))
            if prod:
                total += int(prod.get("price",0)) * qty
        order = {"id": len(orders)+1, "user": session.get("username"), "items": cart, "total": total, "created_at": datetime.utcnow().isoformat()}
        orders.append(order)
        sync_orders()
        session.pop("cart", None)
        flash("Order placed, thank you!", "success")
        return redirect(url_for("home"))
    return render_template("checkout.html")

@app.route("/wishlist")
def wishlist_view():
    wishlist = []
    if session.get("username"):
        user = find_user(session["username"])
        wishlist = user.get("wishlist", []) if user else []
    else:
        wishlist = session.get("wishlist", [])
    items = [find_product(pid) for pid in wishlist if find_product(pid)]
    return render_template("wishlist.html", items=items)

@app.route("/wishlist/add/<int:pid>")
def wishlist_add(pid):
    if session.get("username"):
        user = find_user(session["username"])
        if user:
            user.setdefault("wishlist", [])
            if pid not in user["wishlist"]:
                user["wishlist"].append(pid)
                sync_users()
    else:
        w = session.get("wishlist", [])
        if pid not in w:
            w.append(pid)
            session["wishlist"] = w
            session.modified = True
    flash("Added to wishlist", "success")
    return redirect(request.referrer or url_for("home"))

@app.route("/wishlist/remove/<int:pid>")
def wishlist_remove(pid):
    if session.get("username"):
        user = find_user(session["username"])
        if user:
            user["wishlist"] = [x for x in user.get("wishlist",[]) if x!=pid]
            sync_users()
    else:
        w = session.get("wishlist", [])
        session["wishlist"] = [x for x in w if x!=pid]
        session.modified = True
    flash("Removed from wishlist", "info")
    return redirect(request.referrer or url_for("wishlist_view"))

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        uname = request.form.get("username","").strip()
        pwd = request.form.get("password","")
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
        flash("Signup success. Logged in.", "success")
        return redirect(url_for("home"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        uname = request.form.get("username","").strip()
        pwd = request.form.get("password","")
        user = find_user(uname)
        if user and user.get("password") == pwd:
            session["username"] = uname
            flash("Logged in", "success")
            return redirect(request.args.get("next") or url_for("home"))
        flash("Invalid credentials", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("username", None)
    flash("Logged out", "info")
    return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html", products=products)

@app.route("/admin/add", methods=["GET","POST"])
@admin_required
def admin_add():
    if request.method == "POST":
        name = request.form.get("name")
        price = int(request.form.get("price") or 0)
        img = request.form.get("img")
        category = request.form.get("category") or "Other"
        featured = request.form.get("featured") == "on"
        new_id = max([p["id"] for p in products] or [0]) + 1
        new_p = {"id": new_id, "name": name, "price": price, "img": img, "category": category, "ratings": [], "featured": featured}
        products.append(new_p)
        sync_products()
        flash("Product added", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_add.html")

@app.route("/admin/edit/<int:pid>", methods=["GET","POST"])
@admin_required
def admin_edit(pid):
    p = find_product(pid)
    if not p:
        flash("Not found", "danger")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        p["name"] = request.form.get("name")
        p["price"] = int(request.form.get("price") or 0)
        p["img"] = request.form.get("img")
        p["category"] = request.form.get("category")
        p["featured"] = request.form.get("featured") == "on"
        sync_products()
        flash("Product updated", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", product=p)

@app.route("/admin/delete/<int:pid>")
@admin_required
def admin_delete(pid):
    global products
    products[:] = [p for p in products if p["id"] != pid]
    sync_products()
    flash("Deleted", "info")
    return redirect(url_for("admin_dashboard"))

@app.route("/toggle-dark")
def toggle_dark():
    session["dark_mode"] = not session.get("dark_mode", False)
    session.modified = True
    return redirect(request.referrer or url_for("home"))

@app.route("/api/rate/<int:pid>", methods=["POST"])
def api_rate(pid):
    p = find_product(pid)
    if not p:
        return jsonify({"error":"not found"}), 404
    try:
        r = int(request.json.get("rating"))
        if 1 <= r <= 5:
            p.setdefault("ratings", []).append(r)
            sync_products()
            return jsonify({"ok": True, "avg": sum(p["ratings"])/len(p["ratings"])})
    except:
        pass
    return jsonify({"error":"invalid"}), 400

if __name__ == "__main__":
    # local dev
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
