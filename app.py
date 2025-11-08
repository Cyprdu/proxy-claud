from flask import Flask, request, Response, stream_with_context
import requests
from urllib.parse import urljoin, urlparse
import re
from bs4 import BeautifulSoup
import time

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/',
}

def find_video_from_page(page_url, timeout=15):
    """
    Charge la page et trouve automatiquement le flux vidéo principal
    Retourne l'URL du flux vidéo trouvé
    """
    try:
        # Récupère la page HTML
        response = requests.get(page_url, headers=HEADERS, timeout=timeout)
        html_content = response.text
        
        # Liste de priorité pour les formats
        video_urls = {
            'm3u8': [],
            'mp4': [],
            'mpd': []
        }
        
        # Patterns pour trouver les URLs
        patterns = {
            'm3u8': r'https?://[^\s\'"<>]+\.m3u8[^\s\'"<>]*',
            'mp4': r'https?://[^\s\'"<>]+\.mp4[^\s\'"<>]*',
            'mpd': r'https?://[^\s\'"<>]+\.mpd[^\s\'"<>]*',
        }
        
        # Cherche dans le HTML brut
        for format_type, pattern in patterns.items():
            matches = re.findall(pattern, html_content)
            video_urls[format_type].extend(matches)
        
        # Parse avec BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Cherche dans toutes les balises possibles
        for tag in soup.find_all(['video', 'source', 'iframe', 'script']):
            # Attributs à vérifier
            attrs_to_check = ['src', 'data-src', 'data-url', 'data-video', 'data-stream']
            
            for attr in attrs_to_check:
                src = tag.get(attr)
                if src:
                    full_url = urljoin(page_url, src)
                    if '.m3u8' in full_url:
                        video_urls['m3u8'].append(full_url)
                    elif '.mp4' in full_url:
                        video_urls['mp4'].append(full_url)
                    elif '.mpd' in full_url:
                        video_urls['mpd'].append(full_url)
        
        # Cherche dans les scripts JavaScript
        scripts = soup.find_all('script')
        for script in scripts:
            if script.string:
                # Cherche des patterns communs de déclaration de source vidéo
                for format_type, pattern in patterns.items():
                    matches = re.findall(pattern, script.string)
                    video_urls[format_type].extend(matches)
        
        # Nettoie et déduplique
        for format_type in video_urls:
            video_urls[format_type] = list(set(video_urls[format_type]))
        
        # Retourne le premier trouvé selon la priorité : m3u8 > mp4 > mpd
        if video_urls['m3u8']:
            return video_urls['m3u8'][0], 'm3u8'
        elif video_urls['mp4']:
            return video_urls['mp4'][0], 'mp4'
        elif video_urls['mpd']:
            return video_urls['mpd'][0], 'mpd'
        
        return None, None
        
    except Exception as e:
        print(f"Erreur lors de l'extraction: {e}")
        return None, None

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
        <p>Ce serveur extrait et proxifie automatiquement les flux vidéo.</p>
        
        <div class="endpoint">
            <h3>📋 Endpoints:</h3>
            <p><strong>1. Auto-extraction et stream (recommandé):</strong><br>
            <code>GET /extract?url=URL_DE_LA_PAGE</code><br>
            <small>Trouve automatiquement la vidéo et la stream</small></p>
            
            <p><strong>2. Stream HLS direct:</strong><br>
            <code>GET /hls?url=URL_M3U8</code></p>
            
            <p><strong>3. Stream MP4 direct:</strong><br>
            <code>GET /mp4?url=URL_MP4</code></p>
        </div>
        
        <div class="endpoint">
            <h3>💡 Exemple d'utilisation dans un player:</h3>
            <p class="example">
            &lt;video controls&gt;<br>
            &nbsp;&nbsp;&lt;source src="https://votre-proxy.onrender.com/extract?url=https://site.com/video-page"&gt;<br>
            &lt;/video&gt;
            </p>
        </div>
        
        <p><small>Status: ✅ Serveur actif</small></p>
    </body>
    </html>
    '''

@app.route('/extract')
def extract_and_stream():
    """
    Extrait automatiquement la vidéo depuis une page et la stream directement
    Utilisable directement dans un <video> tag
    """
    page_url = request.args.get('url')
    
    if not page_url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        # Trouve le flux vidéo
        video_url, video_type = find_video_from_page(page_url)
        
        if not video_url:
            return {'error': 'No video found on this page'}, 404
        
        print(f"Vidéo trouvée: {video_url} (type: {video_type})")
        
        # Redirige vers le bon handler selon le type
        if video_type == 'm3u8':
            return stream_hls_content(video_url)
        elif video_type == 'mp4':
            return stream_mp4_content(video_url)
        else:
            return {'error': f'Unsupported video type: {video_type}'}, 400
            
    except Exception as e:
        return {'error': str(e)}, 500

def stream_hls_content(url):
    """Stream HLS content avec modification des URLs"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        # Si c'est un manifeste m3u8
        if '.m3u8' in url or 'mpegurl' in response.headers.get('Content-Type', ''):
            content = response.text
            base_url = url.rsplit('/', 1)[0] + '/'
            
            # Modifie les URLs dans le manifeste
            lines = []
            for line in content.split('\n'):
                if line and not line.startswith('#'):
                    if not line.startswith('http'):
                        # URL relative, on la rend absolue
                        line = urljoin(base_url, line)
                    # Proxifie via /segment
                    proxy_url = request.host_url.rstrip('/') + '/segment?url=' + line
                    lines.append(proxy_url)
                else:
                    lines.append(line)
            
            modified_content = '\n'.join(lines)
            
            resp = Response(modified_content, mimetype='application/vnd.apple.mpegurl')
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = '*'
            return resp
        
        # Sinon stream direct
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get('Content-Type', 'application/octet-stream'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    
    except Exception as e:
        return {'error': str(e)}, 500

def stream_mp4_content(url):
    """Stream MP4 avec support du range"""
    try:
        range_header = request.headers.get('Range')
        headers = HEADERS.copy()
        if range_header:
            headers['Range'] = range_header
        
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        
        def generate():
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk
        
        resp = Response(stream_with_context(generate()), status=response.status_code)
        resp.headers['Content-Type'] = response.headers.get('Content-Type', 'video/mp4')
        resp.headers['Access-Control-Allow-Origin'] = '*'
        
        # Headers pour le seeking
        for header in ['Content-Length', 'Content-Range', 'Accept-Ranges']:
            if header in response.headers:
                resp.headers[header] = response.headers[header]
        
        return resp
    
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/hls')
def stream_hls():
    """Stream HLS direct (si vous avez déjà l'URL m3u8)"""
    url = request.args.get('url')
    if not url:
        return {'error': 'URL parameter required'}, 400
    return stream_hls_content(url)

@app.route('/mp4')
def stream_mp4():
    """Stream MP4 direct (si vous avez déjà l'URL mp4)"""
    url = request.args.get('url')
    if not url:
        return {'error': 'URL parameter required'}, 400
    return stream_mp4_content(url)

@app.route('/segment')
def stream_segment():
    """Proxifie les segments vidéo (utilisé par HLS)"""
    url = request.args.get('url')
    
    if not url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        response = requests.get(url, headers=HEADERS, stream=True, timeout=10)
        
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get('Content-Type', 'video/mp2t'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/test')
def test_page():
    """Page de test avec un player intégré"""
    test_url = request.args.get('url', '')
    
    return f'''
    <html>
    <head>
        <title>Test Video Proxy</title>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            body {{ font-family: Arial; max-width: 900px; margin: 50px auto; padding: 20px; }}
            video {{ width: 100%; max-width: 800px; }}
            input {{ width: 70%; padding: 10px; margin: 10px 0; }}
            button {{ padding: 10px 20px; }}
        </style>
    </head>
    <body>
        <h1>🎥 Test Video Proxy</h1>
        
        <input type="text" id="urlInput" placeholder="URL de la page vidéo" value="{test_url}">
        <button onclick="loadVideo()">Charger la vidéo</button>
        
        <div id="status" style="margin: 20px 0; color: #666;"></div>
        
        <video id="videoPlayer" controls></video>
        
        <script>
            function loadVideo() {{
                const url = document.getElementById('urlInput').value;
                const status = document.getElementById('status');
                const video = document.getElementById('videoPlayer');
                
                if (!url) {{
                    status.textContent = '❌ Veuillez entrer une URL';
                    return;
                }}
                
                status.textContent = '⏳ Chargement...';
                
                const proxyUrl = '/extract?url=' + encodeURIComponent(url);
                
                if (Hls.isSupported()) {{
                    const hls = new Hls();
                    hls.loadSource(proxyUrl);
                    hls.attachMedia(video);
                    hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                        status.textContent = '✅ Vidéo chargée (HLS)';
                        video.play();
                    }});
                    hls.on(Hls.Events.ERROR, function(event, data) {{
                        if (data.fatal) {{
                            status.textContent = '❌ Erreur: ' + data.type;
                        }}
                    }});
                }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                    video.src = proxyUrl;
                    video.addEventListener('loadedmetadata', function() {{
                        status.textContent = '✅ Vidéo chargée (native)';
                        video.play();
                    }});
                }} else {{
                    // Essaye en MP4 direct
                    video.src = proxyUrl;
                    video.addEventListener('loadedmetadata', function() {{
                        status.textContent = '✅ Vidéo chargée (MP4)';
                        video.play();
                    }});
                }}
            }}
            
            // Charge automatiquement si URL présente
            if (document.getElementById('urlInput').value) {{
                loadVideo();
            }}
        </script>
    </body>
    </html>
    '''

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
