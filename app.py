from flask import Flask
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import os

# Flask app
app = Flask(__name__)

# -------------------------------
# Keyword categories
# -------------------------------
keywords_dict = {
    "AI/ML/Data": [
        "Python", "Machine Learning", "Deep Learning", "Artificial Intelligence",
        "Data Analysis", "Data Science", "Computer Vision", "NLP",
        "Natural Language Processing", "Data Engineer", "Big Data", "ETL",
        "Hadoop", "Spark"
    ],
    "Software Development": [
        "Software Development", "Software Engineer", "SDE", "Backend Developer",
        "Frontend Developer", "Full Stack", "Web Development", "Mobile App",
        "Java Developer", "C++ Developer", "C# Developer", "Go Developer"
    ],
    "Cloud/DevOps/Systems": [
        "Cloud", "AWS", "Azure", "GCP", "DevOps", "Docker", "Kubernetes"
    ],
    "General Engineering/Tech": [
        "Embedded Systems", "IoT", "Robotics", "Automation",
        "API Development", "Flask", "Django"
    ]
}

# -------------------------------
# Colors for categories
# -------------------------------
category_colors = {
    "AI/ML/Data": {"red": 0.9, "green": 0.9, "blue": 1.0},
    "Software Development": {"red": 0.9, "green": 1.0, "blue": 0.9},
    "Cloud/DevOps/Systems": {"red": 1.0, "green": 0.95, "blue": 0.8},
    "General Engineering/Tech": {"red": 1.0, "green": 0.85, "blue": 0.85}
}

# -------------------------------
# Google Sheets Setup
# -------------------------------
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
client = gspread.authorize(creds)

service = build("sheets", "v4", credentials=creds)

spreadsheet = client.open("Internships")
sheet1 = spreadsheet.sheet1
spreadsheet_id = spreadsheet.id

# Create Sheet2 if needed
try:
    sheet2 = spreadsheet.worksheet("Jobs")
except:
    sheet2 = spreadsheet.add_worksheet(title="Jobs", rows="1000", cols="5")


# -------------------------------
# Internshala Scraper
# -------------------------------
def scrape_internshala(max_pages=3):
    internships = []
    base_url = "https://internshala.com"

    for page in range(1, max_pages + 1):
        url = f"{base_url}/internships/page-{page}"
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        container = soup.find("div", id="internship_list_container")
        if not container:
            print(f"⚠️ No internship container found on page {page}")
            continue

        listings = container.find_all("div", class_="individual_internship")

        for listing in listings:
            title_tag = listing.find("h3")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            company_tag = listing.find("div", class_="company_name")
            company = company_tag.get_text(strip=True) if company_tag else "N/A"

            link_tag = listing.find("a", class_="view_detail_button")
            if link_tag and link_tag.get("href"):
                link = base_url + link_tag["href"]
            else:
                title_link = listing.find("h3").find("a") if listing.find("h3") else None
                link = base_url + title_link["href"] if title_link else "N/A"

            # Match category
            matched_category = None
            for category, kw_list in keywords_dict.items():
                if any(skill.lower() in title.lower() for skill in kw_list):
                    matched_category = category
                    break

            if matched_category:
                internships.append([title, company, link, matched_category])

    return internships


# -------------------------------
# Internshala Update Function
# -------------------------------
@app.route("/")
@app.route("/update_internshala")
def update_internshala():
    internships = scrape_internshala(max_pages=10)

    existing_links = sheet1.col_values(3)  # Column C

    requests_body = []
    new_count = 0

    for internship in internships:
        link = internship[2]
        category = internship[3]

        if link not in existing_links:
            insert_position = 2   # insert at row 2
            sheet1.insert_row(internship, insert_position)
            new_count += 1

            # Calculate correct row for formatting (0-based)
            row_start = insert_position - 1
            row_end = insert_position

            # ------------------ COLOR ------------------
            requests_body.append({
                "updateCells": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": row_start,
                        "endRowIndex": row_end,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4
                    },
                    "rows": [{
                        "values": [{
                            "userEnteredFormat": {
                                "backgroundColor": category_colors[category]
                            }
                        }] * 4
                    }],
                    "fields": "userEnteredFormat.backgroundColor"
                }
            })

            # ------------------ DROPDOWN ------------------
            requests_body.append({
                "setDataValidation": {
                    "range": {
                        "sheetId": 0,
                        "startRowIndex": row_start,
                        "endRowIndex": row_end,
                        "startColumnIndex": 4,
                        "endColumnIndex": 5
                    },
                    "rule": {
                        "condition": {
                            "type": "ONE_OF_LIST",
                            "values": [
                                {"userEnteredValue": "Applying"},
                                {"userEnteredValue": "Rejected"},
                                {"userEnteredValue": "Not Suitable"},
                                {"userEnteredValue": "Interview"},
                                {"userEnteredValue": "Selected"}
                            ]
                        },
                        "showCustomUi": True
                    }
                }
            })

    # Apply formatting once
    if requests_body:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests_body}
        ).execute()

    return f"✅ Added {new_count} new internships from Internshala."


# -------------------------------
# Health
# -------------------------------
@app.route("/health")
def health():
    return "OK", 200


# -------------------------------
# Unified Endpoint
# -------------------------------
@app.route("/update_all")
def update_all():
    result = update_internshala()
    return f"Internshala → {result}"


# -------------------------------
# Main
# -------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=True)
