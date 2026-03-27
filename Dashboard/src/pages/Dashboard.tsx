import { Component, createEffect, createSignal, onCleanup, Show, Switch, Match} from "solid-js";
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
    const telemetryApiUrl = import.meta.env.VITE_TELEMETRY_API_URL ?? "http://localhost:8000";
    const [connectionMode, setConnectionMode] = createSignal<"connecting" | "live" | "disconnected">("connecting");
    const [sample, setSample] = createSignal<AtmosphericSample>({
        ts: Date.now(),
        runId: 1,
        flightState: "ready",
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
        goalAltitudeM: 3000,
        distanceToGoalM: 3000,
    });
    const target = sample().goalAltitudeM;
    const tollerance = 50;
    const lowerLimit = target - tollerance;
    const t_limit = target + tollerance;

    

    const [isRestarting, setIsRestarting] = createSignal(false);
    const [missionStatus, setMissionStatus] = createSignal<"ready" | "flying" | "success"| "overshoot" | "undershoot">("flying")

    const CELEBRATION_VIDEO_SRC = "assets/video/vitcory.mp4";
    const UNDERSHOOT_VIDEO_SRC = "assets/video/fail.mp4";
    const OVERSHOOT_VIDEO_SRC = "assets/video/fail.mp4";

    

    let ws: WebSocket | undefined;
    let reconnectTimeout: number | undefined;

    const restartFlight = async () => {
        if (isRestarting()) return;
        setIsRestarting(true);
        try {
            await fetch(`${telemetryApiUrl}/flight/restart`, { method: "POST" });
        } finally {
            setIsRestarting(false);
        }
    };

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

    const flightStateLabel = () => {
        if (sample().flightState === "complete") return "Apogee Reached";
        if (sample().flightState === "ascending") return "Ascending";
        return "Ready";
    };

    createEffect(() => {
        const currentAlt = sample().alt;
        const flightState = sample().flightState;
        const currentState = missionStatus();

        if (flightState === "ready" && currentState !== "ready") {
            setMissionStatus("ready");
            return; 
        }

        if (flightState === "ascending" && currentState === "ready") {
            setMissionStatus("flying");
        }

        if (currentAlt > t_limit && currentState !== "overshoot") {
            setMissionStatus("overshoot");
        } 
        else if (flightState === "complete" && currentState === "flying") {
            if (currentAlt >= lowerLimit && currentAlt <= t_limit) {setMissionStatus("success");} 
            else if (currentAlt < lowerLimit) {setMissionStatus("undershoot");}
        }
    });

    const graphTime = () => (sample().flightState === "complete" ? undefined : sample().ts);


    const videoSources = () => {
        const defaultCameras = [
            { id: "cam1", label: "Front Camera", src: "assets/video/199582-910653711_medium.mp4" },
            { id: "cam2", label: "Bottom Camera", src: "assets/video/854224-hd_1280_720_30fps.mp4" },
            { id: "cam3", label: "Arm Camera", src: "assets/video/arm-test.mp4" }
        ];

        if (missionStatus() === "success") {return [{ id: "celebration", label: "🚀 TARGET RAGGIUNTO!", src: CELEBRATION_VIDEO_SRC }];}
        if (missionStatus() === "overshoot") {return [{ id: "o_fail", label: "Missione Fallita", src: OVERSHOOT_VIDEO_SRC }];}
        if (missionStatus() === "undershoot") {return [{ id: "u_fail", label: "Missione Fallita", src: UNDERSHOOT_VIDEO_SRC }];}

        return defaultCameras;
    };

    return (
        <div class="space-y-6">
            <div class="flex items-center justify-between gap-3 flex-wrap">
                <h1 class="text-2xl font-semibold">Dashboard</h1>
                <div class="flex items-center gap-2 flex-wrap">
                    <div class={connectionBadgeClass()}>{connectionLabel()}</div>
                    <div class="badge badge-secondary badge-outline">{flightStateLabel()}</div>
                    <div class="badge badge-outline">Airbrake {sample().airbrakePct.toFixed(1)}%</div>
                    <button class="btn btn-sm btn-primary" onClick={() => void restartFlight()} disabled={isRestarting()}>
                        {isRestarting() ? "Restarting..." : "Restart Flight"}
                    </button>
                </div>
            </div>

            <div class="alert alert-info py-2">
                <span>
                    Goal 3000m: {sample().distanceToGoalM.toFixed(1)}m away
                    {sample().flightState === "complete" ? " (flight stopped at apogee)" : ""}
                </span>
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

             <Switch>
                {/*SUCCESS*/}
                <Match when={missionStatus() === "success"}>
                    <div class="alert alert-success shadow-lg mt-4 border-2 border-green-500 animate-bounce">
                        <span class="text-3xl">🏆</span>
                        <div>
                            <h3 class="font-bold text-lg">Missione Compiuta!</h3>
                            <div class="text-sm">
                                Il volo è terminato a quota <strong>{sample().alt.toFixed(1)}m</strong>, 
                                rimanendo nel range di tolleranza ({lowerLimit}m - {t_limit}m).
                            </div>
                        </div>
                    </div>
                </Match>

                {/*OVERSHOOT*/}
                <Match when={missionStatus() === "overshoot"}>
                    <div class="alert alert-error shadow-lg mt-4 border-2 border-red-500 animate-pulse text-white">
                        <span class="text-3xl">💥</span>
                        <div>
                            <h3 class="font-bold text-lg">Limite massimo superato! Non hai frenato abbastanza</h3>
                            <div class="text-sm">
                                Altitudine massima ({t_limit}m) violata. 
                                Quota attuale: <strong>{sample().alt.toFixed(1)}m</strong>.
                            </div>
                        </div>
                    </div>
                </Match>

                {/*UNDERSHOOT:*/}
                <Match when={missionStatus() === "undershoot"}>
                    <div class="alert alert-warning shadow-lg mt-4 border-2 border-yellow-500">
                        <span class="text-3xl">📉</span>
                        <div>
                            <h3 class="font-bold text-lg">Obiettivo non raggiunto! Hai frenato troppo</h3>
                            <div class="text-sm">
                                Il velivolo ha raggiunto l'apogeo a <strong>{sample().alt.toFixed(1)}m</strong>. 
                                Sono mancati {(target - sample().alt).toFixed(1)}m per raggiungere l'obiettivo.
                            </div>
                        </div>
                    </div>
                </Match>
            </Switch>

            <div class="grid grid-cols-1 lg:grid-cols-4 gap-4">

                <div class="lg:col-span-2 h-full">
                    <VideoPlayer sources={videoSources()} objectFit="cover" />
                </div>

                <div class="flex flex-col sm:flex-row gap-4 lg:col-span-2">
                    
                    {/* SOTTO-COLONNA GRAFICI*/}
                    <div class="flex flex-col gap-4 flex-1 w-full sm:w-0">
                        <VelocityGraphCard
                            time={graphTime()}
                            verticalVelocity={sample().vvel}
                            horizontalVelocity={sample().hvel}
                            resetKey={sample().runId}
                            class="w-full"
                        />

                        <AltitudeGraphCard
                            time={graphTime()}
                            altitude={sample().alt}
                            resetKey={sample().runId}
                            class="w-full"
                        />
                    </div>

                    <AltitudeTracker
                        currentAltitude={sample().alt}
                        targetAltitude={target}
                        maxAltitude={4000}
                        class="w-full sm:w-28 shrink-0 h-[350px] sm:h-auto"
                    />
                </div>

            </div>
            <div class="grid gap-4">
                <AccellerationGraphCard
                    time={graphTime()}
                    accelX={sample().accelX}
                    accelY={sample().accelY}
                    accelZ={sample().accelZ}
                    resetKey={sample().runId}
                    class="w-full"
                />
            </div>
        </div>

    );
};

export default Dashboard;