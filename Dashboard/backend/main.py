from __future__ import annotations

import asyncio
import importlib
import math
import os
import random
import re
import time
from typing import Any, Dict, Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

try:
    serial = importlib.import_module("serial")
    list_ports = importlib.import_module("serial.tools.list_ports")

    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False

app = FastAPI(title="Telemetry Test Backend", version="0.1.0")

# Allow local frontend development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def detect_usb_port() -> str | None:
    if not SERIAL_AVAILABLE or list_ports is None:
        return None
    ports = list_ports.comports()
    for port in ports:
        descriptor = f"{port.description} {port.hwid}".lower()
        if "usb" in descriptor:
            return port.device
    return ports[0].device if ports else None


class TelemetryGenerator:
    def __init__(self) -> None:
        self._flight_t = 0.0
        self._last_ts = int(time.time() * 1000)
        self._launch_idle_s = 1.0

        # Kinematic state
        self._alt = 0.0
        self._vvel = 0.0
        self._hvel = 0.0
        self._vertical_accel = 0.0

        # Launch/mass model placeholders (easy to tune later)
        self._burn_time_s = 20.0
        self._rocket_dry_mass_kg = 12.0
        self._motor_mass_initial_kg = 4.5
        self._motor_mass_burnout_kg = 1.4
        self._motor_accel_peak_m_s2 = 42.0
        self._motor_accel_end_ratio = 0.8

        # Vertical drag factors (simple quadratic model).
        self._rocket_drag_coeff = 0.095
        self._airbrake_drag_coeff_full = 0.28

        self._airbrake = 0.0
        self._airbrake_command_raw = 0
        self._airbrake_command_norm = 0.0
        self._control_mode: Literal["serial", "keyboard"] = "keyboard"

        # Serial command source configuration.
        self._serial_baudrate = int(os.getenv("AIRBRAKE_SERIAL_BAUDRATE", "115200"))
        self._serial_port_override = os.getenv("AIRBRAKE_SERIAL_PORT")
        self._serial_port: str | None = None
        self._serial_connection: Any | None = None
        self._serial_last_connect_attempt_ms = 0
        self._serial_reconnect_interval_ms = 2000
        self._serial_last_value_ms = 0
        self._serial_stale_timeout_s = 1.5

        # Attitude and position state
        self._roll = 0.0
        self._pitch = 0.0
        self._yaw = 0.0
        self._lat = 43.37
        self._long = 10.13

        # Atmospheric state
        self._temp = 20.0
        self._pres = 1013.0
        self._rh = 55.0

        # Lateral acceleration state for smooth curves
        self._accel_x = 0.0
        self._accel_y = 0.0

        self._post_flight_hold_s = 0.0

    def _current_motor_mass(self) -> float:
        burn_elapsed = self._flight_t - self._launch_idle_s
        if burn_elapsed <= 0:
            return self._motor_mass_initial_kg
        if burn_elapsed >= self._burn_time_s:
            return self._motor_mass_burnout_kg
        burn_progress = burn_elapsed / self._burn_time_s
        return self._motor_mass_initial_kg + (self._motor_mass_burnout_kg - self._motor_mass_initial_kg) * burn_progress

    def _current_total_mass(self) -> float:
        return self._rocket_dry_mass_kg + self._current_motor_mass()

    @staticmethod
    def _smooth(current: float, target: float, alpha: float) -> float:
        return current + alpha * (target - current)

    def _is_serial_fresh(self, now_ms: int) -> bool:
        if self._serial_connection is None:
            return False
        return (now_ms - self._serial_last_value_ms) <= int(self._serial_stale_timeout_s * 1000)

    def _refresh_control_mode(self, now_ms: int) -> None:
        self._control_mode = "serial" if self._is_serial_fresh(now_ms) else "keyboard"

    @staticmethod
    def _extract_airbrake_value(raw_line: str) -> int | None:
        # Accept either a plain integer or packets like "airbrake: 1234".
        match = re.search(r"\d+", raw_line)
        if not match:
            return None
        try:
            return int(match.group(0))
        except ValueError:
            return None

    def _close_serial(self) -> None:
        if self._serial_connection is None:
            return
        try:
            self._serial_connection.close()
        finally:
            self._serial_connection = None
            self._serial_port = None

    def _connect_serial_if_needed(self, now_ms: int) -> None:
        if not SERIAL_AVAILABLE or self._serial_connection is not None:
            return
        if (now_ms - self._serial_last_connect_attempt_ms) < self._serial_reconnect_interval_ms:
            return

        self._serial_last_connect_attempt_ms = now_ms
        port = self._serial_port_override or detect_usb_port()
        if not port:
            return

        try:
            self._serial_connection = serial.Serial(
                port=port,
                baudrate=self._serial_baudrate,
                timeout=0.02,
            )
            self._serial_port = port
        except Exception:
            self._close_serial()

    def _poll_serial_command(self, now_ms: int) -> None:
        self._connect_serial_if_needed(now_ms)
        if self._serial_connection is None:
            self._refresh_control_mode(now_ms)
            return

        try:
            while self._serial_connection.in_waiting > 0:
                line = self._serial_connection.readline().decode("utf-8", errors="replace").strip()
                value = self._extract_airbrake_value(line)
                if value is None:
                    continue
                self.set_airbrake_command(value, source="serial", now_ms=now_ms)
                self._serial_last_value_ms = now_ms
        except Exception:
            self._close_serial()

        self._refresh_control_mode(now_ms)

    def set_airbrake_command(
        self,
        raw_value: int,
        source: Literal["serial", "keyboard"] = "keyboard",
        now_ms: int | None = None,
    ) -> Dict[str, float | int | bool | str]:
        if now_ms is None:
            now_ms = int(time.time() * 1000)
        self._refresh_control_mode(now_ms)

        if source == "keyboard" and self._control_mode == "serial":
            return {
                "accepted": False,
                "message": "Serial control is active. Keyboard fallback is disabled.",
                **self.get_airbrake_state(),
            }

        clamped = int(clamp(raw_value, 0, 4096))
        self._airbrake_command_raw = clamped
        self._airbrake_command_norm = clamped / 4096.0
        return {
            "accepted": True,
            "source": source,
            "airbrakeCommandRaw": self._airbrake_command_raw,
            "airbrakeCommandNorm": self._airbrake_command_norm,
            "airbrakeCommandPct": self._airbrake_command_norm * 100.0,
            "controlMode": self._control_mode,
            "serialConnected": self._serial_connection is not None,
            "serialPort": self._serial_port or "",
        }

    def get_airbrake_state(self) -> Dict[str, float | int | bool | str]:
        now_ms = int(time.time() * 1000)
        self._refresh_control_mode(now_ms)
        return {
            "airbrakeCommandRaw": self._airbrake_command_raw,
            "airbrakeCommandNorm": self._airbrake_command_norm,
            "airbrakeCommandPct": self._airbrake_command_norm * 100.0,
            "airbrakeAppliedNorm": self._airbrake,
            "airbrakeAppliedPct": self._airbrake * 100.0,
            "controlMode": self._control_mode,
            "serialConnected": self._serial_connection is not None,
            "serialPort": self._serial_port or "",
        }

    def _reset_flight(self) -> None:
        self._flight_t = 0.0
        self._alt = 0.0
        self._vvel = 0.0
        self._hvel = 0.0
        self._vertical_accel = 0.0
        self._airbrake = self._airbrake_command_norm
        self._roll = random.uniform(-2.0, 2.0)
        self._pitch = random.uniform(-2.0, 2.0)
        self._yaw = random.uniform(0.0, 360.0)
        self._lat = 43.37 + random.uniform(-0.002, 0.002)
        self._long = 10.13 + random.uniform(-0.002, 0.002)
        self._temp = 20.0 + random.uniform(-2.0, 2.0)
        self._pres = 1013.0 + random.uniform(-2.0, 2.0)
        self._rh = 55.0 + random.uniform(-5.0, 5.0)
        self._accel_x = 0.0
        self._accel_y = 0.0
        self._post_flight_hold_s = 0.0

    def _update_flight(self, dt_s: float) -> None:
        self._flight_t += dt_s

        # Keep rocket on launch pad until launch delay expires.
        if self._flight_t < self._launch_idle_s:
            self._airbrake = self._smooth(self._airbrake, self._airbrake_command_norm, 0.18)
            self._vertical_accel = 0.0
            self._vvel = 0.0
            self._alt = 0.0
            self._hvel = self._smooth(self._hvel, 0.0, 0.20)
            return

        # Launch motor profile: strong at ignition, then taper.
        burn_elapsed = self._flight_t - self._launch_idle_s
        thrust_accel = 0.0
        if 0.0 <= burn_elapsed < self._burn_time_s:
            burn_progress = burn_elapsed / self._burn_time_s
            thrust_accel = self._motor_accel_peak_m_s2 * (1.0 - (1.0 - self._motor_accel_end_ratio) * burn_progress)

        # Airbrake opening is externally commanded (0..4096 mapped to 0..1).
        # Keep a small actuator lag so movement is physically plausible.
        self._airbrake = self._smooth(self._airbrake, self._airbrake_command_norm, 0.18)

        total_mass = self._current_total_mass()
        thrust_force = total_mass * thrust_accel

        # Drag grows with velocity^2; airbrake increases drag area/coeff.
        drag_coeff = self._rocket_drag_coeff + self._airbrake_drag_coeff_full * self._airbrake
        drag_force = drag_coeff * self._vvel * abs(self._vvel)
        gravity = 9.81
        weight_force = total_mass * gravity

        # Sign of drag opposes vertical motion.
        drag_direction = -1.0 if self._vvel >= 0 else 1.0
        net_force = thrust_force - weight_force + drag_direction * drag_force
        self._vertical_accel = net_force / total_mass

        # Add tiny vibration/noise to avoid perfectly smooth traces.
        self._vertical_accel += random.uniform(-0.25, 0.25)

        # Integrate motion.
        self._vvel += self._vertical_accel * dt_s
        self._alt = max(0.0, self._alt + self._vvel * dt_s)

        # Horizontal speed: mild wind drift, damped over time.
        wind_target = 7.0 + 4.0 * math.sin(self._flight_t / 8.0)
        if thrust_accel > 0:
            wind_target += 2.0
        self._hvel = self._smooth(self._hvel, wind_target + random.uniform(-0.8, 0.8), 0.08)
        self._hvel = clamp(self._hvel, 0.0, 80.0)

        # End-of-flight handling and automatic relaunch after short hold.
        if self._alt <= 0.0 and self._flight_t > (self._launch_idle_s + self._burn_time_s + 8.0):
            self._vvel = 0.0
            self._vertical_accel = 0.0
            self._post_flight_hold_s += dt_s
            if self._post_flight_hold_s >= 2.0:
                self._reset_flight()

    def next_sample(self) -> Dict[str, float | int | bool | str]:
        now = int(time.time() * 1000)
        dt_s = clamp((now - self._last_ts) / 1000.0, 0.02, 0.2)
        self._last_ts = now

        self._poll_serial_command(now)

        self._update_flight(dt_s)

        # Attitude trends follow flight phase with smooth noisy motion.
        if self._vvel > 0:
            target_pitch = clamp(8.0 + self._vvel / 18.0, -15.0, 18.0)
        else:
            target_pitch = clamp(-6.0 + self._vvel / 22.0, -20.0, 8.0)

        self._pitch = self._smooth(self._pitch, target_pitch + random.uniform(-0.8, 0.8), 0.08)
        self._roll = self._smooth(self._roll, random.uniform(-6.0, 6.0), 0.05)
        yaw_rate = 0.7 + 1.2 * (self._hvel / 80.0)
        self._yaw = (self._yaw + yaw_rate * dt_s * 12.0 + random.uniform(-0.5, 0.5)) % 360.0

        # Position drifts with horizontal velocity and heading.
        ground_speed_m_s = self._hvel
        dx = ground_speed_m_s * math.cos(math.radians(self._yaw)) * dt_s
        dy = ground_speed_m_s * math.sin(math.radians(self._yaw)) * dt_s
        self._lat += dy / 111_111.0
        self._long += dx / (111_111.0 * max(math.cos(math.radians(self._lat)), 0.25))

        # Atmosphere model from altitude with smoothing and slight turbulence.
        target_temp = 20.0 - 0.0065 * self._alt
        target_pres = 1013.25 * (1.0 - 2.25577e-5 * self._alt) ** 5.2559
        target_rh = clamp(62.0 - 0.018 * self._alt, 15.0, 90.0)
        self._temp = self._smooth(self._temp, target_temp + random.uniform(-0.35, 0.35), 0.12)
        self._pres = self._smooth(self._pres, target_pres + random.uniform(-0.9, 0.9), 0.12)
        self._rh = self._smooth(self._rh, target_rh + random.uniform(-0.8, 0.8), 0.10)

        # Lateral accelerations are smooth vibrations + maneuver coupling.
        lateral_target_x = 0.12 * math.sin(self._flight_t * 2.0) + 0.03 * self._roll
        lateral_target_y = 0.12 * math.cos(self._flight_t * 1.5) + 0.03 * self._pitch
        self._accel_x = self._smooth(self._accel_x, lateral_target_x + random.uniform(-0.04, 0.04), 0.15)
        self._accel_y = self._smooth(self._accel_y, lateral_target_y + random.uniform(-0.04, 0.04), 0.15)

        # status/gps become less reliable with high vibration and near-apogee dynamics.
        dynamic_stress = abs(self._vertical_accel) + abs(self._roll) * 0.2 + abs(self._pitch) * 0.2
        status_prob = clamp(0.995 - dynamic_stress * 0.004, 0.92, 0.999)
        gps_prob = clamp(0.98 - self._airbrake * 0.08 - abs(self._pitch) * 0.002, 0.86, 0.995)

        sample = {
            "ts": now,
            "roll": self._roll,
            "pitch": self._pitch,
            "yaw": self._yaw,
            "status": random.random() < status_prob,
            "alt": self._alt,
            "vvel": self._vvel,
            "hvel": self._hvel,
            "lat": self._lat,
            "long": self._long,
            "gps": random.random() < gps_prob,
            "temp": self._temp,
            "pres": self._pres,
            "rh": self._rh,
            "accelX": self._accel_x,
            "accelY": self._accel_y,
            # Vertical acceleration in g for the chart.
            "accelZ": self._vertical_accel / 9.81,
            "airbrakeCmd": self._airbrake_command_raw,
            "airbrake": self._airbrake,
            "airbrakeCmdPct": self._airbrake_command_norm * 100.0,
            "airbrakePct": self._airbrake * 100.0,
            "controlMode": self._control_mode,
            "serialConnected": self._serial_connection is not None,
            "serialPort": self._serial_port or "",
            "massTotalKg": self._current_total_mass(),
            "massMotorKg": self._current_motor_mass(),
        }

        return sample


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


telemetry_generator = TelemetryGenerator()


@app.put("/control/airbrake/{value}")
async def set_airbrake(value: int) -> Dict[str, float | int | bool | str]:
    return telemetry_generator.set_airbrake_command(value, source="keyboard")


@app.get("/control/airbrake")
async def get_airbrake() -> Dict[str, float | int | bool | str]:
    return telemetry_generator.get_airbrake_state()


@app.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(telemetry_generator.next_sample())
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
