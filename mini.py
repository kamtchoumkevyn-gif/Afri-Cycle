from flask import Flask, request, jsonify

app = Flask(__name__)

# -----------------------------
# Temporary data
# -----------------------------

buyers = {}

transactions = []


# -----------------------------
# Register a buyer
# -----------------------------

@app.route("/buyer/register", methods=["POST"])
def register_buyer():

    data = request.get_json()

    name = data.get("name")
    email = data.get("email")

    if not name or not email:
        return jsonify({
            "message": "Name and email are required"
        }), 400

    buyers[email] = {
        "name": name,
        "email": email,
        "price": 0
    }

    return jsonify({
        "message": "Buyer registered successfully",
        "buyer": buyers[email]
    }), 201


# -----------------------------
# Set buyer price
# -----------------------------

@app.route("/buyer/set-price", methods=["POST"])
def set_price():

    data = request.get_json()

    email = data.get("email")
    price = data.get("price")

    if email not in buyers:
        return jsonify({
            "message": "Buyer not found"
        }), 404

    if price is None or price <= 0:
        return jsonify({
            "message": "Price must be greater than 0"
        }), 400

    buyers[email]["price"] = price

    return jsonify({
        "message": "Price updated successfully",
        "price": price
    })


# -----------------------------
# Log a transaction
# -----------------------------

@app.route("/buyer/transaction", methods=["POST"])
def log_transaction():

    data = request.get_json()

    email = data.get("email")
    material = data.get("material")
    quantity = data.get("quantity")

    if email not in buyers:
        return jsonify({
            "message": "Buyer not found"
        }), 404

    if not material or quantity is None:
        return jsonify({
            "message": "Material and quantity are required"
        }), 400

    transaction = {
        "buyer": email,
        "material": material,
        "quantity": quantity,
        "price": buyers[email]["price"]
    }

    transactions.append(transaction)

    return jsonify({
        "message": "Transaction recorded successfully",
        "transaction": transaction
    }), 201


# -----------------------------
# Transaction history
# -----------------------------

@app.route("/buyer/transactions/<email>", methods=["GET"])
def transaction_history(email):

    buyer_transactions = []

    for transaction in transactions:
        if transaction["buyer"] == email:
            buyer_transactions.append(transaction)

    return jsonify({
        "buyer": email,
        "transactions": buyer_transactions
    })


# -----------------------------
# Start the server
# -----------------------------

if __name__ == "__main__":
    app.run(debug=True)