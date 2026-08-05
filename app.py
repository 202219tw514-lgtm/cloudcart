import os
from dotenv import load_dotenv

load_dotenv()
from flask import Flask, render_template, request, redirect, session
import mysql.connector
app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME")
)

cursor = db.cursor()

@app.route("/")
def home():

    sort = request.args.get("sort")

    sql = "SELECT * FROM products"

    if sort == "low":
        sql += " ORDER BY price ASC"

    elif sort == "high":
        sql += " ORDER BY price DESC"

    elif sort == "az":
        sql += " ORDER BY name ASC"

    elif sort == "za":
        sql += " ORDER BY name DESC"

    cursor.execute(sql)

    products = cursor.fetchall()

    return render_template(
        "index.html",
        products=products
    )

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        sql = """
        SELECT * FROM users
        WHERE email=%s AND password=%s
        """

        values = (email, password)

        cursor.execute(sql, values)

        user = cursor.fetchone()

       

        if user:

         session["user_id"] = user[0]
         session["user_name"] = user[1]
         session["is_admin"] = user[5]

         return redirect("/")

        else:

         return "Invalid Email or Password"

    return render_template("login.html")

@app.route("/admin")
def admin():

    if "user_id" not in session:
        return redirect("/login")

    if not session.get("is_admin"):
        return "Access Denied", 403

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

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        sql = """
        INSERT INTO users(name,email,password)
        VALUES (%s,%s,%s)
        """

        values = (name, email, password)

        cursor.execute(sql, values)

        db.commit()

        return "User Registered Successfully!"

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
        return "Access Denied", 403

    cursor.execute(
        "SELECT * FROM users"
    )

    users = cursor.fetchall()

    return render_template(
        "users.html",
        users=users
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

    if request.method == "POST":

        user_id = session["user_id"]

        # Get all cart items
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

        # Check if cart is empty
        if not cart_items:
            return "Your cart is empty."

        total_amount = 0

        # Validate stock and calculate total
        for item in cart_items:

            cursor.execute(
                "SELECT stock FROM products WHERE id=%s",
                (item[0],)
            )

            stock = cursor.fetchone()[0]

            if item[2] > stock:
                return f"Only {stock} item(s) available in stock."

            total_amount += item[1] * item[2]

        # Create order
        cursor.execute(
            """
            INSERT INTO orders
            (user_id, total_amount)
            VALUES (%s, %s)
            """,
            (user_id, total_amount)
        )

        db.commit()

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

        db.commit()

        # Clear cart
        cursor.execute(
            """
            DELETE FROM cart
            WHERE user_id=%s
            """,
            (user_id,)
        )

        db.commit()

        return redirect("/order-success")

    return render_template("checkout.html")

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


@app.route("/logout")
def logout():

    session.clear()

    return redirect("/")

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
        product=product
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)