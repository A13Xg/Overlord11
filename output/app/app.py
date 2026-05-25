from http.server import BaseHTTPRequestHandler, HTTPServer
import argparse

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'<html><body><h1>App scaffold is running</h1></body></html>')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=3000)
    args = parser.parse_args()
    server = HTTPServer(('0.0.0.0', args.port), Handler)
    print(f'Listening on http://0.0.0.0:{args.port}')
    server.serve_forever()

if __name__ == '__main__':
    main()
