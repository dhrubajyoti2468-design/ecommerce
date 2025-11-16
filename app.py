from flask import Flask, render_template, request, session, redirect, url_for, flash
import json, os
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "dhruba_secret_key_prod"  # change if you want

PRODUCTS_FILE = "products.json"
USERS_FILE = "users.json"
ORDERS_FILE = "orders.json"

# ---------------- JSON helpers ----------------
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=2)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def load_products():
    return load_json(PRODUCTS_FILE, [])

def save_products(products):
    save_json(PRODUCTS_FILE, products)

def load_users():
    return load_json(USERS_FILE, [])

def save_users(users):
    save_json(USERS_FILE, users)

def load_orders():
    return load_json(ORDERS_FILE, [])

def save_orders(orders):
    save_json(ORDERS_FILE, orders)

# ---------------- user helpers ----------------
def find_user(username):
    users = load_users()
    for u in users:
        if u.get("username") == username:
            return u
    return None

def get_categories():
    cats = set()
    for p in load_products():
        cats.add(p.get("category","Other"))
    return sorted(list(cats))

def avg_rating(product):
    r = product.get("ratings", [])
    return round(sum(r)/len(r),2) if r else None

# Inject current_user to templates
@app.context_processor
def inject():
    return dict(current_user=session.get("user"), current_role=session.get("role"))

# ---------------- routes ----------------

@app.route("/")
def home():
    q = request.args.get("q","").strip().lower()
    cat = request.args.get("category","").strip()
    products = load_products()
    for p in products:
        p["avg_rating"] = avg_rating(p)
    if cat:
        products = [p for p in products if p.get("category","").lower() == cat.lower()]
    if q:
        products = [p for p in products if q in p.get("name","").lower() or q in p.get("category","").lower()]
    categories = get_categories()
    featured = products[:4]  # top 4 as featured (you can tweak)
    return render_template("home.html", products=products, categories=categories, featured=featured, q=q, selected_category=cat)

@app.route("/product/<int:pid>")
def product(pid):
    p = next((x for x in load_products() if x["id"] == pid), None)
    if not p:
        flash("Product not found","error")
        return redirect(url_for("home"))
    p["avg_rating"] = avg_rating(p)
    return render_template("product.html", p=p)

