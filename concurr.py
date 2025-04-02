"""
Property24 Listing Scraper

Key Features:
- Asynchronously scrapes search result pages to find listing URLs.
- Asynchronously scrapes individual listing pages to extract details.
- Uses a rotating proxy for requests (Credentials should be stored securely).
- Employs batching (`chunker`) to manage concurrent requests efficiently.
- Avoids scraping duplicate listings using listing numbers and visited URLs.
- Cleans extracted data (e.g., removes superscripts, handles duplicate descriptions).
- Saves the collected data into a JSON file.
"""

import asyncio
import datetime
import random
import re
import json
import os  # <--- Import the 'os' module to access environment variables
from threading import Lock
from dotenv import load_dotenv # <--- Import dotenv to load .env file

# Use curl_cffi for requests that can better mimic real browsers
from curl_cffi.requests import AsyncSession
# Use BeautifulSoup for parsing HTML content
from bs4 import BeautifulSoup
from dotenv import load_dotenv
load_dotenv() 


# Regular expression to identify valid Property24 listing URLs.
# This helps ensure we only try to scrape actual property pages.
# I have also noticed that there are honey pot links that when clicked flags anti bot measures on the target site

PROPERTY24_REGEX = re.compile(
    
    r"^https://(www\.)?property24\.com/for-sale/"
    
    r".+?/.+?/.+?/\d+/\d+/?(\?.*)?$",
    re.IGNORECASE 
)


scraped_links = set()

# The main container where we'll store dictionaries of scraped listing data.
data_bun = []

# Keep track of unique listing numbers (Property24 IDs) to avoid duplicates
# even if the same property is accessed via slightly different URLs.
listing_nums = set()
# Locks to ensure thread-safe access to shared global variables when multiple
# async tasks might try to modify them concurrently.
listing_nums_lock = Lock()
data_bun_lock = Lock()

# --- Proxy Configuration (Secure Method) ---

# Fetch proxy credentials from environment variables
# !! Replace 'YOUR_PROXY_USER', 'YOUR_PROXY_PASS', etc. with the actual names
# !! you choose for your environment variables (see explanation below).
PROXY_USER = os.getenv("PROXY_USERNAME")
PROXY_PASS = os.getenv("PROXY_PASSWORD")
PROXY_HOST = os.getenv("PROXY_HOST") # e.g., p.webshare.io
PROXY_PORT = os.getenv("PROXY_PORT") # e.g., 80

# Construct the proxy URL securely if all parts are found

proxy_url = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}:{PROXY_PORT}"
proxy = {
        "http": proxy_url,
        "https": proxy_url  
    }
    



# --- Helper Functions ---

def remove_superscripts(text):
   
    pattern = r'[\u00b2\u00b3\u00e9\u00b0\u00b1]'
    return re.sub(pattern, '', text)

def clean_description(desc):
    """
    Cleans the property description.
    Sometimes Property24 duplicates the description text. This function
    tries to detect and remove such duplication.
    """
    half = len(desc) // 2
    # Check if the first half is identical to the second half
    if desc[:half].strip() == desc[half:].strip():
        # If they match, return only the first half
        return desc[:half].strip()
    return desc.strip()

