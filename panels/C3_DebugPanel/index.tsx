// @panel: C3_DebugPanel
// @role: Always-on diagnostics and system event monitor
// @owner: Hera
// @layout: col-span-1 row-span-1
// @connected_agents: Echo, Argus, Hermes, Oracle

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { Wrench, Camera, MoreHorizontal } from "lucide-react";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { useState } from "react";
import AgentLiveLog from "@/components/+feedback/AgentLiveLog";
import SystemStatus from "@/components/+feedback/SystemStatus";
import InlineError from "@/components/ui/inline-error"; // Assume this exists

const mockLogs = [
  "Echo: Mic started listening",
  "Argus: Controller connected (P1)",
  "Hermes: Firebase sync failed (retrying...)",
  "Oracle: Layout audit passed (9/9 panels)"
];

export default function DebugPanel() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [captureResult, setCaptureResult] = useState<{type: 'success' | 'error', message: string} | null>(null);

  const handleCaptureScreen = async () => {
    setIsCapturing(true);
    setCaptureResult(null);

    try {
      // Use Electron invoke method as you prefer
      const result = await window.electron.invoke("screencap::capture_full_screen");

      if (result && !result.includes("Error")) {
        setCaptureResult({
          type: 'success',
          message: `Screen captured: ${result}`
        });
      } else {
        setCaptureResult({
          type: 'error',
          message: result || 'Screen capture failed'
        });
      }
    } catch (error) {
      setCaptureResult({
        type: 'error',
        message: 'Failed to capture screen'
      });
    } finally {
      setIsCapturing(false);
    }
  };

  return (
    <motion.div className="col-span-1 row-span-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Card className="bg-orange-500 text-white rounded-2xl shadow-lg">
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Wrench className="w-5 h-5" />
            <h2 className="text-xl font-semibold">Debug Console</h2>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="secondary"
              className="text-white bg-white/20 hover:bg-white/30 border-white/30"
              onClick={handleCaptureScreen}
              disabled={isCapturing}
            >
              <Camera className="w-4 h-4" />
            </Button>
            <Badge className="bg-black/30">Online</Badge>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="secondary" className="text-white bg-white/20 hover:bg-white/30">
                  <MoreHorizontal className="w-4 h-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem>Settings</DropdownMenuItem>
                <DropdownMenuItem>Clear Logs</DropdownMenuItem>
                <DropdownMenuItem>Help</DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>

        <CardContent className="p-4 space-y-4">
          {/* Agent Event Log */}
          <AgentLiveLog logs={mockLogs} />

          {/* Status Grid */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            <SystemStatus label="Microphone" value="Listening" agent="Echo" />
            <SystemStatus label="Controllers" value="2 Connected" agent="Argus" />
            <SystemStatus label="Cloud Sync" value="Offline" agent="Hermes" />
            <SystemStatus label="Auditor" value="Last Scan: OK" agent="Oracle" />
          </div>

          {/* Inline Error Example */}
          <InlineError message="Mic access blocked in browser. Click here to fix." />

          {/* Screen Capture Result */}
          {captureResult && (
            <div className={`text-sm p-2 rounded ${
              captureResult.type === 'success'
                ? 'bg-green-600/30 text-green-100'
                : 'bg-red-600/30 text-red-100'
            }`}>
              {captureResult.message}
            </div>
          )}

          {/* Footer */}
          <div className="text-xs text-white/70 pt-2">
            Last updated: 2025-09-26 17:49
            {isCapturing && " | Capturing screen..."}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}