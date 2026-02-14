// @component: AgentLiveLog
// @role: Displays a live scrolling feed of agent activity and warnings
// @used_by: DebugPanel (C3)

import { ScrollArea } from "@/components/ui/scroll-area";

export default function AgentLiveLog({ logs = [] }: { logs?: string[] }) {
  if (!logs.length) {
    return (
      <div className="text-sm text-white/80 italic">
        No agent events recorded yet.
      </div>
    );
  }

  return (
    <ScrollArea className="h-32 pr-2">
      <ul className="text-sm space-y-1 text-white/90">
        {logs.map((line, idx) => (
          <li key={idx} className="opacity-90">
            • {line}
          </li>
        ))}
      </ul>
    </ScrollArea>
  );
}