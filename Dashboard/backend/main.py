from __future__ import annotations

import asyncio
import importlib
import logging
import math
import os
import random
import re
import time
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger("telemetry-backend")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

try:
    serial = importlib.import_module("serial")
    list_ports = importlib.import_module("serial.tools.list_ports")

    SERIAL_AVAILABLE = True
except ImportError:
    serial = None
    list_ports = None
    SERIAL_AVAILABLE = False

if SERIAL_AVAILABLE:
    logger.info("pyserial available: serial input enabled")
else:
    logger.warning("pyserial not installed: serial input disabled")

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
        self._launch_lat = 43.725
        self._launch_long = 10.393694444444445

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
        self._rocket_dry_mass_kg = 20.0
        self._motor_mass_initial_kg = 4.5
        self._motor_mass_burnout_kg = 1.4
        self._motor_accel_peak_m_s2 = 200.0
        self._motor_accel_end_ratio = 0.8

        # Vertical drag factors (simple quadratic model).
        self._rocket_drag_coeff = 0.095
        self._airbrake_drag_coeff_full = 0.28

        self._airbrake = 0.0
        self._airbrake_command_raw = 0
        self._airbrake_command_norm = 0.0
        self._control_mode = "serial"

        # Serial command source configuration.
        self._serial_baudrate = int(os.getenv("AIRBRAKE_SERIAL_BAUDRATE", "115200"))
        self._serial_port_override = os.getenv("AIRBRAKE_SERIAL_PORT")
        self._serial_port: str | None = None
        self._serial_connection: Any | None = None
        self._serial_last_connect_attempt_ms = 0
        self._serial_reconnect_interval_ms = 2000
        self._serial_failure_count = 0
        self._serial_last_value_ms = 0
        self._serial_stale_timeout_s = 1.5

        # Attitude and position state
        self._roll = 0.0
        self._pitch = 0.0
        self._yaw = 0.0
        self._lat = self._launch_lat
        self._long = self._launch_long
        self._vel_east_m_s = 0.0
        self._vel_north_m_s = 0.0

        # Atmospheric state
        self._temp = 20.0
        self._pres = 1013.0
        self._rh = 55.0
        self._status_ok = True
        self._gps_ok = True

        # Lateral acceleration state for smooth curves
        self._accel_x = 0.0
        self._accel_y = 0.0

        self._post_flight_hold_s = 0.0
        self._goal_altitude_m = 3000.0
        self._flight_state = "ready"
        self._run_id = 1

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
            self._serial_failure_count = 0
            self._serial_reconnect_interval_ms = 2000
        except Exception as exc:
            self._serial_failure_count += 1
            # Back off retries to avoid flooding logs when a port is busy/unavailable.
            self._serial_reconnect_interval_ms = min(60_000, 2000 * (2 ** min(self._serial_failure_count, 5)))
            logger.warning(
                "Serial connection failed on %s (%s). Retry in %.1fs [attempt=%s]",
                port,
                exc,
                self._serial_reconnect_interval_ms / 1000.0,
                self._serial_failure_count,
            )
            self._close_serial()

    def _poll_serial_command(self, now_ms: int) -> None:
        self._connect_serial_if_needed(now_ms)
        if self._serial_connection is None:
            return

        try:
            while self._serial_connection.in_waiting > 0:
                line = self._serial_connection.readline().decode("utf-8", errors="replace").strip()
                value = self._extract_airbrake_value(line)
                if value is None:
                    continue
                self.set_airbrake_command(value)
                self._serial_last_value_ms = now_ms
        except Exception as exc:
            logger.warning("Serial polling failed (%s), closing serial connection", exc)
            self._close_serial()

    def set_airbrake_command(self, raw_value: int) -> Dict[str, float | int | bool | str]:

        clamped = int(clamp(raw_value, 0, 4096))
        self._airbrake_command_raw = clamped
        self._airbrake_command_norm = clamped / 4096.0
        self._airbrake = self._airbrake_command_norm
        return {
            "accepted": True,
            "source": "serial",
            "airbrakeCommandRaw": self._airbrake_command_raw,
            "airbrakeCommandNorm": self._airbrake_command_norm,
            "airbrakeCommandPct": self._airbrake_command_norm * 100.0,
            "controlMode": self._control_mode,
            "serialConnected": self._serial_connection is not None,
            "serialPort": self._serial_port or "",
        }

    def get_airbrake_state(self) -> Dict[str, float | int | bool | str]:
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
        self._flight_state = "ready"
        self._roll = random.uniform(-1.5, 1.5)
        self._pitch = random.uniform(-1.5, 1.5)
        self._yaw = random.uniform(-2.0, 2.0)
        self._lat = self._launch_lat
        self._long = self._launch_long
        self._vel_east_m_s = 0.0
        self._vel_north_m_s = 0.0
        self._temp = 20.0 + random.uniform(-2.0, 2.0)
        self._pres = 1013.0 + random.uniform(-2.0, 2.0)
        self._rh = 55.0 + random.uniform(-5.0, 5.0)
        self._status_ok = True
        self._gps_ok = True
        self._accel_x = 0.0
        self._accel_y = 0.0
        self._post_flight_hold_s = 0.0

    def restart_flight(self) -> Dict[str, float | int | bool | str]:
        self._run_id += 1
        self._reset_flight()
        return {
            "accepted": True,
            "runId": self._run_id,
            "flightState": self._flight_state,
            "goalAltitudeM": self._goal_altitude_m,
        }

    def _update_flight(self, dt_s: float) -> None:
        if self._flight_state == "complete":
            # Hold final state until explicit restart request.
            self._vvel = 0.0
            self._vertical_accel = 0.0
            return

        self._flight_t += dt_s

        # Keep rocket on launch pad until launch delay expires.
        if self._flight_t < self._launch_idle_s:
            self._airbrake = self._airbrake_command_norm
            self._vertical_accel = 0.0
            self._vvel = 0.0
            self._alt = 0.0
            self._vel_east_m_s = self._smooth(self._vel_east_m_s, 0.0, 0.20)
            self._vel_north_m_s = self._smooth(self._vel_north_m_s, 0.0, 0.20)
            self._hvel = math.hypot(self._vel_east_m_s, self._vel_north_m_s)
            self._flight_state = "ready"
            return

        self._flight_state = "ascending"

        # Launch motor profile: strong at ignition, then taper.
        burn_elapsed = self._flight_t - self._launch_idle_s
        thrust_accel = 0.0
        if 0.0 <= burn_elapsed < self._burn_time_s:
            burn_progress = burn_elapsed / self._burn_time_s
            thrust_accel = self._motor_accel_peak_m_s2 * (1.0 - (1.0 - self._motor_accel_end_ratio) * burn_progress)

        # Airbrake opening is directly commanded (0..4096 mapped to 0..1).
        self._airbrake = self._airbrake_command_norm

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

        # Trig-coupled horizontal dynamics: motor vector + wind + damping.
        yaw_rad = math.radians(self._yaw)
        pitch_rad = math.radians(self._pitch)
        roll_rad = math.radians(self._roll)

        motor_h_accel = max(0.0, thrust_accel) * max(0.0, math.sin(abs(pitch_rad)))
        roll_side_accel = max(0.0, thrust_accel) * math.sin(roll_rad) * 0.35

        accel_north_motor = motor_h_accel * math.cos(yaw_rad) - roll_side_accel * math.sin(yaw_rad)
        accel_east_motor = motor_h_accel * math.sin(yaw_rad) + roll_side_accel * math.cos(yaw_rad)

        wind_speed = 5.0 + 2.5 * math.sin(self._flight_t / 7.0)
        wind_heading_rad = math.radians(10.0 * math.sin(self._flight_t / 11.0))
        wind_north = wind_speed * math.cos(wind_heading_rad)
        wind_east = wind_speed * math.sin(wind_heading_rad)

        drag_h = 0.035 + 0.06 * self._airbrake
        self._vel_north_m_s += accel_north_motor * dt_s
        self._vel_east_m_s += accel_east_motor * dt_s
        self._vel_north_m_s = self._smooth(self._vel_north_m_s, wind_north, 0.02) - drag_h * self._vel_north_m_s * dt_s
        self._vel_east_m_s = self._smooth(self._vel_east_m_s, wind_east, 0.02) - drag_h * self._vel_east_m_s * dt_s

        self._hvel = clamp(math.hypot(self._vel_east_m_s, self._vel_north_m_s), 0.0, 120.0)

        # Convert ENU velocity components into geodetic drift.
        self._lat += (self._vel_north_m_s * dt_s) / 111_111.0
        self._long += (self._vel_east_m_s * dt_s) / (111_111.0 * max(math.cos(math.radians(self._lat)), 0.25))

        if self._vvel <= 0.0 and self._flight_t > self._launch_idle_s:
            self._vvel = 0.0
            self._vertical_accel = 0.0
            self._flight_state = "complete"
            return

    def next_sample(self) -> Dict[str, float | int | bool | str]:
        now = int(time.time() * 1000)
        dt_s = clamp((now - self._last_ts) / 1000.0, 0.02, 0.2)
        self._last_ts = now

        self._poll_serial_command(now)

        self._update_flight(dt_s)

        if self._flight_state != "complete":
            # Attitude trends follow flight phase with smooth noisy motion.
            if self._vvel > 0:
                target_pitch = clamp(7.0 + self._vvel / 22.0, -10.0, 16.0)
            else:
                target_pitch = clamp(-4.0 + self._vvel / 22.0, -12.0, 6.0)

            heading_deg = 0.0
            if self._hvel > 0.15:
                heading_deg = math.degrees(math.atan2(self._vel_east_m_s, self._vel_north_m_s))

            target_roll = clamp(3.0 * math.sin(self._flight_t * 0.8) + random.uniform(-0.9, 0.9), -9.0, 9.0)
            target_yaw = clamp(0.45 * heading_deg + 3.0 * math.sin(self._flight_t / 6.5), -25.0, 25.0)

            self._pitch = self._smooth(self._pitch, target_pitch + random.uniform(-0.8, 0.8), 0.08)
            self._roll = self._smooth(self._roll, target_roll, 0.10)
            self._yaw = self._smooth(self._yaw, target_yaw, 0.10)

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
            self._status_ok = random.random() < status_prob
            self._gps_ok = random.random() < gps_prob

        sample = {
            "ts": now,
            "runId": self._run_id,
            "flightState": self._flight_state,
            "roll": self._roll,
            "pitch": self._pitch,
            "yaw": self._yaw,
            "status": self._status_ok,
            "alt": self._alt,
            "vvel": self._vvel,
            "hvel": self._hvel,
            "lat": self._lat,
            "long": self._long,
            "gps": self._gps_ok,
            "temp": self._temp,
            "pres": self._pres,
            "rh": self._rh,
            "accelX": self._accel_x,
            "accelY": self._accel_y,
            "accelZ": self._vertical_accel,
            "airbrakePct": self._airbrake * 100.0,
            "controlMode": self._control_mode,
            "goalAltitudeM": self._goal_altitude_m,
            "distanceToGoalM": abs(self._goal_altitude_m - self._alt),
            "massTotalKg": self._current_total_mass(),
            "massMotorKg": self._current_motor_mass(),
        }

        return sample


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


telemetry_generator = TelemetryGenerator()


@app.get("/control/airbrake")
async def get_airbrake() -> Dict[str, float | int | bool | str]:
    logger.info("State endpoint hit: GET /control/airbrake")
    return telemetry_generator.get_airbrake_state()


@app.post("/flight/restart")
async def restart_flight() -> Dict[str, float | int | bool | str]:
    logger.info("Flight restart requested")
    return telemetry_generator.restart_flight()


@app.websocket("/ws/telemetry")
async def telemetry_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    try:
        while True:
            await websocket.send_json(telemetry_generator.next_sample())
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        return
