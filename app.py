import os
from dotenv import load_dotenv
from upstash_redis import Redis
import razorpay,json
load_dotenv()
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from recommendation import get_recommendations  
redis = Redis(
    url=os.getenv("UPSTASH_REDIS_REST_URL"),
    token=os.getenv("UPSTASH_REDIS_REST_TOKEN")
)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

razorpay_client = razorpay.Client(
    auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)
)
import mysql.connector
app = Flask(__name__)
S3_BUCKET_URL ="https://dnj1c6rpjfrz9.cloudfront.net"
app.secret_key = os.getenv("SECRET_KEY")

db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

cursor = db.cursor()

def clear_product_cache():

    sorts = [
        "default",
        "low",
        "high",
        "az",
        "za"
    ]

    for sort in sorts:

        for page in range(1, 100):

            cache_key = f"products:{sort}:page:{page}"

            redis.delete(cache_key)

    print("Product cache cleared")

@app.route("/")
def home():

    sort = request.args.get("sort")
    page = request.args.get("page", 1, type=int)
    per_page = 6
    offset = (page - 1) * per_page
    
    cache_key = f"products:{sort or 'default'}:page:{page}"
    
   
    cached_products = redis.get(cache_key)

    if cached_products:
        products = json.loads(cached_products)

        print("Redis CACHE HIT")

    else:
        print("Redis CACHE MISS")

        sql = "SELECT * FROM products"

        if sort == "low":
            sql += " ORDER BY price ASC"

        elif sort == "high":
            sql += " ORDER BY price DESC"

        elif sort == "az":
            sql += " ORDER BY name ASC"

        elif sort == "za":
            sql += " ORDER BY name DESC"

        sql += " LIMIT %s OFFSET %s"

        cursor.execute(sql, (per_page, offset))

        products = cursor.fetchall()

        # Convert database result to JSON-compatible format
        products = [
            list(product)
            for product in products
        ]

        # Store in Redis for 5 minutes
        redis.set(
            cache_key,
            json.dumps(products, default=str),
            ex=300
        )

    cursor.execute("SELECT COUNT(*) FROM products")

    total_products = cursor.fetchone()[0]

    total_pages = (total_products + per_page - 1) // per_page
    # ML recommendations
    recommendations = []

    if "user_id" in session:

        recommendations = get_recommendations(
            session["user_id"],
            db
        )

    else:

        cursor.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 5
        """)

        recommendations = cursor.fetchall()

    return render_template(
      "index.html",
      products=products,
      recommendations=recommendations,
      s3_bucket=S3_BUCKET_URL,
      page=page,
      total_pages=total_pages,
      sort=sort

    )

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        sql = """
        SELECT * FROM users
        WHERE email=%s
        """

        cursor.execute(sql, (email,))
        user = cursor.fetchone()

        if user and check_password_hash(user[3], password):

            session["user_id"] = user[0]
            session["user_name"] = user[1]
            session["is_admin"] = user[5]

            flash("Login successful!", "success")

            return redirect("/")

        else:

            flash("Invalid email or password.", "danger")

            return redirect("/login")

    return render_template("login.html")

@app.route("/admin")
def admin():

    if "user_id" not in session:
        flash("Please login to access the admin panel.", "warning")
        return redirect("/login")

    if not session.get("is_admin"):
        flash("Access denied. Admin privileges are required.", "danger")
        return redirect("/")

    # Total Users
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]

    # Total Products
    cursor.execute("SELECT COUNT(*) FROM products")
    total_products = cursor.fetchone()[0]

    # Total Orders
    cursor.execute("SELECT COUNT(*) FROM orders")
    total_orders = cursor.fetchone()[0]

    # Total Revenue
    cursor.execute("SELECT SUM(total_amount) FROM orders")
    revenue = cursor.fetchone()[0]

    if revenue is None:
        revenue = 0

    return render_template(
        "admin.html",
        total_users=total_users,
        total_products=total_products,
        total_orders=total_orders,
        revenue=revenue
    )

@app.route("/logout")
def logout():

    session.clear()

    flash("You have been logged out successfully.", "success")

    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        password_hash = generate_password_hash(password)

        sql = """
        INSERT INTO users(name, email, password)
        VALUES (%s, %s, %s)
        """

        values = (name, email, password_hash)

        cursor.execute(sql, values)
        db.commit()

        flash("Account created successfully! Please login.", "success")

        return redirect("/login")

    return render_template("register.html")

@app.route("/increase-cart/<int:cart_id>")
def increase_cart(cart_id):

    if "user_id" not in session:
        return redirect("/login")

    # Get current quantity and stock
    cursor.execute("""
        SELECT cart.quantity, products.stock
        FROM cart
        JOIN products
        ON cart.product_id = products.id
        WHERE cart.id=%s
    """, (cart_id,))

    item = cursor.fetchone()

    if item:

        quantity = item[0]
        stock = item[1]

        if quantity < stock:

            cursor.execute("""
                UPDATE cart
                SET quantity = quantity + 1
                WHERE id=%s
            """, (cart_id,))

            db.commit()

    return redirect("/cart")

@app.route("/decrease-cart/<int:cart_id>")
def decrease_cart(cart_id):

    if "user_id" not in session:
        return redirect("/login")

    cursor.execute(
        "SELECT quantity FROM cart WHERE id=%s",
        (cart_id,)
    )

    quantity = cursor.fetchone()[0]

    if quantity > 1:

        cursor.execute("""
            UPDATE cart
            SET quantity = quantity - 1
            WHERE id=%s
        """, (cart_id,))

    else:

        cursor.execute(
            "DELETE FROM cart WHERE id=%s",
            (cart_id,)
        )

    db.commit()

    return redirect("/cart")

@app.route("/add-product", methods=["GET", "POST"])
def add_product():

    
    if not session.get("is_admin"):
        return "Access Denied", 403

    if request.method == "POST":

        name = request.form["name"]
        description = request.form["description"]
        price = request.form["price"]
        stock = request.form["stock"]
        image = request.form["image"]

        cursor.execute(
            """
            INSERT INTO products
            (name, description, price, image, stock)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, description, price, image, stock)
        )

        db.commit()
        
        clear_product_cache()
        return redirect("/admin-products")

    return render_template("add_product.html")


