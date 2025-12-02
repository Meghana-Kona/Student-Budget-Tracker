import easyocr
import re

# Load OCR reader once
reader = easyocr.Reader(['en'], gpu=False)

# Keywords to detect category
CATEGORY_KEYWORDS = {
    "Food": ["food", "burger", "pizza", "hotel", "restaurant", "meal"],
    "Transport": ["uber", "ola", "bus", "train", "auto", "ride"],
    "Shopping": ["mall", "shopping", "fashion", "clothes", "shirt"],
    "Stationary": ["pen", "pencil", "notebook", "book"],
    "Entertainment": ["movie", "cinema", "ticket", "theatre"],
}

def detect_category(text):
    text = text.lower()
    for category, keywords in CATEGORY_KEYWORDS.items():
        for word in keywords:
            if word in text:
                return category
    return "Other"

def extract_invoice_data(image_path):
    # Extract text using OCR
    result = reader.readtext(image_path, detail=0)
    text = " ".join(result)

    # Find all numbers (prices)
    numbers = re.findall(r"\d+\.\d+|\d+", text)
    amount = max([float(n) for n in numbers]) if numbers else 0

    # Detect category
    category = detect_category(text)

    return {
        "amount": amount,
        "category": category,
        "description": "Auto scanned invoice"
    }
