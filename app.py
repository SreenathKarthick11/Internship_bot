from flask import Flask
import requests
from bs4 import BeautifulSoup
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
import os 
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
sheet1 = spreadsheet.sheet1  # Internshala
spreadsheet_id = spreadsheet.id

# Create or open Sheet2 for jobs
try:
    sheet2 = spreadsheet.worksheet("Jobs")
except:
    sheet2 = spreadsheet.add_worksheet(title="Jobs", rows="1000", cols="5")


# -------------------------------
# Internshala scraper
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
def update_internshala():
    internships = scrape_internshala(max_pages=10)

    # Get all existing links in the sheet to avoid duplicates
    existing_links = sheet1.col_values(3)  # 3rd column = Link

    requests_body = []
    new_count = 0

    for internship in internships:
        link = internship[2]
        category = internship[3]

        if link not in existing_links:
            # Insert at row 2 (just below header)
            sheet1.insert_row(internship, 2)
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

    return f"✅ Added {new_count} new internships from Internshala."


# -------------------------------
# Indeed scraper
# -------------------------------
def scrape_indeed(max_pages=1, query="internship", location="India"):
    base_url = "https://in.indeed.com/jobs"
    jobs = []

    for page in range(0, max_pages * 10, 10):  # 10 jobs per page
        params = {"q": query, "l": location, "start": page}
        response = requests.get(base_url, params=params, headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(response.text, "html.parser")

        listings = soup.find_all("div", class_="job_seen_beacon")
        if not listings:
            print(f"⚠️ No jobs found on page {page//10+1}")
            continue

        for listing in listings:
            title_tag = listing.find("h2")
            title = title_tag.get_text(strip=True) if title_tag else "N/A"

            company_tag = listing.find("span", class_="companyName")
            company = company_tag.get_text(strip=True) if company_tag else "N/A"

            location_tag = listing.find("div", class_="companyLocation")
            loc = location_tag.get_text(strip=True) if location_tag else "N/A"

            link_tag = listing.find("a")
            link = "https://in.indeed.com" + link_tag["href"] if link_tag else "N/A"

            jobs.append([title, company, loc, link])

    return jobs
    
@app.route("/jobs")
def update_jobs():
    jobs = scrape_indeed(max_pages=5)

    # Avoid duplicates (check existing links)
    existing_links = sheet2.col_values(4)  # link is 4th column
    new_count = 0

    for job in jobs:
        link = job[3]
        if link not in existing_links:
            sheet2.insert_row(job, 2)  # insert on top
            new_count += 1

    return f"✅ Added {new_count} new internships from Indeed."

@app.route("/health")
def health():
    return "OK", 200
    
@app.route("/update_all")
def update_all():
    # Run Internshala update
    internshala_result = update_internshala()

    # Run Indeed update
    indeed_result = update_jobs()

    return f"internshala => {internshala_result}\n Indeed => {indeed_result}"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))  # Render assigns PORT dynamically
    app.run(host="0.0.0.0", port=port, debug=True)
