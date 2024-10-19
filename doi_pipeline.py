import os
import re
import sys
import unicodedata
import pdfplumber
import requests
import openai

openai.api_key = os.getenv("OPENAI_API_KEY") #API KEY GOES HERE
 
def call_openai_api_with_retry(api_function, *args, **kwargs):
    max_retries = 5
    for attempt in range(max_retries):
        try:
            return api_function(*args, **kwargs)
        except Exception as e:
            print(f"exception during API call: {e}")
            return None
    print("max retries exceeded.")
    return None

def extract_doi_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            num_pages_to_check = min(5, len(pdf.pages))
            for page_number in range(num_pages_to_check):
                page = pdf.pages[page_number]
                text = page.extract_text()
                if not text:
                    continue
                text = unicodedata.normalize('NFKD', text)
                text = text.encode('ascii', 'ignore').decode('ascii')
                text = text.replace('\n', ' ')
                text = re.sub(r'\s+', ' ', text)
                text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
                doi_pattern = re.compile(
                    r'(10\.\d{4,9}/[^\s"<>]+)',
                    re.IGNORECASE
                )
                matches = doi_pattern.findall(text)
                if matches:
                    doi = max(matches, key=len)
                    doi = doi.rstrip('.,;:')
                    print(f"extracted doi from {pdf_path}: {doi}")
                    crossref_title = get_title_crossref(doi)
                    if crossref_title:
                        return doi, crossref_title, False
                    else:
                        break
            collected_text = ''
            num_pages_to_collect = min(3, len(pdf.pages))
            for page_number in range(num_pages_to_collect):
                page = pdf.pages[page_number]
                text = page.extract_text()
                if text:
                    text = unicodedata.normalize('NFKD', text)
                    text = text.encode('ascii', 'ignore').decode('ascii')
                    text = text.replace('\n', ' ')
                    text = re.sub(r'\s+', ' ', text)
                    text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
                    collected_text += text + ' '
            collected_text = collected_text[:3000]
            used_chatgpt_doi_extraction = True
            doi = get_doi_from_chatgpt(collected_text)
            if doi:
                print(f"doi extracted by ChatGPT from {pdf_path}: {doi}")
                crossref_title = get_title_crossref(doi)
                if crossref_title:
                    return doi, crossref_title, used_chatgpt_doi_extraction
                else:
                    print(f"Invalid DOI extracted by GPT: {doi}")
                    return None, None, used_chatgpt_doi_extraction
            else:
                print(f"gpt could not get doi: {pdf_path}")
                return None, None, used_chatgpt_doi_extraction
    except Exception as e:
        print(f"exeption: {pdf_path}: {e}")
        return None, None, False

def get_doi_from_chatgpt(pdf_text):
    try:
        messages = [
            {"role": "system", "content": "You are an assistant that extracts the DOI from provided text of a research paper."},
            {"role": "user", "content": f"Extract and provide only the DOI of the research paper from the following text. If the DOI is not present, reply 'DOI not found'.\n\n{pdf_text}\n\nDOI:"}
        ]
        response = call_openai_api_with_retry(
            openai.ChatCompletion.create,
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=50,
            temperature=0
        )
        if response:
            doi = response['choices'][0]['message']['content'].strip()
            print(f"DOI from gpt: {doi}")
            if "doi not found" in doi.lower():
                return None
            else:
                return doi
        else:
            return None
    except Exception as e:
        print(f"exception raised while getting doi from gpt: {e}")
        return None

