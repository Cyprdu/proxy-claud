from flask import Flask, request, Response, stream_with_context
import requests
from urllib.parse import urljoin, urlparse
import asyncio
from playwright.async_api import async_playwright
import re
import os

# Configure le chemin des navigateurs Playwright dès le démarrage
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH', 
                      os.path.expanduser('~/.cache/ms-playwright'))

app = Flask(__name__)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.google.com/',
}

# Cache pour éviter de re-scanner les mêmes pages
video_cache = {}

async def extract_video_with_browser(page_url, timeout=30):
    """
    Utilise un navigateur headless pour charger la page et capturer
    les requêtes réseau pour trouver le flux m3u8/mp4
    """
    captured_videos = []
    
    async with async_playwright() as p:
        # Lance Chrome en mode headless avec args pour Render
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-gpu'
            ]
        )
        
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        
        page = await context.new_page()
        
        # Intercepte toutes les requêtes réseau
        async def handle_route(route, request):
            url = request.url
            
            # Cherche les fichiers vidéo dans les requêtes
            if any(ext in url for ext in ['.m3u8', '.mp4', '.mpd', '.ts']):
                print(f"🎥 Vidéo détectée: {url}")
                if '.m3u8' in url:
                    captured_videos.append(('m3u8', url))
                elif '.mp4' in url:
                    captured_videos.append(('mp4', url))
                elif '.mpd' in url:
                    captured_videos.append(('mpd', url))
            
            # Continue la requête normalement
            await route.continue_()
        
        # Active l'interception des requêtes
        await page.route('**/*', handle_route)
        
        try:
            # Charge la page
            print(f"🌐 Chargement de la page: {page_url}")
            await page.goto(page_url, wait_until='networkidle', timeout=timeout * 1000)
            
            # Attend un peu pour que les vidéos se chargent
            await page.wait_for_timeout(5000)
            
            # Essaye de cliquer sur le bouton play si présent
            try:
                play_button = await page.query_selector('button[aria-label*="play"], button.play, .play-button, button[title*="Play"]')
                if play_button:
                    print("▶️ Clic sur le bouton play")
                    await play_button.click()
                    await page.wait_for_timeout(3000)
            except:
                pass
            
            # Essaye de cliquer sur la vidéo elle-même
            try:
                video = await page.query_selector('video')
                if video:
                    print("🎬 Clic sur la vidéo")
                    await video.click()
                    await page.wait_for_timeout(3000)
            except:
                pass
            
        except Exception as e:
            print(f"⚠️ Erreur lors du chargement: {e}")
        
        finally:
            await browser.close()
    
    # Priorise m3u8 > mp4 > mpd
    for video_type, url in captured_videos:
        if video_type == 'm3u8':
            return url, 'm3u8'
    
    for video_type, url in captured_videos:
        if video_type == 'mp4':
            return url, 'mp4'
    
    for video_type, url in captured_videos:
        if video_type == 'mpd':
            return url, 'mpd'
    
    return None, None

def extract_video_sync(page_url):
    """Version synchrone pour Flask"""
    # Vérifie le cache
    if page_url in video_cache:
        print(f"📦 Utilisation du cache pour: {page_url}")
        return video_cache[page_url]
    
    # Crée un nouvel event loop pour l'async
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        video_url, video_type = loop.run_until_complete(
            extract_video_with_browser(page_url)
        )
        
        # Met en cache
        if video_url:
            video_cache[page_url] = (video_url, video_type)
        
        return video_url, video_type
    finally:
        loop.close()

@app.route('/')
def home():
    return '''
    <html>
    <head>
        <title>Video Proxy Server - Browser Edition</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }
            h1 { color: #333; }
            .endpoint { background: #f4f4f4; padding: 15px; border-radius: 5px; margin: 20px 0; }
            code { background: #e8e8e8; padding: 2px 6px; border-radius: 3px; }
            .example { color: #0066cc; }
            .warning { background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 15px 0; }
        </style>
    </head>
    <body>
        <h1>🎥 Video Proxy Server (Browser Edition)</h1>
        <p>Ce serveur utilise un navigateur headless pour capturer les flux vidéo dynamiques.</p>
        
        <div class="warning">
            ⚠️ <strong>Note:</strong> L'extraction avec navigateur prend 5-10 secondes. Soyez patient !
        </div>
        
        <div class="endpoint">
            <h3>📋 Endpoints:</h3>
            <p><strong>1. Auto-extraction intelligente (avec navigateur):</strong><br>
            <code>GET /extract?url=URL_DE_LA_PAGE</code><br>
            <small>Simule une vraie visite, exécute le JS, capture le réseau</small></p>
            
            <p><strong>2. Stream HLS direct:</strong><br>
            <code>GET /hls?url=URL_M3U8</code></p>
            
            <p><strong>3. Stream MP4 direct:</strong><br>
            <code>GET /mp4?url=URL_MP4</code></p>
        </div>
        
        <div class="endpoint">
            <h3>💡 Utilisation:</h3>
            <p class="example">
            &lt;video controls&gt;<br>
            &nbsp;&nbsp;&lt;source src="/extract?url=https://site.com/video-page"&gt;<br>
            &lt;/video&gt;
            </p>
        </div>
        
        <p><a href="/test" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🧪 Page de test</a></p>
        
        <p><small>Status: ✅ Serveur actif | Engine: Playwright Chromium</small></p>
    </body>
    </html>
    '''

