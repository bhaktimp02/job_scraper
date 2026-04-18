import time
import pandas as pd
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import os
import json
import traceback
import random
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# LangChain imports
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

# --- Pydantic Models for Structured Output ---

class JobSkills(BaseModel):
    key_words: List[str] = Field(description="List of data related skills, tools, and programming languages")
    experience: str = Field(description="Experience range required for the job (e.g., '2 to 5 years')")

class ResumeRecommendation(BaseModel):
    Recommendation: str = Field(description="Matching level: High, Medium, or Low")
    Notes: str = Field(description="Brief reason for the recommendation")

# --- Configuration & Initialization ---

now = datetime.now()
timestamp = now.strftime("%Y-%m-%d_%H-%M-%S")
output_file = f"cognizant_jobs_details_{timestamp}.xlsx"
RESUME_PATH = "Bhakti_Resume.txt"

# Initialize LangChain LLM (using OpenRouter)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
llm = ChatOpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
    model="qwen/qwen3.5-9b",
    temperature=0
)

# --- LangChain Chains ---

# 1. Skill Extraction Chain
skill_parser = PydanticOutputParser(pydantic_object=JobSkills)
skill_prompt = ChatPromptTemplate.from_template(
    "Read the job description and provide keywords of all data related skills, "
    "data analysis tools, and programming languages required!\n"
    "Also extract the experience range needed for this job.\n"
    "{format_instructions}\n"
    "Job Description:\n{jd}"
)
skill_chain = skill_prompt | llm | skill_parser 

# 2. Resume Recommendation Chain
rec_parser = PydanticOutputParser(pydantic_object=ResumeRecommendation)
rec_prompt = ChatPromptTemplate.from_template(
    "Can you tell if the Job Description is suitable for the resume provided below?\n\n"
    "Job Description:\n{jd}\n\n"
    "Resume:\n{resume_text}\n\n"
    "{format_instructions}"
)
rec_chain = rec_prompt | llm | rec_parser

# --- Helper Functions ---

def get_processed_job_ids():
    processed_urls = []
    files = list(Path(".").glob('*cognizant*.xlsx'))
    for file in files:
        try:
            df = pd.read_excel(file)
            if 'URL' in df.columns:
                processed_urls.extend(df['URL'].tolist())
        except Exception as e:
            print(f"Error reading {file}: {e}")
    return set(processed_urls)


def is_rate_limit_error(err: Exception) -> bool:
    """Detect OpenRouter quota errors so we can stop retrying for this run."""
    error_text = str(err).lower()
    return (
        "429" in error_text
        or "rate limit" in error_text
        or "free-models-per-day" in error_text
    )


def apply_ai_fallback(job_details, reason: str):
    job_details['Skills'] = []
    job_details['Experience'] = "N/A"
    job_details['Recommendation'] = "Skipped"
    job_details['Notes'] = reason

