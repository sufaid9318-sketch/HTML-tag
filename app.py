# app.py - Fully configured for public deployment
"""
Bulk Meta Tag Extractor - Public Ready Version
Configured for PythonAnywhere, Railway, or ngrok
"""
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests
from bs4 import BeautifulSoup
import csv
import json
import io
import threading
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

app = Flask(__name__)
CORS(app)

# ==========================================
# RATE LIMITING - For public access
# ==========================================
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "20 per hour"]
)

# Initialize limiter after app creation
app.config['LIMITER_ENABLED'] = True

# Store processing jobs
jobs = {}

# ==========================================
# Meta Extractor Class
# ==========================================
class MetaExtractor:
    """Extract meta tags from URLs"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def extract_meta(self, url):
        """Extract all meta tags from a URL"""
        result = {
            'url': url,
            'status': 'pending',
            'title': '',
            'description': '',
            'keywords': '',
            'og_title': '',
            'og_description': '',
            'og_image': '',
            'og_url': '',
            'twitter_card': '',
            'twitter_title': '',
            'twitter_description': '',
            'twitter_image': '',
            'canonical': '',
            'robots': '',
            'author': '',
            'viewport': '',
            'charset': '',
            'language': '',
            'status_code': 0,
            'error': '',
            'response_time': 0,
            'content_length': 0
        }
        
        start_time = time.time()
        
        try:
            if not self.is_valid_url(url):
                result['status'] = 'error'
                result['error'] = 'Invalid URL'
                return result
            
            response = self.session.get(url, timeout=10, allow_redirects=True)
            result['status_code'] = response.status_code
            result['response_time'] = round((time.time() - start_time) * 1000, 2)
            result['content_length'] = len(response.content)
            
            if response.status_code != 200:
                result['status'] = 'error'
                result['error'] = f'HTTP {response.status_code}'
                return result
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            title_tag = soup.find('title')
            result['title'] = title_tag.get_text().strip() if title_tag else ''
            
            meta_tags = soup.find_all('meta')
            for meta in meta_tags:
                name = meta.get('name', '').lower()
                property_name = meta.get('property', '').lower()
                http_equiv = meta.get('http-equiv', '').lower()
                content = meta.get('content', '')
                
                if name == 'description':
                    result['description'] = content
                elif name == 'keywords':
                    result['keywords'] = content
                elif name == 'author':
                    result['author'] = content
                elif name == 'robots':
                    result['robots'] = content
                elif name == 'viewport':
                    result['viewport'] = content
                elif name == 'language':
                    result['language'] = content
                elif property_name == 'og:title':
                    result['og_title'] = content
                elif property_name == 'og:description':
                    result['og_description'] = content
                elif property_name == 'og:image':
                    result['og_image'] = content
                elif property_name == 'og:url':
                    result['og_url'] = content
                elif name == 'twitter:card':
                    result['twitter_card'] = content
                elif name == 'twitter:title':
                    result['twitter_title'] = content
                elif name == 'twitter:description':
                    result['twitter_description'] = content
                elif name == 'twitter:image':
                    result['twitter_image'] = content
                elif http_equiv == 'content-type':
                    if 'charset=' in content.lower():
                        result['charset'] = content.split('charset=')[-1]
            
            canonical = soup.find('link', rel='canonical')
            result['canonical'] = canonical.get('href', '') if canonical else ''
            
            result['status'] = 'success'
            
        except requests.exceptions.Timeout:
            result['status'] = 'error'
            result['error'] = 'Request timeout'
            result['response_time'] = round((time.time() - start_time) * 1000, 2)
        except requests.exceptions.RequestException as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['response_time'] = round((time.time() - start_time) * 1000, 2)
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            result['response_time'] = round((time.time() - start_time) * 1000, 2)
        
        return result
    
    def is_valid_url(self, url):
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

extractor = MetaExtractor()

# ==========================================
# Processing Functions
# ==========================================
def process_urls(urls, job_id, max_workers=10):
    """Process multiple URLs in parallel"""
    jobs[job_id]['status'] = 'processing'
    jobs[job_id]['total'] = len(urls)
    jobs[job_id]['processed'] = 0
    jobs[job_id]['success'] = 0
    jobs[job_id]['errors'] = 0
    
    results = []
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(extractor.extract_meta, url): url for url in urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                result = future.result()
                results.append(result)
                jobs[job_id]['processed'] += 1
                
                if result['status'] == 'success':
                    jobs[job_id]['success'] += 1
                else:
                    jobs[job_id]['errors'] += 1
                
                jobs[job_id]['progress'] = round((jobs[job_id]['processed'] / jobs[job_id]['total']) * 100, 2)
                
            except Exception as e:
                jobs[job_id]['errors'] += 1
                jobs[job_id]['processed'] += 1
                results.append({
                    'url': url,
                    'status': 'error',
                    'error': str(e)
                })
    
    jobs[job_id]['status'] = 'completed'
    jobs[job_id]['results'] = results
    jobs[job_id]['completed_at'] = datetime.now().isoformat()

# ==========================================
# Flask Routes
# ==========================================
@app.route('/')
def index():
    """Main page"""
    return render_template('index.html')

@app.route('/api/extract', methods=['POST'])
@limiter.limit("10 per minute")  # Rate limit for public
def extract_meta_tags():
    """Extract meta tags from URLs"""
    data = request.json
    
    if not data or 'urls' not in data:
        return jsonify({'error': 'No URLs provided'}), 400
    
    urls = data['urls']
    urls = [url.strip() for url in urls if url.strip()]
    
    if not urls:
        return jsonify({'error': 'No valid URLs provided'}), 400
    
    max_urls = data.get('max_urls', 5000)
    if len(urls) > max_urls:
        urls = urls[:max_urls]
    
    job_id = f"job_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(jobs)}"
    jobs[job_id] = {
        'id': job_id,
        'status': 'queued',
        'created_at': datetime.now().isoformat(),
        'total': len(urls),
        'processed': 0,
        'success': 0,
        'errors': 0,
        'progress': 0,
        'urls': urls
    }
    
    max_workers = data.get('workers', 10)
    thread = threading.Thread(target=process_urls, args=(urls, job_id, max_workers))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'job_id': job_id,
        'message': f'Processing {len(urls)} URLs',
        'status': 'queued'
    })

@app.route('/api/job/<job_id>')
def get_job_status(job_id):
    """Get job status and results"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    if job['status'] == 'processing':
        return jsonify({
            'job_id': job_id,
            'status': job['status'],
            'progress': job['progress'],
            'total': job['total'],
            'processed': job['processed'],
            'success': job['success'],
            'errors': job['errors'],
            'results': job.get('results', [])[:10]
        })
    
    return jsonify({
        'job_id': job_id,
        'status': job['status'],
        'progress': job['progress'],
        'total': job['total'],
        'processed': job['processed'],
        'success': job['success'],
        'errors': job['errors'],
        'created_at': job['created_at'],
        'completed_at': job.get('completed_at'),
        'results': job.get('results', [])
    })

