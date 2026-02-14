// @panel: B2_ApiKeyManagerPanel
// @role: Secure API key entry and testing for Claude, OpenAI, Anthropic
// @owner: Hera
// @layout: col-span-1 row-span-1
// @connected_agents: Hermes, Janus

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { motion } from "framer-motion";
import { Key } from "lucide-react";

import ApiKeyField from "@/components/+input/ApiKeyField";
import LocalOnlyToggle from "@/components/+input/LocalOnlyToggle";

// Mock key statuses for initial layout
const keys = [
  {
    provider: "Claude",
    id: "claude_api",
    value: "sk-cl...abc",
    status: "Valid"
  },
  {
    provider: "OpenAI",
    id: "openai_api",
    value: "",
    status: "Missing"
  },
  {
    provider: "Anthropic",
    id: "anthropic_api",
    value: "sk-an...xyz",
    status: "Expired"
  }
];

export default function ApiKeyManagerPanel() {
  const allValid = keys.every(k => k.status === "Valid");
  const chip = allValid ? "All Valid" : keys.some(k => k.status !== "Missing") ? "Partial" : "Missing";

  return (
    <motion.div className="col-span-1 row-span-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Card className="bg-emerald-600 text-white rounded-2xl shadow-lg">
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Key className="w-5 h-5" />
            <h2 className="text-xl font-semibold">API Keys</h2>
          </div>
          <Badge className="bg-black/30">{chip}</Badge>
        </CardHeader>

        <CardContent className="p-4 space-y-4">
          {/* Key fields */}
          {keys.map(key => (
            <ApiKeyField
              key={key.id}
              provider={key.provider}
              value={key.value}
              status={key.status}
              onChange={() => {}}
              onTest={() => {}}
            />
          ))}

          {/* Local-only toggle */}
          <LocalOnlyToggle enabled={false} onToggle={() => {}} />

          {/* Footer */}
          <div className="text-xs text-white/70 pt-2">
            Your keys are stored locally and never shared.
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}