import time
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from openai import OpenAI 
import os
import json
import traceback
from datetime import datetime
from pathlib import Path

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")

alr_processed_files = list(Path(".").glob('*cognizant*.xlsx'))

def get_processed_job_ids(alr_processed_files):
    processed_files=[]
    for file in alr_processed_files:
        df1=pd.read_excel(file)
        l1=df1['URL'].tolist()
        processed_files = processed_files + l1
    return processed_files

processed_files = get_processed_job_ids(alr_processed_files)


# 3. Construct the full filename
original_filename = "cognizant_jobs_details_"
file_extension = ".xlsx"
output_file = f"{original_filename}_{timestamp}{file_extension}"

# output_file = "cognizant_jobs_details_9Dec205.xlsx"

prompt_empty = '{"key_words": []}'  # No need for extra explanations in empty response
prompt = '''
Read the job description and provide keywords of all data related skills,
data analysis tools, and programming languages required!
Also extract the experience range needed for this job
Format keywords and experience in this JSON format:
{"key_words": ["skill 1", "skill 2", "tool 1", "tool 2", "language 1", "language 2"],
 "experience":"xx to xx years"}

No explanations, unique keywords, no duplicates. Be brief.

'''  

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
client = OpenAI(   base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY);


def get_genai_resp(prompt, client):
    response = client.responses.create(
    model="nvidia/nemotron-nano-9b-v2:free",
    input=prompt
    )
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return { 'key_words': 'No Data', 'experience': 'No Data' }



RESUME_PATH = "Bhakti_Resume.txt"

def get_resume_recommendation(jd, client):
    with open(RESUME_PATH, "r", encoding="utf-8") as f:
        resume_text = f.read()

    prompt = (
        f"can you tell if the Job Description is suitable for the candidates resume that is included.\n\n"
        f"Job Description:\n{jd}\n\n"
        f"Resume:\n{resume_text}\n\n"
        'Respond ONLY in this JSON format:\n'
        '{"Recommendation": "High/Medium/Low", "Notes": "brief reason"}\n'
        "No explanations, unique keywords, no duplicates. Be brief."
    )

    response = client.responses.create(
        model="nvidia/nemotron-nano-9b-v2:free",
        input=prompt
    )
    try:
        return json.loads(response.output_text)
    except json.JSONDecodeError:
        return {}


def get_job_details(driver, url):
    """
    Navigates to a job URL and extracts details.
    """
    str_to_replace="""The Cognizant community:
We are a high caliber team who appreciate and support one another. Our people uphold an energetic, collaborative and inclusive workplace where everyone can thrive.
Cognizant is a global community with more than 300,000 associates around the world.
We don’t just dream of a better way – we make it happen.
We take care of our people, clients, company, communities and climate by doing what’s right.
We foster an innovative environment where you can build the career path that’s right for you.
About us:
Cognizant is one of the world's leading professional services companies, transforming clients' business, operating, and technology models for the digital era. Our unique industry-based, consultative approach helps clients envision, build, and run more innovative and efficient businesses. Headquartered in the U.S., Cognizant (a member of the NASDAQ-100 and one of Forbes World’s Best Employers 2025) is consistently listed among the most admired companies in the world. Learn how Cognizant helps clients lead with digital at
www.cognizant.com
Cognizant is an equal opportunity employer. Your application and candidacy will not be considered based on race, color, sex, religion, creed, sexual orientation, gender identity, national origin, disability, genetic information, pregnancy, veteran status or any other characteristic protected by federal, state or local laws.
If you have a disability that requires reasonable accommodation to search for a job opening or submit an application, please email
CareersNA2@cognizant.com
with your request and contact information.
Disclaimer:
Compensation information is accurate as of the date of this posting. Cognizant reserves the right to modify this information at any time, subject to applicable law.
Applicants may be required to attend interviews in person or by video conference. In addition, candidates may be required to present their current state or government issued ID during each interview."""
    try:
        driver.get(url)
        # Wait for the job meta to be present
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.job-meta"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = {'URL': url}
        
        # Extract structured fields from dl.job-meta
        meta_dl = soup.select_one('dl.job-meta')
        # breakpoint()
        if meta_dl:
            dts = meta_dl.find_all('dt')
            dds = meta_dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True).rstrip(':')
                # Handle multiple links or text in dd
                val = ' / '.join([a.get_text(strip=True) for a in dd.find_all('a')] or [dd.get_text(strip=True)])
                data[key] = val
        
        # Extract full description text
        # Try finding the main content area. Based on previous file, it might be article.cms-content
        article = soup.select_one('article.cms-content')
        if article:
            data['Description'] = article.get_text("\n", strip=True)
        else:
            # Fallback if specific class not found, try to find a likely container
            main_col = soup.select_one('div.main-col')
            if main_col:
                v1 =  main_col.get_text("\n", strip=True)
                data['Description'] = v1.replace(str_to_replace, "")
            else:
                data['Description'] = "Content not found"
                
        return data

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {'URL': url, 'Error': str(e)}

