from flask import Flask
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build

# Flask app
app = Flask(__name__)

# Keywords dictionary grouped by field
keywords_dict = {
    "AI/ML/Data": [
        "Python", "Machine Learning", "Deep Learning", "Artificial Intelligence",
        "Data Analysis", "Data Science", "Computer Vision", "NLP", "Natural Language Processing",
        "Data Engineer", "Big Data", "ETL", "Hadoop", "Spark"
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
        "Embedded Systems", "IoT", "Robotics", "Automation", "API Development", "Flask", "Django"
    ]
}

# Color mapping for each category
category_colors = {
    "AI/ML/Data": {"red": 0.9, "green": 0.9, "blue": 1.0},  # light blue
    "Software Development": {"red": 0.9, "green": 1.0, "blue": 0.9},  # light green
    "Cloud/DevOps/Systems": {"red": 1.0, "green": 0.95, "blue": 0.8},  # light yellow
    "General Engineering/Tech": {"red": 1.0, "green": 0.85, "blue": 0.85}  # light red/pink
}

# Setup Google Sheets API
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("/etc/secrets/credentials.json", scope)
client = gspread.authorize(creds)

# Build Google Sheets API service for formatting
service = build("sheets", "v4", credentials=creds)

spreadsheet = client.open("Internships")
sheet = spreadsheet.sheet1
spreadsheet_id = spreadsheet.id


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
            # Title
            title_tag = listing.find("h3")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            # Company
            company_tag = listing.find("div", class_="company_name")
            company = company_tag.get_text(strip=True) if company_tag else "N/A"

            # Link
            link_tag = listing.find("a", class_="view_detail_button")
            if link_tag and link_tag.get("href"):
                link = base_url + link_tag["href"]
            else:
                title_link = listing.find("h3").find("a") if listing.find("h3") else None
                link = base_url + title_link["href"] if title_link else "N/A"

            # Match keywords by category
            matched_category = None
            for category, kw_list in keywords_dict.items():
                if any(skill.lower() in title.lower() for skill in kw_list):
                    matched_category = category
                    break

            if matched_category:
                internships.append([title, company, link, matched_category])

    return internships


@app.route("/")
def update_sheet():
    internships = scrape_internshala(max_pages=10)

    # Get all existing links in the sheet to avoid duplicates
    existing_links = sheet.col_values(3)  # 3rd column = Link

    requests_body = []
    new_count = 0

    for internship in internships:
        link = internship[2]
        category = internship[3]

        if link not in existing_links:
            # Insert at row 2 (just below header)
            sheet.insert_row(internship, 2)
            new_count += 1

            # Prepare color formatting request for this row
            requests_body.append({
                "updateCells": {
                    "range": {
                        "sheetId": 0,  # usually first sheet = 0
                        "startRowIndex": 1,  # row 2 (0-based index)
                        "endRowIndex": 2,
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

    # Apply batch formatting if new rows added
    if requests_body:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests_body}
        ).execute()

    return f"✅ Added {new_count} new internships (latest on top)."



if __name__ == "__main__":
    app.run(debug=True)
