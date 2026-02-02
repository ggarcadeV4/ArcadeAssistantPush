// @component: ApiKeyField
// @role: Allows secure input and testing of a single provider API key
// @used_by: ApiKeyManagerPanel (B2)

import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Check, X, Loader2 } from "lucide-react";

const statusColor = {
  Valid: "bg-green-600",
  Expired: "bg-yellow-500",
  Invalid: "bg-red-600",
  Missing: "bg-black/30",
  Testing: "bg-blue-500"
};

const statusIcon = {
  Valid: <Check className="w-3 h-3" />,
  Expired: <X className="w-3 h-3" />,
  Invalid: <X className="w-3 h-3" />,
  Missing: null,
  Testing: <Loader2 className="w-3 h-3 animate-spin" />
};

export default function ApiKeyField({
  provider,
  value,
  status,
  onChange,
  onTest
}: {
  provider: string;
  value: string;
  status: "Valid" | "Expired" | "Invalid" | "Missing" | "Testing";
  onChange: (val: string) => void;
  onTest: () => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <label className="text-sm font-semibold">{provider}</label>
      <div className="flex items-center gap-2">
        <Input
          type="password"
          value={value}
          onChange={e => onChange(e.target.value)}
          className="w-full text-white/90"
          placeholder="Enter API Key..."
        />
        <Button size="sm" variant="secondary" onClick={onTest} aria-label="Test Key">
          Test
        </Button>
        <Badge className={`${statusColor[status]} flex items-center gap-1`}>
          {statusIcon[status]}
          {status}
        </Badge>
      </div>
    </div>
  );
}