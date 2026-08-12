from collections import defaultdict
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np


def get_recommendations(user_id, db):

    cursor = db.cursor()

    # Get all purchase relationships:
    # user -> product -> quantity
    cursor.execute("""
        SELECT o.user_id, oi.product_id, oi.quantity
        FROM orders o
        JOIN order_items oi
            ON o.id = oi.order_id
    """)

    rows = cursor.fetchall()

    # No purchase history at all
    if not rows:
        cursor.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 5
        """)
        return cursor.fetchall()

    # Create user-product matrix
    user_products = defaultdict(dict)

    for db_user_id, product_id, quantity in rows:
        user_products[db_user_id][product_id] = quantity

    users = list(user_products.keys())

    # Get all product IDs
    cursor.execute("SELECT id FROM products")
    product_rows = cursor.fetchall()

    product_ids = [row[0] for row in product_rows]

    # Build matrix
    matrix = []

    for db_user_id in users:
        vector = [
            user_products[db_user_id].get(product_id, 0)
            for product_id in product_ids
        ]

        matrix.append(vector)

    matrix = np.array(matrix)

    # Find the current user
    if user_id not in user_products:
        cursor.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 5
        """)
        return cursor.fetchall()

    user_index = users.index(user_id)

    # Calculate similarity between users
    similarities = cosine_similarity(matrix)

    similar_users = similarities[user_index]

    # Rank products based on similar users' purchases
    scores = defaultdict(float)

    purchased_products = set(
        user_products[user_id].keys()
    )

    for index, similarity in enumerate(similar_users):

        # Don't compare the user with themselves
        if index == user_index:
            continue

        similar_user_id = users[index]

        for product_id, quantity in user_products[similar_user_id].items():

            # Don't recommend something the user already bought
            if product_id not in purchased_products:

                scores[product_id] += similarity * quantity

    # No suitable recommendations
    if not scores:
        cursor.execute("""
            SELECT *
            FROM products
            ORDER BY id DESC
            LIMIT 5
        """)
        return cursor.fetchall()

    # Sort by recommendation score
    recommended_ids = sorted(
        scores,
        key=scores.get,
        reverse=True
    )[:5]

    # Get product details
    placeholders = ",".join(["%s"] * len(recommended_ids))

    cursor.execute(
        f"""
        SELECT *
        FROM products
        WHERE id IN ({placeholders})
        """,
        tuple(recommended_ids)
    )

    products = cursor.fetchall()

    # Preserve recommendation ranking
    product_map = {
        product[0]: product
        for product in products
    }

    return [
        product_map[product_id]
        for product_id in recommended_ids
        if product_id in product_map
    ]