import random

def scrape_cognizant_jobs(max_pages=2):
    options = uc.ChromeOptions()
    # options.add_argument("--headless") # Headless mode detected/blocked by site
    # options.add_argument("--window-size=1920,1080")
    # options.add_argument("--no-sandbox")
    # options.add_argument("--disable-dev-shm-usage")
    # Fix for version mismatch: specify the main version of the installed Chrome
    driver = uc.Chrome(options=options, version_main=146)
    wait = WebDriverWait(driver, 15)
    
    all_job_data = []
    # output_file = "cognizant_jobs_details_9Dec205.xlsx"
    
    try:
        # Loop through pages 1 to max_pages
        for page in range(1, max_pages + 1):
            print(f"Processing listing page {page}...")
            listing_url = f"https://careers.cognizant.com/us-en/jobs/?page={page}&location=U.S.A.&radius=100&lat=&lng=&cname=United%20States&ccode=US&pagesize=50#results"

            
            try:
                driver.get(listing_url)
            except Exception as e:
                print(f"Error loading listing page {page}: {e}")
                continue
            
            # Handle cookie banner on first page
            if page == 1:
                try:
                    accept_btn = wait.until(
                        EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept All')]"))
                    )
                    accept_btn.click()
                    print("Cookie consent accepted.")
                    time.sleep(2)
                except:
                    pass
            
            # Wait for job cards
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.card-job")))
                time.sleep(2) # Extra wait for dynamic content
            except Exception as e:
                print(f"Could not load jobs on page {page}: {e}")
                continue
                
            # Extract job links from the current listing page
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            job_cards = soup.select('div.card-job')
            
            page_links = []
            for card in job_cards:
                link_tag = card.select_one('h2.card-title a')
                if link_tag and link_tag.get('href'):
                    href = link_tag['href']
                    if not href.startswith('http'):
                        href = "https://careers.cognizant.com" + href
                    page_links.append(href)
            
            print(f"Found {len(page_links)} jobs on page {page}.")
            
            # Visit each job link
            for i, link in enumerate(page_links):
                if link in processed_files :
                    # no need to process this url
                    print("skipping this link")
                    continue

                print(f"  Scraping job {i+1}/{len(page_links)}: {link}")
                # breakpoint()
                job_details = get_job_details(driver, link)
                recommend = get_resume_recommendation(job_details['Description'], client)
                # breakpoint()
                #job_details['Description']
                # v1=json.loads(response.output_text)
                # job_details['key_words'] = v1['key_words']
                # job_details['Description'] = v1['Description']
                
                jd_prompt = prompt+job_details['Description']

                ai_resp = get_genai_resp(jd_prompt, client)
                job_details['Skills'] = ai_resp['key_words']
                job_details['Experience'] = ai_resp['experience']
                job_details['Recommendation'] = recommend.get('Recommendation',"No data") 
                if recommend.get('Recommendation',"No data") == 'High' :
                    print("*"*10, "High match with ", link)
                job_details['Notes'] = recommend.get('Notes', "No Data")

                all_job_data.append(job_details)
                
                # Random delay between 1 and 3 seconds
                sleep_time = random.uniform(1, 5)
                time.sleep(sleep_time) 
                
                # Checkpoint every 10 jobs
                if len(all_job_data) % 10 == 0:
                    df = pd.DataFrame(all_job_data)
                    df.to_excel(output_file, index=False)
                    print(f"  [Checkpoint] Saved {len(all_job_data)} jobs to {output_file}")

    except KeyboardInterrupt:
        print("\nScraping interrupted by user.")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        traceback.print_exc() 
    finally:
        driver.quit()
        
    # Final Save
    if all_job_data:
        df = pd.DataFrame(all_job_data)
        df.to_excel(output_file, index=False)
        print(f"Successfully scraped {len(all_job_data)} jobs. Saved to {output_file}")
    else:
        print("No jobs scraped.")

if __name__ == "__main__":
    # Run for 1 page for demonstration, user can change this
    scrape_cognizant_jobs(max_pages=16)