# ---------------- auth ----------------
@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        if not username or not password:
            flash("Provide username and password","error")
            return redirect(url_for("signup"))
        if find_user(username):
            flash("Username already exists","error")
            return redirect(url_for("signup"))
        users = load_users()
        users.append({
            "username": username,
            "password": generate_password_hash(password),
            "role": "user",
            "wishlist": []
        })
        save_users(users)
        flash("Account created. Login now.","success")
        return redirect(url_for("login"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","").strip()
        user = find_user(username)
        if not user or not check_password_hash(user.get("password",""), password):
            flash("Invalid credentials","error")
            return redirect(url_for("login"))
        session["user"] = username
        session["role"] = user.get("role","user")
        flash(f"Welcome {username}","success")
        return redirect(url_for("home"))
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("role", None)
    flash("Logged out","info")
    return redirect(url_for("home"))

# ---------------- cart ----------------
@app.route("/add/<int:pid>")
def add_to_cart(pid):
    cart = session.get("cart", {})
    cart[str(pid)] = cart.get(str(pid), 0) + 1
    session["cart"] = cart
    flash("Added to cart","success")
    return redirect(request.referrer or url_for("home"))

@app.route("/cart")
def cart():
    cart = session.get("cart", {})
    products = load_products()
    cart_items = []
    total = 0
    for pid_str, qty in cart.items():
        pid = int(pid_str)
        p = next((x for x in products if x["id"]==pid), None)
        if p:
            item = p.copy()
            item["qty"] = qty
            item["subtotal"] = qty * p["price"]
            cart_items.append(item)
            total += item["subtotal"]
    return render_template("cart.html", items=cart_items, total=total)

@app.route("/cart/increase/<int:pid>")
def cart_increase(pid):
    cart = session.get("cart",{})
    cart[str(pid)] = cart.get(str(pid),0) + 1
    session["cart"] = cart; session.modified = True
    return redirect(url_for("cart"))

@app.route("/cart/decrease/<int:pid>")
def cart_decrease(pid):
    cart = session.get("cart",{})
    if str(pid) in cart:
        cart[str(pid)] -= 1
        if cart[str(pid)] <= 0:
            cart.pop(str(pid), None)
    session["cart"] = cart; session.modified = True
    return redirect(url_for("cart"))

@app.route("/remove/<int:pid>")
def cart_remove(pid):
    cart = session.get("cart",{})
    cart.pop(str(pid), None)
    session["cart"] = cart; session.modified = True
    return redirect(url_for("cart"))

# ---------------- wishlist ----------------
@app.route("/wishlist")
def wishlist():
    if "user" not in session:
        flash("Login to view wishlist","error")
        return redirect(url_for("login"))
    user = find_user(session["user"])
    prods = load_products()
    items = [p for p in prods if p["id"] in user.get("wishlist",[])]
    return render_template("wishlist.html", items=items)

@app.route("/wishlist/add/<int:pid>")
def wishlist_add(pid):
    if "user" not in session:
        flash("Login to add to wishlist","error")
        return redirect(url_for("login"))
    users = load_users()
    user = find_user(session["user"])
    if pid not in user.get("wishlist",[]):
        user.setdefault("wishlist",[]).append(pid)
        save_users(users)
        flash("Added to wishlist","success")
    return redirect(request.referrer or url_for("home"))

@app.route("/wishlist/remove/<int:pid>")
def wishlist_remove(pid):
    if "user" not in session:
        flash("Login to remove wishlist","error")
        return redirect(url_for("login"))
    users = load_users()
    user = find_user(session["user"])
    if pid in user.get("wishlist",[]):
        user["wishlist"].remove(pid)
        save_users(users)
        flash("Removed from wishlist","info")
    return redirect(request.referrer or url_for("wishlist"))

# ---------------- ratings ----------------
@app.route("/rate/<int:pid>", methods=["POST"])
def rate(pid):
    if "user" not in session:
        flash("Login to rate products","error")
        return redirect(url_for("login"))
    try:
        score = int(request.form.get("score"))
        if score < 1 or score > 5:
            raise ValueError()
    except:
        flash("Invalid rating","error")
        return redirect(request.referrer or url_for("product", pid=pid))
    prods = load_products()
    for p in prods:
        if p["id"] == pid:
            p.setdefault("ratings",[]).append(score)
            save_products(prods)
            flash("Thank you for rating","success")
            return redirect(request.referrer or url_for("product", pid=pid))
    flash("Product not found","error")
    return redirect(url_for("home"))

# ---------------- checkout & orders ----------------
@app.route("/checkout", methods=["GET","POST"])
def checkout():
    if "user" not in session:
        flash("Login to checkout","error")
        return redirect(url_for("login"))
    cart = session.get("cart",{})
    if not cart:
        flash("Cart is empty","error")
        return redirect(url_for("cart"))
    if request.method == "POST":
        name = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        address = request.form.get("address","").strip()
        city = request.form.get("city","").strip()
        pincode = request.form.get("pincode","").strip()
        prods = load_products()
        items = []
        total = 0
        for pid_str, qty in cart.items():
            pid = int(pid_str)
            p = next((x for x in prods if x["id"]==pid), None)
            if p:
                subtotal = p["price"] * qty
                total += subtotal
                items.append({"id":p["id"],"name":p["name"],"price":p["price"],"qty":qty,"subtotal":subtotal})
        orders = load_orders()
        new_order = {
            "user": session["user"],
            "items": items,
            "total": total,
            "address": {"name":name,"phone":phone,"address":address,"city":city,"pincode":pincode},
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        orders.append(new_order)
        save_orders(orders)
        session.pop("cart", None)
        flash("Order placed successfully","success")
        return redirect(url_for("orders"))
    return render_template("checkout.html")

@app.route("/orders")
def orders():
    if "user" not in session:
        flash("Login to view orders","error")
        return redirect(url_for("login"))
    all_orders = load_orders()
    user_orders = [o for o in all_orders if o["user"] == session["user"]]
    return render_template("orders.html", orders=user_orders)

# ---------------- admin (protected) ----------------
def is_admin():
    return session.get("role") == "admin"

@app.route("/admin")
def admin_dashboard():
    if not is_admin():
        flash("Admin only","error")
        return redirect(url_for("login"))
    prods = load_products()
    return render_template("admin_dashboard.html", products=prods)

@app.route("/admin/add", methods=["GET","POST"])
def admin_add():
    if not is_admin():
        flash("Admin only","error")
        return redirect(url_for("login"))
    if request.method == "POST":
        name = request.form.get("name","").strip()
        price = float(request.form.get("price","0"))
        img = request.form.get("img","").strip()
        category = request.form.get("category","").strip()
        prods = load_products()
        new_id = max([p.get("id",0) for p in prods] or [0]) + 1
        prods.append({"id":new_id,"name":name,"price":price,"img":img,"category":category,"ratings":[]})
        save_products(prods)
        flash("Product added","success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_add.html")

@app.route("/admin/edit/<int:pid>", methods=["GET","POST"])
def admin_edit(pid):
    if not is_admin():
        flash("Admin only","error")
        return redirect(url_for("login"))
    prods = load_products()
    prod = next((p for p in prods if p["id"]==pid), None)
    if not prod:
        flash("Product not found","error")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        prod["name"] = request.form.get("name","").strip()
        prod["price"] = float(request.form.get("price","0"))
        prod["img"] = request.form.get("img","").strip()
        prod["category"] = request.form.get("category","").strip()
        save_products(prods)
        flash("Product updated","success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", p=prod)

@app.route("/admin/delete/<int:pid>")
def admin_delete(pid):
    if not is_admin():
        flash("Admin only","error")
        return redirect(url_for("login"))
    prods = load_products()
    prods = [p for p in prods if p["id"] != pid]
    save_products(prods)
    flash("Product deleted","info")
    return redirect(url_for("admin_dashboard"))

# ---------------- start ----------------
if __name__ == "__main__":
    # ensure files exist with defaults
    load_products()
    load_users()
    load_orders()
    app.run(debug=True)
