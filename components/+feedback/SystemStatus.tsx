// @component: SystemStatus
// @role: Displays label + value for one system metric (mic, cloud, usb, audit)
// @used_by: DebugPanel (C3)

import { Badge } from "@/components/ui/badge";
import { Mic, Plug, Cloud, ShieldCheck } from "lucide-react";

const iconMap = {
  Echo: <Mic className="w-4 h-4" />,
  Argus: <Plug className="w-4 h-4" />,
  Hermes: <Cloud className="w-4 h-4" />,
  Oracle: <ShieldCheck className="w-4 h-4" />
};

export default function SystemStatus({
  label,
  value,
  agent
}: {
  label: string;
  value: string;
  agent: "Echo" | "Argus" | "Hermes" | "Oracle";
}) {
  return (
    <div className="flex items-center gap-2 justify-between">
      <div className="flex items-center gap-2">
        {iconMap[agent]}
        <span className="font-semibold">{label}</span>
      </div>
      <Badge className="bg-black/30 text-white/90">{value}</Badge>
    </div>
  );
}