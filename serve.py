#!/usr/bin/env python3
"""HTTP server with Range request support (required for PMTiles)."""
import os, sys
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeHandler(SimpleHTTPRequestHandler):
    def send_head(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            return super().send_head()

        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(404, "File not found")
            return None

        fs = os.fstat(f.fileno())
        file_size = fs.st_size
        ctype = self.guess_type(path)
        range_header = self.headers.get("Range")

        if range_header:
            try:
                unit, rng = range_header.strip().split("=", 1)
                start_s, end_s = rng.split("-", 1)
                start = int(start_s) if start_s else 0
                end   = int(end_s)   if end_s   else file_size - 1
                end   = min(end, file_size - 1)
                length = end - start + 1
                f.seek(start)
                self.send_response(206)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                self.end_headers()
                return f
            except Exception as e:
                f.close()
                self.send_error(400, f"Bad Range header: {e}")
                return None
        else:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(file_size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            return f

    def log_message(self, fmt, *args):
        # 省略表示（Range リクエストが大量に出るため）
        if args and str(args[1]) not in ("200", "206"):
            super().log_message(fmt, *args)


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    print(f"Serving at http://localhost:{port}/docs/")
    with HTTPServer(("", port), RangeHandler) as httpd:
        httpd.serve_forever()
