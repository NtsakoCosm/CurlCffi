# Property24 Listing Scraper

This Python script asynchronously scrapes property listings from Property24.com, focusing on efficiency and avoiding duplicate entries. It extracts key details from listing pages and saves the collected data into a JSON file.

## Key Features

*   **Asynchronous Scraping:** Utilizes `asyncio` and `curl_cffi` to efficiently scrape multiple search result pages and individual listing pages concurrently.
*   **Proxy Rotation:** Leverages a proxy for requests to minimize the risk of IP blocking. Proxy credentials should be stored securely using environment variables.
*   **Batch Processing:** Employs a `chunker` utility to manage concurrent asynchronous requests in manageable batches, controlling the load on both the local machine and the target website.
*   **Duplicate Avoidance:** Tracks visited listing URLs (`scraped_links`) and unique Property24 listing numbers (`listing_nums`) to prevent scraping and saving the same property multiple times, even if accessed via different URLs.
*   **Data Cleaning:** Includes functions to clean extracted data, such as removing unwanted characters (e.g., superscripts like m², R²) and handling potential duplicate content within property descriptions.
*   **Targeted Extraction:** Uses `BeautifulSoup` to parse HTML and precisely extract specific data points like price, size, description, features, address, location (province, city, town), listing number, and image URL.
*   **JSON Output:** Saves the aggregated, cleaned listing data into a well-formatted JSON file (`gauteng_listings.json` by default).
*   **Browser Mimicking:** Uses `curl_cffi` with `impersonate="chrome110"` to make requests appear more like a real browser, potentially bypassing simpler anti-bot measures.
*   **Configuration via Environment Variables:** Securely loads sensitive proxy credentials using `python-dotenv` from a `.env` file.

## Prerequisites

*   Python 3.7+ (due to `asyncio` and f-strings)
*   `pip` (Python package installer)
*   Access to a rotating proxy service (recommended)

## Setup & Installation

1.  **Clone the repository (or download the script):**
    ```bash
    git clone https://github.com/NtsakoCosm/CurlCffi
    cd CurlCffi
    ```

2.  **Create and activate a virtual environment (recommended):**
    ```bash
    python -m venv venv
    # On Windows
    .\venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Create a `requirements.txt` file** with the following content:
    ```txt
    curl_cffi
    beautifulsoup4
    python-dotenv
    ```

4.  **Install the dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The scraper requires proxy credentials to run. These should be stored securely in a `.env` file in the same directory as the script.

1.  **Create a file named `.env`**.
2.  **Add your proxy details to the `.env` file**, replacing the placeholder values:

    ```dotenv
    # .env file
    PROXY_USERNAME=your_proxy_username
    PROXY_PASSWORD=your_proxy_password
    PROXY_HOST=your_proxy_host_address # e.g., p.webshare.io or rotate.proxyprovider.com
    PROXY_PORT=your_proxy_port        # e.g., 80 or 9999
    ```

    *   **`PROXY_USERNAME`**: Your username for the proxy service.
    *   **`PROXY_PASSWORD`**: Your password for the proxy service.
    *   **`PROXY_HOST`**: The hostname or IP address of your proxy server/endpoint. Use the rotating endpoint if provided by your service.
    *   **`PROXY_PORT`**: The port number for your proxy service.

    The script uses `python-dotenv` to automatically load these variables when it runs. **Do not commit the `.env` file to version control if it contains sensitive credentials.** Add `.env` to your `.gitignore` file.

## Usage

1.  Ensure your virtual environment is activated and the `.env` file is correctly configured.
2.  Run the script from your terminal:

    ```bash
    python your_script_name.py # Replace your_script_name.py with the actual filename
    ```

3.  The script will perform the following steps:
    *   Print status messages indicating the start and progress of scraping phases.
    *   **Phase 1:** Scrape the specified range of search result pages (e.g., pages 1-10 for Gauteng) to gather unique listing URLs.
    *   **Phase 2:** Scrape the individual listing pages found in Phase 1, extracting details and checking for duplicates based on the listing number.
    *   Print progress updates for each batch of pages/listings processed.
    *   **Phase 3:** Save the collected unique listing data to `gauteng_listings.json`.
    *   Print a summary upon completion, including total execution time and the number of listings saved.

## Output

The script generates a JSON file named `gauteng_listings.json` (by default) in the same directory. This file contains a list of dictionaries, where each dictionary represents a scraped property listing with the following structure:

```json
[
  {
    "price": "R 2 500 000",
    "size": "150 m", // Superscripts removed
    "description": "Spacious family home with modern finishes...", // Cleaned description
    "Rates & Taxes": "R 850", // Example feature key-value pair
    "Levies": "R 1 200",      // Example feature key-value pair
    "features": [             // List of features not in key:value format
      "Pet Friendly",
      "Garden"
    ],
    "address": "123 Example Street, Suburb Name",
    "Province": "Gauteng",
    "City": "Johannesburg",
    "Town": "Sandton",
    "ListingNo": "112345678",
    "image_url": "https://example.com/path/to/image.jpg",
    "url": "https://www.property24.com/for-sale/gauteng/..." // Source URL
  },
  // ... more listings
]