def get_title_crossref(doi):
    try:
        url = f'https://api.crossref.org/works/{doi}'
        response = requests.get(url)
        print(f"CrossRef response for DOI {doi}: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            if 'title' in data['message'] and data['message']['title']:
                title = data['message']['title'][0]
                print(f"Title from CrossRef: {title}")
                return title.strip()
            else:
                print(f"No title found in CrossRef response for DOI {doi}")
                return None
        else:
            print(f"Failed to retrieve data from CrossRef for DOI {doi}")
            return None
    except Exception as e:
        print(f"exception while using crossref for title {doi}: {e}")
        return None

def get_title_chatgpt(pdf_text):
    try:
        pdf_text = pdf_text[:3000]
        messages = [
            {"role": "system", "content": "You extract the title of research papers from provided text."},
            {"role": "user", "content": f"Extract and provide only the title of the research paper from the following text:\n\n{pdf_text}\n\nTitle:"}
        ]
        response = call_openai_api_with_retry(
            openai.ChatCompletion.create,
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=100,
            temperature=0
        )
        if response:
            title = response['choices'][0]['message']['content'].strip()
            print(f"Title from ChatGPT: {title}")
            return title
        else:
            return None
    except Exception as e:
        print(f"Exception in get_title_chatgpt: {e}")
        return None

def extract_title_from_pdf(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            first_page_text = pdf.pages[0].extract_text()
            if not first_page_text:
                print(f"No text extracted from first page of {pdf_path}")
                return None
            return first_page_text
    except Exception as e:
        print(f"Exception in extract_title_from_pdf for {pdf_path}: {e}")
        return None

def compare_titles_with_chatgpt(title1, title2):
    try:
        messages = [
            {"role": "system", "content": "You determine whether two titles refer to the same paper. You are not too strict, is the majority of the words match, the papers are a match. Ignore 'Supplementary material for'"},
            {"role": "user", "content": f"Do the following two titles refer to the same research paper?\n\nTitle 1: {title1}\nTitle 2: {title2}\n\nAnswer 'Yes' or 'No'."}
        ]
        response = call_openai_api_with_retry(
            openai.ChatCompletion.create,
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=5,
            temperature=0
        )
        if response:
            answer = response['choices'][0]['message']['content'].strip().lower()
            print(f"ChatGPT comparison result: {answer}")
            if 'yes' in answer:
                return True
            else:
                return False
        else:
            return False
    except Exception as e:
        print(f"Exception in compare_titles_with_chatgpt: {e}")
        return False

def main(folder_path):
    total_pdfs = 0
    successful_matches = 0
    num_used_chatgpt_doi_extraction = 0
    num_doi_not_found = 0
    num_failed_with_all_values_extracted = 0
    results = []
    for filename in os.listdir(folder_path):
        if filename.lower().endswith('.pdf'):
            pdf_path = os.path.join(folder_path, filename)
            print(f"\nProcessing {filename}...")
            doi, crossref_title, used_chatgpt_doi_extraction = extract_doi_from_pdf(pdf_path)
            if used_chatgpt_doi_extraction:
                num_used_chatgpt_doi_extraction += 1
            if not doi:
                num_doi_not_found += 1
                status = 'DOI not found'
                print(f"{filename}: {status}")
                results.append({
                    'filename': filename,
                    'doi': 'DOI not found',
                    'crossref_title': None,
                    'chatgpt_title': None,
                    'status': status
                })
                continue
            total_pdfs += 1
            pdf_text = extract_title_from_pdf(pdf_path)
            if not pdf_text:
                status = 'Fail (PDF text extraction failed)'
                num_failed_with_all_values_extracted += 1
                print(f"{filename}: {status}")
                results.append({
                    'filename': filename,
                    'doi': doi,
                    'crossref_title': crossref_title,
                    'chatgpt_title': None,
                    'status': status
                })
                continue
            chatgpt_title = get_title_chatgpt(pdf_text)
            if not chatgpt_title:
                status = 'Fail (ChatGPT title extraction failed)'
                num_failed_with_all_values_extracted += 1
                print(f"{filename}: {status}")
                results.append({
                    'filename': filename,
                    'doi': doi,
                    'crossref_title': crossref_title,
                    'chatgpt_title': None,
                    'status': status
                })
                continue
            titles_match = compare_titles_with_chatgpt(crossref_title, chatgpt_title)
            if titles_match:
                status = 'Success'
                successful_matches += 1
            else:
                status = 'Fail (Titles do not match)'
                num_failed_with_all_values_extracted +=1
            print(f"{filename}: {status}")
            results.append({
                'filename': filename,
                'doi': doi,
                'crossref_title': crossref_title,
                'chatgpt_title': chatgpt_title,
                'status': status
            })

    accuracy = (successful_matches / total_pdfs) * 100
    print(f"\nAccuracy: {accuracy:.2f}% ({successful_matches}/{total_pdfs})")
    print(f"Number of pdfs processed: {total_pdfs}")
    print(f"Number of successes: {successful_matches}")
    print(f"Number of times gpt was used to extract DOI: {num_used_chatgpt_doi_extraction}")
    print(f"Number of dois not found: {num_doi_not_found}")
    print(f"Number of title mismatch: {num_failed_with_all_values_extracted}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        folder_path = sys.argv[1]
    else:
        folder_path = input('Input your folder path here') #input forlder path here
    main(folder_path)
