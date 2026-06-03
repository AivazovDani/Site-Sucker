import os
from django.conf import settings
from celery import shared_task
from .models import Projects
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import httpx
import anthropic
from urllib.parse import urljoin, urlparse
import tempfile
import zipfile
import time
import threading
from anthropic import RateLimitError
from .utils import call_api_with_retry


@shared_task
def scrape(project_id):
    print('TASK STARTED, project_id:', project_id)
    project = Projects.objects.get(id=project_id)

    print('PROJECT FOUND:', project)
    print('URL:', project.website_link)
    project.status = 'proccessing'
    url = project.website_link
    
    project.save()
    print('STATUS SET TO PROCESSING')

    try:
        with tempfile.TemporaryDirectory() as temp_folder: # -> after excecution the tempfolder gets deleted and it leaves us with the relative paths only for every file, once we dowload the zip folder
            start = time.perf_counter()
            html = render_page(url)
            clean_urls = extract_assets(html, url)
            assets_map = download_assets(clean_urls, temp_folder)
            assets_map, html_path = clean_code(assets_map, html, temp_folder)
            html_content = rewrites_paths(assets_map, html_path)
            zipp_name = f'project_{project_id}.zip' # -> having the zip name as a veriable to reduce missunderstanding in the code
            zipped_path = zipp(temp_folder, zipp_name)
            end = time.perf_counter()
            print(f"Elapsed: {end - start:.4f}s")

            with open(zipped_path, 'rb') as f:

                project.cleaned_zip.save(zipp_name, f)

            
            project.status = 'ready'
            project.save()

    except Exception as e:
        project.status = 'failed'

        print('SCRAPE ERROR:', e)
        project.save()

def render_page(url): # Playwright
    with sync_playwright() as p: # -> gives you the playwright object
        browser = p.chromium.launch(headless=True) # -> gives you the browser with headless==True meaning - no window openning on start
        page = browser.new_page() # -> gives you the page
        page.goto(url) # -> navigates and waits for everything to load
        page.wait_for_load_state('networkidle')
        html = page.content() # -> returns the full rendered HTML

    
    return html


def extract_assets(html, base_url):
    soup = BeautifulSoup(html, 'html.parser')
    clean_urls = [] # -> storing the clean and absolute path urls with the css, js and img files we need

    for tag in soup.find_all('link', rel='stylesheet'):
        url = tag.get('href')
        if url:
            clean_urls.append(urljoin(base_url, url)) # -> Example: BaseUrl: https://example.com + AssetElement: style.css = https://example.com/style.css

    for tag in soup.find_all('script', src=True):
        url = tag.get('src')
        if url:
            clean_urls.append(urljoin(base_url, url))

    for tag in soup.find_all('img', src=True):
        url = tag.get('src')
        if url:
            clean_urls.append(urljoin(base_url, url))


    
    
    return clean_urls


def download_assets(clean_urls, temp_folder):
    asset_map = {} # Storing the relative path in the origial html and the full_path of the file inside tempfolder with the cleaned content: 'css/style.css': 'abc/123/style_css.css'
    lock = threading.Lock()

    def download_each_asset_threads(url):
        try:
            response = httpx.get(url, headers={
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'accept-language': 'en-US,en;q=0.9',
                'cache-control': 'max-age=0',
                }) # -> download the content inside the url: https://example.com/style/css.css + giving it proper headers to bypass basic security on websites

            filename = urlparse(url).path # -> get the path only: /style/css.css
            filename = filename.strip('/') # -> style.css | (prevention against absolute path vs relative path)
            filename = filename.replace('/', '_') # -> style_css | (avoid collisions with other files inside my mac)


            full_path = os.path.join(temp_folder, filename) # -> abc/123/style_css.css

            with open(full_path, 'wb') as f: # -> open the file in the tempfolder
                f.write(response.content) # -> write the original response and inertriate it as binary

            with lock: # allowing only one thread to right to the dict at a time
                asset_map[urlparse(url).path] = full_path # -> store the original path - tempfolder: 'style/css.css': 'abc/123/style_css.css'

        except:
            print('Error occured during download of each file')

    threads = []
    for url in  clean_urls:
        t = threading.Thread(target=download_each_asset_threads, args=(url, ))
        t.start() # start the threads one by one but effectivly all at ones
        threads.append(t)



    for t in threads: # waits for the threads to finish before continuing with the main code (calling it manually)
        t.join()
        

        # try/except to prevent errors to ruin our flow

    return asset_map



