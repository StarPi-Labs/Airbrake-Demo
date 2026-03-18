import argparse
import serial
from serial.tools import list_ports


def detect_usb_port():
	ports = list_ports.comports()
	for port in ports:
		descriptor = f"{port.description} {port.hwid}".lower()
		if "usb" in descriptor:
			return port.device
	return ports[0].device if ports else None


def build_parser():
	parser = argparse.ArgumentParser(description="Read serial data at 115200 baud.")
	parser.add_argument(
		"-p",
		"--port",
		help="Serial port name (for example COM3). If omitted, tries to auto-detect USB port.",
	)
	parser.add_argument(
		"-b",
		"--baudrate",
		type=int,
		default=115200,
		help="Baud rate for serial communication (default: 115200).",
	)
	return parser


def main():
	args = build_parser().parse_args()

	port = args.port or detect_usb_port()
	if not port:
		print("No serial port found. Connect the device or pass --port COMx")
		return

	print(f"Opening {port} at {args.baudrate} baud...")
	with serial.Serial(port=port, baudrate=args.baudrate, timeout=1) as ser:
		print("Reading serial data. Press Ctrl+C to stop.")
		try:
			while True:
				line = ser.readline()
				if line:
					print(f"Raw Line: {line.decode('utf-8', errors='replace').rstrip()}")
					'''					
					analog_value = line.decode("utf-8", errors="replace").rstrip().split(",")[0].split(":")[1].strip()
					print(f"Analog Value: {analog_value}")
					'''
				else:
					print("Disconnected.")
					break
		except KeyboardInterrupt:
			print("Stopped.")


if __name__ == "__main__":
	main()

