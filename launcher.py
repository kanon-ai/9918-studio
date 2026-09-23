"""Open an existing studio, or run a new loopback instance."""
import json
import urllib.request
import webbrowser

def main():
    url='http://127.0.0.1:8765'
    try:
        with urllib.request.urlopen(url+'/api/health',timeout=2) as response:
            if json.load(response).get('application')=='msx-pixel-studio':
                webbrowser.open(url);return
    except Exception:pass
    try:
        from server import main as serve
        serve()
    except ImportError:
        print('Pillow is required. Run setup.cmd once, then start.cmd.')
        input('Press Enter to close...')
    except OSError as e:
        print('Could not start MSX Pixel Studio:',e)
        print('Port 8765 may already be used by another application.')
        input('Press Enter to close...')

if __name__=='__main__':main()
