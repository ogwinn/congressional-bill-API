import requests
import pandas as pd
import re
import time
import os
from datetime import datetime


# API Configuration
API_KEY = "EJrUQCHuJ0IahRmYL00NZmEFar04efTqfRWx1EUe"  # Replace with your actual API key
SEARCH_URL = "https://api.govinfo.gov/search"
OUTPUT_FILE = f"house_bills_117th_congress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
BILL_LIMIT = 100  # Limit for faster testing
BILL_TEXT_FOLDER = "bill_texts"
os.makedirs(BILL_TEXT_FOLDER, exist_ok=True)

# Step 1: Fetch House Bills (H.R.) from 117th Congress
def fetch_house_bills():
    headers = {"Content-Type": "application/json"}
    bills = []
    offsetMark = "*"

    print("\nFetching the first 10 House Bills from the 117th Congress...")

    while len(bills) < BILL_LIMIT:
        query_payload = {
            "query": "collection:BILLS congress:117 billtype:HR",
            "offsetMark": offsetMark,
            "pageSize": 50,  # Fetch in batches of 50
            "sort": "dateDesc",
            "format": "json"
        }

        response = requests.post(
            SEARCH_URL, json=query_payload, headers=headers, params={"api_key": API_KEY}
        )

        if response.status_code != 200:
            print(f"❌ Failed to fetch data: {response.status_code}")
            print(response.text)  # Print API error details
            return []

        data = response.json()
        bills.extend(data.get("results", []))

        # Stop once we have at least 10 bills
        if len(bills) >= BILL_LIMIT:
            break

        # Update offsetMark for next page
        offsetMark = data.get("offsetMark", None)
        if not offsetMark:
            break  # No more pages left

    print(f"✅ Fetched {len(bills[:BILL_LIMIT])} House Bills for testing.\n")
    return bills[:BILL_LIMIT]

# Step 2: Fetch detailed metadata from summary page
def fetch_bill_metadata(summary_url):
    headers = {"Content-Type": "application/json"}  
    try:
        response = requests.get(summary_url, headers=headers, params={"api_key": API_KEY})
        if response.status_code != 200:
            print(f"⚠️ Skipping metadata fetch (Status Code: {response.status_code}) for {summary_url}")
            return None  # Skip if the summary page is not available
        return response.json()
    except Exception as e:
        print(f"❌ Error fetching metadata from {summary_url}: {e}")
        return None

def download_bill_text(bill_id, bill_version):
    """Download and save the bill text if the version is 'ih'."""
    if bill_version != "ih":
        print(f"⏩ Skipping {bill_id}, not 'ih' version.")
        return
    
    text_url = f"https://www.govinfo.gov/content/pkg/BILLS-{bill_id}ih/html/BILLS-{bill_id}ih.htm"
    file_path = os.path.join(BILL_TEXT_FOLDER, f"{bill_id}ih.txt")
    print(f"📥 Downloading bill text for {bill_id}...")
    try:
        response = requests.get(text_url)
        if response.status_code == 200:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(response.text)
            print(f"✅ Downloaded and saved: {file_path}")
        else:
            print(f"⚠️ Failed to download {text_url} (Status: {response.status_code})")
    except Exception as e:
        print(f"❌ Error downloading {text_url}: {e}")

# Step 3: Extract metadata from the API response
def extract_name(member):
    """ Extract full name from the `name` field, with a fallback."""
    if "name" in member:
        if isinstance(member["name"], list) and member["name"]:
            return member["name"][0].get("authority-fnf", member["name"][0].get("fullName", "Unknown"))
        elif isinstance(member["name"], dict):
            return member["name"].get("authority-fnf", member["name"].get("fullName", "Unknown"))
    return "Unknown"

def download_bill_text(congress, bill_number):
    """Download and save the bill text if the version is 'ih'."""
    bill_id = f"BILLS-{congress}hr{bill_number}ih"
    text_url = f"https://www.govinfo.gov/content/pkg/{bill_id}/html/{bill_id}.htm"
    file_path = os.path.join(BILL_TEXT_FOLDER, f"{bill_id}.txt")
    print(f"📥 Downloading bill text for HR {bill_number} (Congress {congress})...")
    try:
        response = requests.get(text_url)
        if response.status_code == 200:
            with open(file_path, "w", encoding="utf-8") as file:
                file.write(response.text)
            print(f"✅ Downloaded and saved: {file_path}")
        else:
            print(f"⚠️ Failed to download {text_url} (Status: {response.status_code})")
    except Exception as e:
        print(f"❌ Error downloading {text_url}: {e}")

