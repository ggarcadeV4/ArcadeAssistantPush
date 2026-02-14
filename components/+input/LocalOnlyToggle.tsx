// @component: LocalOnlyToggle
// @role: Toggles local-only mode to disable cloud calls
// @used_by: ApiKeyManagerPanel (B2), enforced by Janus

import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export default function LocalOnlyToggle({
  enabled,
  onToggle
}: {
  enabled: boolean;
  onToggle: (val: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between border-t border-white/10 pt-4 mt-2">
      <div>
        <Label className="text-white/90 text-sm font-medium">
          Use Local AI Only
        </Label>
        <p className="text-xs text-white/60">Disable all cloud API calls</p>
      </div>
      <Switch checked={enabled} onCheckedChange={onToggle} />
    </div>
  );
}