def get_job_details(driver, url):
    """Navigates to a job URL and extracts details."""
    str_to_replace = """The Cognizant community:
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
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "ul.job-meta"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data = {'URL': url}
        
        # Extract structured metadata
        meta_dl = soup.select_one('dl.job-meta')
        if meta_dl:
            dts = meta_dl.find_all('dt')
            dds = meta_dl.find_all('dd')
            for dt, dd in zip(dts, dds):
                key = dt.get_text(strip=True).rstrip(':')
                val = ' / '.join([a.get_text(strip=True) for a in dd.find_all('a')] or [dd.get_text(strip=True)])
                data[key] = val
        
        # Extract Description
        article = soup.select_one('article.cms-content')
        if article:
            data['Description'] = article.get_text("\n", strip=True)
        else:
            main_col = soup.select_one('div.main-col')
            if main_col:
                data['Description'] = main_col.get_text("\n", strip=True).replace(str_to_replace, "")
            else:
                data['Description'] = "Content not found"
                
        return data

    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return {'URL': url, 'Error': str(e)}

def scrape_cognizant_jobs(max_pages=2):
    processed_files = get_processed_job_ids()
    ai_available = bool(OPENROUTER_API_KEY)
    ai_unavailable_reason = "OPENROUTER_API_KEY is not set" if not ai_available else ""
    
    # Load Resume Text
    resume_text = ""
    if os.path.exists(RESUME_PATH):
        with open(RESUME_PATH, "r", encoding="utf-8") as f:
            resume_text = f.read()
    else:
        print(f"Warning: Resume not found at {RESUME_PATH}")

    options = uc.ChromeOptions()
    driver = uc.Chrome(options=options, version_main=146)
    wait = WebDriverWait(driver, 15)
    
    all_job_data = []
    
    try:
        for page in range(1, max_pages + 1):
            print(f"Processing listing page {page}...")
            listing_url = f"https://careers.cognizant.com/us-en/jobs/?page={page}&location=USA&radius=100&lat=&lng=&cname=United%20States&ccode=US&pagesize=50"
            driver.get(listing_url)
            
            if page == 1:
                try:
                    accept_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Accept All')]")))
                    accept_btn.click()
                    time.sleep(2)
                except: pass
            
            try:
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.card-job")))
            except:
                print(f"No jobs found on page {page}")
                continue
                
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            job_cards = soup.select('div.card-job')
            
            for card in job_cards:
                link_tag = card.select_one('h2.card-title a')
                if not link_tag: continue
                
                url = link_tag['href']
                if not url.startswith('http'):
                    url = "https://careers.cognizant.com" + url
                
                if url in processed_files:
                    continue

                print(f"  Scraping: {url}")
                job_details = get_job_details(driver, url)
                jd = job_details.get('Description', "")

                # --- AI Processing with LangChain ---
                if ai_available:
                    try:
                        # 1. Skills & Experience
                        skills_output = skill_chain.invoke({
                            "jd": jd,
                            "format_instructions": skill_parser.get_format_instructions()
                        })
                        job_details['Skills'] = skills_output.key_words
                        job_details['Experience'] = skills_output.experience

                        # 2. Resume Match
                        if resume_text:
                            rec_output = rec_chain.invoke({
                                "jd": jd,
                                "resume_text": resume_text,
                                "format_instructions": rec_parser.get_format_instructions()
                            })
                            job_details['Recommendation'] = rec_output.Recommendation
                            job_details['Notes'] = rec_output.Notes

                            if rec_output.Recommendation == 'High':
                                print(f"*** High Match Found! ***")
                        else:
                            job_details['Recommendation'] = "Skipped"
                            job_details['Notes'] = "Resume file not found"

                    except Exception as ai_err:
                        if is_rate_limit_error(ai_err):
                            ai_available = False
                            ai_unavailable_reason = (
                                "OpenRouter free-tier daily quota exceeded; AI skipped for remaining jobs"
                            )
                            print(f"AI quota reached: {ai_err}")
                            print("Disabling AI processing for the rest of this run.")
                            apply_ai_fallback(job_details, ai_unavailable_reason)
                        else:
                            print(f"AI Processing Error: {ai_err}")
                            apply_ai_fallback(job_details, f"AI error: {ai_err}")
                else:
                    apply_ai_fallback(job_details, ai_unavailable_reason)

                all_job_data.append(job_details)
                time.sleep(random.uniform(1, 3))
                
                if len(all_job_data) % 10 == 0:
                    pd.DataFrame(all_job_data).to_excel(output_file, index=False)

    except Exception as e:
        print(f"Critical Error: {e}")
        traceback.print_exc()
    finally:
        driver.quit()
        if all_job_data:
            pd.DataFrame(all_job_data).to_excel(output_file, index=False)
            print(f"Saved {len(all_job_data)} jobs to {output_file}")

if __name__ == "__main__":
    scrape_cognizant_jobs(max_pages=1)
