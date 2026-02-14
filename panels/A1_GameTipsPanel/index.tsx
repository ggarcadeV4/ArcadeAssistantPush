// @panel: A1_GameTipsPanel
// @role: Displays game-specific tips and secrets based on running title
// @owner: Hera
// @layout: col-span-1 row-span-1
// @connected_agents: Claude, Hephaestus, Hermes

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { motion } from "framer-motion";
import { Book } from "lucide-react";

// Placeholder tips — should be replaced by context engine (Hephaestus)
const mockTips = [
  "Up, Up, Down, Down, Left, Right, Left, Right, B, A",
  "Hold Start to skip intro scenes",
  "Press Select twice to enter debug mode"
];

export default function GameTipsPanel() {
  const gameDetected = true; // This should come from context service
  const status = gameDetected ? "Context Found" : "Idle";
  const tips = gameDetected ? mockTips : [];

  return (
    <motion.div className="col-span-1 row-span-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Card className="bg-blue-600 text-white rounded-2xl shadow-lg">
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Book className="w-5 h-5" />
            <h2 className="text-xl font-semibold">Game Tips</h2>
          </div>
          <Badge className="bg-black/30">{status}</Badge>
        </CardHeader>

        <CardContent className="p-4 space-y-4">
          {tips.length > 0 ? (
            <ul className="text-sm leading-6 list-disc pl-4 space-y-1">
              {tips.map((tip, idx) => (
                <li key={idx}>{tip}</li>
              ))}
            </ul>
          ) : (
            <div className="text-sm opacity-80 italic">
              No tips found for current game.
            </div>
          )}

          <div className="text-xs text-white/70 pt-2">
            Source: {gameDetected ? "Local Knowledgebase" : "N/A"}
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}