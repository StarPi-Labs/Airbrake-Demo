import argparse
import serial
from serial.tools import list_ports


def detect_usb_port() -> str | None:
	ports = list_ports.comports()
	for port in ports:
		descriptor = f"{port.description} {port.hwid}".lower()
		if "usb" in descriptor:
			return port.device
	return ports[0].device if ports else None


def main():
	parser = argparse.ArgumentParser(description="Read serial data at 115200 baud.")
	parser.add_argument(
		"--port",
		help="Serial port name (for example COM3). If omitted, tries to auto-detect USB port.",
	)
	args = parser.parse_args()

	port = args.port or detect_usb_port()
	if not port:
		print("No serial port found. Connect the device or pass --port COMx")
		return

	print(f"Opening {port} at 115200 baud...")
	with serial.Serial(port=port, baudrate=115200, timeout=1) as ser:
		print("Reading serial data. Press Ctrl+C to stop.")
		try:
			while True:
				line = ser.readline()
				if line:
					analog_value = line.decode("utf-8", errors="replace").rstrip().split(",")[0].split(":")[1].strip()
					print(f"Analog Value: {analog_value}")
		except KeyboardInterrupt:
			print("Stopped.")


if __name__ == "__main__":
	main()

