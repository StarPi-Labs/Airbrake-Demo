import { Component, createSignal, onCleanup } from "solid-js";
import AttitudeCard from "../components/AttitudeCard";
import AtmosphereCard from "../components/AtmosphereCard";
import NavigationCard from "../components/NavigationCard";
import { AtmosphericSample } from "../models/atmospheric-sample";
import VelocityGraphCard from "../components/VelocityGraphCard";
import AltitudeGraphCard from "../components/AltitudeGraphCard";
import VideoPlayer from "../components/VideoPlayer";
import AccellerationGraphCard from "../components/AccellerationGraphCard";
import AltitudeTracker from "../components/AltitudeTracker";

const Dashboard: Component = () => {
    const telemetryWsUrl = import.meta.env.VITE_TELEMETRY_WS_URL ?? "ws://localhost:8000/ws/telemetry";
    const [connectionMode, setConnectionMode] = createSignal<"connecting" | "live" | "disconnected">("connecting");
    const [sample, setSample] = createSignal<AtmosphericSample>({
        ts: Date.now(),
        roll: 0,
        pitch: 0,
        yaw: 0,
        status: false,
        alt: 0,
        vvel: 0,
        hvel: 0,
        lat: 0,
        long: 0,
        gps: false,
        temp: 0,
        pres: 0,
        rh: 0,
        accelX: 0,
        accelY: 0,
        accelZ: 0,
        airbrakePct: 0,
        controlMode: "serial",
    });
    let ws: WebSocket | undefined;
    let reconnectTimeout: number | undefined;

    const connectTelemetry = () => {
        setConnectionMode("connecting");
        try {
            ws = new WebSocket(telemetryWsUrl);
        } catch {
            setConnectionMode("disconnected");
            reconnectTimeout = window.setTimeout(connectTelemetry, 2000);
            return;
        }

        ws.onopen = () => {
            setConnectionMode("live");
        };

        ws.onmessage = (event) => {
            try {
                const incoming = JSON.parse(event.data) as AtmosphericSample;
                if (typeof incoming?.ts === "number") {
                    setSample(incoming);
                }
            } catch {
                // Ignore malformed packets and keep the current sample.
            }
        };

        ws.onerror = () => {
            ws?.close();
        };

        ws.onclose = () => {
            setConnectionMode("disconnected");
            reconnectTimeout = window.setTimeout(connectTelemetry, 2000);
        };
    };

    connectTelemetry();

    onCleanup(() => {
        if (reconnectTimeout) window.clearTimeout(reconnectTimeout);
        ws?.close();
    });

    const timestampLabel = () => {
        const value = sample().ts;
        return new Date(value).toLocaleTimeString();
    };

    const connectionBadgeClass = () => {
        if (connectionMode() === "live") return "badge badge-success badge-outline";
        if (connectionMode() === "disconnected") return "badge badge-warning badge-outline";
        return "badge badge-info badge-outline";
    };

    const connectionLabel = () => {
        if (connectionMode() === "live") return "Live Backend";
        if (connectionMode() === "disconnected") return "Disconnected";
        return "Connecting...";
    };

    return (
        <div class="space-y-6">
            <div class="flex items-center justify-between gap-3 flex-wrap">
                <h1 class="text-2xl font-semibold">Dashboard</h1>
                <div class="flex items-center gap-2 flex-wrap">
                    <div class={connectionBadgeClass()}>{connectionLabel()}</div>
                    <div class="badge badge-outline">Airbrake {sample().airbrakePct.toFixed(1)}%</div>
                </div>
            </div>

            <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
                <AttitudeCard
                    roll={sample().roll}
                    pitch={sample().pitch}
                    yaw={sample().yaw}
                    status={sample().status}
                    timestampLabel={timestampLabel()}
                />
                <AtmosphereCard
                    temperature={sample().temp}
                    pressure={sample().pres}
                    humidity={sample().rh}
                />
                <NavigationCard
                    altitude={sample().alt}
                    verticalVelocity={sample().vvel}
                    horizontalVelocity={sample().hvel}
                    latitude={sample().lat}
                    longitude={sample().long}
                    gpsFix={sample().gps}
                />
            </div>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">

                <div class="lg:col-span-2 h-full">
                    <VideoPlayer
                        sources={[
                            { id: "cam1", label: "Front Camera", src: "/video/199582-910653711_medium.mp4" },
                            { id: "cam2", label: "Bottom Camera", src: "video/854224-hd_1280_720_30fps.mp4" },
                            { id: "cam3", label: "Arm Camera", src: "/video/arm-test.mp4" }
                        ]}
                        objectFit="cover"
                    />
                </div>

                <div class="flex flex-col sm:flex-row gap-4 lg:col-span-2">

                    {/* SOTTO-COLONNA GRAFICI (flex-1 gli fa prendere tutto lo spazio rimasto) */}
                    <div class="flex flex-col gap-4 flex-1 w-full sm:w-0">
                        <VelocityGraphCard
                            time={sample().ts}
                            verticalVelocity={sample().vvel}
                            horizontalVelocity={sample().hvel}
                            class="w-full"
                        />

                        <AltitudeGraphCard
                            time={sample().ts}
                            altitude={sample().alt}
                            class="w-full"
                        />
                    </div>

                    {/* IL RAZZO (Largo fisso 112px o 128px, ma si stira in altezza) */}
                    <AltitudeTracker
                        currentAltitude={sample().alt}
                        targetAltitude={3000}
                        maxAltitude={4000}
                        class="w-full sm:w-28 shrink-0 h-[350px] sm:h-auto"
                    />

                </div>

            </div>
            <div class="grid gap-4">
                <AccellerationGraphCard
                    time={sample().ts}
                    accelX={sample().accelX}
                    accelY={sample().accelY}
                    accelZ={sample().accelZ}
                    class="w-full"
                />
            </div>
        </div>

    );
};

export default Dashboard;
