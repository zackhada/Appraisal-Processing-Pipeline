#!/usr/bin/env python3
"""
Appraisal PDF Extraction - AI-Powered Real Estate Document Processing

A comprehensive automation system for extracting structured data from real estate 
appraisal PDFs using advanced AI technologies, web scraping, and cloud processing.
This system demonstrates cutting-edge document processing, computer vision, and 
enterprise-scale data extraction capabilities.

Key Features:
- Selenium-based web scraping for automated document discovery
- LlamaParse integration for advanced PDF text extraction
- OpenAI GPT-4 powered structured data extraction
- Azure Blob Storage integration for scalable document processing
- Complex schema validation for appraisal comparables
- Automated document classification and metadata extraction
- Real-time progress tracking and error handling

Author: Zachary Hada
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import pandas as pd
from dataclasses import dataclass

# Web scraping and automation
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# AI and document processing
import openai
from llama_parse import LlamaParse

# Azure cloud services
from azure.storage.blob import BlobServiceClient

# Environment and utilities
from dotenv import load_dotenv
import re
import io
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('appraisal_processing.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@dataclass
class AppraisalDocument:
    """Data class for appraisal document metadata."""
    loan_id: str
    filename: str
    blob_path: str
    file_size: int
    upload_date: str
    processing_status: str = "pending"
    extraction_data: Optional[Dict] = None
    error_message: Optional[str] = None

@dataclass
class ExtractionProgress:
    """Data class for tracking extraction progress."""
    total_documents: int
    processed_documents: int
    successful_extractions: int
    failed_extractions: int
    current_document: str
    start_time: datetime
    estimated_completion: Optional[datetime] = None

class WebScrapingEngine:
    """
    Advanced web scraping engine for automated document discovery.
    Handles authentication, navigation, and document extraction from web portals.
    """
    
    def __init__(self):
        self.driver = None
        self.download_dir = None
        self.setup_driver()
    
    def setup_driver(self):
        """Configure Chrome WebDriver with optimized settings."""
        self.download_dir = os.path.join(os.getcwd(), "downloads")
        os.makedirs(self.download_dir, exist_ok=True)
        
        options = webdriver.ChromeOptions()
        
        # Performance optimizations
        options.add_argument('--disable-gpu')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-extensions')
        options.add_argument('--disable-background-timer-throttling')
        options.add_argument('--disable-backgrounding-occluded-windows')
        options.add_argument('--disable-renderer-backgrounding')
        
        # Headless mode for production
        if os.getenv('HEADLESS_MODE', '').lower() == 'true':
            options.add_argument('--headless')
            logger.info("🔍 Running in headless mode")
        else:
            options.add_argument('--start-maximized')
            logger.info("🖥️ Running with GUI")
        
        # Download preferences
        prefs = {
            "download.default_directory": self.download_dir,
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "plugins.always_open_pdf_externally": True
        }
        options.add_experimental_option("prefs", prefs)
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.set_window_size(1920, 1080)
        logger.info(f"📁 Downloads directory: {self.download_dir}")
    
    def authenticate(self, username: str, password: str, login_url: str) -> bool:
        """Authenticate with the web portal."""
        try:
            logger.info("🚀 Logging in to portal...")
            self.driver.get(login_url)
            
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "employeeId"))
            )
            password_field = self.driver.find_element(By.ID, "password")
            
            username_field.send_keys(username)
            password_field.send_keys(password)
            password_field.send_keys("\n")
            
            time.sleep(3)
            logger.info("✅ Authentication successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Authentication failed: {e}")
            return False
    
    def navigate_to_pipeline(self) -> bool:
        """Navigate to the loan pipeline interface."""
        try:
            logger.info("📋 Navigating to pipeline...")
            
            # Navigate to Pipelines
            pipelines_nav = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//div[contains(@class, 'NavIconContainer')]//div[text()='Pipelines']"))
            )
            self.driver.execute_script("arguments[0].click();", pipelines_nav)
            time.sleep(2)
            
            # Click My Pipeline
            my_pipeline_link = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.XPATH, "//a[@href='/MyPipeline.aspx']"))
            )
            self.driver.execute_script("arguments[0].click();", my_pipeline_link)
            time.sleep(2)
            
            # Apply Post Funding filter
            post_funding_link = WebDriverWait(self.driver, 8).until(
                EC.element_to_be_clickable((By.ID, "lnkStage2566"))
            )
            self.driver.execute_script("arguments[0].click();", post_funding_link)
            time.sleep(2)
            
            logger.info("✅ Pipeline navigation successful")
            return True
            
        except Exception as e:
            logger.error(f"❌ Pipeline navigation failed: {e}")
            return False
    
    def discover_appraisal_documents(self, processed_loan_ids: set = None) -> List[Dict]:
        """
        Discover appraisal documents across all loans in the pipeline.
        Uses advanced filtering to identify construction appraisal reports.
        """
        discovered_documents = []
        processed_loan_ids = processed_loan_ids or set()
        
        try:
            # Find all unprocessed loans
            unprocessed_loans = self._find_unprocessed_loans(processed_loan_ids)
            logger.info(f"🔍 Found {len(unprocessed_loans)} unprocessed loans")
            
            for loan_info in unprocessed_loans:
                loan_id = loan_info['loan_id']
                logger.info(f"📊 Processing loan: {loan_id}")
                
                # Navigate to loan details
                if self._navigate_to_loan(loan_info):
                    # Extract appraisal documents
                    documents = self._extract_appraisal_documents_from_loan(loan_id)
                    discovered_documents.extend(documents)
                    
                    # Navigate to next loan
                    if not self._navigate_to_next_loan():
                        break
            
            logger.info(f"📄 Discovered {len(discovered_documents)} appraisal documents")
            return discovered_documents
            
        except Exception as e:
            logger.error(f"❌ Document discovery failed: {e}")
            return []
    
    def _find_unprocessed_loans(self, processed_loan_ids: set) -> List[Dict]:
        """Find loans that haven't been processed yet."""
        loan_elements = self.driver.find_elements(By.XPATH, "//a[contains(@id, 'btnloanIdclick')]")
        unprocessed_loans = []
        
        for element in loan_elements:
            try:
                loan_id = element.text.strip()
                if loan_id and loan_id not in processed_loan_ids:
                    unprocessed_loans.append({
                        'loan_id': loan_id,
                        'element': element
                    })
            except Exception as e:
                logger.warning(f"⚠️ Error processing loan element: {e}")
                continue
        
        return unprocessed_loans
    
    def _navigate_to_loan(self, loan_info: Dict) -> bool:
        """Navigate to a specific loan details page."""
        try:
            loan_element = loan_info['element']
            self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", loan_element)
            time.sleep(1)
            self.driver.execute_script("arguments[0].click();", loan_element)
            time.sleep(5)
            
            # Verify navigation
            WebDriverWait(self.driver, 15).until(
                EC.presence_of_element_located((By.ID, "headerLoanID"))
            )
            return True
            
        except Exception as e:
            logger.error(f"❌ Navigation to loan failed: {e}")
            return False
    
    def _extract_appraisal_documents_from_loan(self, loan_id: str) -> List[Dict]:
        """Extract appraisal documents from current loan page."""
        documents = []
        
        try:
            # Click Needs button
            needs_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.ID, "SubNavNeeds"))
            )
            self.driver.execute_script("arguments[0].click();", needs_button)
            time.sleep(3)
            
            # Find appraisal report sections
            page_source = self.driver.page_source
            soup = BeautifulSoup(page_source, 'html.parser')
            
            target_rows = self._find_appraisal_rows(soup)
            
            for row in target_rows:
                doc_spans = row.find_all('span', onclick=lambda x: x and 'openNeedDocs' in x)
                
                if doc_spans:
                    first_span = doc_spans[0]
                    onclick = first_span.get('onclick', '')
                    
                    match = re.search(r"openNeedDocs\('([^']+)','([^']+)'\)", onclick)
                    if match:
                        need_id = match.group(1)
                        doc_id = match.group(2)
                        
                        # Download documents from modal
                        downloaded_docs = self._download_from_modal(need_id, doc_id, loan_id)
                        documents.extend(downloaded_docs)
            
            return documents
            
        except Exception as e:
            logger.error(f"❌ Document extraction failed for loan {loan_id}: {e}")
            return []
    
    def _find_appraisal_rows(self, soup: BeautifulSoup) -> List:
        """Find rows containing appraisal reports using advanced filtering."""
        target_rows = []
        all_rows = soup.find_all('tr', class_='need')
        
        for row in all_rows:
            row_text = row.get_text()
            
            # Primary search: Construction + Appraisal
            has_construction = any(keyword in row_text for keyword in [
                "LO-LOI Accepted-Construction - Ground Up Sale",
                "Construction - Ground Up Sale",
                "Construction"
            ])
            has_appraisal = any(keyword in row_text for keyword in [
                "Appraisal Report",
                "Appraisal"
            ])
            
            # Secondary search: Value types
            has_value_type = any(keyword in row_text for keyword in [
                "As Is", "ARV", "Subject To", "Completed"
            ])
            
            if (has_construction and has_appraisal) or (has_appraisal and has_value_type):
                target_rows.append(row)
        
        return target_rows
    
    def _download_from_modal(self, need_id: str, doc_id: str, loan_id: str) -> List[Dict]:
        """Download documents from modal dialog."""
        downloaded_docs = []
        
        try:
            # Open modal
            script = f"openNeedDocs('{need_id}', '{doc_id}');"
            self.driver.execute_script(script)
            time.sleep(3)
            
            # Wait for modal content
            WebDriverWait(self.driver, 8).until(
                EC.presence_of_element_located((By.CLASS_NAME, "modal-content"))
            )
            
            # Find downloadable files
            open_doc_buttons = self.driver.find_elements(By.XPATH, "//button[contains(@onclick, 'openDoc')]")
            
            for i, button in enumerate(open_doc_buttons):
                try:
                    # Extract filename from onclick
                    onclick = button.get_attribute('onclick')
                    filename_match = re.search(r"openDoc\('[^']*','[^']*','([^']*)'\)", onclick)
                    filename = filename_match.group(1) if filename_match else f"appraisal_{i+1}.pdf"
                    
                    logger.info(f"⬇️ Downloading: {filename}")
                    
                    # Download file
                    initial_files = set(os.listdir(self.download_dir)) if os.path.exists(self.download_dir) else set()
                    self.driver.execute_script("arguments[0].click();", button)
                    
                    # Wait for download completion
                    actual_filename = self._wait_for_download(initial_files)
                    
                    if actual_filename:
                        doc_info = {
                            'loan_id': loan_id,
                            'need_id': need_id,
                            'doc_id': doc_id,
                            'filename': filename,
                            'actual_filename': actual_filename,
                            'local_path': os.path.join(self.download_dir, actual_filename),
                            'section': 'Appraisal Report - Construction',
                            'download_successful': True
                        }
                        downloaded_docs.append(doc_info)
                        logger.info(f"✅ Downloaded: {actual_filename}")
                    
                    time.sleep(2)
                    
                except Exception as e:
                    logger.error(f"⚠️ Error downloading file {i+1}: {e}")
                    continue
            
            # Close modal
            self._close_modal()
            
            return downloaded_docs
            
        except Exception as e:
            logger.error(f"❌ Modal download failed: {e}")
            return []
    
    def _wait_for_download(self, initial_files: set, timeout: int = 15) -> Optional[str]:
        """Wait for file download to complete and return the filename."""
        for _ in range(timeout):
            time.sleep(1)
            if os.path.exists(self.download_dir):
                current_files = set(os.listdir(self.download_dir))
                new_files = current_files - initial_files
                
                for new_file in new_files:
                    if not new_file.endswith(('.crdownload', '.tmp')):
                        file_path = os.path.join(self.download_dir, new_file)
                        try:
                            if os.path.getsize(file_path) > 1024:  # File has content
                                return new_file
                        except:
                            continue
        return None
    
    def _close_modal(self):
        """Close modal dialog using multiple methods."""
        try:
            # Try multiple close selectors
            close_selectors = [
                "//button[@class='close']",
                "//button[contains(@class, 'close')]",
                "//*[@data-dismiss='modal']",
                "//button[contains(text(), 'Close')]"
            ]
            
            for selector in close_selectors:
                try:
                    close_buttons = self.driver.find_elements(By.XPATH, selector)
                    for button in close_buttons:
                        if button.is_displayed() and button.is_enabled():
                            self.driver.execute_script("arguments[0].click();", button)
                            time.sleep(2)
                            return
                except:
                    continue
            
            # Force close with JavaScript
            self.driver.execute_script("""
                $('.modal').modal('hide');
                $('.modal-backdrop').remove();
                document.body.classList.remove('modal-open');
            """)
            
        except Exception as e:
            logger.warning(f"⚠️ Modal close error: {e}")
    
    def _navigate_to_next_loan(self) -> bool:
        """Navigate to the next loan in the pipeline."""
        try:
            next_buttons = self.driver.find_elements(By.CLASS_NAME, "SubNavNext")
            for btn in next_buttons:
                if btn.is_displayed() and btn.is_enabled():
                    onclick_attr = btn.get_attribute('onclick')
                    if onclick_attr and "loadIndex2(" in onclick_attr and "loadIndex2('')" not in onclick_attr:
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(5)
                        return True
            return False
        except:
            return False
    
    def cleanup(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()

class AIDocumentProcessor:
    """
    Advanced AI-powered document processing engine.
    Integrates LlamaParse for PDF extraction and OpenAI for structured data extraction.
    """
    
    def __init__(self):
        self.llama_parser = None
        self.openai_client = None
        self.schema = None
        self._initialize_ai_services()
        self._load_extraction_schema()
    
    def _initialize_ai_services(self):
        """Initialize AI services with API keys."""
        try:
            # Initialize LlamaParse
            llama_api_key = os.getenv("LLAMA_CLOUD_API_KEY")
            if llama_api_key:
                self.llama_parser = LlamaParse(
                    api_key=llama_api_key,
                    result_type="markdown",
                    verbose=True,
                    language="en"
                )
                logger.info("✅ LlamaParse initialized")
            else:
                logger.warning("⚠️ LLAMA_CLOUD_API_KEY not found")
            
            # Initialize OpenAI
            openai_api_key = os.getenv("OPENAI_API_KEY")
            if openai_api_key:
                self.openai_client = openai.OpenAI(api_key=openai_api_key)
                logger.info("✅ OpenAI initialized")
            else:
                logger.warning("⚠️ OPENAI_API_KEY not found")
                
        except Exception as e:
            logger.error(f"❌ AI services initialization failed: {e}")
    
    def _load_extraction_schema(self):
        """Load the comprehensive appraisal extraction schema."""
        self.schema = {
            "properties": {
                "Filename": {"type": "string"},
                "Appraisal Form Type": {"type": "string"},
                "Subject Property Address": {"type": "string"},
                "Effective Date of Appraisal": {"type": "string", "format": "date"},
                "Appraiser Name": {"type": "string"},
                "Borrower Name": {"type": "string"},
                "Subject Additional Square Footage": {"type": "string"},
                "Document Title": {"type": "string"},
                "Subject Property Value": {"type": "number"},
                "As-Is Value": {"type": "number"},
                "ARV Value": {"type": "number"},
                "Sales Comparables": {"type": "array"},
                "ARV Comparables": {"type": "array"},
                "Land Comparables": {"type": "array"},
                "Other Comparables": {"type": "array"}
            },
            "required": [
                "Filename", "Appraisal Form Type", "Subject Property Address",
                "Subject Additional Square Footage", "Document Title",
                "Effective Date of Appraisal", "Appraiser Name", "Borrower Name",
                "Subject Property Value", "As-Is Value", "ARV Value",
                "Sales Comparables", "ARV Comparables", "Land Comparables", "Other Comparables"
            ]
        }
    
    def extract_text_from_pdf(self, file_path: str) -> Optional[str]:
        """Extract text from PDF using LlamaParse."""
        try:
            if not self.llama_parser:
                logger.error("❌ LlamaParse not initialized")
                return None
            
            logger.info(f"📄 Extracting text from: {os.path.basename(file_path)}")
            
            # Parse document
            documents = self.llama_parser.load_data(file_path)
            
            if documents:
                extracted_text = "\n".join([doc.text for doc in documents])
                logger.info(f"✅ Extracted {len(extracted_text)} characters")
                return extracted_text
            else:
                logger.warning("⚠️ No text extracted from PDF")
                return None
                
        except Exception as e:
            logger.error(f"❌ PDF text extraction failed: {e}")
            return None
    
    def extract_structured_data(self, text: str, filename: str) -> Dict:
        """
        Extract structured data from appraisal text using AI.
        Implements comprehensive schema validation and comparable analysis.
        """
        try:
            if not self.openai_client:
                logger.error("❌ OpenAI client not initialized")
                return {"error": "OpenAI client not available"}
            
            logger.info("🤖 Performing AI-powered data extraction...")
            
            prompt = self._generate_extraction_prompt()
            
            # Make API call to OpenAI
            response = self.openai_client.chat.completions.create(
                model="gpt-4-1106-preview",
                messages=[
                    {"role": "system", "content": "You are an expert real estate appraisal analyst."},
                    {"role": "user", "content": f"{prompt}\n\nDocument filename: {filename}\n\nDocument text:\n{text}"}
                ],
                temperature=0.1,
                max_tokens=4000
            )
            
            result = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                extracted_data = json.loads(result)
                extracted_data["Filename"] = filename
                
                # Validate against schema
                validation_result = self._validate_extraction(extracted_data)
                if validation_result["valid"]:
                    logger.info("✅ Data extraction and validation successful")
                    return extracted_data
                else:
                    logger.warning(f"⚠️ Validation warnings: {validation_result['warnings']}")
                    return extracted_data  # Return data with warnings
                    
            except json.JSONDecodeError:
                # Try to extract JSON from response
                json_start = result.find('{')
                json_end = result.rfind('}') + 1
                if json_start != -1 and json_end != 0:
                    extracted_data = json.loads(result[json_start:json_end])
                    extracted_data["Filename"] = filename
                    return extracted_data
                else:
                    return {"error": f"Could not parse AI response as JSON: {result}"}
                    
        except Exception as e:
            logger.error(f"❌ Structured data extraction failed: {e}")
            return {"error": str(e)}
    
    def _generate_extraction_prompt(self) -> str:
        """Generate comprehensive extraction prompt for AI."""
        return """
You are an expert data extraction specialist for real estate appraisal documents. 
Analyze the entire document thoroughly and extract structured data following this exact JSON schema.

Return ONLY a valid JSON object with this structure:

{
  "Appraisal Form Type": "Form designation (Fannie Mae Form 1004, 2055, 1025, 1073, 1075, GP2-4, GPLND)",
  "Subject Property Address": "Full property address",
  "Effective Date of Appraisal": "YYYY-MM-DD format",
  "Appraiser Name": "Name of appraiser",
  "Borrower Name": "Entity name of borrower",
  "Subject Additional Square Footage": "Numeric value for ADU/basement/casita sq ft",
  "Document Title": "Title on first page",
  "Subject Property Value": 000000,
  "As-Is Value": 000000,
  "ARV Value": 000000,
  "Sales Comparables": [
    {
      "Comp Address": "Address",
      "Comp Bed Count": 0,
      "Comp Bath Count": 0,
      "Comp GLA": 0000,
      "Comp Sale Price": 000000,
      "Comp Adjusted Sale Price": 000000,
      "Comp Sale Date": "YYYY-MM-DD",
      "Comp Data Source": "MLS/Public Records/etc",
      "Comp Lot Size": 0000,
      "Comp List of Amenities": "Description",
      "Comp Distance": "0.25 miles",
      "As-Is/ARV": "As-Is or ARV",
      "Comp Additional Square Footage": "0",
      "Comp Number and Type": "Sales Comparable #1"
    }
  ],
  "ARV Comparables": [...],
  "Land Comparables": [...],
  "Other Comparables": [...]
}

CRITICAL EXTRACTION RULES:

**Appraisal Form Type**: Search for exact text "Fannie Mae Form XXXX" or "Form GP2-4" or "Form GPLND"
Only return these valid options: "Fannie Mae Form 1004", "Fannie Mae Form 2055", "Fannie Mae Form 1025", 
"Fannie Mae Form 1073", "Fannie Mae Form 1075", "Form GP2-4", "Form GPLND"

**As-Is Value and ARV Value Logic**:
Check the reconciliation section box that starts with "This appraisal is made":
- Box 1 ("as is"): As-Is value in reconciliation, ARV in comments/addendum
- Box 2-4 (subject to completion/repairs): ARV in reconciliation, As-Is in comments/addendum

**Comparable Types and Extraction**:
- Sales Comparables: Regular market sales for current value
- ARV Comparables: Properties for after-repair value analysis
- Land Comparables: Land sales for land value analysis
- Other Comparables: Rental comps, listings, etc.

For each comparable extract ALL fields:
- Address, bed/bath count, GLA, sale price, adjusted price, sale date
- Data source, lot size, amenities list, distance from subject
- Whether As-Is or ARV type, additional square footage
- Comparable number and section type

**Distance Extraction**: Look for distance measurements on location maps or in comparable descriptions
**Additional Square Footage**: Find basement, ADU, casita square footage for each comparable

Return null for missing numeric values, empty string for missing text values.
Ensure all comparable arrays have complete data structures even if some fields are empty.
"""
    
    def _validate_extraction(self, data: Dict) -> Dict:
        """Validate extracted data against schema."""
        warnings = []
        
        # Check required fields
        required_fields = self.schema["required"]
        for field in required_fields:
            if field not in data:
                warnings.append(f"Missing required field: {field}")
        
        # Validate appraisal form type
        valid_forms = [
            "Fannie Mae Form 1004", "Fannie Mae Form 2055", "Fannie Mae Form 1025",
            "Fannie Mae Form 1073", "Fannie Mae Form 1075", "Form GP2-4", "Form GPLND"
        ]
        form_type = data.get("Appraisal Form Type", "")
        if form_type and not any(valid_form in form_type for valid_form in valid_forms):
            warnings.append(f"Invalid appraisal form type: {form_type}")
        
        # Validate comparable structures
        comparable_types = ["Sales Comparables", "ARV Comparables", "Land Comparables", "Other Comparables"]
        for comp_type in comparable_types:
            comps = data.get(comp_type, [])
            if isinstance(comps, list):
                for i, comp in enumerate(comps):
                    if not isinstance(comp, dict):
                        warnings.append(f"{comp_type}[{i}] is not a dictionary")
                    elif not comp.get("Comp Address"):
                        warnings.append(f"{comp_type}[{i}] missing address")
        
        return {
            "valid": len(warnings) == 0,
            "warnings": warnings
        }

class AzureStorageManager:
    """
    Azure Blob Storage manager for scalable document processing.
    Handles uploads, downloads, and metadata management.
    """
    
    def __init__(self):
        self.connection_string = os.getenv('AZURE_CONNECTION_STRING')
        self.container_name = 'appraisals'
        self.blob_folder = 'processed_appraisals/'
        
        if not self.connection_string:
            logger.warning("⚠️ AZURE_CONNECTION_STRING not found - Azure uploads disabled")
            self.blob_service_client = None
        else:
            try:
                self.blob_service_client = BlobServiceClient.from_connection_string(self.connection_string)
                logger.info(f"✅ Connected to Azure storage - container: {self.container_name}")
            except Exception as e:
                logger.error(f"❌ Azure connection failed: {e}")
                self.blob_service_client = None
    
    def get_processed_loan_ids(self) -> set:
        """Get set of loan IDs that have already been processed."""
        if not self.blob_service_client:
            return set()
        
        try:
            logger.info("🔍 Checking Azure for processed loans...")
            container_client = self.blob_service_client.get_container_client(self.container_name)
            
            blobs = container_client.list_blobs(name_starts_with=self.blob_folder)
            processed_loan_ids = set()
            
            for blob in blobs:
                blob_path = blob.name
                if blob_path.startswith(self.blob_folder):
                    remaining_path = blob_path[len(self.blob_folder):]
                    if '/' in remaining_path:
                        loan_id = remaining_path.split('/')[0]
                        if loan_id:
                            processed_loan_ids.add(loan_id)
            
            logger.info(f"✅ Found {len(processed_loan_ids)} processed loans")
            return processed_loan_ids
            
        except Exception as e:
            logger.error(f"❌ Error checking processed loans: {e}")
            return set()
    
    def upload_document(self, local_file_path: str, loan_id: str, filename: str = None) -> bool:
        """Upload document to Azure Blob Storage."""
        if not self.blob_service_client:
            return False
        
        try:
            if not os.path.exists(local_file_path):
                logger.error(f"❌ File not found: {local_file_path}")
                return False
            
            filename = filename or os.path.basename(local_file_path)
            blob_name = f"{self.blob_folder}{loan_id}/{filename}"
            
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            
            with open(local_file_path, "rb") as data:
                blob_client.upload_blob(data, overwrite=True)
            
            logger.info(f"☁️ Uploaded: {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Upload error: {e}")
            return False
    
    def upload_extraction_results(self, results: Dict, loan_id: str) -> bool:
        """Upload extraction results as JSON to Azure."""
        if not self.blob_service_client:
            return False
        
        try:
            results_json = json.dumps(results, indent=2)
            blob_name = f"{self.blob_folder}{loan_id}/extraction_results.json"
            
            blob_client = self.blob_service_client.get_blob_client(
                container=self.container_name,
                blob=blob_name
            )
            
            blob_client.upload_blob(results_json, overwrite=True)
            logger.info(f"☁️ Uploaded extraction results for loan {loan_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Results upload error: {e}")
            return False

class AppraisalProcessingPipeline:
    """
    Main orchestration class for the complete appraisal processing pipeline.
    Coordinates web scraping, AI processing, and cloud storage operations.
    """
    
    def __init__(self):
        self.web_scraper = WebScrapingEngine()
        self.ai_processor = AIDocumentProcessor()
        self.azure_manager = AzureStorageManager()
        self.progress = None
        
    def run_complete_pipeline(self, max_loans: int = None) -> Dict:
        """
        Run the complete appraisal processing pipeline.
        
        Args:
            max_loans: Maximum number of loans to process (None = all)
            
        Returns:
            Dictionary with processing results and statistics
        """
        start_time = datetime.now()
        logger.info("🚀 Starting Appraisal Processing Pipeline")
        logger.info("=" * 60)
        
        try:
            # Step 1: Authentication
            username = os.getenv("NOVA_USERNAME")
            password = os.getenv("NOVA_PASSWORD")
            login_url = "https://ascentds.liquidlogics.com/#TeamMemberLogin"
            
            if not self.web_scraper.authenticate(username, password, login_url):
                return {"error": "Authentication failed"}
            
            # Step 2: Navigate to pipeline
            if not self.web_scraper.navigate_to_pipeline():
                return {"error": "Pipeline navigation failed"}
            
            # Step 3: Get processed loans from Azure
            processed_loan_ids = self.azure_manager.get_processed_loan_ids()
            
            # Step 4: Discover documents
            logger.info("📥 Discovering appraisal documents...")
            discovered_docs = self.web_scraper.discover_appraisal_documents(processed_loan_ids)
            
            if max_loans:
                discovered_docs = discovered_docs[:max_loans]
            
            # Step 5: Process documents
            processing_results = self._process_documents(discovered_docs)
            
            # Step 6: Generate summary
            end_time = datetime.now()
            processing_time = end_time - start_time
            
            summary = {
                "pipeline_start_time": start_time.isoformat(),
                "pipeline_end_time": end_time.isoformat(),
                "total_processing_time": str(processing_time),
                "documents_discovered": len(discovered_docs),
                "documents_processed": processing_results["processed"],
                "successful_extractions": processing_results["successful"],
                "failed_extractions": processing_results["failed"],
                "success_rate": f"{(processing_results['successful'] / max(processing_results['processed'], 1)) * 100:.1f}%",
                "detailed_results": processing_results["results"]
            }
            
            # Save summary
            self._save_processing_summary(summary)
            
            logger.info("✅ Pipeline completed successfully")
            logger.info(f"📊 Processed: {processing_results['processed']} documents")
            logger.info(f"✨ Success rate: {summary['success_rate']}")
            
            return summary
            
        except Exception as e:
            logger.error(f"❌ Pipeline failed: {e}")
            return {"error": str(e)}
        
        finally:
            self.web_scraper.cleanup()
    
    def _process_documents(self, documents: List[Dict]) -> Dict:
        """Process all discovered documents with AI extraction."""
        results = {
            "processed": 0,
            "successful": 0,
            "failed": 0,
            "results": []
        }
        
        total_docs = len(documents)
        logger.info(f"📄 Processing {total_docs} documents...")
        
        for i, doc_info in enumerate(documents, 1):
            logger.info(f"🔄 Processing document {i}/{total_docs}: {doc_info['filename']}")
            
            try:
                # Extract text from PDF
                local_path = doc_info['local_path']
                extracted_text = self.ai_processor.extract_text_from_pdf(local_path)
                
                if not extracted_text:
                    logger.warning(f"⚠️ No text extracted from {doc_info['filename']}")
                    results["failed"] += 1
                    continue
                
                # Extract structured data
                structured_data = self.ai_processor.extract_structured_data(
                    extracted_text, 
                    doc_info['filename']
                )
                
                if "error" in structured_data:
                    logger.error(f"❌ Extraction error: {structured_data['error']}")
                    results["failed"] += 1
                    continue
                
                # Upload to Azure
                loan_id = doc_info['loan_id']
                
                # Upload original document
                self.azure_manager.upload_document(
                    local_path, 
                    loan_id, 
                    doc_info['filename']
                )
                
                # Upload extraction results
                self.azure_manager.upload_extraction_results(structured_data, loan_id)
                
                # Store result
                processing_result = {
                    "loan_id": loan_id,
                    "filename": doc_info['filename'],
                    "processing_time": datetime.now().isoformat(),
                    "text_length": len(extracted_text),
                    "extraction_successful": True,
                    "extracted_data": structured_data
                }
                
                results["results"].append(processing_result)
                results["successful"] += 1
                
                logger.info(f"✅ Successfully processed: {doc_info['filename']}")
                
            except Exception as e:
                logger.error(f"❌ Processing failed for {doc_info['filename']}: {e}")
                
                error_result = {
                    "loan_id": doc_info.get('loan_id', 'unknown'),
                    "filename": doc_info['filename'],
                    "processing_time": datetime.now().isoformat(),
                    "extraction_successful": False,
                    "error": str(e)
                }
                
                results["results"].append(error_result)
                results["failed"] += 1
            
            results["processed"] += 1
            
            # Progress update
            progress_pct = (i / total_docs) * 100
            logger.info(f"📊 Progress: {progress_pct:.1f}% ({i}/{total_docs})")
        
        return results
    
    def _save_processing_summary(self, summary: Dict):
        """Save processing summary to local file and Azure."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"appraisal_processing_summary_{timestamp}.json"
        
        # Save locally
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        logger.info(f"💾 Summary saved: {filename}")
        
        # Upload to Azure
        if self.azure_manager.blob_service_client:
            try:
                blob_name = f"processing_summaries/{filename}"
                blob_client = self.azure_manager.blob_service_client.get_blob_client(
                    container=self.azure_manager.container_name,
                    blob=blob_name
                )
                
                with open(filename, "rb") as data:
                    blob_client.upload_blob(data, overwrite=True)
                
                logger.info("☁️ Summary uploaded to Azure")
                
            except Exception as e:
                logger.warning(f"⚠️ Azure summary upload failed: {e}")

def main():
    """
    Main execution function for the Appraisal Processing Pipeline.
    Demonstrates the complete end-to-end automation system.
    """
    print("🏗️ APPRAISAL PDF EXTRACTION PIPELINE")
    print("=" * 60)
    print("🤖 AI-Powered Real Estate Document Processing")
    print("🔧 Technologies: Selenium, LlamaParse, OpenAI GPT-4, Azure")
    print("=" * 60)
    
    # Initialize pipeline
    pipeline = AppraisalProcessingPipeline()
    
    # Configuration
    max_loans = int(os.getenv('MAX_LOANS', '0')) or None
    if max_loans:
        print(f"🎯 Processing mode: Limited to {max_loans} loans")
    else:
        print("🎯 Processing mode: All available loans")
    
    # Run pipeline
    try:
        results = pipeline.run_complete_pipeline(max_loans=max_loans)
        
        if "error" not in results:
            print("\n🎉 PIPELINE COMPLETED SUCCESSFULLY!")
            print(f"📊 Documents processed: {results['documents_processed']}")
            print(f"✅ Successful extractions: {results['successful_extractions']}")
            print(f"❌ Failed extractions: {results['failed_extractions']}")
            print(f"📈 Success rate: {results['success_rate']}")
            print(f"⏱️ Total time: {results['total_processing_time']}")
            print(f"☁️ Results uploaded to Azure Blob Storage")
        else:
            print(f"❌ Pipeline failed: {results['error']}")
    
    except KeyboardInterrupt:
        print("\n⚠️ Pipeline interrupted by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