@app.route('/api/export/<job_id>/<format>')
def export_results(job_id, format):
    """Export results"""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = jobs[job_id]
    
    if job['status'] != 'completed':
        return jsonify({'error': 'Job not completed yet'}), 400
    
    results = job.get('results', [])
    
    if format == 'csv':
        output = io.StringIO()
        if results:
            fieldnames = results[0].keys()
            writer = csv.DictWriter(output, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(results)
        output.seek(0)
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'meta_tags_{job_id}.csv'
        )
    
    elif format == 'json':
        return send_file(
            io.BytesIO(json.dumps(results, indent=2).encode('utf-8')),
            mimetype='application/json',
            as_attachment=True,
            download_name=f'meta_tags_{job_id}.json'
        )
    
    elif format == 'excel':
        try:
            import pandas as pd
            df = pd.DataFrame(results)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Meta Tags')
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'meta_tags_{job_id}.xlsx'
            )
        except ImportError:
            return jsonify({'error': 'Excel export requires pandas'}), 500
    
    return jsonify({'error': 'Invalid format'}), 400

@app.route('/api/stats')
def get_stats():
    """Get system statistics"""
    total_jobs = len(jobs)
    completed_jobs = sum(1 for j in jobs.values() if j['status'] == 'completed')
    processing_jobs = sum(1 for j in jobs.values() if j['status'] == 'processing')
    total_urls = sum(j['total'] for j in jobs.values())
    total_success = sum(j['success'] for j in jobs.values())
    total_errors = sum(j['errors'] for j in jobs.values())
    
    return jsonify({
        'total_jobs': total_jobs,
        'completed_jobs': completed_jobs,
        'processing_jobs': processing_jobs,
        'total_urls': total_urls,
        'total_success': total_success,
        'total_errors': total_errors,
        'success_rate': round((total_success / total_urls * 100), 2) if total_urls > 0 else 0
    })

# ==========================================
# Main Entry Point
# ==========================================
if __name__ == '__main__':
    # PythonAnywhere requires host=0.0.0.0 and port=8080
    # Railway/Railway automatically uses port
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

# For local development
# if __name__ == '__main__':
#     app.run(debug=True, host='0.0.0.0', port=5000)