@app.route("/admin-products")
def admin_products():
   if "user_id" not in session:
    return redirect("/login")

   if not session.get("is_admin"):
     return "Access Denied", 403
   
   cursor.execute(
        "SELECT * FROM products"
    )

   products = cursor.fetchall()

   return render_template(
        "admin_product.html",
        products=products
    )

@app.route("/delete-product/<int:id>")
def delete_product(id):

    sql = """
    DELETE FROM products
    WHERE id=%s
    """

    cursor.execute(sql, (id,))

    db.commit()
    clear_product_cache()
    return redirect("/admin-products")

@app.route("/edit-product/<int:id>", methods=["GET", "POST"])
def edit_product(id):

    if not session.get("is_admin"):
        return "Access Denied", 403

    if request.method == "POST":

        name = request.form["name"]
        description = request.form["description"]
        price = request.form["price"]
        stock = request.form["stock"]
        image = request.form["image"]

        sql = """
        UPDATE products
        SET
            name=%s,
            description=%s,
            price=%s,
            image=%s,
            stock=%s
        WHERE id=%s
        """

        values = (
            name,
            description,
            price,
            image,
            stock,
            id
        )

        cursor.execute(sql, values)

        db.commit()
        clear_product_cache()
        return redirect("/admin-products")

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (id,)
    )

    product = cursor.fetchone()

    return render_template(
        "edit_product.html",
        product=product
    )

