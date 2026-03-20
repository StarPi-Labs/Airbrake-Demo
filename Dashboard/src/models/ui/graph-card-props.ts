import { JSX } from "solid-js";
import { GraphLineConfig } from "./graph-line";

export interface GraphCardProps {
    title: string;
    subtitle?: string;
    newPoint?: any;
    resetKey?: number;
    maxPoints?: number;
    xKey: string;
    lines: GraphLineConfig[];
    controls?: JSX.Element;
    class?: string;
}