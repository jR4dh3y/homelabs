#!/usr/bin/env python3
"""
Network Statistics Server for Glance Dashboard
Provides live upload/download bandwidth usage for ethernet interface
"""

import json
import time
import os
from collections import deque
from http.server import HTTPServer, BaseHTTPRequestHandler
from threading import Thread, Lock

# Configuration
INTERFACE = os.environ.get("NETWORK_INTERFACE", "eth0")
UPDATE_INTERVAL = 1  # seconds
PORT = int(os.environ.get("NETSTAT_PORT", 8085))
HISTORY_SIZE = 60  # Keep 60 seconds of history


class NetworkStats:
    def __init__(self, interface):
        self.interface = interface
        self.lock = Lock()
        self.rx_speed = 0  # bytes per second
        self.tx_speed = 0  # bytes per second
        self.last_rx = 0
        self.last_tx = 0
        self.last_time = time.time()
        # History for graphing
        self.rx_history = deque([0] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
        self.tx_history = deque([0] * HISTORY_SIZE, maxlen=HISTORY_SIZE)
        
    def get_bytes(self):
        """Read current rx/tx bytes from /sys/class/net"""
        try:
            with open(f"/sys/class/net/{self.interface}/statistics/rx_bytes") as f:
                rx = int(f.read().strip())
            with open(f"/sys/class/net/{self.interface}/statistics/tx_bytes") as f:
                tx = int(f.read().strip())
            return rx, tx
        except FileNotFoundError:
            # Try alternative interfaces
            for alt in ["enp36s0", "enp0s3", "enp0s25", "eno1", "ens33", "wlan0", "wlp2s0"]:
                try:
                    with open(f"/sys/class/net/{alt}/statistics/rx_bytes") as f:
                        rx = int(f.read().strip())
                    with open(f"/sys/class/net/{alt}/statistics/tx_bytes") as f:
                        tx = int(f.read().strip())
                    self.interface = alt
                    print(f"Using interface: {alt}")
                    return rx, tx
                except FileNotFoundError:
                    continue
            return 0, 0
    
    def update(self):
        """Update speed calculations"""
        current_time = time.time()
        rx, tx = self.get_bytes()
        
        time_diff = current_time - self.last_time
        if time_diff > 0 and self.last_rx > 0:
            with self.lock:
                self.rx_speed = (rx - self.last_rx) / time_diff
                self.tx_speed = (tx - self.last_tx) / time_diff
                self.rx_history.append(self.rx_speed)
                self.tx_history.append(self.tx_speed)
        
        self.last_rx = rx
        self.last_tx = tx
        self.last_time = current_time
    
    def get_stats(self):
        """Get current stats with lock"""
        with self.lock:
            return {
                "interface": self.interface,
                "download_speed": self.rx_speed,
                "upload_speed": self.tx_speed,
                "download_formatted": self.format_speed(self.rx_speed),
                "upload_formatted": self.format_speed(self.tx_speed),
                "rx_history": list(self.rx_history),
                "tx_history": list(self.tx_history),
            }
    
    @staticmethod
    def format_speed(bytes_per_sec):
        """Format bytes/sec to human readable"""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.1f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec / 1024:.1f} KB/s"
        elif bytes_per_sec < 1024 * 1024 * 1024:
            return f"{bytes_per_sec / (1024 * 1024):.1f} MB/s"
        else:
            return f"{bytes_per_sec / (1024 * 1024 * 1024):.2f} GB/s"


# Global stats instance
stats = NetworkStats(INTERFACE)


def stats_updater():
    """Background thread to update stats"""
    while True:
        stats.update()
        time.sleep(UPDATE_INTERVAL)


class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress logging
    
    def generate_svg_graph(self, rx_history, tx_history, width=300, height=80):
        """Generate SVG graph server-side"""
        all_values = list(rx_history) + list(tx_history)
        max_val = max(max(all_values), 1024)  # At least 1KB scale
        
        num_points = len(rx_history)
        point_width = width / max(num_points - 1, 1)
        
        # Generate path for download (rx)
        rx_points = []
        for i, val in enumerate(rx_history):
            x = i * point_width
            y = height - (val / max_val * height)
            rx_points.append(f"{x:.1f},{y:.1f}")
        rx_line = " ".join(rx_points)
        rx_area = f"0,{height} " + rx_line + f" {width},{height}"
        
        # Generate path for upload (tx)
        tx_points = []
        for i, val in enumerate(tx_history):
            x = i * point_width
            y = height - (val / max_val * height)
            tx_points.append(f"{x:.1f},{y:.1f}")
        tx_line = " ".join(tx_points)
        tx_area = f"0,{height} " + tx_line + f" {width},{height}"
        
        # Format max value for display
        max_formatted = NetworkStats.format_speed(max_val)
        
        svg = f'''<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" xmlns="http://www.w3.org/2000/svg" style="display:block;">
  <rect width="{width}" height="{height}" fill="rgba(255,255,255,0.03)" rx="4"/>
  <polygon points="{rx_area}" fill="rgba(34,197,94,0.25)"/>
  <polyline points="{rx_line}" fill="none" stroke="#22c55e" stroke-width="1.5"/>
  <polygon points="{tx_area}" fill="rgba(59,130,246,0.25)"/>
  <polyline points="{tx_line}" fill="none" stroke="#3b82f6" stroke-width="1.5"/>
  <text x="{width-5}" y="12" text-anchor="end" fill="rgba(255,255,255,0.5)" font-size="10">{max_formatted}</text>
</svg>'''
        return svg
    
    def do_GET(self):
        if self.path == "/stats":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(stats.get_stats()).encode())
        elif self.path == "/widget":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Widget-Content-Type", "html")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            data = stats.get_stats()
            svg_graph = self.generate_svg_graph(data["rx_history"], data["tx_history"])
            
            html = f'''<div style="display:flex;flex-direction:column;gap:0.5rem;">
  {svg_graph}
  <div style="display:flex;justify-content:space-between;align-items:center;">
    <div style="display:flex;align-items:center;gap:0.4rem;">
      <div style="width:8px;height:8px;border-radius:50%;background:#22c55e;"></div>
      <span style="opacity:0.7;font-size:0.85rem;">↓</span>
      <span style="font-size:0.95rem;font-weight:600;color:#22c55e;">{data["download_formatted"]}</span>
    </div>
    <div style="display:flex;align-items:center;gap:0.4rem;">
      <div style="width:8px;height:8px;border-radius:50%;background:#3b82f6;"></div>
      <span style="opacity:0.7;font-size:0.85rem;">↑</span>
      <span style="font-size:0.95rem;font-weight:600;color:#3b82f6;">{data["upload_formatted"]}</span>
    </div>
  </div>
  <div style="font-size:0.7rem;opacity:0.5;text-align:right;">{data["interface"]}</div>
</div>'''
            self.wfile.write(html.encode())
        else:
            self.send_response(404)
            self.end_headers()


def main():
    # Start background updater
    updater_thread = Thread(target=stats_updater, daemon=True)
    updater_thread.start()
    
    # Give it a moment to get initial readings
    time.sleep(1.5)
    
    print(f"Network Stats Server starting on port {PORT}")
    print(f"Monitoring interface: {stats.interface}")
    
    server = HTTPServer(("0.0.0.0", PORT), RequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
