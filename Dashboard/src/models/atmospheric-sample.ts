import { InertialSample } from "./inertial-sample"

export interface AtmosphericSample extends InertialSample {
    alt: number
    vvel: number
    hvel: number
    lat: number
    long: number
    gps: boolean
    temp: number
    pres: number
    rh: number
    accelX: number
    accelY: number
    accelZ: number
    airbrakeCmd: number
    airbrake: number
    airbrakeCmdPct: number
    airbrakePct: number
    controlMode: "serial" | "keyboard"
    serialConnected: boolean
    serialPort: string
}
