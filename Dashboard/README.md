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

### External Airbrake Control (0 to 4096)

The simulator airbrake is externally commanded with an integer value in the range `0..4096`.

Set command value:

```bash
curl -X PUT http://localhost:8000/control/airbrake/2048
```

Read current command/applied state:

```bash
curl http://localhost:8000/control/airbrake
```

Notes:
- `airbrakeCommandRaw` is the exact command value (`0..4096`).
- `airbrakeCommandNorm` is normalized command (`0..1`).
- `airbrakeAppliedNorm` is the simulated applied opening (`0..1`) with actuator lag.

### `npm run build`

Builds the app for production to the `dist` folder.<br>
It correctly bundles Solid in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.<br>
Your app is ready to be deployed!

## Deployment

You can deploy the `dist` folder to any static host provider (netlify, surge, now, etc.)

## This project was created with the [Solid CLI](https://github.com/solidjs-community/solid-cli)
