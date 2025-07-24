import sys
import socket
import threading
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QGroupBox, QComboBox
)
from PyQt5.QtCore import QTimer
import pyqtgraph.opengl as gl
import pyqtgraph as pg
import time

class IMUVisualizer(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("ESP32 IMU Visualizer")
        self.setGeometry(100, 100, 1200, 600)

        self.connected = False
        self.client_socket = None
        self.angle_data = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.preset_data = {"x": None, "y": None, "z": None}
        self.data_history = {"time": [], "x": [], "y": [], "z": []}
        self.start_time = time.time()

        # Define 6 predefined presets (Clear removed)
        self.presets = [
            {"name": "Preset 1", "x": 17.2, "y": 1.7, "z": -75.0},
            {"name": "Preset 2", "x": -31.4, "y": -13.3, "z": 60.0},
            {"name": "Preset 3", "x": -22.5, "y": -2.9, "z": -170.0},
            {"name": "Preset 4", "x": -7.0, "y": 43.7, "z": 15.0},
            {"name": "Preset 5", "x": -44.0, "y": 31.9, "z": 180.0},
            {"name": "Preset 6", "x": 2.6, "y": 12.2, "z": -110.0}
        ]

        self.initUI()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_cube)
        self.timer.start(50)

        self.plot_timer = QTimer()
        self.plot_timer.timeout.connect(self.update_plot)
        self.plot_timer.start(200)

    def initUI(self):
        main_layout = QHBoxLayout()
        left_panel = QVBoxLayout()

        conn_group = QGroupBox("Connection")
        conn_layout = QHBoxLayout()
        self.ip_input = QLineEdit()
        self.ip_input.setPlaceholderText("Enter ESP32 IP")
        self.status_label = QLabel("Not connected")
        conn_btn = QPushButton("Connect")
        conn_btn.clicked.connect(self.connect_to_esp)
        conn_layout.addWidget(self.ip_input)
        conn_layout.addWidget(conn_btn)
        conn_group.setLayout(conn_layout)

        # Preset selection dropdown (without Clear)
        preset_group = QGroupBox("Select Preset")
        preset_layout = QHBoxLayout()
        self.preset_combo = QComboBox()
        self.preset_combo.addItems([p["name"] for p in self.presets])
        enter_btn = QPushButton("Enter")
        enter_btn.clicked.connect(self.set_preset)
        preset_layout.addWidget(self.preset_combo)
        preset_layout.addWidget(enter_btn)
        preset_group.setLayout(preset_layout)

        # Add Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self.clear_preset_momentary)

        self.preset_label = QLabel("Preset:\nX: --\nY: --\nZ: --")
        self.preset_label.setStyleSheet("font-size: 60px; padding: 10px; background: #FFFFFF; border: 2px solid #000000;")

        self.angle_label = QLabel("Current:\nX: 0.0\nY: 0.0\nZ: 0.0")
        self.angle_label.setStyleSheet("font-size: 60px; padding: 10px; background: #FFFFFF; border: 2px solid #000000;")

        self.signal_label = QLabel("Signal: --")
        self.signal_label.setStyleSheet("font-size: 20px; color: black;")

        left_panel.addWidget(conn_group)
        left_panel.addWidget(preset_group)
        left_panel.addWidget(clear_btn)
        left_panel.addWidget(self.status_label)
        left_panel.addWidget(self.signal_label)
        left_panel.addWidget(self.preset_label)
        left_panel.addWidget(self.angle_label)
        left_panel.addStretch()

        # 3D Cube
        self.view = gl.GLViewWidget()
        self.view.opts['distance'] = 400
        grid = gl.GLGridItem()
        grid.scale(20, 20, 1)
        self.view.addItem(grid)

        verts = np.array([
            [-50, -50, -50],
            [ 50, -50, -50],
            [ 50,  50, -50],
            [-50,  50, -50],
            [-50, -50,  50],
            [ 50, -50,  50],
            [ 50,  50,  50],
            [-50,  50,  50]
        ])
        faces = np.array([
            [0,1,2], [0,2,3],
            [4,5,6], [4,6,7],
            [0,1,5], [0,5,4],
            [2,3,7], [2,7,6],
            [1,2,6], [1,6,5],
            [0,3,7], [0,7,4]
        ])
        colors = np.array([
            [1,0,0,1], [1,0,0,1],
            [0,1,0,1], [0,1,0,1],
            [0,0,1,1], [0,0,1,1],
            [1,1,0,1], [1,1,0,1],
            [1,0,1,1], [1,0,1,1],
            [0,1,1,1], [0,1,1,1]
        ])
        self.mesh = gl.GLMeshItem(vertexes=verts, faces=faces, faceColors=colors, smooth=False, drawEdges=True)
        self.view.addItem(self.mesh)

        # Overlay Cube for Preset Orientation
        overlay_colors = np.array([
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025],  # Gray with 97.5% transparency
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025],
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025],
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025],
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025],
            [0.5, 0.5, 0.5, 0.025], [0.5, 0.5, 0.5, 0.025]
        ])
        self.overlay_mesh = gl.GLMeshItem(vertexes=verts, faces=faces, faceColors=overlay_colors, smooth=False, drawEdges=True, edgeColor=(0.5, 0.5, 0.5, 0.075))  # Gray edge with 92.5% transparency
        self.view.addItem(self.overlay_mesh)
        self.overlay_mesh.setVisible(False)  # Hidden until a preset is selected

        # Real-time Plot
        self.plot_widget = pg.PlotWidget(title="Angle Tracking")
        self.plot_widget.setYRange(-180, 180)
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.addLegend()
        self.x_curve = self.plot_widget.plot(pen='y', name="X (Yellow)")
        self.y_curve = self.plot_widget.plot(pen='r', name="Y (Red)")
        self.z_curve = self.plot_widget.plot(pen='b', name="Z (Blue)")

        # Configure y-axis with smaller increments
        self.plot_widget.getAxis('left').setTickSpacing(10.0, 5.0)

        # Initialize preset lines with matching colors
        self.preset_x_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('y', width=2), label='Preset X: {value:.1f}°', labelOpts={'position': 0.1, 'color': (1, 1, 0, 1)})
        self.preset_y_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('r', width=2), label='Preset Y: {value:.1f}°', labelOpts={'position': 0.1, 'color': (1, 0, 0, 1)})
        self.preset_z_line = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen('b', width=2), label='Preset Z: {value:.1f}°', labelOpts={'position': 0.1, 'color': (0, 0, 1, 1)})
        self.plot_widget.addItem(self.preset_x_line)
        self.plot_widget.addItem(self.preset_y_line)
        self.plot_widget.addItem(self.preset_z_line)
        self.preset_x_line.setVisible(False)
        self.preset_y_line.setVisible(False)
        self.preset_z_line.setVisible(False)

        right_panel = QVBoxLayout()
        right_panel.addWidget(self.view, 3)  # Increased from 2 to 3 to maintain proportion
        right_panel.addWidget(self.plot_widget, 2)  # Increased from 1 to 2 (20% more than original 1.67 ratio)

        main_layout.addLayout(left_panel, 1)
        main_layout.addLayout(right_panel, 3)
        self.setLayout(main_layout)

    def connect_to_esp(self):
        ip = self.ip_input.text()
        if not ip:
            self.status_label.setText("Please enter an IP address.")
            return
        try:
            self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.client_socket.settimeout(10)
            self.client_socket.connect((ip, 1234))
            self.connected = True
            self.status_label.setText(f"Connected to {ip}")
            threading.Thread(target=self.receive_data, daemon=True).start()
        except Exception as e:
            self.status_label.setText(f"Connection failed: {e}")

    def set_preset(self):
        if not self.connected or not self.client_socket:
            self.status_label.setText("Not connected to ESP32.")
            return
        try:
            index = self.preset_combo.currentIndex()
            preset = self.presets[index]
            x, y, z = preset["x"], preset["y"], preset["z"]
            preset_msg = f"PRESET:x:{x:.2f},y:{y:.2f},z:{z:.2f}\n"
            self.client_socket.send(preset_msg.encode())
            self.preset_data = {"x": x, "y": y, "z": z}
            self.preset_label.setText(
                f"Preset:\nX: {x:.2f}\nY: {y:.2f}\nZ: {z:.2f}"
            )
            self.status_label.setText(f"Sent preset {preset['name']} to {self.ip_input.text()}")
            self.overlay_mesh.setVisible(True)  # Show overlay when preset is set
            self.preset_x_line.setValue(x)
            self.preset_y_line.setValue(y)
            self.preset_z_line.setValue(z)
            self.preset_x_line.setVisible(True)
            self.preset_y_line.setVisible(True)
            self.preset_z_line.setVisible(True)
        except Exception as e:
            self.status_label.setText(f"Error sending preset: {e}")

    def clear_preset_momentary(self):
        if self.connected and self.client_socket:
            try:
                self.client_socket.send("PRESET:CLEAR\n".encode())
                self.preset_data = {"x": None, "y": None, "z": None}
                self.preset_label.setText("Preset:\nX: --\nY: --\nZ: --")
                self.status_label.setText(f"Sent clear command to {self.ip_input.text()}")
                self.overlay_mesh.setVisible(False)  # Hide overlay when cleared
                self.preset_x_line.setVisible(False)
                self.preset_y_line.setVisible(False)
                self.preset_z_line.setVisible(False)
            except Exception as e:
                self.status_label.setText(f"Error sending clear: {e}")

    def normalize_angle(self, angle):
        return angle - 360 if angle >= 180 else angle

    def receive_data(self):
        buffer = ""
        last_msg_time = time.time()
        while self.connected:
            try:
                data = self.client_socket.recv(1024).decode()
                if not data:
                    self.connected = False
                    self.status_label.setText("Disconnected")
                    break
                buffer += data
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.startswith("PRESET:CLEAR"):
                        self.preset_data = {"x": None, "y": None, "z": None}
                        self.preset_label.setText("Preset:\nX: --\nY: --\nZ: --")
                        self.overlay_mesh.setVisible(False)  # Hide overlay on clear from ESP32
                        self.preset_x_line.setVisible(False)
                        self.preset_y_line.setVisible(False)
                        self.preset_z_line.setVisible(False)
                    elif line.startswith("PRESET:"):
                        try:
                            parts = line[7:].split(",")
                            self.preset_data = {
                                "x": float(parts[0].split(":")[1]),
                                "y": float(parts[1].split(":")[1]),
                                "z": float(parts[2].split(":")[1])
                            }
                            self.preset_label.setText(
                                f"Preset:\nX: {self.preset_data['x']:.2f}\n"
                                f"Y: {self.preset_data['y']:.2f}\nZ: {self.preset_data['z']:.2f}"
                            )
                            self.overlay_mesh.setVisible(True)  # Show overlay when preset is received
                            self.preset_x_line.setValue(self.preset_data["x"])
                            self.preset_y_line.setValue(self.preset_data["y"])
                            self.preset_z_line.setValue(self.preset_data["z"])
                            self.preset_x_line.setVisible(True)
                            self.preset_y_line.setVisible(True)
                            self.preset_z_line.setVisible(True)
                        except Exception as e:
                            print(f"Preset parse error: {e}")
                    elif line.startswith("X:") and ",Y:" in line and ",Z:" in line:
                        try:
                            parts = line.strip().split(',')
                            self.angle_data["x"] = self.normalize_angle(float(parts[0].split(":")[1]))
                            self.angle_data["y"] = self.normalize_angle(float(parts[1].split(":")[1]))
                            self.angle_data["z"] = self.normalize_angle(float(parts[2].split(":")[1]))
                            last_msg_time = time.time()
                            self.signal_label.setText(f"Signal: OK")
                            self.signal_label.setStyleSheet("color: green;")
                        except Exception as e:
                            print(f"Parsing error: {e}")
                if time.time() - last_msg_time > 2:
                    self.signal_label.setText("Signal: Lost")
                    self.signal_label.setStyleSheet("color: red;")
            except (socket.timeout, ConnectionError):
                self.connected = False
                self.status_label.setText("Disconnected")
                break
            except Exception as e:
                print(f"Socket error: {e}")
                break
        if self.client_socket:
            self.client_socket.close()

    def update_cube(self):
        x = self.angle_data["x"]
        y = self.angle_data["y"]
        z = self.angle_data["z"]

        self.angle_label.setText(f"Current:\nX: {x:.2f}\nY: {y:.2f}\nZ: {z:.2f}")

        if self.preset_data["x"] is not None:
            self.preset_label.setText(
                f"Preset:\nX: {self.preset_data['x']:.2f}\n"
                f"Y: {self.preset_data['y']:.2f}\nZ: {self.preset_data['z']:.2f}"
            )
            # Update overlay cube orientation to match preset
            self.overlay_mesh.resetTransform()
            self.overlay_mesh.rotate(self.preset_data["x"], 1, 0, 0)
            self.overlay_mesh.rotate(self.preset_data["y"], 0, 1, 0)
            self.overlay_mesh.rotate(self.preset_data["z"], 0, 0, 1)
        else:
            self.overlay_mesh.setVisible(False)  # Ensure overlay is hidden if no preset

        self.mesh.resetTransform()
        self.mesh.rotate(x, 1, 0, 0)
        self.mesh.rotate(y, 0, 1, 0)
        self.mesh.rotate(z, 0, 0, 1)

        # Update history for plotting
        t = time.time() - self.start_time
        self.data_history["time"].append(t)
        self.data_history["x"].append(x)
        self.data_history["y"].append(y)
        self.data_history["z"].append(z)
        if len(self.data_history["time"]) > 200:
            for key in self.data_history:
                self.data_history[key].pop(0)

    def update_plot(self):
        self.x_curve.setData(self.data_history["time"], self.data_history["x"])
        self.y_curve.setData(self.data_history["time"], self.data_history["y"])
        self.z_curve.setData(self.data_history["time"], self.data_history["z"])
        if self.preset_data["x"] is not None:
            self.preset_x_line.setValue(self.preset_data["x"])
            self.preset_y_line.setValue(self.preset_data["y"])
            self.preset_z_line.setValue(self.preset_data["z"])

if __name__ == "__main__":
    app = QApplication(sys.argv)
    try:
        window = IMUVisualizer()
        window.show()
        sys.exit(app.exec_())  # Corrected to include parentheses
    except Exception as e:
        print(f"Error during execution: {e}")
        sys.exit(1)