@app.route("/users")
def users():

    if "user_id" not in session:
        return redirect("/login")

    if not session.get("is_admin"):
       if not session.get("is_admin"):
           flash("Access denied. Admin privileges are required.", "danger")
           return redirect("/")

    cursor.execute(
        "SELECT * FROM users"
    )

    users = cursor.fetchall()

    return render_template(
        "users.html",
        users=users
    )

@app.route("/edit-user/<int:user_id>", methods=["GET", "POST"])
def edit_user(user_id):

    # Check login
    if "user_id" not in session:
        flash("Please login to access this page.", "warning")
        return redirect("/login")

    # Check admin
    if not session.get("is_admin"):
        flash("Access denied. Admin privileges are required.", "danger")
        return redirect("/")

    # Get existing user
    cursor.execute(
        "SELECT * FROM users WHERE id=%s",
        (user_id,)
    )

    user = cursor.fetchone()

    if not user:
        flash("User not found.", "danger")
        return redirect("/users")

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        is_admin = request.form.get("is_admin", 0)

        cursor.execute(
            """
            UPDATE users
            SET name=%s, email=%s, is_admin=%s
            WHERE id=%s
            """,
            (name, email, is_admin, user_id)
        )

        db.commit()

        flash("User updated successfully!", "success")

        return redirect("/users")

    return render_template(
        "edit_user.html",
        user=user
    )

@app.route("/add-to-cart/<int:product_id>")
def add_to_cart(product_id):

    if "user_id" not in session:
       return redirect("/login")

    user_id = session["user_id"]

    sql = """
    INSERT INTO cart
    (user_id, product_id)
    VALUES (%s,%s)
    """

    values = (
        user_id,
        product_id
    )

    cursor.execute(sql, values)

    db.commit()

    return redirect("/")

@app.route("/cart")
def cart():

    if "user_id" not in session:
        return redirect("/login")

    sql = """
    SELECT
        cart.id,
        products.name,
        products.price,
        cart.quantity,
        (products.price * cart.quantity),
        products.image
    FROM cart
    JOIN products
    ON cart.product_id = products.id
    WHERE cart.user_id = %s
    """

    cursor.execute(sql, (session["user_id"],))

    items = cursor.fetchall()
    total = sum(item[4] for item in items)
    return render_template(
    "cart.html",
    items=items,
    total=total

    )

@app.route(
    "/update-cart/<int:id>",
    methods=["POST"]
)
def update_cart(id):

    quantity = request.form["quantity"]

    cursor.execute(
        """
        UPDATE cart
        SET quantity=%s
        WHERE id=%s
        """,
        (quantity, id)
    )

    db.commit()

    return redirect("/cart")

@app.route("/remove-cart/<int:id>")
def remove_cart(id):

    sql = """
    DELETE FROM cart
    WHERE id=%s
    """

    cursor.execute(
        sql,
        (id,)
    )

    db.commit()

    return redirect("/cart")

@app.route("/delete-user/<int:id>")
def delete_user(id):

    cursor.execute(
        "DELETE FROM users WHERE id=%s",
        (id,)
    )

    db.commit()

    return redirect("/users")

@app.route("/checkout", methods=["GET", "POST"])
def checkout():

    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]

    
    cursor.execute("""
        SELECT
            products.id,
            products.price,
            cart.quantity
        FROM cart
        JOIN products
        ON cart.product_id = products.id
        WHERE cart.user_id=%s
    """, (user_id,))

    cart_items = cursor.fetchall()

    
    if not cart_items:
        flash("Your cart is empty.", "warning")
        return redirect("/cart")

    total_amount = 0

    
    for item in cart_items:

        cursor.execute(
            "SELECT stock FROM products WHERE id=%s",
            (item[0],)
        )

        stock = cursor.fetchone()[0]

        if item[2] > stock:
            flash(
                f"Only {stock} item(s) available in stock.",
                "danger"
            )
            return redirect("/cart")

        total_amount += item[1] * item[2]

    
    amount_paise = int(total_amount * 100)

    if request.method == "POST":

        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "payment_capture": 1
        })

        return render_template(
            "checkout.html",
            razorpay_key=RAZORPAY_KEY_ID,
            razorpay_order_id=razorpay_order["id"],
            amount=amount_paise
        )

    return render_template(
        "checkout.html",
        razorpay_key=RAZORPAY_KEY_ID,
        razorpay_order_id=None,
        amount=amount_paise
    )

