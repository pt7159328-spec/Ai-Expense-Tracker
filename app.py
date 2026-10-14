from dotenv import load_dotenv
load_dotenv()
from flasgger import Swagger
from flask import Flask
from config import Config
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from flask_jwt_extended import JWTManager
from flask import request, jsonify
from werkzeug.utils import secure_filename
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import re
import difflib
from flask_jwt_extended import create_access_token
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_cors import CORS
from bson import ObjectId
from flask import send_file, render_template
from fpdf import FPDF
import os
import threading

# UPI-aware receipt parsing is kept in the dedicated service module.
from services.receipt_ocr import parse_upi_transaction

app = Flask(__name__)
app.config.from_object(Config)

# Receipt scanner upload guard. The file is stored in MongoDB with its metadata;
# keep uploads below MongoDB's 16 MB document limit.
app.config.setdefault("MAX_CONTENT_LENGTH", 10 * 1024 * 1024)

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

# Create the index used by the authenticated receipt-history query. Initialization
# is deferred until the first request so importing the app does not require an
# immediately available MongoDB connection. MongoDB create_index is idempotent.
_receipt_indexes_ready = False
_receipt_indexes_lock = threading.Lock()


@app.before_request
def _ensure_receipt_indexes():
    """Ensure receipt-history queries have a supporting compound index."""
    global _receipt_indexes_ready
    if _receipt_indexes_ready:
        return None

    with _receipt_indexes_lock:
        if _receipt_indexes_ready:
            return None
        try:
            mongo.db.receipts.create_index(
                [("user_id", 1), ("created_at", -1)],
                name="receipt_user_created_at",
            )
        except Exception as exc:
            # Do not make app startup/import fail solely because index creation
            # could not run; log it so the deployment can investigate.
            app.logger.warning("Could not initialize receipt indexes: %s", exc)
            return None

        _receipt_indexes_ready = True

    return None

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

# Frontend page routes
# These aliases allow the existing .html links used by the frontend to work
# when the application is served through Flask.
@app.route("/login.html")
def login_html():
    return render_template("login.html")

@app.route("/register.html")
def register_html():
    return render_template("register.html")

@app.route("/dashboard.html")
def dashboard_html():
    return render_template("dashboard.html")

@app.route("/add-expense.html")
def add_expense_page():
    return render_template("add-expense.html")

@app.route("/expenses.html")
def expenses_page():
    return render_template("expenses.html")

@app.route("/summary.html")
def summary_page():
    return render_template("summary.html")

@app.route("/ai.html")
def ai_page():
    return render_template("ai.html")

@app.route("/budget.html")
def budget_page():
    return render_template("budget.html")

@app.route("/privacy-policy.html")
def privacy_policy_page():
    return render_template("privacy-policy.html")

@app.route("/terms-and-conditions.html")
def terms_page():
    return render_template("terms-and-conditions.html")


@app.route("/register", methods=["POST"])
def register():
    data = request.json or {}

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")

    if not name or not email or not password:
        return jsonify({
            "msg": "Name, email and password are required"
        }), 400

    existing_user = mongo.db.users.find_one({
        "email": email
    })

    if existing_user:
        return jsonify({
            "msg": "User already exists"
        }), 400

    hashed_password = bcrypt.generate_password_hash(
        password
    ).decode("utf-8")

    result = mongo.db.users.insert_one({
        "name": name,
        "email": email,
        "password": hashed_password
    })

    token = create_access_token(
        identity=str(result.inserted_id)
    )

    return jsonify({
        "msg": "User registered successfully",
        "access_token": token,
        "name": name
    }), 201


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

@app.route("/report-pdf", methods=["GET"])
@jwt_required()
def report_pdf():

    user_id = get_jwt_identity()

    user = mongo.db.users.find_one({
        "_id": ObjectId(user_id)
    })

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

    expenses = list(
        mongo.db.expenses.find(query)
    )

    # ================================
    # CREATE PDF
    # ================================
    pdf = FPDF()
    pdf.add_page()

    # ================================
    # LOGO
    # ================================
    logo_path = os.path.join(
        app.root_path,
        "static",
        "images",
        "logo.png"
    )

    if os.path.exists(logo_path):
        pdf.image(
            logo_path,
            10,
            8,
            20
        )

    # ================================
    # TITLE
    # ================================
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(0, 102, 204)

    pdf.cell(
        200,
        15,
        txt="AI Expense Tracker",
        ln=True,
        align="C"
    )

    pdf.set_font("Arial", "", 12)
    pdf.set_text_color(80, 80, 80)

    pdf.cell(
        200,
        8,
        txt=f"Prepared For: {user_name}",
        ln=True,
        align="C"
    )

    pdf.set_font("Arial", "", 14)
    pdf.set_text_color(0, 0, 0)

    pdf.cell(
        200,
        10,
        txt="Expense Report",
        ln=True,
        align="C"
    )

    pdf.ln(10)

    # ================================
    # FILTER INFO
    # ================================
    pdf.set_font("Arial", "B", 12)

    if from_date and to_date:
        pdf.cell(
            200,
            8,
            txt=f"Date: {from_date} to {to_date}",
            ln=True
        )

    if category:
        pdf.cell(
            200,
            8,
            txt=f"Category: {category}",
            ln=True
        )

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

        amount = float(
            exp.get("amount", 0)
        )

        category_name = exp.get(
            "category",
            ""
        )

        date = exp.get(
            "date",
            ""
        )

        total += amount

        pdf.cell(
            20,
            10,
            str(count),
            1,
            0,
            "C"
        )

        pdf.cell(
            60,
            10,
            category_name,
            1,
            0,
            "C"
        )

        pdf.cell(
            50,
            10,
            f"Rs. {amount}",
            1,
            0,
            "C"
        )

        pdf.cell(
            50,
            10,
            date,
            1,
            1,
            "C"
        )

        count += 1

    pdf.ln(10)

    # ================================
    # TOTAL
    # ================================
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(0, 102, 204)

    pdf.cell(
        200,
        10,
        txt=f"Total Expense: Rs. {total}",
        ln=True
    )

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
    file_path = os.path.join(
        app.root_path,
        "expense_report.pdf"
    )

    pdf.output(file_path)

    return send_file(
        file_path,
        as_attachment=True,
        download_name="expense_report.pdf",
        mimetype="application/pdf"
    )


# ============================================================================
# SMART AI-BASED RECEIPT SCANNER
# ============================================================================
# This implementation intentionally uses optional OCR/PDF packages so the
# existing application can still start when those packages are not installed.
# Install pytesseract + Tesseract OCR for image OCR, and PyMuPDF (fitz) or
# pypdf for PDF text extraction. No external AI service is called from here.

RECEIPT_ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff", "pdf"}
RECEIPT_MAX_BYTES = 10 * 1024 * 1024
RECEIPT_MAX_PDF_PAGES = 20
RECEIPT_MAX_IMAGE_PIXELS = 40_000_000
RECEIPT_MAX_IMAGE_FRAMES = 20