@app.route('/extract')
def extract_and_stream():
    """
    Extrait la vidéo avec un navigateur headless et la stream
    """
    page_url = request.args.get('url')
    
    if not page_url:
        return {'error': 'URL parameter required'}, 400
    
    try:
        print(f"🔍 Extraction demandée pour: {page_url}")
        
        # Extrait la vidéo avec le navigateur
        video_url, video_type = extract_video_sync(page_url)
        
        if not video_url:
            return {
                'error': 'No video found', 
                'message': 'Le navigateur n\'a détecté aucun flux vidéo sur cette page'
            }, 404
        
        print(f"✅ Vidéo trouvée: {video_url} (type: {video_type})")
        
        # Stream selon le type
        if video_type == 'm3u8':
            return stream_hls_content(video_url)
        elif video_type == 'mp4':
            return stream_mp4_content(video_url)
        elif video_type == 'mpd':
            return stream_mpd_content(video_url)
        else:
            return {'error': f'Unsupported video type: {video_type}'}, 400
            
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return {'error': str(e)}, 500

def stream_hls_content(url):
    """Stream HLS avec modification des URLs relatives"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        
        if '.m3u8' in url or 'mpegurl' in response.headers.get('Content-Type', ''):
            content = response.text
            base_url = url.rsplit('/', 1)[0] + '/'
            
            # Modifie les URLs relatives dans le manifeste
            lines = []
            for line in content.split('\n'):
                if line.strip() and not line.startswith('#'):
                    if not line.startswith('http'):
                        # URL relative -> absolue
                        absolute_url = urljoin(base_url, line.strip())
                    else:
                        absolute_url = line.strip()
                    
                    # Proxifie les segments
                    proxy_url = request.host_url.rstrip('/') + '/segment?url=' + absolute_url
                    lines.append(proxy_url)
                else:
                    lines.append(line)
            
            modified_content = '\n'.join(lines)
            
            resp = Response(modified_content, mimetype='application/vnd.apple.mpegurl')
            resp.headers['Access-Control-Allow-Origin'] = '*'
            resp.headers['Access-Control-Allow-Methods'] = 'GET, OPTIONS'
            resp.headers['Access-Control-Allow-Headers'] = '*'
            return resp
        
        # Stream binaire direct
        return Response(
            stream_with_context(response.iter_content(chunk_size=8192)),
            content_type=response.headers.get('Content-Type', 'application/octet-stream'),
            headers={'Access-Control-Allow-Origin': '*'}
        )
    
    except Exception as e:
        return {'error': str(e)}, 500

def stream_mp4_content(url):
    """Stream MP4 avec support du seeking"""
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
        
        for header in ['Content-Length', 'Content-Range', 'Accept-Ranges']:
            if header in response.headers:
                resp.headers[header] = response.headers[header]
        
        return resp
    
    except Exception as e:
        return {'error': str(e)}, 500

def stream_mpd_content(url):
    """Stream DASH/MPD"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        return Response(
            response.content,
            content_type='application/dash+xml',
            headers={'Access-Control-Allow-Origin': '*'}
        )
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/hls')
def stream_hls():
    url = request.args.get('url')
    if not url:
        return {'error': 'URL parameter required'}, 400
    return stream_hls_content(url)

@app.route('/mp4')
def stream_mp4():
    url = request.args.get('url')
    if not url:
        return {'error': 'URL parameter required'}, 400
    return stream_mp4_content(url)

