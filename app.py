from dotenv import load_dotenv
load_dotenv()
from flasgger import Swagger
from flask import Flask
from config import Config
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask import request, jsonify
from flask_jwt_extended import create_access_token
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import CORS
from bson import ObjectId
from flask import send_file, render_template
from bson.objectid import ObjectId
from fpdf import FPDF
import os

app = Flask(__name__)
app.config.from_object(Config)

CORS(app)

# ✅ FIXED Swagger Config
swagger = Swagger(app, template={
    "info": {
        "title": "Expense Tracker API",
        "description": "API for AI Expense Tracker",
        "version": "1.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "Enter: Bearer <your_token>"
        }
    }
})

mongo = PyMongo(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login-page")
def login_page():
    return render_template("login.html")

@app.route("/register-page")
def register_page():
    return render_template("register.html")

@app.route("/dashboard-page")
def dashboard_page():
    return render_template("dashboard.html")

@app.route("/expenses-page")
def expenses_page():
    return render_template("expenses.html")

@app.route("/add-expense-page")
def add_expense_page():
    return render_template("add-expense.html")

@app.route("/summary-page")
def summary_page():
    return render_template("summary.html")

@app.route("/budget-page")
def budget_page():
    return render_template("budget.html")

@app.route("/ai-page")
def ai_page():
    return render_template("ai.html")

@app.route("/privacy-policy")
def privacy_policy():
    return render_template("privacy-policy.html")

@app.route("/terms-and-conditions")
def terms_and_conditions():
    return render_template("terms-and-conditions.html")


# 🔐 REGISTER API
@app.route("/register", methods=["POST"])
def register():
    """
    Register User
    ---
    tags:
      - Authentication
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - name
            - email
            - password
          properties:
            name:
              type: string
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: User registered
    """
    data = request.json

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if mongo.db.users.find_one({"email": email}):
        return jsonify({"msg": "User already exists"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")

    mongo.db.users.insert_one({
        "name": name,
        "email": email,
        "password": hashed_password
    })

    return jsonify({"msg": "User registered successfully"})


# 🔐 LOGIN API
@app.route("/login", methods=["POST"])
def login():
    """
    Login User
    ---
    tags:
      - Authentication
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - email
            - password
          properties:
            email:
              type: string
            password:
              type: string
    responses:
      200:
        description: JWT Token
    """
    data = request.json

    email = data.get("email")
    password = data.get("password")

    user = mongo.db.users.find_one({"email": email})

    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"msg": "Invalid credentials"}), 401

    token = create_access_token(identity=str(user["_id"]))

    return jsonify({
    "access_token": token,
    "name": user["name"]   # 👈 IMPORTANT
})



#add-expense api
@app.route("/add-expense", methods=["POST"])
@jwt_required()
def add_expense():
    """
    Add Expense
    ---
    tags:
      - Expense
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - amount
            - category
            - date
          properties:
            amount:
              type: number
            category:
              type: string
            date:
              type: string
    responses:
      200:
        description: Expense added
    """
    user_id = get_jwt_identity()
    data = request.json

    mongo.db.expenses.insert_one({
    "user_id": user_id,
    "amount": data.get("amount"),
    "category": data.get("category"),
    "currency": data.get("currency"),
    "date": data.get("date")
})

    return jsonify({"msg": "Expense added successfully"})

#get all expenses
@app.route("/expenses", methods=["GET"])
@jwt_required()
def get_expenses():
    """
    Get All Expenses
    ---
    tags:
      - Expense
    security:
      - Bearer: []
    responses:
      200:
        description: List of expenses
    """
    user_id = get_jwt_identity()

    expenses = list(mongo.db.expenses.find({"user_id": user_id}))

    for e in expenses:
        e["_id"] = str(e["_id"])

    return jsonify(expenses)

# monthly expenses
@app.route("/monthly-expenses/<month>", methods=["GET"])
@jwt_required()
def monthly_expenses(month):
    """
    Monthly Expenses
    ---
    tags:
      - Expense
    security:
      - Bearer: []
    parameters:
      - in: path
        name: month
        type: string
        required: true
        description: Month in format YYYY-MM
    responses:
      200:
        description: Monthly data
    """
    user_id = get_jwt_identity()

    expenses = list(mongo.db.expenses.find({
        "user_id": user_id,
        "date": {"$regex": f"^{month}"}
    }, {"_id": 0}))

    return jsonify(expenses)

@app.route("/expense-summary", methods=["GET"])
@jwt_required()
def expense_summary():

    user_id = get_jwt_identity()

    start = request.args.get("start")
    end = request.args.get("end")
    category = request.args.get("category")

    query = {"user_id": user_id}

    if start and end:
        query["date"] = {"$gte": start, "$lte": end}

    if category:
        query["category"] = category

    expenses = list(mongo.db.expenses.find(query))

    amounts = [float(e.get("amount", 0)) for e in expenses]

    total = sum(amounts)
    count = len(amounts)
    avg = total / count if count > 0 else 0
    high = max(amounts) if count > 0 else 0
    low = min(amounts) if count > 0 else 0

    return jsonify({
        "total_expense": total,
        "total_transactions": count,
        "average_expense": round(avg, 2),
        "highest_expense": high,
        "lowest_expense": low
    })

#ai-spending-analysis 
@app.route("/ai-spending-analysis", methods=["GET"])
@jwt_required()
def ai_spending_analysis():
    """
    AI Spending Analysis
    ---
    tags:
      - AI
    security:
      - Bearer: []
    responses:
      200:
        description: AI insights
    """
    user_id = get_jwt_identity()

    expenses = list(mongo.db.expenses.find({"user_id": user_id}))

    if not expenses:
        return jsonify({"msg": "No data for analysis"})

    # total expense
    total = sum(float(e.get("amount", 0)) for e in expenses)

    # category analysis
    category_data = {}
    for e in expenses:
        cat = e.get("category", "Other")
        amount = float(e.get("amount", 0))

        if cat in category_data:
            category_data[cat] += amount
        else:
            category_data[cat] = amount

    # highest spending category
    highest_category = max(category_data, key=category_data.get)

    # simple alert logic
    alert = ""
    if total > 10000:
        alert = "⚠️ You are spending too much!"
    else:
        alert = "✅ Your spending is under control"

    # suggestion
    suggestion = f"Try to reduce spending on {highest_category}"

    return jsonify({
        "total_spent": total,
        "highest_spending_category": highest_category,
        "alert": alert,
        "suggestion": suggestion
    })

#update expenses
@app.route("/update-expense/<id>", methods=["PUT"])
@jwt_required()
def update_expense(id):
    """
    Update Expense
    ---
    tags:
      - Expense
    security:
      - Bearer: []
    """
    user_id = get_jwt_identity()
    data = request.json

    try:
        result = mongo.db.expenses.update_one(
            {"_id": ObjectId(id), "user_id": user_id},
            {
    "$set": {
        "amount": data.get("amount"),
        "category": data.get("category"),
        "currency": data.get("currency"),
        "date": data.get("date")
    }
}
        )

        if result.matched_count == 0:
            return jsonify({"msg": "Expense not found"}), 404

        return jsonify({"msg": "Expense updated successfully"})

    except:
        return jsonify({"msg": "Invalid ID"}), 400
    
@app.route("/delete-expense/<id>", methods=["DELETE"])
@jwt_required()
def delete_expense(id):
    """
    Delete Expense
    ---
    tags:
      - Expense
    security:
      - Bearer: []
    """
    user_id = get_jwt_identity()

    try:
        result = mongo.db.expenses.delete_one({
            "_id": ObjectId(id),
            "user_id": user_id
        })

        if result.deleted_count == 0:
            return jsonify({"msg": "Expense not found"}), 404

        return jsonify({"msg": "Expense deleted successfully"})

    except:
        return jsonify({"msg": "Invalid ID"}), 400

  #set budget
@app.route("/set-budget", methods=["POST"])
@jwt_required()
def set_budget():
    """
    Set Budget
    ---
    tags:
      - Budget
    security:
      - Bearer: []
    parameters:
      - in: body
        name: body
        schema:
          type: object
          required:
            - month
            - amount
          properties:
            month:
              type: string
              example: "2026-04"
            amount:
              type: number
              example: 10000
    responses:
      200:
        description: Budget set successfully
    """

    user_id = get_jwt_identity()
    data = request.json

    month = data.get("month")
    amount = data.get("amount")

    existing = mongo.db.budgets.find_one({
        "user_id": user_id,
        "month": month
    })

    if existing:
        mongo.db.budgets.update_one(
            {"_id": existing["_id"]},
            {"$set": {"amount": amount}}
        )
        return jsonify({"msg": "Budget updated successfully"})

    mongo.db.budgets.insert_one({
        "user_id": user_id,
        "month": month,
        "amount": amount
    })

    return jsonify({"msg": "Budget set successfully"})

  #budget alert
@app.route("/budget-alert/<month>", methods=["GET"])
@jwt_required()
def budget_alert(month):
    """
    Get Budget Alert
    ---
    tags:
      - Budget
    security:
      - Bearer: []
    parameters:
      - name: month
        in: path
        type: string
        required: true
        example: "2026-04"
    responses:
      200:
        description: Budget alert data
    """

    user_id = get_jwt_identity()

    budget = mongo.db.budgets.find_one({
        "user_id": user_id,
        "month": month
    })

    if not budget:
        return jsonify({"alert": "No budget set", "spent": 0, "budget": 0})

    expenses = list(mongo.db.expenses.find({
        "user_id": user_id,
        "date": {"$regex": f"^{month}"}
    }))

    total_spent = sum(float(e.get("amount", 0)) for e in expenses)
    budget_amount = float(budget.get("amount", 0))

    if total_spent > budget_amount:
        alert_msg = "⚠️ Budget exceeded!"
    else:
        alert_msg = "✅ You are within budget"

    return jsonify({
        "alert": alert_msg,
        "spent": total_spent,
        "budget": budget_amount
    })

  # delete budget
@app.route("/delete-budget/<month>", methods=["DELETE"])
@jwt_required()
def delete_budget(month):
    """
    Delete Budget
    ---
    tags:
      - Budget
    security:
      - Bearer: []
    parameters:
      - name: month
        in: path
        type: string
        required: true
        example: "2026-04"
    responses:
      200:
        description: Budget deleted successfully
    """

    user_id = get_jwt_identity()

    result = mongo.db.budgets.delete_one({
        "user_id": user_id,
        "month": month
    })

    if result.deleted_count == 0:
        return jsonify({"msg": "No budget found"}), 404

    return jsonify({"msg": "Budget deleted successfully"})

# ================================
# FILTER EXPENSES
# ================================
@app.route("/filter-expenses", methods=["GET"])
@jwt_required()
def filter_expenses():

    user_id = get_jwt_identity()

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    category = request.args.get("category")
    currency = request.args.get("currency")

    query = {
        "user_id": user_id
    }

    # Date filter
    if from_date and to_date:
        query["date"] = {
            "$gte": from_date,
            "$lte": to_date
        }

    # Category filter
    if category:
        query["category"] = category

    # Currency filter
    if currency:
        query["currency"] = currency    

    expenses = list(mongo.db.expenses.find(query))

    for exp in expenses:
        exp["_id"] = str(exp["_id"])

    return jsonify(expenses)


# ================================
# USER CATEGORIES
# ================================
@app.route("/user-categories", methods=["GET"])
@jwt_required()
def user_categories():

    user_id = get_jwt_identity()

    categories = mongo.db.expenses.distinct(
        "category",
        {"user_id": user_id}
    )

    return jsonify(categories)


# ================================
# PROFESSIONAL PDF REPORT
# ================================
@app.route("/report-pdf", methods=["GET"])
@jwt_required()
def report_pdf():

    user_id = get_jwt_identity()

    user = mongo.db.users.find_one({"_id": ObjectId(user_id)})
    
    user_name = "User"

    if user:
      user_name = user.get("name", "User")

    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")
    category = request.args.get("category")

    query = {
        "user_id": user_id
    }

    # DATE FILTER
    if from_date and to_date:
        query["date"] = {
            "$gte": from_date,
            "$lte": to_date
        }

    # CATEGORY FILTER
    if category:
        query["category"] = category

    expenses = list(mongo.db.expenses.find(query))

    # PDF CREATE
    pdf = FPDF()
    pdf.add_page()

    # ================================
    # LOGO
    # ================================
    pdf.image("frontend/images/logo.png", 10, 8, 20)
    # ================================
    # TITLE
    # ================================
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(0, 102, 204)

    pdf.cell(200, 15, txt="AI Expense Tracker", ln=True, align="C")
    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(80, 80, 80)

    pdf.cell(200, 8, txt=f"Prepared For: {user_name}", ln=True, align="C")

    pdf.set_font("Arial", "", 14)
    pdf.set_text_color(0, 0, 0)

    pdf.cell(200, 10, txt="Expense Report", ln=True, align="C")

    pdf.ln(10)

    # ================================
    # FILTER INFO
    # ================================
    pdf.set_font("Arial", "B", 12)

    if from_date and to_date:
        pdf.cell(200, 8, txt=f"Date: {from_date} to {to_date}", ln=True)

    if category:
        pdf.cell(200, 8, txt=f"Category: {category}", ln=True)

    pdf.ln(5)

    # ================================
    # TABLE HEADER
    # ================================
    pdf.set_fill_color(0, 102, 204)
    pdf.set_text_color(255, 255, 255)

    pdf.set_font("Arial", "B", 12)

    pdf.cell(20, 10, "No", 1, 0, "C", True)
    pdf.cell(60, 10, "Category", 1, 0, "C", True)
    pdf.cell(50, 10, "Amount", 1, 0, "C", True)
    pdf.cell(50, 10, "Date", 1, 1, "C", True)

    # ================================
    # TABLE DATA
    # ================================
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Arial", "", 11)

    total = 0
    count = 1

    for exp in expenses:

        amount = float(exp.get("amount", 0))
        category_name = exp.get("category", "")
        date = exp.get("date", "")

        total += amount

        pdf.cell(20, 10, str(count), 1, 0, "C")
        pdf.cell(60, 10, category_name, 1, 0, "C")
        pdf.cell(50, 10, f"Rs. {amount}", 1, 0, "C")
        pdf.cell(50, 10, date, 1, 1, "C")

        count += 1

    pdf.ln(10)

    # ================================
    # TOTAL BOX
    # ================================
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 102, 204)

    pdf.cell(200, 10, txt=f"Total Expense: Rs. {total}", ln=True)

    pdf.ln(15)

    # ================================
    # FOOTER
    # ================================
    pdf.set_font("Arial", "I", 10)
    pdf.set_text_color(100, 100, 100)

    pdf.cell(
        200,
        10,
        txt="Generated by AI Expense Tracker",
        ln=True,
        align="C"
    )

    # ================================
    # SAVE PDF
    # ================================
    file_path = "expense_report.pdf"

    pdf.output(file_path)

    return send_file(
        file_path,
        as_attachment=True,
        download_name="expense_report.pdf"
    )

if __name__ == "__main__":
    app.run(debug=True)