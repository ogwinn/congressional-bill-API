import pandas as pd
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
import requests, os, time
import xml.etree.ElementTree as ET

# API Configuration
API_KEY = "EJrUQCHuJ0IahRmYL00NZmEFar04efTqfRWx1EUe"
SEARCH_URL = "https://api.govinfo.gov/search"
OUTPUT_FILE = f"house_bills_117th_congress_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
BILL_LIMIT = 999999
BILL_TEXT_FOLDER = "bill_texts"
os.makedirs(BILL_TEXT_FOLDER, exist_ok=True)

# Function to fetch House Bills
def fetch_house_bills():
    headers = {"Content-Type": "application/json"}
    bills = []
    offsetMark = "*"
    
    print("\nFetching House Bills from the 117th Congress...")
    while len(bills) < BILL_LIMIT:
        query_payload = {
            "query": "collection:BILLS congress:117 billtype:HR",
            "offsetMark": offsetMark,
            "pageSize": 50,
            "sort": "dateDesc",
            "format": "json"
        }
        response = requests.post(SEARCH_URL, json=query_payload, headers=headers, params={"api_key": API_KEY})
        if response.status_code != 200:
            print(f"❌ Failed to fetch data: {response.status_code}")
            return []
        data = response.json()
        bills.extend(data.get("results", []))
        if len(bills) >= BILL_LIMIT:
            break
        offsetMark = data.get("offsetMark", None)
        if not offsetMark:
            break
    return bills[:BILL_LIMIT]

# Function to check if bill text exists before downloading
def bill_text_exists(congress, bill_number, version):
    bill_id = f"BILLS-{congress}hr{bill_number}{version}"
    url = f"https://www.govinfo.gov/content/pkg/{bill_id}/html/{bill_id}.htm"
    response = requests.head(url)
    return response.status_code == 200

# Function to download bill text
def download_bill_text(congress, bill_number, version):
    if not bill_text_exists(congress, bill_number, version):
        print(f"⚠️ {version.upper()} version not found for HR {bill_number}.")
        return None
    
    bill_id = f"BILLS-{congress}hr{bill_number}{version}"
    url = f"https://www.govinfo.gov/content/pkg/{bill_id}/html/{bill_id}.htm"
    file_path = os.path.join(BILL_TEXT_FOLDER, f"{bill_id}.txt")
    response = requests.get(url)
    if response.status_code == 200:
        with open(file_path, "w", encoding="utf-8") as file:
            file.write(response.text)
        print(f"✅ Downloaded and saved: {file_path}")
        return file_path
    else:
        print(f"❌ Failed to download {bill_id}.")
        return None

# Function to extract the correct name format
def extract_name(member):
    if isinstance(member, dict):
        name_list = member.get("name", [])
        if isinstance(name_list, list) and name_list:  # Ensure it's a list and not empty
            return name_list[0].get("authority-fnf", "Unknown")  # Extract full name
        return member.get("memberName", "Unknown")  # Fallback to 'memberName' field
    return "Unknown"

# Function to fetch bill metadata with retries
def fetch_bill_metadata(result_link, retries=3, timeout=10):
    """Fetch bill metadata with retries and timeout handling."""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(result_link, params={"api_key": API_KEY}, timeout=timeout)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"⚠️ Attempt {attempt}: Received status {response.status_code}, retrying...")

        except requests.exceptions.ChunkedEncodingError:
            print(f"❌ ChunkedEncodingError on attempt {attempt}, retrying...")
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Request error: {e}, retrying...")

        time.sleep(2 ** attempt)  # Exponential backoff

    print(f"❌ Failed to fetch metadata after {retries} attempts.")
    return None


# Function to flatten a nested list
def flatten_list(nested_list):
    flat_list = []
    for item in nested_list:
        if isinstance(item, list):
            flat_list.extend(flatten_list(item))
        else:
            flat_list.append(item)
    return flat_list

# Extract metadata
def extract_metadata(bills):
    extracted_data = []
    print("\n📊 Extracting metadata from bills...")
    
    for index, bill in enumerate(bills, start=1):
        print(f"🔄 Processing {index}/{len(bills)}: {bill.get('packageId', 'Unknown')}")
        package_id = bill.get("packageId", "").replace("BILLS-", "")
        title = bill.get("title", "")
        last_modified = bill.get("lastModified", "")
        result_link = bill.get("resultLink", "")

        # Fetch bill metadata safely
        bill_metadata = fetch_bill_metadata(result_link)
        if not bill_metadata:
            print(f"⚠️ Skipping {package_id} due to repeated request failures.")
            continue

        members = flatten_list(bill_metadata.get("members", []))
        
        short_titles = ", ".join([st.get("title", "Unknown") for st in bill_metadata.get("shortTitle", [])])
        full_title = bill_metadata.get("title", "Unknown")
        sponsors = ", ".join([extract_name(m) for m in members if isinstance(m, dict) and m.get("role") == "SPONSOR"])
        cosponsors = ", ".join([extract_name(m) for m in members if isinstance(m, dict) and m.get("role") == "COSPONSOR"])
        committees_list = bill_metadata.get("committees", [])
        committees = ", ".join([c.get("committeeName", "Unknown") for c in committees_list if isinstance(c, dict)])
        session = bill_metadata.get("session", "Unknown")
        
        match = re.match(r"(\d+)hr(\d+)([a-z]*)", package_id)
        if match:
            congress_num, bill_num, bill_version = match.groups()
            bill_version = bill_version if bill_version else "ih"
        else:
            continue
        
        bill_summary_link = f"https://www.govinfo.gov/app/details/BILLS-{congress_num}hr{bill_num}{bill_version}"
        
        ih_file = download_bill_text(congress_num, bill_num, "ih")
        rh_file = download_bill_text(congress_num, bill_num, "rh")
        extracted_data.append({
            "Congress Number": congress_num,
            "Session": session,
            "Bill Number": f"HR {bill_num}",
            "Title": full_title,
            "Short Titles": short_titles,
            "Sponsors": sponsors if sponsors else "None",
            "Cosponsors": cosponsors if cosponsors else "None",
            "Committees": committees if committees else "None",
            "Last Modified": last_modified,
            "Bill Summary Link": bill_summary_link,
            "IH_BILL_VERSION": ih_file if ih_file else "Not Available",
            "RH_BILL_VERSION": rh_file if rh_file else "Not Available"
        })
    
    print("✅ Metadata extraction complete.")
    return extracted_data

# Execute script
bills = fetch_house_bills()
if bills:
    metadata = extract_metadata(bills)
    df = pd.DataFrame(metadata)
    df = df.sort_values(by=["Bill Number", "Last Modified"], ascending=[True, False]).drop_duplicates(subset=["Bill Number"], keep="first")
    df.to_csv(OUTPUT_FILE, index=False)
    print(f"✅ Metadata and text files successfully saved in {OUTPUT_FILE}")
else:
    print("❌ No bills found or an error occurred.")