def extract_metadata(bills):
    extracted_data = []
    
    print(f"Extracting metadata from the first {len(bills)} bills...\n")

    for i, bill in enumerate(bills):
        package_id = bill.get("packageId", "").replace("BILLS-", "")  # Remove "BILLS-" prefix
        title = bill.get("title", "")
        last_modified = bill.get("lastModified", "")
        result_link = bill.get("resultLink", "")

        # Extract Bill Number (e.g., "117hr99ih" -> "HR 99")
        match = re.search(r"117hr(\d+)", package_id)
        bill_number = f"HR {match.group(1)}" if match else "Unknown"

        # Default values
        sponsors, cosponsors, committees, actions, session, bill_version, report_number = "None", "None", "None", "Not Available", "Unknown", "Unknown", "None"
        short_titles, is_private, branch, is_appropriation, collection_name, publisher, su_doc_class, date_issued, current_chamber, government_author1, government_author2, category = "None", "False", "Unknown", "False", "None", "None", "None", "Unknown", "Unknown", "None", "None", "None"

        if result_link:
            print(f"🔄 Fetching metadata for Bill {bill_number} ({i+1}/{len(bills)})...")
            bill_metadata = fetch_bill_metadata(result_link)
            if bill_metadata:
                # Extract Titles
                title = bill_metadata.get("title", title)
                short_titles = ", ".join([st.get("title", "Unknown") for st in bill_metadata.get("shortTitle", [])])

                # Extract other metadata
                session = bill_metadata.get("session", "Unknown")
                bill_version = bill_metadata.get("billVersion", "Unknown")
                is_private = bill_metadata.get("isPrivate", "False")
                branch = bill_metadata.get("branch", "Unknown")
                is_appropriation = bill_metadata.get("isAppropriation", "False")
                collection_name = bill_metadata.get("collectionName", "None")
                publisher = bill_metadata.get("publisher", "None")
                su_doc_class = bill_metadata.get("suDocClassNumber", "None")
                date_issued = bill_metadata.get("dateIssued", "Unknown")
                current_chamber = bill_metadata.get("currentChamber", "Unknown")
                government_author1 = bill_metadata.get("governmentAuthor1", "None")
                government_author2 = bill_metadata.get("governmentAuthor2", "None")
                category = bill_metadata.get("category", "None")

                # Extract Sponsors and Cosponsors
                members = bill_metadata.get("members", [])

                def extract_name(member):
                    """ Safely extract the full name from the `name` field in `members` """
                    if "name" in member and isinstance(member["name"], list):
                        return member["name"][0].get("authority-fnf", "Unknown")
                    return "Unknown"

                sponsors = ", ".join([extract_name(m) for m in members if m.get("role") == "SPONSOR"])
                cosponsors = ", ".join([extract_name(m) for m in members if m.get("role") == "COSPONSOR"])

                # Extract Committees
                committees_list = bill_metadata.get("committees", [])
                committees = ", ".join([c.get("committeeName", "Unknown") for c in committees_list if isinstance(c, dict)])

                # Extract Actions (Not available in this API)
                actions = "Not Available"

                # Extract Report Number if available
                other_identifier = bill_metadata.get("otherIdentifier", {})
                report_number = other_identifier.get("stock-number", "None")

                if bill_version == "ih":
                    download_bill_text(package_id, bill_version)

        # Append extracted data
        extracted_data.append({
            "Congress Number": 117,
            "Session": session,
            "Bill Number": bill_number,
            "Title": title,
            "Short Titles": short_titles,
            "Bill Version": bill_version,
            "Is Private": is_private,
            "Branch": branch,
            "Is Appropriation": is_appropriation,
            "Collection Name": collection_name,
            "Publisher": publisher,
            "SuDoc Class": su_doc_class,
            "Date Issued": date_issued,
            "Current Chamber": current_chamber,
            "Government Author 1": government_author1,
            "Government Author 2": government_author2,
            "Category": category,
            "Last Action Date": last_modified,
            "Report Number": report_number,
            "Bill Summary Link": result_link,
            "Sponsors": sponsors if sponsors else "None",
            "Cosponsors": cosponsors if cosponsors else "None",
            "Committees": committees if committees else "None",
            "Actions": actions
        })

        # Sleep to avoid rate limits
        time.sleep(0.5)  # Adjust if needed

    print(f"\n✅ Completed metadata extraction for {len(bills)} bills!\n")
    return extracted_data

# Main Execution
bills = fetch_house_bills()
if not bills:
    print("❌ No bills found or error in API call.")
else:
    metadata = extract_metadata(bills)
    
    # Save to CSV
    df = pd.DataFrame(metadata)
    if df.isnull().sum().sum() > 0:
        print("⚠️ Warning: Some fields have missing values. Review the dataset.")
    df.to_csv(OUTPUT_FILE, index=False)
    df.to_csv(OUTPUT_FILE, index=False)

    print(f"✅ Successfully saved metadata for {len(metadata)} bills to {OUTPUT_FILE} 🎉")