def clean_code(assets_map, html, temp_folder):
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY) # anthropic client

    def clean_file(relative_path, full_path):

        
        if full_path.endswith('.css'): # -> search for css file
            with open(full_path, 'r') as r:
                css_content = r.read() # -> read/get the content inside it

            # Clean CSS
            css_response = call_api_with_retry(
                model='claude-sonnet-4-5',
                system="""You are a code cleaning assistant.
                Clean this CSS by:
                - Removing duplicate rules
                - Removing unused vendor prefixes
                - Removing commented out code
                Return only the cleaned CSS, nothing else.""",
                content = css_content,
                client=client
            )

            css_cleaned = css_response.content[0].text # get the first response as we promt it to return only the cleaned css

            with open(full_path, 'w') as f: # -> open the full path and override the cleaned_css
                f.write(css_cleaned)
        
        if full_path.endswith('.js'):
            with open(full_path, 'r') as r:
                js_content = r.read()

                # Clean JS
            js_response = call_api_with_retry(
                model='claude-sonnet-4-5',
                system="""You are a code cleaning assistant.
                Clean this JavaScript by:
                - Removing all console.log statements
                - Removing analytics and tracking code
                - Removing commented out code
                - Removing dead code that is never called
                Return only the cleaned JavaScript, nothing else.""",
                content = js_content,
                client=client
            )

            js_cleaned = js_response.content[0].text

            with open(full_path, 'w') as f:
                f.write(js_cleaned)

    threads = []
    for relative_path, full_path in assets_map.items():
        t = threading.Thread(target=clean_file, args=(relative_path, full_path))
        t.start() # start the threads one by one but effectivly all at ones
        threads.append(t)

    for t in threads: # waits for the threads to finish before continuing with the main code (calling it manually)
        t.join()
    
    
    # Clean HTML
    html_response = client.messages.create(
        model='claude-sonnet-4-5',
        max_tokens=8096,
        system="""You are a code cleaning assistant. 
        You will receive raw scraped HTML from a landing page.
        Clean it by:
        - Removing all tracking scripts (Google Analytics, Google Tag Manager, Meta Pixel, Hotjar)
        - Removing cookie banners and GDPR popups
        - Removing all HTML comments
        - Removing empty or broken tags
        - Keeping all structural content, layout, images and text intact
        Return only the cleaned HTML, nothing else. No explanation, no markdown.""",
        messages=[
            {'role': 'user', 'content': html}
        ])
    


    # getting the text response, creating a file in the temp_folder, creating a html_path, writing to the folder
    cleaned_html = html_response.content[0].text


    html_path = os.path.join(temp_folder, 'index.html') # -> creating the index.html file inside our tempfolder
    with open(html_path, 'w') as f:
        f.write(cleaned_html)


    return assets_map, html_path



def rewrites_paths(assets_map, html_path):

    with open(html_path, 'r') as f:

        html_content = f.read() # -> reading the html content into a variable from disk


    for r_path, full_path in assets_map.items(): # -> doing the replacment in memory with the Python string
        path_after_unzip = os.path.basename(full_path) # -> getting the path of our file assets in the tempfolder
        html_content = html_content.replace(r_path, path_after_unzip) # -> replacing the old relative path with the cleaned one from our temp_folder | 'style/css.css': 'style_css.css'

    with open(html_path, 'w') as f:
        f.write(html_content) # -> write back to disk

    return html_content


def zipp(temp_folder, z_name):
    zip_path = os.path.join(temp_folder, z_name) # we create a path string inside my tempfolder

    with zipfile.ZipFile(zip_path, 'w') as zipf: # -> creates an empty zip file inside my zip path string
        for root, dirs, files in os.walk(temp_folder): # -> loop throught the tempfolder
            for file in files:
                if file == z_name: # -> prevent collisions cause we have the zip file as a actual file inside our temp_folder
                    continue
                full_path = os.path.join(root, file) # -> get's the actual full path of the file in the tempfolder
                zipf.write(full_path, arcname=file) # -> Adds that file to the zip. arcname=file means inside the zip it will just be called style_css.css not the full temp path. So when the user unzips they get clean filenames.
                
                
    return zip_path
