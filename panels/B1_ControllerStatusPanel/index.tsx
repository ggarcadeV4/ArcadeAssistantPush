// @panel: B1_ControllerStatusPanel
// @role: Real-time controller detection + status dashboard
// @owner: Hera
// @agent: Argus
// @layout: col-span-1 row-span-1
// @connected_panels: DebugPanel

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { motion } from "framer-motion";
import { Gamepad } from "lucide-react";

// Mock controller data — will be replaced by Argus feed
const mockControllers = [
  { name: "8BitDo SN30 Pro", player: "Player 1", type: "Bluetooth", status: "Connected" },
  { name: "iPAC2", player: "Player 2", type: "HID", status: "Connected" },
  { name: "Generic USB Gamepad", player: "Unassigned", type: "USB", status: "Disconnected" }
];

const getStatus = () => {
  const allConnected = mockControllers.every(d => d.status === "Connected");
  const anyMissing = mockControllers.some(d => d.status === "Disconnected");
  if (allConnected) return "All Connected";
  if (anyMissing) return "Some Missing";
  return "Idle";
};

export default function ControllerStatusPanel() {
  const chip = getStatus();

  return (
    <motion.div className="col-span-1 row-span-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Card className="bg-emerald-600 text-white rounded-2xl shadow-lg">
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Gamepad className="w-5 h-5" />
            <h2 className="text-xl font-semibold">Controllers</h2>
          </div>
          <Badge className="bg-black/30">{chip}</Badge>
        </CardHeader>

        <CardContent className="p-4 space-y-3 text-sm">
          {mockControllers.length > 0 ? (
            <>
              {mockControllers.map((d, i) => (
                <div
                  key={i}
                  className={`flex justify-between items-center rounded-md p-2 ${
                    d.status === "Connected"
                      ? "bg-white/10"
                      : "bg-white/10 border border-red-400"
                  }`}
                >
                  <div className="flex flex-col">
                    <span className="font-medium truncate max-w-[150px]" title={d.name}>
                      {d.name}
                    </span>
                    <span className="text-xs opacity-80">
                      {d.player} — {d.type}
                    </span>
                  </div>
                  <Badge className={d.status === "Connected" ? "bg-green-600" : "bg-red-600"}>
                    {d.status}
                  </Badge>
                </div>
              ))}
            </>
          ) : (
            <div className="text-sm opacity-80 italic py-4 text-center">
              No controllers detected. Connect a device to begin.
            </div>
          )}

          <div className="text-xs text-white/70 pt-2 border-t border-white/10">
            Devices: {mockControllers.length} | Last updated: 2025-09-26 18:12
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}