def extract_listing_data(soup: BeautifulSoup):
    """
    Parses the HTML soup of a listing page and extracts key details.

    Returns:
        dict: A dictionary containing extracted property data (price, size,
              description, features, address, location, listing number, image URL).
              Returns defaults like "None" or "None Found" if an element isn't present.
    """
    data = {} 

    # --- Price ---
    price_elem = soup.find(class_="p24_price")
    # Use .get_text(strip=True) to get text content without leading/trailing whitespace
    data["price"] = price_elem.get_text(strip=True) if price_elem else "None"

    # --- Size ---
    size_elem = soup.find(class_="p24_size")
    if size_elem:
        size_text = size_elem.get_text(strip=True)
        data["size"] = size_text.split(":")[0].strip() if ":" in size_text else size_text
        
        data["size"] = remove_superscripts(data["size"])
    else:
        data["size"] = "None"

    # --- Description ---
    # Try finding the description in the element revealed by "Read More"
    desc_elem = soup.find(class_="js_readMoreText")
    # Fallback to the container if the specific text element isn't there
    if not desc_elem:
        desc_elem = soup.find(class_="js_readMoreContainer")

    if desc_elem:

        raw_desc = desc_elem.get_text(" ", strip=True).replace(" Read Less", "")
        data["description"] = clean_description(raw_desc)
        
        data["description"] = remove_superscripts(data["description"])
    else:
        data["description"] = "None Found" 

    # --- Features ---
    features = [] # List to hold features not in key:value format
    # Find all elements listing features
    for item in soup.find_all(class_="p24_listingFeatures"):
        text = item.get_text(strip=True)
        
        if ":" in text:
            key, val = text.split(":", 1) # Split only on the first colon
            # Store as a key-value pair in the main data dictionary
            data[key.strip()] = val.strip()
        else:
            
            features.append(text)
   
    data["features"] = features

    # --- Address ---
    address_elem = soup.find(class_="p24_addressPropOverview")
    data["address"] = address_elem.get_text(strip=True) if address_elem else "None found"

    # --- Location (Province, City, Town) from Breadcrumbs ---
    # Select breadcrumb list items, skipping the first one (usually "Home")
    breadcrumbs = soup.select("#breadCrumbContainer li:not(:first-child)")
    crumbs = []
    for li in breadcrumbs:
        text = li.get_text(strip=True)
        # Filter out separators and irrelevant links/text
        if text not in ['|', '>', 'Back to Results', 'Property for Sale'] and not text.isdigit():
            crumbs.append(text)
    # Assign based on typical breadcrumb structure (Province > City > Town)
    if len(crumbs) >= 1:
        data["Province"] = crumbs[0]
    if len(crumbs) >= 2:
        data["City"] = crumbs[1]
    if len(crumbs) >= 3:
        data["Town"] = crumbs[2]
    # Note: If the structure varies, this might need adjustment

    # --- Listing Number (Property ID) ---
    # Select the element containing the listing number using a CSS selector
    listing_no_elem = soup.select_one(".p24_propertyOverviewRow:nth-child(1) .p24_info")
    data["ListingNo"] = listing_no_elem.get_text(strip=True) if listing_no_elem else "None"

    # --- Main Image URL ---
    # Find the div that holds the main image URL in a data attribute
    img_elem = soup.find("div", class_=lambda c: c and "js_lightboxImageWrapper" in c)
    data["image_url"] = img_elem.get("data-image-url") if img_elem and img_elem.has_attr("data-image-url") else None

    return data

# --- Utility Functions ---

