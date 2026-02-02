// @panel: B3_ClaudeTestPanel
// @role: Dev tool to test Claude API call + fallback enforcement
// @owner: Hera
// @agent: ClaudeCloudClient

import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { motion } from "framer-motion";
import { Send, Bot } from "lucide-react";
import { useState } from "react";

// Claude client (real API call with Hermes + Janus)
import { call_claude } from "@/services/claude_client";

export default function ClaudeTestPanel() {
  const [input, setInput] = useState("");
  const [output, setOutput] = useState("");
  const [loading, setLoading] = useState(false);

  const handleTest = async () => {
    if (!input.trim()) return;

    setLoading(true);
    try {
      const response = await call_claude(input);
      setOutput(response);
    } catch (error) {
      setOutput(`Error: ${error.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleTest();
    }
  };

  return (
    <motion.div className="col-span-1 row-span-1" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <Card className="bg-purple-600 text-white rounded-2xl shadow-lg">
        <CardHeader className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Bot className="w-5 h-5" />
            <h2 className="text-xl font-semibold">Claude Test</h2>
          </div>
          <div className="text-xs opacity-70">ESC to clear</div>
        </CardHeader>

        <CardContent className="p-4 space-y-4">
          <Input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask Claude something..."
            className="text-black"
            disabled={loading}
          />

          <div className="flex gap-2">
            <Button
              onClick={handleTest}
              disabled={loading || !input.trim()}
              className="text-white flex-1"
              variant="secondary"
            >
              <Send className="w-4 h-4 mr-2" />
              {loading ? "Sending..." : "Send"}
            </Button>

            <Button
              onClick={() => { setInput(""); setOutput(""); }}
              variant="secondary"
              className="text-white"
              size="sm"
            >
              Clear
            </Button>
          </div>

          <div className="text-sm text-white/80 border-t border-white/10 pt-3 min-h-[60px] max-h-[120px] overflow-y-auto">
            {output || "No response yet. This panel tests real Claude API calls through Janus security."}
          </div>

          <div className="text-xs text-white/60 pt-2">
            All calls logged to agent_calls/ • Respects local-only mode
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}