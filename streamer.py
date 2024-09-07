import io
import logging
import socketserver
from http import server
from threading import Condition
import numpy as np
from picamera2 import Picamera2
from picamera2.encoders import JpegEncoder
from picamera2.outputs import FileOutput
import cv2

# HTML page for streaming
PAGE = """\
<html>
<head>
<title>Picamera2 MJPEG Streaming Demo</title>
<script>
function sendButtonPress() {
    fetch('/button-press', { method: 'POST' })
        .then(response => {
            if (response.ok) {
                console.log('Button press acknowledged');
            } else {
                console.error('Failed to acknowledge button press');
            }
        });
}
</script>
</head>
<body>
<h1>Picamera2 MJPEG Streaming</h1>
<img src="stream.mjpg" width="640" height="480" />
<button id="pressButton" onclick="sendButtonPress()">Press</button>
</body>
</html>
"""

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

def button():
    print("Button pressed")
    # Add additional logic here if needed

class StreamingHandler(server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            content = PAGE.encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content)
        elif self.path == '/stream.mjpg':
            self.send_response(200)
            self.send_header('Age', 0)
            self.send_header('Cache-Control', 'no-cache, private')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    
                    # Ensure frame is valid
                    if frame is None:
                        continue
                    
                    # Convert frame to numpy array
                    image_array = np.frombuffer(frame, dtype=np.uint8)  # Ensure it's a byte buffer
                    image_array = cv2.imdecode(image_array, cv2.IMREAD_COLOR)  # Decode the image

                    # Check if the image was decoded correctly
                    if image_array is None:
                        logging.error("Failed to decode image from frame buffer")
                        continue
                    
                    # Convert to grayscale
                    try:
                        gray = cv2.cvtColor(image_array, cv2.COLOR_RGB2GRAY)
                    except Exception as e:
                        logging.error(f"Error converting image to grayscale: {e}")
                        continue
                    
                    # Encode the image as JPEG
                    success, jpeg_image = cv2.imencode('.jpg', gray)
                    
                    if not success:
                        logging.error("Failed to encode image as JPEG")
                        continue
                    
                    # Send the JPEG image to the client
                    self.wfile.write(b'--FRAME\r\n')
                    self.send_header('Content-Type', 'image/jpeg')
                    self.send_header('Content-Length', len(jpeg_image))
                    self.end_headers()
                    self.wfile.write(jpeg_image.tobytes())
                    self.wfile.write(b'\r\n')
            except Exception as e:
                logging.warning(
                    'Removed streaming client %s: %s',
                    self.client_address, str(e))
        else:
            self.send_error(404)
            self.end_headers()

    def do_POST(self):
        if self.path == '/button-press':
            button()
            self.send_response(200)
            self.end_headers()
        else:
            self.send_error(404)
            self.end_headers()

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

# Initialize Picamera2 and configure
picam2 = Picamera2()
picam2.configure(picam2.create_video_configuration(main={"size": (640, 480)}))
output = StreamingOutput()
picam2.start_recording(JpegEncoder(), FileOutput(output))

try:
    address = ('', 7123)
    server = StreamingServer(address, StreamingHandler)
    print("Starting server on port 7123...")
    server.serve_forever()
finally:
    picam2.stop_recording()
