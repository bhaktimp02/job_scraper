# Cognizant Job Scraper

This project scrapes Cognizant job postings from the U.S. careers site and saves the results to Excel. It includes two scraper variants:

- `job_scraper.py`: a direct OpenAI/OpenRouter client version
- `job_scraper_langchain.py`: a LangChain-based version with structured output parsing

## LangChain Scraper

`job_scraper_langchain.py` scrapes Cognizant job listings and uses LangChain plus an OpenRouter-hosted chat model to enrich each job with:

- extracted skills and tools
- required experience
- a resume match recommendation
- short notes explaining the recommendation

The script writes results to a timestamped Excel file such as `cognizant_jobs_details_2026-04-18_10-30-00.xlsx`.

## What It Does

For each job posting, the LangChain scraper:

1. Opens the Cognizant careers listing page.
2. Collects job links from the selected number of pages.
3. Visits each job detail page and extracts metadata plus the full description.
4. Sends the job description to a LangChain chain that returns structured skills and experience data.
5. Compares the job description with the text in `Bhakti_Resume.txt`.
6. Saves the combined result set to Excel, with periodic checkpoints every 10 jobs.

## Requirements

- Python 3.10+
- Google Chrome installed locally
- A compatible Chrome version for `undetected-chromedriver`
- An OpenRouter API key in `OPENROUTER_API_KEY`

## Install

Using `uv`:

```bash
uv venv --python 3.10.19
source .venv/bin/activate
uv init
uv add -r requirements.txt
```


## Configuration

Set your OpenRouter key before running:

```bash
export OPENROUTER_API_KEY="your_openrouter_api_key"
```

The LangChain scraper also expects a plain-text resume file at:

```text
Bhakti_Resume.txt
```

If the resume file is missing, the scraper will still run, but recommendation fields will be marked as skipped.

## Run The LangChain Scraper

```bash
python3 job_scraper_langchain.py
```

By default, the script runs:

```python
scrape_cognizant_jobs(max_pages=1)
```

## Output Columns

The generated Excel file can include fields such as:

- `URL`
- job metadata pulled from the Cognizant job page
- `Description`
- `Skills`
- `Experience`
- `Recommendation`
- `Notes`

## AI Model Notes

The LangChain scraper initializes `ChatOpenAI` with:

- `base_url="https://openrouter.ai/api/v1"`
- `model="qwen/qwen3.5-9b"`
- `temperature=0`

If you want to switch models, update the `model` value near the top of [job_scraper_langchain.py](/Users/mehul/Downloads/bhaktipatel/cognizant_demo/job_scraper_langchain.py:37).

## Rate Limits And Fallback Behavior

If OpenRouter returns a quota or rate-limit error such as HTTP `429`, the LangChain scraper now:

- keeps scraping job pages
- disables AI enrichment for the rest of the run
- fills fallback values into the spreadsheet

Typical fallback values are:

- `Skills = []`
- `Experience = "N/A"`
- `Recommendation = "Skipped"`
- `Notes =` a message explaining why AI processing was skipped

This prevents one quota error from stopping the entire scrape.

## Known Limitations

- The careers site is dynamic, so selector changes on Cognizant's site may break scraping.
- `undetected-chromedriver` can still fail if the local Chrome version changes significantly.
- AI output quality depends on the selected model and the completeness of the job description.
- If OpenRouter credits or daily quota are exhausted, AI enrichment will be skipped.

## Main Files

- [job_scraper_langchain.py](/Users/mehul/Downloads/bhaktipatel/cognizant_demo/job_scraper_langchain.py:1): LangChain-based scraper
- [job_scraper.py](/Users/mehul/Downloads/bhaktipatel/cognizant_demo/job_scraper.py:1): non-LangChain scraper
- [Bhakti_Resume.txt](/Users/mehul/Downloads/bhaktipatel/cognizant_demo/Bhakti_Resume.txt:1): resume text used for recommendation matching
- [requirements.txt](/Users/mehul/Downloads/bhaktipatel/cognizant_demo/requirements.txt:1): pinned dependencies

## Troubleshooting

- `OPENROUTER_API_KEY is not set`
  Set the environment variable before running the script.

- `AI quota reached` or `429`
  Your OpenRouter plan or model quota has been exceeded. Wait for reset, add credits, or switch to another model.

- Chrome driver fails to start
  Make sure Chrome is installed and compatible with the `version_main` value used by `undetected-chromedriver`.