def chunker(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

# --- Asynchronous Scraping Functions ---

async def async_scrape_page(session: AsyncSession, url):
    """
    Asynchronously scrapes a Property24 search results page to find listing URLs.

    Returns:
        list: A list of unique listing URLs found on the page that haven't been
              seen before globally. Returns an empty list on error.
    """
    print(f"Scraping search page: {url}")
    try:
       
        r = await session.get(url, proxies=proxy, impersonate="chrome110", timeout=30)
        r.raise_for_status() 

        # Parse the HTML content
        soup = BeautifulSoup(r.text, "html.parser")
        links = set() # Use a set to automatically handle duplicates on *this page*

        # Find all anchor tags with an 'href' attribute
        for a in soup.select("a[href]"):
            href = a["href"]
            # Handle relative URLs (starting with '/')
            if href.startswith("/"):
                href = f"https://www.property24.com{href}"

            # Check if the URL matches our property listing pattern AND we haven't
            # already added it to our global list of links to scrape.
            if PROPERTY24_REGEX.match(href) and href not in scraped_links:
                links.add(href) # Add to this page's unique links
                scraped_links.add(href) # Add to the global set to prevent future adds

        print(f"Found {len(links)} new listing links on {url}")
        return list(links) 

    except Exception as e:
        
        print(f"Error scraping page {url}: {str(e)}")
        return [] # Return empty list on failure

async def async_scrape_listing(session: AsyncSession, url):
    """
    Asynchronously scrapes an individual Property24 listing page.

    Args:
        session (AsyncSession): The curl_cffi session object.
        url (str): The URL of the listing page.

    Returns:
        dict or None: A dictionary containing the scraped data if successful and
                      the listing is unique (based on ListingNo), otherwise None.
    """
   
    try:
       
        r = await session.get(url, proxies=proxy, impersonate="chrome110", timeout=30)
        r.raise_for_status()

        
        soup = BeautifulSoup(r.text, "html.parser")

        # Extract data using our helper function
        listing_data = extract_listing_data(soup)
        listing_data["url"] = url # Add the source URL to the data

        # --- Duplicate Check using Listing Number ---
        # Use a lock to safely check and update the global set of listing numbers
        with listing_nums_lock:
            if listing_data["ListingNo"] != "None" and listing_data["ListingNo"] not in listing_nums:
                # If the listing number is valid and not seen before, add it
                listing_nums.add(listing_data["ListingNo"])
                
                return listing_data 
            elif listing_data["ListingNo"] == "None":
                
                return listing_data
            else:
                
                return None # Indicate that this is a duplicate

    except Exception as e:
        
        print(f"Error scraping listing {url}: {str(e)}")
        return None # Return None on failure

# --- Main Execution Logic ---

async def main():
    """
    Main asynchronous function to orchestrate the scraping process.
    """
    
    base_url = "https://www.property24.com/for-sale/gauteng/1/p{}"
    # Define the range of search result pages to scrape
    max_pages_to_scrape = 10 
    # How many requests to run concurrently in each batch
    batch_size = 10

    # Create a single asynchronous session to reuse connections
    async with AsyncSession() as session:

        # --- Phase 1: Scrape Search Pages for Listing URLs ---
        print(f"Starting Phase 1: Scraping search pages 1 to {max_pages_to_scrape}...")
        page_tasks = []
        for page_num in range(1, max_pages_to_scrape + 1):
            page_url = base_url.format(page_num)
            # Create a task for scraping each search page
            page_tasks.append(async_scrape_page(session, page_url))

        all_listing_links = []
        # Process page scraping tasks in batches
        for i, batch in enumerate(chunker(page_tasks, batch_size)):
            print(f"Running page scraping batch {i+1}...")
            # Wait for all tasks in the current batch to complete
            batch_results = await asyncio.gather(*batch)
            # Flatten the list of lists into a single list of links
            for links in batch_results:
                all_listing_links.extend(links)
            
            await asyncio.sleep(random.uniform(3,6))

        print(f"Phase 1 complete. Found {len(all_listing_links)} potential listing URLs.")
        

        # --- Phase 2: Scrape Individual Listing Pages ---
        print(f"Starting Phase 2: Scraping {len(all_listing_links)} listings...")
        listing_tasks = []
        for link in all_listing_links:
            # Create a task for scraping each individual listing page
            listing_tasks.append(async_scrape_listing(session, link))

        # Process listing scraping tasks in batches
        for i, batch in enumerate(chunker(listing_tasks, batch_size)):
            print(f"Running listing scraping batch {i+1}/{len(listing_tasks)//batch_size + 1}...")
            # Wait for all tasks in the batch to complete
            batch_results = await asyncio.gather(*batch)
            # Process the results from the batch
            for data in batch_results:
                # Use a lock to safely append to the shared data list
                with data_bun_lock:
                    if data: # Only append if data was returned (i.e., not None)
                        data_bun.append(data)

            print(f"Batch {i+1} complete. Total listings collected so far: {len(data_bun)}")
            # Optional: A slightly longer delay between listing batches
            await asyncio.sleep(random.uniform(5, 10)) 

        print("Phase 2 complete.")

        # --- Phase 3: Save Data ---
        if data_bun:
            output_filename = "gauteng_listings.json"
            print(f"Saving {len(data_bun)} scraped listings to {output_filename}...")
            # Save the collected data to a JSON file with nice formatting
            with open(output_filename, "w", encoding="utf-8") as f:
                json.dump(data_bun, f, indent=4, ensure_ascii=False)
            print("Data saved successfully.")
        else:
            print("No new listing data was collected to save.")


# --- Script Entry Point ---
if __name__ == "__main__":
    print("Script starting...")
    start_time = datetime.datetime.now()

    # Run the main asynchronous function
    asyncio.run(main())

    finish_time = datetime.datetime.now()
    print("-" * 30)
    print(f"Scraping finished.")
    print(f"Total execution time: {finish_time - start_time}")
    print(f"Total unique listings saved: {len(data_bun)}")
    print(f"Total unique listing numbers encountered: {len(listing_nums)}")
    print("-" * 30)
