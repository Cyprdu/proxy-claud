from flask import Flask, request, Response, stream_with_context
import requests
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup

app = Flask(__name__)

# Headers pour simuler un navigateur
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/',
}

def extract_video_urls(html_content, page_url):
    """Extrait les URLs de vidéos depuis le HTML"""
    video_urls = []
    
    # Recherche des URLs m3u8, mp4, mpd
    patterns = [
        r'https?://[^\s\'"]+\.m3u8[^\s\'"]*',
        r'https?://[^\s\'"]+\.mp4[^\s\'"]*',
        r'https?://[^\s\'"]+\.mpd[^\s\'"]*',
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        video_urls.extend(matches)
    
    # Parse avec BeautifulSoup pour trouver les sources
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Cherche dans les balises video et source
    for tag in soup.find_all(['video', 'source', 'iframe']):
        src = tag.get('src') or tag.get('data-src')
        if src:
            if any(ext in src for ext in ['.m3u8', '.mp4', '.mpd']):
                full_url = urljoin(page_url, src)
                video_urls.append(full_url)
    
    return list(set(video_urls))  # Supprime les doublons

@app.route('/')
def home():
    return '''
    <html>
    <head>
        <title>Video Proxy Server</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .endpoint { background: #f4f4f4; padding: 15px; border-radius: 5px; margin: 20px 0; }
            code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; }
            .example { color: #0066cc; }
        </style>
    </head>
    <body>
        <h1>🎥 Video Proxy Server</h1>
        <p>Ce serveur extrait et proxifie les flux vidéo depuis n'importe quelle URL.</p>
        
        <div class="endpoint">
            <h3>📋 Endpoints disponibles:</h3>
            <p><strong>1. Extraire les vidéos:</strong><br>
            <code>GET /extract?url=URL_DE_LA_PAGE</code></p>
            
            <p><strong>2. Streamer HLS/M3U8:</strong><br>
            <code>GET /hls?url=URL_DIRECTE_M3U8</code></p>
            
            <p><strong>3. Streamer MP4:</strong><br>
            <code>GET /mp4?url=URL_DIRECTE_MP4</code></p>
        </div>
        
        <div class="endpoint">
            <h3>💡 Exemples:</h3>
            <p class="example">
            /extract?url=https://example.com/video-page<br>
            /hls?url=https://example.com/video.m3u8<br>
            /mp4?url=https://example.com/video.mp4
            </p>
        </div>
        
        <p><small>Status: ✅ Serveur actif</small></p>
    </body>
    </html>
    '''

@app.route('/extract')
def extract():
    """Extrait les URLs de vidéos depuis une page"""
    url = request.args.get('url')
    
    if not url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        video_urls = extract_video_urls(response.text, url)
        
        return {
            'success': True,
            'page_url': url,
            'videos_found': len(video_urls),
            'videos': video_urls
        }
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/hls')
def stream_hls():
    """Proxifie les flux HLS/M3U8"""
    url = request.args.get('url')
    
    if not url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        # Récupère le contenu m3u8
        response = requests.get(url, headers=HEADERS, stream=True)
        
        # Si c'est un fichier m3u8, on modifie les URLs relatives
        if '.m3u8' in url or 'application/vnd.apple.mpegurl' in response.headers.get('Content-Type', ''):
            content = response.text
            base_url = url.rsplit('/', 1)[0] + '/'
            
            # Remplace les URLs relatives par des URLs complètes via le proxy
            lines = []
            for line in content.split('\n'):
                if line and not line.startswith('#'):
                    if not line.startswith('http'):
                        line = urljoin(base_url, line)
                    # Proxifie les segments via ce serveur
                    line = f"/segment?url={line}"
                lines.append(line)
            
            return Response('\n'.join(lines), mimetype='application/vnd.apple.mpegurl')
        
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get('Content-Type', 'application/octet-stream')
        )
    
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/mp4')
def stream_mp4():
    """Proxifie les vidéos MP4"""
    url = request.args.get('url')
    
    if not url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        # Support du range request pour le seeking
        range_header = request.headers.get('Range')
        headers = HEADERS.copy()
        if range_header:
            headers['Range'] = range_header
        
        response = requests.get(url, headers=headers, stream=True)
        
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        resp = Response(stream_with_context(generate()), status=response.status_code)
        resp.headers['Content-Type'] = response.headers.get('Content-Type', 'video/mp4')
        
        if 'Content-Length' in response.headers:
            resp.headers['Content-Length'] = response.headers['Content-Length']
        if 'Content-Range' in response.headers:
            resp.headers['Content-Range'] = response.headers['Content-Range']
        if 'Accept-Ranges' in response.headers:
            resp.headers['Accept-Ranges'] = response.headers['Accept-Ranges']
        
        resp.headers['Access-Control-Allow-Origin'] = '*'
        
        return resp
    
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/segment')
def stream_segment():
    """Proxifie les segments vidéo (pour HLS)"""
    url = request.args.get('url')
    
    if not url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get('Content-Type', 'application/octet-stream'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