@app.route('/segment')
def stream_segment():
    """Proxifie les segments vidéo (TS, etc.)"""
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
    """Page de test interactive"""
    test_url = request.args.get('url', '')
    
    return f'''
    <html>
    <head>
        <title>Test Video Proxy</title>
        <script src="https://cdn.jsdelivr.net/npm/hls.js@latest"></script>
        <style>
            body {{ font-family: Arial; max-width: 900px; margin: 50px auto; padding: 20px; }}
            video {{ width: 100%; max-width: 800px; background: #000; }}
            input {{ width: 70%; padding: 10px; margin: 10px 0; }}
            button {{ padding: 10px 20px; background: #007bff; color: white; border: none; cursor: pointer; }}
            button:hover {{ background: #0056b3; }}
            #status {{ margin: 20px 0; padding: 10px; border-radius: 5px; }}
            .loading {{ background: #fff3cd; color: #856404; }}
            .success {{ background: #d4edda; color: #155724; }}
            .error {{ background: #f8d7da; color: #721c24; }}
        </style>
    </head>
    <body>
        <h1>🎥 Test Video Proxy</h1>
        
        <input type="text" id="urlInput" placeholder="URL de la page vidéo (ex: https://111movies.com/movie/...)" value="{test_url}">
        <button onclick="loadVideo()">🚀 Extraire et lire</button>
        
        <div id="status"></div>
        
        <video id="videoPlayer" controls></video>
        
        <script>
            function setStatus(message, type) {{
                const status = document.getElementById('status');
                status.textContent = message;
                status.className = type;
            }}
            
            function loadVideo() {{
                const url = document.getElementById('urlInput').value;
                const video = document.getElementById('videoPlayer');
                
                if (!url) {{
                    setStatus('❌ Veuillez entrer une URL', 'error');
                    return;
                }}
                
                setStatus('⏳ Chargement de la page avec le navigateur... (peut prendre 10-15 secondes)', 'loading');
                
                const proxyUrl = '/extract?url=' + encodeURIComponent(url);
                
                if (Hls.isSupported()) {{
                    const hls = new Hls({{
                        debug: false,
                        enableWorker: true,
                        lowLatencyMode: true,
                    }});
                    
                    hls.loadSource(proxyUrl);
                    hls.attachMedia(video);
                    
                    hls.on(Hls.Events.MANIFEST_PARSED, function() {{
                        setStatus('✅ Vidéo chargée avec succès ! (HLS)', 'success');
                        video.play();
                    }});
                    
                    hls.on(Hls.Events.ERROR, function(event, data) {{
                        if (data.fatal) {{
                            setStatus('❌ Erreur: ' + data.type + ' - ' + data.details, 'error');
                        }}
                    }});
                }} else if (video.canPlayType('application/vnd.apple.mpegurl')) {{
                    video.src = proxyUrl;
                    video.addEventListener('loadedmetadata', function() {{
                        setStatus('✅ Vidéo chargée avec succès ! (Native HLS)', 'success');
                        video.play();
                    }});
                    video.addEventListener('error', function() {{
                        setStatus('❌ Erreur de chargement de la vidéo', 'error');
                    }});
                }} else {{
                    video.src = proxyUrl;
                    video.addEventListener('loadedmetadata', function() {{
                        setStatus('✅ Vidéo chargée avec succès ! (MP4)', 'success');
                        video.play();
                    }});
                    video.addEventListener('error', function() {{
                        setStatus('❌ Erreur de chargement de la vidéo', 'error');
                    }});
                }}
            }}
            
            if (document.getElementById('urlInput').value) {{
                loadVideo();
            }}
        </script>
    </body>
    </html>
    '''

@app.route('/clear-cache')
def clear_cache():
    """Vide le cache des vidéos"""
    video_cache.clear()
    return {'success': True, 'message': 'Cache cleared'}

def check_playwright_installation():
    """Vérifie que Playwright est correctement installé"""
    import os
    from pathlib import Path
    
    # Définit le chemin des navigateurs
    playwright_path = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', 
                                     os.path.expanduser('~/.cache/ms-playwright'))
    
    print(f"🔍 Vérification de Playwright...")
    print(f"📂 Chemin des navigateurs: {playwright_path}")
    
    if Path(playwright_path).exists():
        print(f"✅ Dossier Playwright trouvé")
        # Liste les navigateurs installés
        for item in Path(playwright_path).iterdir():
            if item.is_dir():
                print(f"   - {item.name}")
    else:
        print(f"⚠️ Dossier Playwright non trouvé")

if __name__ == '__main__':
    import os
    
    # Vérifie l'installation de Playwright au démarrage
    check_playwright_installation()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)