@app.route("/payment-success", methods=["POST"])
def payment_success():

    if "user_id" not in session:
        return redirect("/login")

    payment_id = request.form.get("razorpay_payment_id")
    razorpay_order_id = request.form.get("razorpay_order_id")
    signature = request.form.get("razorpay_signature")

    try:

        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": payment_id,
            "razorpay_signature": signature
        })

    except Exception:

        flash("Payment verification failed.", "danger")
        return redirect("/checkout")

    user_id = session["user_id"]

    # Get cart again after successful payment
    cursor.execute("""
        SELECT
            products.id,
            products.price,
            cart.quantity
        FROM cart
        JOIN products
        ON cart.product_id = products.id
        WHERE cart.user_id=%s
    """, (user_id,))

    cart_items = cursor.fetchall()

    if not cart_items:
        flash("Cart is empty.", "warning")
        return redirect("/")

    total_amount = 0

    # Check stock again
    for item in cart_items:

        cursor.execute(
            "SELECT stock FROM products WHERE id=%s",
            (item[0],)
        )

        stock = cursor.fetchone()[0]

        if item[2] > stock:
            flash(
                f"Only {stock} item(s) available in stock.",
                "danger"
            )
            return redirect("/cart")

        total_amount += item[1] * item[2]

    # Create CloudCart order
    cursor.execute(
        """
        INSERT INTO orders
        (user_id, total_amount)
        VALUES (%s, %s)
        """,
        (user_id, total_amount)
    )

    order_id = cursor.lastrowid

    # Save order items and reduce stock
    for item in cart_items:

        cursor.execute(
            """
            INSERT INTO order_items
            (
                order_id,
                product_id,
                quantity,
                price
            )
            VALUES (%s,%s,%s,%s)
            """,
            (
                order_id,
                item[0],
                item[2],
                item[1]
            )
        )

        cursor.execute(
            """
            UPDATE products
            SET stock = stock - %s
            WHERE id = %s
            """,
            (
                item[2],
                item[0]
            )
        )

    # Clear cart
    cursor.execute(
        """
        DELETE FROM cart
        WHERE user_id=%s
        """,
        (user_id,)
    )

    db.commit()
    clear_product_cache()
    flash("Payment successful! Order placed successfully.", "success")

    return redirect("/order-success")

@app.route("/order-success")
def order_success():

    if "user_id" not in session:
        return redirect("/login")

    return render_template("order_success.html")

@app.route("/my-orders")
def my_orders():

    if "user_id" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT
            orders.id,
            products.name,
            products.image,
            order_items.quantity,
            order_items.price,
            orders.total_amount,
            orders.order_date
        FROM orders
        JOIN order_items
            ON orders.id = order_items.order_id
        JOIN products
            ON order_items.product_id = products.id
        WHERE orders.user_id = %s
        ORDER BY orders.id DESC
    """, (session["user_id"],))

    orders = cursor.fetchall()

    return render_template(
        "my_orders.html",
        orders=orders
    )

@app.route("/search")
def search():

    keyword = request.args.get("query")

    cursor.execute(
        """
        SELECT *
        FROM products
        WHERE name LIKE %s
        """,
        ("%" + keyword + "%",)
    )

    products = cursor.fetchall()

    return render_template(
        "index.html",
        products=products
    )

@app.route("/product/<int:product_id>")
def product_details(product_id):

    cursor.execute(
        "SELECT * FROM products WHERE id=%s",
        (product_id,)
    )

    product = cursor.fetchone()

    return render_template(
        "product_details.html",
        product=product,
        s3_bucket=S3_BUCKET_URL
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)