def _receipt_json_safe(value):
    """Convert Mongo/BSON values to JSON-safe values recursively."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _receipt_json_safe(val) for key, val in value.items() if key != "file_data"}
    if isinstance(value, list):
        return [_receipt_json_safe(item) for item in value]
    return value


def _receipt_extract_text(filename, content):
    """Safely extract text from supported receipt images and PDFs in memory."""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if not content:
        raise ValueError("The uploaded receipt file is empty.")

    if extension == "pdf":
        # Prefer PyMuPDF because it supports embedded text and OCR-ready page rendering.
        try:
            import fitz  # PyMuPDF, optional
        except ImportError:
            fitz = None

        if fitz is not None:
            document = None
            text_parts = []
            ocr_dependency_missing = False
            try:
                document = fitz.open(stream=content, filetype="pdf")
                if document.needs_pass:
                    raise ValueError("This PDF is password-protected. Upload an unlocked PDF.")
                if document.page_count < 1:
                    raise ValueError("The PDF has no pages. Upload a PDF containing a receipt.")
                if document.page_count > RECEIPT_MAX_PDF_PAGES:
                    raise ValueError(
                        f"This PDF has {document.page_count} pages. The maximum supported is "
                        f"{RECEIPT_MAX_PDF_PAGES} pages per receipt."
                    )

                for page in document:
                    page_text = (page.get_text("text", sort=True) or "").strip()

                    # OCR image-only or nearly empty pages. OCR is optional; embedded
                    # text is retained if OCR dependencies are not available.
                    if len(page_text) < 40:
                        try:
                            import pytesseract
                            from PIL import Image
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                            image = Image.open(io.BytesIO(pix.tobytes("png")))
                            try:
                                ocr_text = (pytesseract.image_to_string(
                                    image, config="--psm 6"
                                ) or "").strip()
                            except pytesseract.TesseractNotFoundError:
                                ocr_dependency_missing = True
                                ocr_text = ""
                            if len(ocr_text) > len(page_text):
                                page_text = ocr_text
                        except ImportError:
                            ocr_dependency_missing = True
                        except Exception as exc:
                            # Keep readable embedded PDF text if rendering/OCR fails.
                            app.logger.warning("Receipt PDF page OCR failed: %s", exc)

                    if page_text:
                        text_parts.append(page_text)

                extracted = "\n".join(text_parts).strip()
                if not extracted and ocr_dependency_missing:
                    raise RuntimeError(
                        "This PDF appears to be scanned, but OCR is not configured. "
                        "Install Pillow and pytesseract, plus the Tesseract OCR engine."
                    )
                return extracted
            except (ValueError, RuntimeError):
                raise
            except Exception as exc:
                raise ValueError(
                    "The PDF could not be read. Upload a valid, unencrypted PDF."
                ) from exc
            finally:
                if document is not None:
                    try:
                        document.close()
                    except Exception:
                        pass

        # Fallback supports text-based PDFs when PyMuPDF is not installed.
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "PDF reading is not configured. Install PyMuPDF (recommended) or pypdf."
            ) from exc
        try:
            reader = PdfReader(io.BytesIO(content), strict=False)
            if reader.is_encrypted:
                try:
                    unlocked = reader.decrypt("")
                except Exception:
                    unlocked = 0
                if not unlocked:
                    raise ValueError("This PDF is password-protected. Upload an unlocked PDF.")
            page_count = len(reader.pages)
            if page_count < 1:
                raise ValueError("The PDF has no pages. Upload a PDF containing a receipt.")
            if page_count > RECEIPT_MAX_PDF_PAGES:
                raise ValueError(
                    f"This PDF has {page_count} pages. The maximum supported is "
                    f"{RECEIPT_MAX_PDF_PAGES} pages per receipt."
                )
            return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise ValueError(
                "The PDF could not be read. Upload a valid, unencrypted PDF."
            ) from exc

    # Pillow is used to validate image dimensions, apply EXIF rotation, and iterate
    # every frame of TIFF receipts without loading unbounded image dimensions.
    try:
        from PIL import Image, ImageOps, ImageFilter, UnidentifiedImageError
    except ImportError as exc:
        raise RuntimeError(
            "Image processing is not configured. Install Pillow, pytesseract, "
            "and the Tesseract OCR engine."
        ) from exc

    try:
        source = Image.open(io.BytesIO(content))
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(
            "The image is corrupt or unreadable. Upload a valid JPG, PNG, WEBP, BMP, or TIFF."
        ) from exc

    try:
        frame_count = int(getattr(source, "n_frames", 1) or 1)
        if frame_count < 1:
            raise ValueError("The image contains no readable frames.")
        if frame_count > RECEIPT_MAX_IMAGE_FRAMES:
            raise ValueError(
                f"This image contains {frame_count} frames. The maximum supported is "
                f"{RECEIPT_MAX_IMAGE_FRAMES} frames per receipt."
            )

        for frame_index in range(frame_count):
            source.seek(frame_index)
            width, height = source.size
            if width <= 0 or height <= 0:
                raise ValueError("The image has invalid dimensions.")
            if width * height > RECEIPT_MAX_IMAGE_PIXELS:
                raise ValueError(
                    "The image resolution is too large to process safely. "
                    "Upload an image with 40 megapixels or fewer."
                )

        # Re-open after dimension checks; process every frame (e.g. multi-page TIFF).
        ocr_parts = []
        try:
            import pytesseract
        except ImportError as exc:
            raise RuntimeError(
                "Image OCR is not configured. Install Pillow and pytesseract, "
                "and install the Tesseract OCR engine."
            ) from exc

        for frame_index in range(frame_count):
            source.seek(frame_index)
            image = ImageOps.exif_transpose(source.copy()).convert("RGB")
            image = ImageOps.grayscale(image)
            image = ImageOps.autocontrast(image)
            image = image.filter(ImageFilter.SHARPEN)
            try:
                page_text = (pytesseract.image_to_string(image, config="--psm 6") or "").strip()
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError(
                    "Tesseract OCR engine was not found. Install Tesseract and ensure "
                    "it is available on the system PATH."
                ) from exc
            if page_text:
                ocr_parts.append(page_text)
        return "\n".join(ocr_parts).strip()
    except (ValueError, RuntimeError):
        raise
    except Exception as exc:
        raise ValueError(
            "The image could not be processed. Try a clearer JPG or PNG image."
        ) from exc
    finally:
        try:
            source.close()
        except Exception:
            pass


def _receipt_parse_date(text):
    """Return an ISO date when a recognizable date is found."""
    patterns = [
        (r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", (1, 2, 3)),
        (r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", (3, 2, 1)),
    ]
    for pattern, order in patterns:
        for match in re.finditer(pattern, text):
            try:
                parts = [int(match.group(i)) for i in order]
                return datetime(parts[0], parts[1], parts[2]).date().isoformat()
            except (ValueError, IndexError):
                continue
    month_names = "January February March April May June July August September October November December"
    month_pattern = r"\b(\d{1,2})\s+(" + "|".join(month_names.split()) + r")\s+(20\d{2})\b"
    match = re.search(month_pattern, text, flags=re.IGNORECASE)
    if match:
        try:
            month = datetime.strptime(match.group(2).title(), "%B").month
            return datetime(int(match.group(3)), month, int(match.group(1))).date().isoformat()
        except ValueError:
            pass
    return None


def _receipt_parse_amount(text):
    """Extract a likely payable total without treating postal codes or balance due as spend."""
    if not text or not text.strip():
        return None

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    # Prefer explicit payable-total labels. Subtotal, payment made and balance due
    # are deliberately excluded because they are not necessarily the purchase total.
    strong_total = re.compile(
        r"\b(grand\s+total|invoice\s+total|total\s+amount|amount\s+payable|"
        r"net\s+payable|total\s+payable|amount\s+due|total)\b", re.I
    )
    excluded_label = re.compile(
        r"\b(sub\s*total|subtotal|balance\s+due|payment\s+made|amount\s+paid|"
        r"change\s+due|previous\s+balance)\b", re.I
    )
    # Money-like values: decimals or comma-grouped thousands avoid mistaking a
    # bare 6-digit Indian PIN code for an amount during fallback extraction.
    money_re = re.compile(
        r"(?:₹|Rs\.?\s*|INR\s*)?\s*"
        r"((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)", re.I
    )

    def values_in(line):
        vals = []
        # Remove leading negative/payment markers so they cannot be treated as totals.
        if re.search(r"^\s*\(?\s*-", line):
            return vals
        for match in money_re.finditer(line):
            raw = match.group(1)
            # Plain ungrouped long numbers are often IDs/PINs, not prices.
            # Four-digit years (e.g. 2026 in a date line) must not become expenses.
            prefix = line[max(0, match.start()-5):match.start()]
            has_currency = bool(re.search(r"₹|Rs\.?|INR", prefix, re.I))
            if "," not in raw and "." not in raw and len(raw) >= 5 and not has_currency:
                continue
            try:
                val = Decimal(raw.replace(",", ""))
                if len(raw) == 4 and val == val.to_integral_value() and Decimal("1900") <= val <= Decimal("2100") and not has_currency:
                    continue
                if Decimal("0") <= val < Decimal("100000000"):
                    vals.append(val)
            except InvalidOperation:
                pass
        return vals

    # Labels and values are often split across separate PDF text lines. Inspect
    # the next two lines after each label; rank explicit grand/payable total first.
    ranked = []
    for i, line in enumerate(lines):
        if excluded_label.search(line):
            continue
        if strong_total.search(line):
            rank = 3 if re.search(r"grand\s+total|amount\s+payable|net\s+payable|total\s+payable|invoice\s+total", line, re.I) else 2
            nearby = " ".join(lines[i:i+3])
            # Only collect values from the label line and immediately following
            # lines, stopping if another financial label starts.
            nearby_values = values_in(line)
            for j in range(i+1, min(i+3, len(lines))):
                if excluded_label.search(lines[j]) or strong_total.search(lines[j]):
                    break
                nearby_values.extend(values_in(lines[j]))
            if nearby_values:
                ranked.extend((rank, value, i) for value in nearby_values if value > 0)

    if ranked:
        # Prefer the highest-priority label; within the same label use the first
        # plausible amount, not an unrelated address or a later balance.
        best_rank = max(item[0] for item in ranked)
        best = sorted((item for item in ranked if item[0] == best_rank), key=lambda item: item[2])
        return float(best[0][1])

    # Fallback only to clearly formatted monetary values, never an arbitrary PIN.
    candidates = []
    for line in lines:
        if excluded_label.search(line):
            continue
        # Date-only lines should never be used as fallback expense amounts.
        if (re.search(r"\b(date|invoice\s+date|bill\s+date|transaction\s+date)\b", line, re.I)
                or re.search(r"\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2})\b", line)):
            if not re.search(r"₹|Rs\.?|INR|\b(grand\s+total|invoice\s+total|amount\s+payable|net\s+payable|total\s+payable|amount\s+due|total)\b", line, re.I):
                continue
        candidates.extend(v for v in values_in(line) if v > 0)
    return float(max(candidates)) if candidates else None


def _receipt_parse_currency(text):
    upper = text.upper()
    if "₹" in text or re.search(r"\b(INR|RS\.?|RUPEES?)\b", upper):
        return "INR"
    if "$" in text or re.search(r"\bUSD\b", upper):
        return "USD"
    if "€" in text or re.search(r"\bEUR\b", upper):
        return "EUR"
    if "£" in text or re.search(r"\bGBP\b", upper):
        return "GBP"
    return None


def _receipt_parse_merchant(text, filename):
    """Find a plausible merchant line while ignoring invoice labels and generator footers."""
    ignored = re.compile(
        r"(receipt|invoice|tax invoice|bill\s*(no|to)?|invoice\s*(no|date)?|date|time|cashier|gstin|"
        r"\bphone\b|\bwww\.|https?://|\btotal\b|\bamount\b|crafted with ease|"
        r"visit\b|create truly professional invoices|zoho\.com|authorized signature|"
        r"total in words|notes|thanks for your business|terms|due on receipt|payment made|balance due)",
        re.I,
    )
    candidates = []
    for raw_line in text.splitlines():
        clean = re.sub(r"\s+", " ", raw_line).strip(" -|:")
        if len(clean) < 3 or ignored.search(clean) or re.fullmatch(r"[\d\W]+", clean):
            continue
        if re.search(r"\b(20\d{2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b", clean):
            continue
        if len(re.findall(r"\d", clean)) >= 5:
            continue
        # Prefer uppercase/company-like names over ordinary address lines.
        letters = re.sub(r"[^A-Za-z]", "", clean)
        upper_ratio = sum(ch.isupper() for ch in letters) / max(1, len(letters))
        score = (3 if upper_ratio > 0.7 and len(letters) >= 4 else 0)
        if re.search(r"\b(studio|store|market|mart|ltd|limited|llp|pvt|private|shop|services|enterprise|enterprises)\b", clean, re.I):
            score += 2
        candidates.append((score, clean))
    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1][:120]
    base = os.path.splitext(os.path.basename(filename))[0]
    return base[:120] if base else "Unknown merchant"


def _receipt_parse_items(text):
    """Extract item rows from OCR text while preserving the existing receipt schema.

    The parser supports common receipt layouts: ``Item 2 50.00 100.00``,
    ``Item 2 x 50.00 100.00``, ``2 x Item 100.00`` and ``Item 100.00``.
    Item totals remain available as ``line_total`` for existing insights/expense code.
    """
    if not text or not str(text).strip():
        return []

    items = []
    seen = set()
    skip_line = re.compile(
        r"^(?:sub\s*total|subtotal|grand\s+total|total(?:\s+amount)?|tax|gst|cgst|sgst|"
        r"discount|cash|change|balance|amount\s+due|invoice|receipt|thank\s+you|date|time|"
        r"phone|address|gstin|payment|card|round\s*off|authorized\s+signature|total\s+in\s+words|"
        r"notes|bill\s+to|terms|qty\b|quantity\b|description\b|item\s+description\b)", re.I
    )
    money_token = r"(?:₹\s*|Rs\.?\s*|INR\s*)?((?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    money_re = re.compile(money_token, re.I)
    qty_unit_total = re.compile(
        r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?:x|×)\s*"
        + money_token + r"\s+" + money_token + r"\s*$", re.I
    )
    name_qty_rate_total = re.compile(
        r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+"
        + money_token + r"\s+" + money_token + r"\s*$", re.I
    )
    qty_name_total = re.compile(
        r"^(?P<qty>\d+(?:\.\d+)?)\s*(?:x|×)\s*(?P<name>.+?)\s+"
        + money_token + r"\s*$", re.I
    )
    trailing_price = re.compile(money_token + r"\s*$", re.I)

    def parse_price(raw):
        try:
            value = float(str(raw).replace(",", ""))
            return value if 0 < value < 10000000 else None
        except (TypeError, ValueError):
            return None

    def clean_name(raw):
        name = re.sub(r"\s+", " ", str(raw or "")).strip(" .:-|*\t")
        name = re.sub(r"^(?:\d+\s*[.)-]\s*)", "", name)
        name = re.sub(r"\s+(?:HSN|SAC)\s*[:#-]?\s*\w+\s*$", "", name, flags=re.I)
        return name.strip(" .:-|*\t")

    for raw_line in str(text).splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip(" \t|-")
        if len(line) < 3 or skip_line.search(line):
            continue
        # A bare six-digit PIN/postal code is not an item price.
        if re.fullmatch(r"\d{6}", line):
            continue
        if re.search(r"\b\d{6}\b", line) and not re.search(r"(?:₹|Rs\.?|INR|\d+[,.]\d{2})", line, re.I):
            continue

        name = ""
        quantity = None
        unit_price = None
        line_total = None
        confidence = 0.0

        # Layout: Item 2 x 50.00 100.00 (quantity, unit price, line total).
        match = qty_unit_total.match(line)
        if match:
            name = clean_name(match.group("name"))
            quantity = float(match.group("qty"))
            values = [parse_price(v) for v in money_re.findall(line)]
            values = [v for v in values if v is not None]
            if len(values) >= 2:
                unit_price, line_total = values[-2], values[-1]
                confidence = 0.92

        # Layout: Item 2 50.00 100.00.
        if not name:
            match = name_qty_rate_total.match(line)
            if match:
                candidate = clean_name(match.group("name"))
                values = [parse_price(v) for v in money_re.findall(line)]
                values = [v for v in values if v is not None]
                qty = float(match.group("qty"))
                if len(candidate) >= 2 and len(values) >= 2 and qty > 0:
                    name, quantity = candidate, qty
                    unit_price, line_total = values[-2], values[-1]
                    confidence = 0.88

        # Layout: 2 x Item 100.00 (only line total printed).
        if not name:
            match = qty_name_total.match(line)
            if match:
                candidate = clean_name(match.group("name"))
                price = parse_price(money_re.findall(line)[-1]) if money_re.findall(line) else None
                if len(candidate) >= 2 and price is not None:
                    name, quantity, line_total = candidate, float(match.group("qty")), price
                    if quantity > 0:
                        unit_price = round(line_total / quantity, 2)
                        confidence = 0.78

        # General layout: Item name ... price at end. Keep this fallback conservative.
        if not name:
            match = trailing_price.search(line)
            if not match:
                continue
            candidate = clean_name(line[:match.start()])
            price = parse_price(match.group(1))
            if len(candidate) < 2 or re.fullmatch(r"[\d\W]+", candidate) or price is None:
                continue
            if re.search(r"\b\d{6}\b", candidate):
                continue
            # Do not interpret a date or a quantity-only prefix as a product name.
            if re.fullmatch(r"(?:\d{1,4}[/.-]){1,2}\d{2,4}", candidate):
                continue
            qty_match = re.search(r"^(?P<name>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s*$", candidate)
            if qty_match and len(clean_name(qty_match.group("name"))) >= 2:
                name = clean_name(qty_match.group("name"))
                quantity = float(qty_match.group("qty"))
                line_total = price
                unit_price = round(price / quantity, 2) if quantity > 0 else None
                confidence = 0.68
            else:
                name, line_total, confidence = candidate, price, 0.62

        if not name or line_total is None or line_total <= 0:
            continue
        if len(name) > 120:
            name = name[:120].rstrip()
        # Avoid duplicate rows caused by repeated OCR lines, without merging
        # genuinely separate purchases that have different quantities/prices.
        signature = (name.casefold(), quantity, round(float(line_total), 2))
        if signature in seen:
            continue
        seen.add(signature)
        item = {
            "name": name,
            "line_total": round(float(line_total), 2),
            "quantity": quantity,
            "unit_price": round(float(unit_price), 2) if unit_price is not None else None,
            "extraction_confidence": confidence,
        }
        items.append(item)
        if len(items) >= 100:
            break
    return items


def _receipt_extraction_confidence(text, merchant, receipt_date, total_amount, currency, items, filename):
    """Estimate field-level extraction confidence for review guidance, not as a guarantee."""
    text = str(text or "")
    normalized_text = text.casefold()
    base_name = os.path.splitext(os.path.basename(filename or ""))[0].strip()

    merchant_confidence = 0.0
    if merchant and merchant != "Unknown merchant" and merchant != base_name and text.strip():
        merchant_confidence = 0.82
        merchant_normalized = _receipt_normalize_match_text(merchant)
        if merchant_normalized and merchant_normalized in _receipt_normalize_match_text(text):
            merchant_confidence = 0.92
    elif merchant and merchant != "Unknown merchant":
        merchant_confidence = 0.35

    date_confidence = 0.95 if receipt_date else 0.0

    explicit_total = bool(re.search(
        r"\b(grand\s+total|invoice\s+total|total\s+amount|amount\s+payable|"
        r"net\s+payable|total\s+payable|amount\s+due|total)\b", text, re.I
    ))
    amount_confidence = 0.0
    if total_amount is not None:
        amount_confidence = 0.92 if explicit_total else 0.62
        # Penalize extraction when multiple total-like labels conflict, since OCR
        # can confuse subtotal, tax, paid amount and final payable amount.
        total_labels = re.findall(
            r"\b(grand\s+total|invoice\s+total|total\s+amount|amount\s+payable|"
            r"net\s+payable|total\s+payable|amount\s+due|total|subtotal|sub\s*total)\b",
            text, re.I
        )
        if len(total_labels) > 3:
            amount_confidence = max(0.45, amount_confidence - 0.12)

    currency_confidence = 0.95 if currency else (0.55 if total_amount is not None else 0.0)

    item_confidence = 0.0
    if items:
        item_confidence = 0.75
        if total_amount is not None:
            item_total = round(sum(float(item.get("line_total") or 0) for item in items), 2)
            if abs(item_total - float(total_amount)) <= max(1.0, float(total_amount) * 0.05):
                item_confidence = 0.9
            else:
                item_confidence = 0.5

    return {
        "merchant": round(merchant_confidence, 2),
        "receipt_date": round(date_confidence, 2),
        "total_amount": round(amount_confidence, 2),
        "currency": round(currency_confidence, 2),
        "items": round(item_confidence, 2),
        "overall": round(sum((merchant_confidence, date_confidence, amount_confidence, currency_confidence, item_confidence)) / 5, 2),
    }


def _receipt_normalize_match_text(value):
    """Normalize merchant/item/OCR text for conservative duplicate comparison."""
    value = str(value or "").casefold()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _receipt_item_names(items):
    names = set()
    for item in items or []:
        name = _receipt_normalize_match_text(item.get("name", ""))
        if name and len(name) >= 3:
            names.add(name)
    return names


def _receipt_find_content_duplicate(user_id, merchant, receipt_date, amount, currency, items, extracted_text):
    """Find a high-confidence same-bill match even when the uploaded file bytes differ.

    A merchant/date/amount match alone is not enough to block a receipt because
    users can make multiple purchases at the same shop on the same day. We also
    require matching item names or very similar OCR text.
    """
    if not receipt_date or amount is None or float(amount) <= 0:
        return None

    normalized_merchant = _receipt_normalize_match_text(merchant)
    if len(normalized_merchant) < 3:
        return None

    query = {
        "user_id": user_id,
        "receipt_date": receipt_date,
        "total_amount": {"$gte": round(float(amount) - 0.01, 2), "$lte": round(float(amount) + 0.01, 2)},
        "currency": currency or "INR",
    }
    candidates = mongo.db.receipts.find(query).sort("created_at", -1).limit(100)
    new_items = _receipt_item_names(items)
    new_text = _receipt_normalize_match_text(extracted_text)

    for candidate in candidates:
        old_merchant = _receipt_normalize_match_text(candidate.get("merchant", ""))
        if not old_merchant:
            continue
        merchant_similarity = difflib.SequenceMatcher(None, normalized_merchant, old_merchant).ratio()
        if merchant_similarity < 0.90:
            continue

        old_items = _receipt_item_names(candidate.get("items", []))
        items_match = False
        if new_items and old_items:
            overlap = len(new_items & old_items) / max(1, len(new_items | old_items))
            items_match = overlap >= 0.50

        old_text = _receipt_normalize_match_text(candidate.get("extracted_text", ""))
        text_match = (
            len(new_text) >= 30 and len(old_text) >= 30
            and difflib.SequenceMatcher(None, new_text[:5000], old_text[:5000]).ratio() >= 0.82
        )

        if items_match or text_match:
            return candidate
    return None


def _receipt_make_insights(parsed):
    items = parsed.get("items") or []
    amount = parsed.get("total_amount")
    item_sum = round(sum(float(item.get("line_total") or 0) for item in items), 2)
    return {
        "item_count": len(items),
        "items_total_estimate": item_sum,
        "receipt_total": amount,
        "items_total_matches_receipt": (
            abs(item_sum - amount) <= max(1.0, amount * 0.05)
            if amount is not None and items else None
        ),
        "review_recommended": bool(parsed.get("warnings")),
    }


@app.route("/api/receipts/scan", methods=["POST"])
@jwt_required()
def scan_receipt():
    """Upload an image/PDF, extract fields, prevent duplicates and save results."""
    user_id = get_jwt_identity()
    uploaded = request.files.get("file") or request.files.get("receipt")
    if not uploaded or not uploaded.filename:
        return jsonify({"msg": "Select a receipt image or PDF in the 'file' field."}), 400

    safe_name = secure_filename(uploaded.filename)
    extension = safe_name.rsplit(".", 1)[-1].lower() if "." in safe_name else ""
    if extension not in RECEIPT_ALLOWED_EXTENSIONS:
        return jsonify({"msg": "Unsupported file type. Upload JPG, PNG, WEBP, TIFF, BMP or PDF."}), 400

    content = uploaded.read(RECEIPT_MAX_BYTES + 1)
    if not content:
        return jsonify({"msg": "The uploaded file is empty."}), 400
    if len(content) > RECEIPT_MAX_BYTES:
        return jsonify({"msg": "File is too large. Maximum receipt size is 10 MB."}), 413

    # Verify file signature rather than trusting the filename/MIME type alone.
    if extension == "pdf" and not content.lstrip().startswith(b"%PDF-"):
        return jsonify({"msg": "The selected file does not appear to be a valid PDF."}), 400
    if extension != "pdf":
        signatures = {
            "jpg": (b"\xff\xd8\xff",), "jpeg": (b"\xff\xd8\xff",),
            "png": (b"\x89PNG\r\n\x1a\n",), "webp": (b"RIFF",),
            "bmp": (b"BM",), "tif": (b"II*\x00", b"MM\x00*"),
            "tiff": (b"II*\x00", b"MM\x00*"),
        }
        if not any(content.startswith(sig) for sig in signatures.get(extension, ())):
            return jsonify({"msg": "File content does not match the selected image type."}), 400
        if extension == "webp" and (len(content) < 12 or content[8:12] != b"WEBP"):
            return jsonify({"msg": "The selected file is not a valid WEBP image."}), 400

    file_hash = hashlib.sha256(content).hexdigest()
    try:
        existing = mongo.db.receipts.find_one({"user_id": user_id, "file_hash": file_hash})
    except Exception:
        app.logger.exception("Receipt duplicate check failed")
        return jsonify({
            "msg": "Receipt storage is temporarily unavailable. Please try again.",
            "code": "RECEIPT_STORAGE_UNAVAILABLE",
        }), 503
    if existing:
        # If the user explicitly chooses to add a previously scanned UPI
        # transaction, allow promotion of that saved receipt into an expense.
        # This makes the user-choice flow work even when the same screenshot
        # is submitted a second time.
        add_choice = (request.form.get("add_as_expense") or "").strip().lower()
        wants_expense = add_choice in {"1", "true", "yes", "on"}
        saved_transaction = existing.get("transaction") or {}
        promoted_expense_id = existing.get("expense_id")

        if wants_expense and saved_transaction and not promoted_expense_id:
            try:
                reference = saved_transaction.get("transaction_reference")
                prior_expense = None
                if reference:
                    prior_expense = mongo.db.expenses.find_one({
                        "user_id": user_id,
                        "transaction_reference": reference,
                    })

                if prior_expense:
                    promoted_expense_id = str(prior_expense["_id"])
                    mongo.db.receipts.update_one(
                        {"_id": existing["_id"], "user_id": user_id},
                        {"$set": {"expense_id": promoted_expense_id}},
                    )
                else:
                    saved_amount = existing.get("total_amount")
                    if saved_amount is None or float(saved_amount) <= 0:
                        return jsonify({
                            "msg": "The transaction amount is missing or invalid. Please scan a clearer screenshot.",
                            "duplicate": True,
                            "expense_created": False,
                            "receipt": _receipt_json_safe(existing),
                            "warnings": existing.get("warnings", []),
                        }), 200

                    saved_date = (
                        saved_transaction.get("transaction_date")
                        or existing.get("receipt_date")
                        or datetime.now().date().isoformat()
                    )
                    expense_doc = {
                        "user_id": user_id,
                        "amount": float(saved_amount),
                        "category": "Other",
                        "currency": existing.get("currency") or "INR",
                        "date": saved_date,
                        "source": "upi_transaction",
                        "merchant": existing.get("merchant") or "UPI transaction",
                        "items": existing.get("items") or [],
                        "receipt_id": str(existing["_id"]),
                        "transaction_type": saved_transaction.get("transaction_type"),
                        "transaction_reference": reference,
                        "payment_status": saved_transaction.get("payment_status"),
                        "payment_platform": saved_transaction.get("platform"),
                        "counterparty": saved_transaction.get("counterparty"),
                        "transaction_time": saved_transaction.get("transaction_time"),
                        "possible_self_transfer": bool(saved_transaction.get("possible_self_transfer")),
                        "user_confirmed_expense": True,
                    }
                    expense_result = mongo.db.expenses.insert_one(expense_doc)
                    promoted_expense_id = str(expense_result.inserted_id)
                    link_result = mongo.db.receipts.update_one(
                        {"_id": existing["_id"], "user_id": user_id},
                        {"$set": {"expense_id": promoted_expense_id}},
                    )
                    if link_result.matched_count != 1:
                        mongo.db.expenses.delete_one({
                            "_id": expense_result.inserted_id,
                            "user_id": user_id,
                        })
                        raise RuntimeError("Receipt-to-expense link could not be saved.")

                    existing["expense_id"] = promoted_expense_id
            except Exception:
                app.logger.exception("Could not add previously scanned UPI transaction as expense")
                return jsonify({
                    "msg": "The transaction was already scanned, but could not be added as an expense. Please try again.",
                    "code": "UPI_EXPENSE_SAVE_FAILED",
                    "duplicate": True,
                    "expense_created": False,
                    "receipt": _receipt_json_safe(existing),
                }), 503

        return jsonify({
            "msg": (
                "Previously scanned UPI transaction added as an expense."
                if promoted_expense_id and wants_expense
                else "This receipt has already been scanned. No duplicate expense was created."
            ),
            "duplicate": True,
            "expense_created": bool(promoted_expense_id),
            "expense_id": promoted_expense_id,
            "receipt": _receipt_json_safe(existing),
            "warnings": ["Duplicate file detected; existing saved receipt returned."],
        }), 200

    try:
        extracted_text = _receipt_extract_text(safe_name, content)
    except RuntimeError as exc:
        return jsonify({"msg": str(exc), "code": "OCR_NOT_CONFIGURED"}), 503
    except ValueError as exc:
        return jsonify({"msg": str(exc), "code": "RECEIPT_FILE_INVALID"}), 400
    except Exception:
        app.logger.exception("Unexpected receipt text extraction failure")
        return jsonify({
            "msg": "The receipt could not be processed. Please try another file or a clearer scan.",
            "code": "RECEIPT_PROCESSING_FAILED",
        }), 500

    warnings = []
    if not extracted_text:
        warnings.append("No readable text was detected. Try a sharper, well-lit image or a text-based PDF.")

    # Keep the existing receipt parser for normal shopping receipts, and use
    # the dedicated service for payment-app transaction screenshots.
    try:
        upi_transaction = parse_upi_transaction(extracted_text, filename=safe_name)
    except Exception:
        app.logger.exception("UPI transaction parsing failed; falling back to receipt parsing")
        upi_transaction = None

    is_upi_transaction = bool(
        upi_transaction and (
            upi_transaction.get("platform")
            or re.search(
                r"\b(UPI|money sent|money received|you paid|paid to|received from|"
                r"debited|credited|transaction successful|payment successful)\b",
                extracted_text or "", re.I
            )
        )
    )

    if is_upi_transaction:
        merchant = (
            upi_transaction.get("counterparty")
            or _receipt_parse_merchant(extracted_text, safe_name)
        )
        total_amount = upi_transaction.get("amount")
        receipt_date = upi_transaction.get("transaction_date")
        currency = upi_transaction.get("currency") or _receipt_parse_currency(extracted_text) or "INR"
        items = []
        warnings.extend(upi_transaction.get("warnings") or [])
    else:
        merchant = _receipt_parse_merchant(extracted_text, safe_name) if extracted_text else os.path.splitext(safe_name)[0][:120]
        total_amount = _receipt_parse_amount(extracted_text) if extracted_text else None
        receipt_date = _receipt_parse_date(extracted_text) if extracted_text else None
        currency = _receipt_parse_currency(extracted_text) if extracted_text else None
        items = _receipt_parse_items(extracted_text) if extracted_text else []

    extraction_confidence = _receipt_extraction_confidence(
        extracted_text, merchant, receipt_date, total_amount, currency, items, safe_name
    )

    # UPI duplicate detection: transaction references are the strongest signal.
    # The lookup is user-scoped and does not expose another user's records.
    if is_upi_transaction and upi_transaction.get("transaction_reference"):
        transaction_reference = upi_transaction["transaction_reference"]
        try:
            prior_receipt = mongo.db.receipts.find_one({
                "user_id": user_id,
                "transaction.transaction_reference": transaction_reference,
            })
            prior_expense = mongo.db.expenses.find_one({
                "user_id": user_id,
                "transaction_reference": transaction_reference,
            })
        except Exception:
            app.logger.exception("UPI transaction duplicate check failed")
            return jsonify({
                "msg": "Transaction duplicate verification is temporarily unavailable. Please try again.",
                "code": "RECEIPT_DUPLICATE_CHECK_FAILED",
            }), 503

        if prior_receipt or prior_expense:
            return jsonify({
                "msg": "This UPI transaction reference has already been recorded. No duplicate expense was created.",
                "duplicate": True,
                "duplicate_type": "transaction_reference",
                "receipt": _receipt_json_safe(prior_receipt) if prior_receipt else None,
                "expense_id": str(prior_expense.get("_id")) if prior_expense else None,
                "warnings": ["Duplicate UPI transaction reference detected."],
            }), 200

    # Content-based duplicate check catches the same bill uploaded as a different
    # photo, re-encoded image, or PDF. The helper requires matching merchant,
    # date, amount/currency plus matching items or highly similar OCR text.
    try:
        content_duplicate = _receipt_find_content_duplicate(
            user_id, merchant, receipt_date, total_amount, currency or "INR", items, extracted_text
        )
    except Exception:
        app.logger.exception("Receipt content duplicate check failed")
        return jsonify({
            "msg": "Receipt duplicate verification is temporarily unavailable. Please try again.",
            "code": "RECEIPT_DUPLICATE_CHECK_FAILED",
        }), 503

    if content_duplicate:
        return jsonify({
            "msg": "This appears to be the same receipt already scanned. No duplicate expense was created.",
            "duplicate": True,
            "duplicate_type": "content_match",
            "receipt": _receipt_json_safe(content_duplicate),
            "warnings": [
                "A receipt with matching merchant, date, amount, and receipt details was found. Existing receipt returned."
            ],
        }), 200

    if total_amount is None:
        warnings.append("Transaction/receipt amount could not be confidently detected; no expense was auto-created.")
    if not receipt_date:
        warnings.append("Date was not detected; today's date is used for a saved expense. Please review it.")
    if not items and not is_upi_transaction:
        warnings.append("No line items were detected. You can still review the receipt and extracted total.")
    if not currency:
        warnings.append("Currency was not detected; INR is used as the default currency. Please review it.")
    if (not is_upi_transaction and total_amount is not None
            and extraction_confidence["total_amount"] < 0.8):
        warnings.append("The total amount was estimated without a clear payable-total label. Please verify it before relying on the expense.")
    if merchant == os.path.splitext(safe_name)[0][:120] and not extracted_text.strip():
        warnings.append("Merchant name could not be extracted from the receipt. Please review it.")
    if total_amount is not None and items:
        item_total = round(sum(float(item.get("line_total") or 0) for item in items), 2)
        if abs(item_total - total_amount) > max(1.0, total_amount * 0.05):
            warnings.append(
                "Detected item totals do not closely match the receipt total. Please review the extracted amounts."
            )

    effective_date = receipt_date or datetime.now().date().isoformat()
    effective_currency = currency or "INR"
    parsed = {
        "merchant": merchant,
        "receipt_date": receipt_date,
        "total_amount": total_amount,
        "currency": effective_currency,
        "items": items,
        "warnings": warnings,
        "extraction_confidence": extraction_confidence,
    }
    if is_upi_transaction:
        parsed["transaction"] = upi_transaction

    receipt_doc = {
        "user_id": user_id,
        "original_filename": safe_name,
        "content_type": uploaded.mimetype or ("application/pdf" if extension == "pdf" else "image/" + extension),
        "file_hash": file_hash,
        "file_data": content,
        "file_size": len(content),
        "file_extension": extension,
        "extracted_text": extracted_text[:30000],
        "merchant": merchant,
        "receipt_date": receipt_date,
        "total_amount": total_amount,
        "currency": effective_currency,
        "items": items,
        "warnings": warnings,
        "extraction_confidence": extraction_confidence,
        "status": "needs_review" if warnings else "processed",
        "created_at": datetime.now(timezone.utc),
        "expense_id": None,
    }
    if is_upi_transaction:
        receipt_doc["transaction"] = upi_transaction
    try:
        receipt_result = mongo.db.receipts.insert_one(receipt_doc)
    except Exception:
        app.logger.exception("Failed to save scanned receipt")
        return jsonify({
            "msg": "The receipt was processed but could not be saved. Please try again.",
            "code": "RECEIPT_SAVE_FAILED",
        }), 503

    receipt_id = str(receipt_result.inserted_id)

    # Normal receipts retain their existing automatic-save behavior. For UPI,
    # automatically save completed outgoing payments; received payments,
    # ambiguous transactions and possible self-transfers require the explicit
    # add_as_expense=true form field so the user's choice is respected.
    add_as_expense_value = (request.form.get("add_as_expense") or "").strip().lower()
    explicit_add_as_expense = add_as_expense_value in {"1", "true", "yes", "on"}
    explicit_skip_expense = add_as_expense_value in {"0", "false", "no", "off"}

    if is_upi_transaction:
        safe_upi_auto_save = (
            upi_transaction.get("payment_status") == "success"
            and upi_transaction.get("transaction_type") == "money_sent"
            and not upi_transaction.get("possible_self_transfer")
        )
        should_create_expense = (
            explicit_add_as_expense
            or (safe_upi_auto_save and not explicit_skip_expense)
        )
        if not should_create_expense:
            if upi_transaction.get("payment_status") != "success":
                warnings.append("UPI transaction was not auto-added because payment success could not be confirmed. Submit add_as_expense=true only if you have verified it and want to record it.")
            elif upi_transaction.get("transaction_type") != "money_sent" or upi_transaction.get("possible_self_transfer"):
                warnings.append("This UPI transaction needs your choice before it is added as an expense. Resubmit with add_as_expense=true if you want to record it.")
    else:
        should_create_expense = not explicit_skip_expense

    # Keep receipt/expense linkage consistent if either database write fails.
    expense_id = None
    if should_create_expense and total_amount is not None and total_amount > 0:
        expense_result = None
        try:
            expense_doc = {
                "user_id": user_id,
                "amount": total_amount,
                "category": "Shopping" if (not is_upi_transaction and re.search(r"(market|mart|store|supermarket|grocery|retail)", merchant, re.I)) else "Other",
                "currency": effective_currency,
                "date": effective_date,
                "source": "upi_transaction" if is_upi_transaction else "receipt_scanner",
                "merchant": merchant,
                "items": items,
                "receipt_id": receipt_id,
            }
            if is_upi_transaction:
                expense_doc.update({
                    "transaction_type": upi_transaction.get("transaction_type"),
                    "transaction_reference": upi_transaction.get("transaction_reference"),
                    "payment_status": upi_transaction.get("payment_status"),
                    "payment_platform": upi_transaction.get("platform"),
                    "counterparty": upi_transaction.get("counterparty"),
                    "transaction_time": upi_transaction.get("transaction_time"),
                    "possible_self_transfer": bool(upi_transaction.get("possible_self_transfer")),
                    "user_confirmed_expense": explicit_add_as_expense,
                })
            expense_result = mongo.db.expenses.insert_one(expense_doc)
            expense_id = str(expense_result.inserted_id)
            link_result = mongo.db.receipts.update_one(
                {"_id": receipt_result.inserted_id, "user_id": user_id},
                {"$set": {"expense_id": expense_id}}
            )
            if link_result.matched_count != 1:
                raise RuntimeError("Receipt-to-expense link could not be saved.")
            receipt_doc["expense_id"] = expense_id
        except Exception:
            app.logger.exception("Failed to save or link receipt expense")
            # Compensating cleanup prevents an unlinked expense from remaining behind.
            if expense_result is not None:
                try:
                    mongo.db.expenses.delete_one({"_id": expense_result.inserted_id, "user_id": user_id})
                except Exception:
                    app.logger.exception("Could not roll back unlinked receipt expense")
            expense_id = None
            receipt_doc["expense_id"] = None
            warning = "Receipt was saved, but its expense could not be linked. Please review the receipt and try again."
            if warning not in warnings:
                warnings.append(warning)
            receipt_doc["warnings"] = warnings
            receipt_doc["status"] = "needs_review"
            try:
                mongo.db.receipts.update_one(
                    {"_id": receipt_result.inserted_id, "user_id": user_id},
                    {"$set": {"expense_id": None, "warnings": warnings, "status": "needs_review"}}
                )
            except Exception:
                app.logger.exception("Could not persist receipt review status")
                return jsonify({
                    "msg": "The receipt was saved, but its final status could not be confirmed. Check receipt history before retrying to avoid duplicates.",
                    "code": "RECEIPT_STATUS_UPDATE_FAILED",
                    "receipt_id": receipt_id,
                }), 503

    # Persist warnings added during the save decision so receipt history reflects
    # why an UPI transaction was not automatically added as an expense.
    if warnings != receipt_doc.get("warnings", []):
        receipt_doc["warnings"] = warnings
        receipt_doc["status"] = "needs_review"
        try:
            mongo.db.receipts.update_one(
                {"_id": receipt_result.inserted_id, "user_id": user_id},
                {"$set": {"warnings": warnings, "status": "needs_review"}},
            )
        except Exception:
            app.logger.exception("Could not update receipt warnings")

    receipt_doc["_id"] = receipt_result.inserted_id
    parsed["warnings"] = warnings
    return jsonify({
        "msg": (
            "Transaction scanned and expense saved. Please review any warnings."
            if expense_id is not None and is_upi_transaction
            else "Receipt scanned and saved. Please review any warnings before relying on extracted values."
        ),
        "duplicate": False,
        "receipt": _receipt_json_safe(receipt_doc),
        "expense_created": expense_id is not None,
        "expense_id": expense_id,
        "transaction": upi_transaction if is_upi_transaction else None,
        "requires_expense_choice": bool(
            is_upi_transaction and expense_id is None and total_amount is not None
            and not explicit_skip_expense
        ),
        "insights": _receipt_make_insights(parsed),
        "warnings": warnings,
    }), 201


@app.route("/api/receipts", methods=["GET"])
@jwt_required()
def list_receipts():
    """List the current user's receipt scan history without returning file bytes/OCR text."""
    user_id = get_jwt_identity()
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 100)
    except ValueError:
        limit = 50
    cursor = mongo.db.receipts.find(
        {"user_id": user_id},
        {"file_data": 0, "extracted_text": 0}
    ).sort("created_at", -1).limit(limit)
    receipts = [_receipt_json_safe(doc) for doc in cursor]
    return jsonify(receipts)


