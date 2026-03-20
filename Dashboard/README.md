## Usage

Those templates dependencies are maintained via [pnpm](https://pnpm.io) via `pnpm up -Lri`.

This is the reason you see a `pnpm-lock.yaml`. That being said, any package manager will work. This file can be safely be removed once you clone a template.

```bash
$ npm install # or pnpm install or yarn install
```

### Learn more on the [Solid Website](https://solidjs.com) and come chat with us on our [Discord](https://discord.com/invite/solidjs)

## Available Scripts

In the project directory, you can run:

### `npm run dev` or `npm start`

Runs the app in the development mode.<br>
Open [http://localhost:3000](http://localhost:3000) to view it in the browser.

The page will reload if you make edits.<br>

## Telemetry Test Backend (FastAPI)

This project can consume live telemetry over WebSocket from a local Python backend.

1. Create and activate a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install backend dependencies:

```bash
pip install -r backend/requirements.txt
```

3. Run the FastAPI telemetry server:

```bash
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

4. Start the frontend:

```bash
npm run dev
```

The dashboard connects to `ws://localhost:8000/ws/telemetry` by default.

Optional: override the WebSocket URL with an environment variable:

```bash
VITE_TELEMETRY_WS_URL=ws://localhost:8000/ws/telemetry npm run dev
```

If the socket is unavailable, the dashboard automatically falls back to local simulated telemetry.

### Airbrake Control (Serial First + Keyboard Fallback)

The backend now prefers live serial input for airbrake command values (`0..4096`).

- If a USB serial device is available, incoming values drive the airbrake command.
- If serial is unavailable (or stale), keyboard fallback is enabled from the dashboard UI with `Arrow Up` / `Arrow Down`.
- The dashboard shows both command and applied airbrake percentages.

Optional serial environment variables:

```bash
AIRBRAKE_SERIAL_PORT=COM3
AIRBRAKE_SERIAL_BAUDRATE=115200
```

Manual fallback API (used by keyboard controls):

```bash
curl -X PUT http://localhost:8000/control/airbrake/2048
curl http://localhost:8000/control/airbrake
```

Notes:
- `airbrakeCommandRaw` is the exact command value (`0..4096`).
- `airbrakeCommandNorm` and `airbrakeCommandPct` are the normalized/percent command values.
- `airbrakeAppliedNorm` and `airbrakeAppliedPct` are the simulated actuator-applied values.
- `controlMode` is either `serial` or `keyboard`.

### `npm run build`

Builds the app for production to the `dist` folder.<br>
It correctly bundles Solid in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.<br>
Your app is ready to be deployed!

## Deployment

You can deploy the `dist` folder to any static host provider (netlify, surge, now, etc.)

## This project was created with the [Solid CLI](https://github.com/solidjs-community/solid-cli)
