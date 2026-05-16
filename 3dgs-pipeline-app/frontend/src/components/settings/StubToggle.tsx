import { Switch } from "@/components/ui/switch"
import { Badge } from "@/components/ui/badge"

interface StubToggleProps {
  tool: string          // "RealityCapture" | "LichtFeld Studio"
  enabled: boolean
  onChange: (val: boolean) => void
  durationSeconds?: number
  onDurationChange?: (val: number) => void
}

export function StubToggle({
  tool, enabled, onChange, durationSeconds, onDurationChange
}: StubToggleProps) {
  return (
    <div className="border border-orange-500/30 rounded-md p-3 mt-4 bg-orange-500/5">
      <div className="flex items-center gap-2 mb-2">
        <Badge variant="outline" className="text-orange-400 border-orange-400 text-xs">
          DEV
        </Badge>
        <span className="text-xs text-orange-300 font-mono">Stub Mode</span>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-slate-300">Simulate {tool}</p>
          <p className="text-xs text-slate-500 mt-0.5">
            {enabled
              ? "Real tool NOT called — fake logs + outputs generated"
              : "Real tool will be called — ensure exe path is set"}
          </p>
        </div>
        <Switch checked={enabled} onCheckedChange={onChange} />
      </div>
      {enabled && durationSeconds !== undefined && onDurationChange && (
        <div className="mt-3">
          <label className="text-xs text-slate-400">
            Simulation duration: <span className="text-cyan-400">{durationSeconds}s</span>
          </label>
          <input
            type="range" min={3} max={60} step={1}
            value={durationSeconds}
            onChange={e => onDurationChange(Number(e.target.value))}
            className="w-full mt-1 accent-cyan-400"
          />
        </div>
      )}
    </div>
  )
}