@app.route("/api/receipts/<receipt_id>", methods=["GET"])
@jwt_required()
def get_receipt(receipt_id):
    """Get one receipt's extracted fields and warnings, excluding the raw file bytes."""
    user_id = get_jwt_identity()
    try:
        receipt = mongo.db.receipts.find_one(
            {"_id": ObjectId(receipt_id), "user_id": user_id},
            {"file_data": 0}
        )
    except Exception:
        return jsonify({"msg": "Invalid receipt ID."}), 400
    if not receipt:
        return jsonify({"msg": "Receipt not found."}), 404
    return jsonify(_receipt_json_safe(receipt))


@app.route("/api/receipts/insights", methods=["GET"])
@jwt_required()
def receipt_insights():
    """Return receipt-based spending trends and actionable, data-grounded insights."""
    user_id = get_jwt_identity()
    receipts = list(mongo.db.receipts.find(
        {"user_id": user_id},
        {"file_data": 0, "extracted_text": 0}
    ))

    def safe_amount(value):
        try:
            amount = float(value or 0)
            return amount if amount >= 0 and amount < 1e12 else 0.0
        except (TypeError, ValueError, OverflowError):
            return 0.0

    def receipt_month(receipt):
        raw = str(receipt.get("receipt_date") or "")[:10]
        try:
            parsed_date = datetime.strptime(raw, "%Y-%m-%d").date()
            return parsed_date.strftime("%Y-%m"), parsed_date
        except (TypeError, ValueError):
            created = receipt.get("created_at")
            if isinstance(created, datetime):
                try:
                    return created.strftime("%Y-%m"), created.date()
                except (ValueError, OverflowError):
                    pass
            return None, None

    total_receipts = len(receipts)
    all_items = []
    currency_totals = {}
    monthly_totals = {}
    merchant_totals = {}
    item_totals = {}
    review_count = 0
    dated_receipts = []

    for receipt in receipts:
        currency = str(receipt.get("currency") or "INR").upper().strip() or "INR"
        amount = safe_amount(receipt.get("total_amount"))
        currency_totals[currency] = currency_totals.get(currency, 0.0) + amount
        merchant = str(receipt.get("merchant") or "Unknown merchant").strip() or "Unknown merchant"
        merchant_key = (merchant, currency)
        merchant_totals[merchant_key] = merchant_totals.get(merchant_key, 0.0) + amount
        month, parsed_date = receipt_month(receipt)
        if month:
            monthly_key = (month, currency)
            monthly_totals[monthly_key] = monthly_totals.get(monthly_key, 0.0) + amount
            dated_receipts.append((parsed_date, amount, currency, merchant))
        if receipt.get("warnings") or receipt.get("status") == "needs_review":
            review_count += 1
        for item in receipt.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            all_items.append(item)
            name = str(item.get("name") or "Unknown item").strip() or "Unknown item"
            item_key = (name, currency)
            item_totals[item_key] = item_totals.get(item_key, 0.0) + safe_amount(item.get("line_total"))

    top_items = sorted(
        [{"name": name, "currency": currency, "total_spent": round(amount, 2)}
         for (name, currency), amount in item_totals.items()],
        key=lambda entry: entry["total_spent"], reverse=True
    )[:5]
    top_merchants = sorted(
        [{"merchant": merchant, "currency": currency, "total_spent": round(amount, 2)}
         for (merchant, currency), amount in merchant_totals.items()],
        key=lambda entry: entry["total_spent"], reverse=True
    )[:5]
    monthly_spend = [
        {"month": month, "currency": currency, "total_spent": round(amount, 2)}
        for (month, currency), amount in sorted(monthly_totals.items())
    ]
    currency_summary = [
        {"currency": currency, "total_spend": round(amount, 2),
         "average_receipt": round(amount / sum(1 for r in receipts if str(r.get("currency") or "INR").upper().strip() == currency), 2)}
        for currency, amount in sorted(currency_totals.items())
    ]

    # Insights are based only on available receipt data; do not compare unlike currencies.
    insight_messages = []
    if not receipts:
        insight_messages.append({"type": "info", "message": "Scan a receipt to start building your receipt spending insights."})
    else:
        if review_count:
            insight_messages.append({"type": "review", "message": f"{review_count} receipt(s) have warnings or need review. Verify extracted totals and item details."})
        if top_merchants:
            leading = top_merchants[0]
            insight_messages.append({"type": "merchant", "message": f"Your highest receipt spend by merchant is {leading['merchant']}: {leading['currency']} {leading['total_spent']:.2f}."})
        if top_items:
            leading_item = top_items[0]
            insight_messages.append({"type": "item", "message": f"Your highest item-wise spend is {leading_item['name']}: {leading_item['currency']} {leading_item['total_spent']:.2f}."})
        if len(monthly_spend) >= 2:
            latest_month = monthly_spend[-1]
            prior = next((entry for entry in reversed(monthly_spend[:-1]) if entry["currency"] == latest_month["currency"]), None)
            if prior:
                change = latest_month["total_spent"] - prior["total_spent"]
                if prior["total_spent"] > 0:
                    pct = abs(change) / prior["total_spent"] * 100
                    direction = "increased" if change > 0 else "decreased" if change < 0 else "stayed the same"
                    insight_messages.append({"type": "trend", "message": f"Receipt spending for {latest_month['month']} {direction} by {pct:.1f}% compared with {prior['month']} ({latest_month['currency']})."})
        if not all_items:
            insight_messages.append({"type": "info", "message": "No item rows were extracted yet; receipt-level totals are still included."})

    # Keep legacy fields intact for existing frontend integrations. The legacy total
    # is retained for compatibility; use currency_totals for currency-safe comparisons.
    saved_total = sum(safe_amount(r.get("total_amount")) for r in receipts)
    return jsonify({
        "receipt_count": total_receipts,
        "receipt_total_spend": round(saved_total, 2),
        "items_detected": len(all_items),
        "receipts_needing_review": review_count,
        "top_items_by_spend": top_items,
        "currency_totals": currency_summary,
        "monthly_spend": monthly_spend,
        "top_merchants_by_spend": top_merchants,
        "average_receipt_spend_by_currency": currency_summary,
        "insights": insight_messages,
    })


@app.route("/api/receipts/<receipt_id>/file", methods=["GET"])
@jwt_required()
def get_receipt_file(receipt_id):
    """Download the original receipt file; ownership is enforced by the JWT user."""
    user_id = get_jwt_identity()
    try:
        receipt = mongo.db.receipts.find_one(
            {"_id": ObjectId(receipt_id), "user_id": user_id},
            {"file_data": 1, "original_filename": 1, "content_type": 1}
        )
    except Exception:
        return jsonify({"msg": "Invalid receipt ID."}), 400
    if not receipt or not receipt.get("file_data"):
        return jsonify({"msg": "Receipt file not found."}), 404
    from flask import Response
    return Response(
        receipt["file_data"],
        mimetype=receipt.get("content_type") or "application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=\"" + secure_filename(receipt.get("original_filename", "receipt")) + "\""}
    )


if __name__ == "__main__":
    app.run(debug=True)