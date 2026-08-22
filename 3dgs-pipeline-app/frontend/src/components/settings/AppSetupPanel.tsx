import React, { useEffect, useMemo, useState } from 'react';
import {
  Boxes,
  Clapperboard,
  Filter,
  FolderCog,
  Gauge,
  Orbit,
  PackageOpen,
  RotateCcw,
  Scan,
  TriangleAlert,
} from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useDefaults } from '@/hooks/useDefaults';
import { useSettings } from '@/hooks/useSettings';
import type {
  AppDefaults,
  ColmapExportDefaults,
  DefaultsSection,
  UndistortDefaults,
} from '@/types';

/* ── Small field primitives ─────────────────────────────────────────────── */

const Row: React.FC<{
  label: string;
  hint?: string;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ label, hint, wide, children }) => (
  <div className="flex items-start justify-between gap-6 py-2">
    <div className="min-w-0">
      <Label className="text-slate-200">{label}</Label>
      {hint && <p className="text-xs text-slate-500 mt-0.5 leading-snug">{hint}</p>}
    </div>
    <div className={wide ? 'shrink-0 w-[380px]' : 'shrink-0 w-[220px]'}>{children}</div>
  </div>
);

const NumField: React.FC<{
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  disabled?: boolean;
}> = ({ value, onChange, step = 1, min, disabled }) => (
  <Input
    type="number"
    step={step}
    min={min}
    value={value}
    disabled={disabled}
    onChange={(e) => {
      const n = Number(e.target.value);
      if (!Number.isNaN(n)) onChange(n);
    }}
    className="bg-slate-950 border-slate-700 text-slate-100 disabled:opacity-50"
  />
);

const TextField: React.FC<{ value: string; onChange: (v: string) => void; placeholder?: string }> = ({
  value,
  onChange,
  placeholder,
}) => (
  <Input
    value={value}
    placeholder={placeholder}
    onChange={(e) => onChange(e.target.value)}
    className="bg-slate-950 border-slate-700 text-slate-100"
  />
);

/**
 * Editable free-text path box.
 *
 * Tool paths go straight to config.json, and `updateSettings` replaces the
 * whole settings object with the server response. Committing per keystroke
 * therefore raced the PUT and reset the caret, which made the box look
 * read-only. Keystrokes stay local; the commit happens on blur or Enter,
 * Escape reverts.
 */
const PathField: React.FC<{
  value: string;
  onCommit: (v: string) => void;
  placeholder?: string;
}> = ({ value, onCommit, placeholder }) => {
  const [local, setLocal] = useState(value);
  const [editing, setEditing] = useState(false);

  // Adopt external changes only while the user is not typing in this box.
  useEffect(() => {
    if (!editing) setLocal(value);
  }, [value, editing]);

  const commit = () => {
    setEditing(false);
    const trimmed = local.trim();
    if (trimmed !== local) setLocal(trimmed);
    if (trimmed !== value) onCommit(trimmed);
  };

  return (
    <Input
      value={local}
      placeholder={placeholder}
      spellCheck={false}
      autoComplete="off"
      title={local || placeholder}
      onFocus={() => setEditing(true)}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          e.currentTarget.blur();
        } else if (e.key === 'Escape') {
          e.preventDefault();
          setLocal(value);
          setEditing(false);
          e.currentTarget.blur();
        }
      }}
      className="bg-slate-950 border-slate-700 text-slate-100 font-mono text-xs"
    />
  );
};

/** Groups a run of rows under a heading, for sections long enough to need one. */
const SubHeading: React.FC<{ title: string; note?: string }> = ({ title, note }) => (
  <div className="pt-5 pb-1">
    <p className="text-xs font-semibold uppercase tracking-wide text-cyan-400">{title}</p>
    {note && <p className="text-xs text-slate-500 mt-1 leading-snug max-w-prose">{note}</p>}
  </div>
);

const Choice: React.FC<{
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}> = ({ value, onChange, options }) => (
  <Select value={value} onValueChange={onChange}>
    <SelectTrigger className="bg-slate-950 border-slate-700 text-slate-100">
      <SelectValue />
    </SelectTrigger>
    <SelectContent className="bg-slate-800 border-slate-700 text-slate-100">
      {options.map((o) => (
        <SelectItem key={o.value} value={o.value}>
          {o.label}
        </SelectItem>
      ))}
    </SelectContent>
  </Select>
);

/* ── Sections ───────────────────────────────────────────────────────────── */

type SectionId = DefaultsSection | 'tools';

const SECTIONS: { id: SectionId; label: string; icon: React.ElementType }[] = [
  { id: 'extract', label: 'Extraction', icon: Clapperboard },
  { id: 'curate', label: 'Curation', icon: Filter },
  { id: 'rc', label: 'RealityScan', icon: Scan },
  { id: 'lfs', label: 'LichtFeld', icon: Gauge },
  { id: 'export', label: 'Export', icon: PackageOpen },
  { id: 'blender', label: 'Blender', icon: Boxes },
  { id: 'viewer', label: '3D viewer', icon: Orbit },
  { id: 'tools', label: 'Tools', icon: FolderCog },
];

interface AppSetupPanelProps {
  open: boolean;
  onClose: () => void;
}

const AppSetupPanel: React.FC<AppSetupPanelProps> = ({ open, onClose }) => {
  const { defaults, presets, saving, error, updateDefaults, resetDefaults, previewFps } =
    useDefaults();
  const { settings, updateSettings } = useSettings();

  const [section, setSection] = useState<SectionId>('extract');
  // Local draft so typing does not fire a PUT per keystroke.
  const [draft, setDraft] = useState<AppDefaults | null>(null);
  const [sampleFps, setSampleFps] = useState(100);
  const [sampleDuration, setSampleDuration] = useState(120);
  const [fpsPreview, setFpsPreview] = useState<string>('');

  useEffect(() => {
    if (defaults) setDraft(defaults);
  }, [defaults]);

  const dirty = useMemo(
    () => !!draft && !!defaults && JSON.stringify(draft) !== JSON.stringify(defaults),
    [draft, defaults],
  );

  // Resolve the fps policy against a sample source, so the number is never a
  // black box. Debounced — every keystroke would otherwise hit the backend.
  useEffect(() => {
    if (!draft || section !== 'extract') return;
    const t = setTimeout(() => {
      previewFps(draft.extract, sampleFps || null, sampleDuration || null)
        .then((r) => setFpsPreview(r.explanation))
        .catch(() => setFpsPreview(''));
    }, 250);
    return () => clearTimeout(t);
  }, [draft, section, sampleFps, sampleDuration, previewFps]);

  const patch = <S extends DefaultsSection>(s: S, key: keyof AppDefaults[S], value: unknown) => {
    setDraft((d) => (d ? { ...d, [s]: { ...d[s], [key]: value } } : d));
  };

  // rc.colmap is two levels deep and rc.colmap.undistort three, which `patch`
  // cannot reach without replacing the whole sub-object and dropping its
  // siblings on every keystroke.
  const patchColmap = (key: keyof ColmapExportDefaults, value: unknown) => {
    setDraft((d) =>
      d ? { ...d, rc: { ...d.rc, colmap: { ...d.rc.colmap, [key]: value } } } : d,
    );
  };

  const patchUndistort = (key: keyof UndistortDefaults, value: unknown) => {
    setDraft((d) =>
      d
        ? {
            ...d,
            rc: {
              ...d.rc,
              colmap: {
                ...d.rc.colmap,
                undistort: { ...d.rc.colmap.undistort, [key]: value },
              },
            },
          }
        : d,
    );
  };

  const handleSave = async () => {
    if (!draft) return;
    await updateDefaults(draft);
  };

  const handleResetSection = async () => {
    if (section === 'tools') return;
    await resetDefaults(section);
  };

  const activePreset = presets.find((p) => p.id === draft?.extract.capture_preset);

  return (
    <Sheet open={open} onOpenChange={(o) => !o && onClose()}>
      <SheetContent
        side="right"
        className="sm:max-w-none w-[840px] max-w-[95vw] flex flex-col p-0"
      >
        <SheetHeader className="px-6 py-4 border-b border-slate-700">
          <SheetTitle className="text-slate-100">Application setup</SheetTitle>
          <p className="text-xs text-slate-500">
            Defaults applied to every new project. A project that overrides a value keeps its own.
          </p>
        </SheetHeader>

        <div className="flex flex-1 overflow-hidden">
          {/* Section rail */}
          <nav className="w-[190px] shrink-0 border-r border-slate-700 overflow-y-auto py-2">
            {SECTIONS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setSection(id)}
                className={`w-full flex items-center gap-2 px-4 py-2 text-sm text-left transition-colors ${
                  section === id
                    ? 'bg-slate-800 text-cyan-400 border-l-2 border-cyan-400'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/50 border-l-2 border-transparent'
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </button>
            ))}
          </nav>

          {/* Section body */}
          <div className="flex-1 overflow-y-auto px-6 py-4">
            {!draft && <p className="text-slate-500 text-sm">Loading defaults…</p>}

            {draft && section === 'extract' && (
              <div className="divide-y divide-slate-800">
                <Row
                  label="Capture preset"
                  hint={activePreset?.notes ?? 'Sets the target frame count and the overlap band.'}
                >
                  <Choice
                    value={draft.extract.capture_preset}
                    onChange={(v) => patch('extract', 'capture_preset', v)}
                    options={presets.map((p) => ({ value: p.id, label: p.label }))}
                  />
                </Row>

                <Row
                  label="Working fps mode"
                  hint="auto = target frames ÷ probed duration. ratio = fraction of the source cadence. absolute = a fixed number."
                >
                  <Choice
                    value={draft.extract.fps_mode}
                    onChange={(v) => patch('extract', 'fps_mode', v)}
                    options={[
                      { value: 'auto', label: 'Auto (from source)' },
                      { value: 'ratio', label: 'Ratio of source fps' },
                      { value: 'absolute', label: 'Absolute fps' },
                    ]}
                  />
                </Row>

                {draft.extract.fps_mode === 'auto' && (
                  <Row
                    label="Target frame count"
                    hint={
                      activePreset
                        ? `Clamped to ${activePreset.min_fps}–${activePreset.max_fps} fps by the preset.`
                        : undefined
                    }
                  >
                    <NumField
                      value={draft.extract.target_frame_count}
                      min={10}
                      step={10}
                      onChange={(v) => patch('extract', 'target_frame_count', v)}
                    />
                  </Row>
                )}

                <Row
                  label="Fps ratio"
                  hint="Used by ratio mode, and as the fallback when ffprobe gives no duration. 0.2 matches the RealityScan video-import default."
                >
                  <NumField
                    value={draft.extract.fps_ratio}
                    step={0.05}
                    min={0.01}
                    onChange={(v) => patch('extract', 'fps_ratio', v)}
                  />
                </Row>

                <Row label="Absolute fps" hint="Used by absolute mode, and when the source cadence is unknown.">
                  <NumField
                    value={draft.extract.fps_absolute}
                    step={0.5}
                    min={0.1}
                    onChange={(v) => patch('extract', 'fps_absolute', v)}
                  />
                </Row>

                <Row
                  label="Remove duplicate frames (mpdecimate)"
                  hint="Off by default: it duplicates the overlap gate and drops frames non-deterministically, breaking the frame-index ↔ timecode mapping curation relies on."
                >
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={draft.extract.mpdecimate}
                      onCheckedChange={(v) => patch('extract', 'mpdecimate', v)}
                    />
                    {draft.extract.mpdecimate && (
                      <span className="flex items-center gap-1 text-xs text-amber-400">
                        <TriangleAlert className="w-3.5 h-3.5" />
                        breaks curation
                      </span>
                    )}
                  </div>
                </Row>

                <Row label="JPEG quality" hint="FFmpeg -qscale:v — 1 is best, 5 is worst.">
                  <NumField
                    value={draft.extract.quality}
                    min={1}
                    onChange={(v) => patch('extract', 'quality', v)}
                  />
                </Row>

                <Row label="Max frames" hint="0 = unlimited.">
                  <NumField
                    value={draft.extract.max_frames}
                    min={0}
                    step={10}
                    onChange={(v) => patch('extract', 'max_frames', v)}
                  />
                </Row>

                {/* Policy preview */}
                <div className="pt-4">
                  <p className="text-xs uppercase tracking-wide text-slate-500 mb-2">
                    Preview on a sample source
                  </p>
                  <div className="flex items-end gap-3">
                    <div className="w-[120px]">
                      <Label className="text-xs text-slate-400">Source fps</Label>
                      <NumField value={sampleFps} step={5} min={1} onChange={setSampleFps} />
                    </div>
                    <div className="w-[120px]">
                      <Label className="text-xs text-slate-400">Duration (s)</Label>
                      <NumField value={sampleDuration} step={10} min={1} onChange={setSampleDuration} />
                    </div>
                  </div>
                  {fpsPreview && (
                    <p className="mt-3 text-sm text-cyan-400 font-mono bg-slate-950 border border-slate-800 rounded px-3 py-2">
                      {fpsPreview}
                    </p>
                  )}
                </div>
              </div>
            )}

            {draft && section === 'curate' && (
              <div className="divide-y divide-slate-800">
                <Row label="Curation enabled" hint="Blur rejection, scene cuts and the overlap gate.">
                  <Switch
                    checked={draft.curate.enabled}
                    onCheckedChange={(v) => patch('curate', 'enabled', v)}
                  />
                </Row>
                <Row
                  label="Run automatically after extraction"
                  hint="Analysis can always be re-run alone from step 2, without re-extracting."
                >
                  <Switch
                    checked={draft.curate.auto_after_extract}
                    onCheckedChange={(v) => patch('curate', 'auto_after_extract', v)}
                  />
                </Row>
                <Row label="Scene detector" hint="Adaptive tolerates constant camera motion such as orbits.">
                  <Choice
                    value={draft.curate.scene_detector}
                    onChange={(v) => patch('curate', 'scene_detector', v)}
                    options={[
                      { value: 'adaptive', label: 'Adaptive' },
                      { value: 'content', label: 'Content' },
                      { value: 'off', label: 'Off' },
                    ]}
                  />
                </Row>
                <Row label="Min scene length" hint="Frames. Shorter cuts are merged into the neighbouring sequence.">
                  <NumField
                    value={draft.curate.min_scene_len}
                    min={1}
                    onChange={(v) => patch('curate', 'min_scene_len', v)}
                  />
                </Row>
                <Row
                  label="Sharpness window"
                  hint="Rolling median window, in frames. Rejection is relative to this window — never an absolute threshold."
                >
                  <NumField
                    value={draft.curate.sharpness_window}
                    min={3}
                    onChange={(v) => patch('curate', 'sharpness_window', v)}
                  />
                </Row>
                <Row label="Sharpness sensitivity" hint="0–100. Higher rejects more aggressively.">
                  <NumField
                    value={draft.curate.sharpness_sensitivity}
                    min={0}
                    onChange={(v) => patch('curate', 'sharpness_sensitivity', v)}
                  />
                </Row>
                <Row
                  label="Overlap band from capture preset"
                  hint={
                    activePreset
                      ? `The preset carries the band along with the target frame count — '${activePreset.label}' means ${activePreset.overlap_min_step_pct}–${activePreset.overlap_band_max_pct}%. Turn this off to pin the two values below by hand.`
                      : 'The preset carries the band along with the target frame count. Turn this off to pin the two values below by hand.'
                  }
                >
                  <Switch
                    checked={draft.curate.overlap_from_preset}
                    onCheckedChange={(v) => patch('curate', 'overlap_from_preset', v)}
                  />
                </Row>
                <Row
                  label="Overlap min step (%)"
                  hint="Below this ORB displacement the frame is redundant and gets dropped."
                >
                  <NumField
                    value={
                      draft.curate.overlap_from_preset && activePreset
                        ? activePreset.overlap_min_step_pct
                        : draft.curate.overlap_min_step_pct
                    }
                    step={0.5}
                    min={0}
                    disabled={draft.curate.overlap_from_preset}
                    onChange={(v) => patch('curate', 'overlap_min_step_pct', v)}
                  />
                </Row>
                <Row
                  label="Overlap max step (%)"
                  hint="Above this the frame is kept but flagged as an alignment-risk gap."
                >
                  <NumField
                    value={
                      draft.curate.overlap_from_preset && activePreset
                        ? activePreset.overlap_band_max_pct
                        : draft.curate.overlap_band_max_pct
                    }
                    step={0.5}
                    min={0}
                    disabled={draft.curate.overlap_from_preset}
                    onChange={(v) => patch('curate', 'overlap_band_max_pct', v)}
                  />
                </Row>
              </div>
            )}

            {draft && section === 'rc' && (
              <div className="divide-y divide-slate-800">
                <Row label="Alignment precision">
                  <Choice
                    value={draft.rc.precision}
                    onChange={(v) => patch('rc', 'precision', v)}
                    options={[
                      { value: 'Preview', label: 'Preview' },
                      { value: 'Normal', label: 'Normal' },
                      { value: 'High', label: 'High' },
                    ]}
                  />
                </Row>
                <Row label="Max features per image">
                  <NumField
                    value={draft.rc.max_features}
                    step={5000}
                    min={1000}
                    onChange={(v) => patch('rc', 'max_features', v)}
                  />
                </Row>
                <Row label="Keep largest component only">
                  <Switch
                    checked={draft.rc.keep_largest}
                    onCheckedChange={(v) => patch('rc', 'keep_largest', v)}
                  />
                </Row>
                <Row
                  label="Merge components"
                  hint="Runs -mergeComponents before the maximal-component selection. Turn off if your RealityScan build rejects the verb."
                >
                  <Switch
                    checked={draft.rc.merge_components}
                    onCheckedChange={(v) => patch('rc', 'merge_components', v)}
                  />
                </Row>
                <Row
                  label="Normalise export for LichtFeld"
                  hint="Hoists PINHOLE intrinsics to the top level of transforms.json and rotates the sparse cloud onto the cameras. Affects the NeRF export only, never the COLMAP one."
                >
                  <Switch
                    checked={draft.rc.normalise_for_lfs}
                    onCheckedChange={(v) => patch('rc', 'normalise_for_lfs', v)}
                  />
                </Row>

                <SubHeading
                  title="COLMAP export"
                  note="Written next to transforms.json, not instead of it. LichtFeld Studio picks the COLMAP dataset over the NeRF one on its own, and it carries one intrinsic per image rather than one median for all of them — which matters because RealityScan crops every undistorted image slightly differently."
                />
                <Row label="Export COLMAP dataset">
                  <Switch
                    checked={draft.rc.colmap.enabled}
                    onCheckedChange={(v) => patchColmap('enabled', v)}
                  />
                </Row>
                <Row
                  label="Directory structure"
                  hint="Standard puts the images in images/ and the model in sparse/0/ — the layout LichtFeld Studio looks for first."
                >
                  <Choice
                    value={draft.rc.colmap.directory_structure}
                    onChange={(v) => patchColmap('directory_structure', v)}
                    options={[
                      { value: 'standard', label: 'COLMAP standard' },
                      { value: 'flat', label: 'Flat' },
                    ]}
                  />
                </Row>
                <Row
                  label="File type"
                  hint="Binary is what LichtFeld Studio takes when both are present, and points3D in ASCII runs to hundreds of megabytes."
                >
                  <Choice
                    value={draft.rc.colmap.file_type}
                    onChange={(v) => patchColmap('file_type', v)}
                    options={[
                      { value: 'binary', label: 'Binary (.bin)' },
                      { value: 'ascii', label: 'ASCII (.txt)' },
                    ]}
                  />
                </Row>
                <Row
                  label="Exclude unreliable tie points"
                  hint="Drops the tie points RealityScan flagged weak, ill-conditioned or outlier. They seed the gaussians, so a cleaner cloud beats a bigger one."
                >
                  <Switch
                    checked={draft.rc.colmap.exclude_unreliable_tie_points}
                    onCheckedChange={(v) => patchColmap('exclude_unreliable_tie_points', v)}
                  />
                </Row>
                <Row
                  label="Export masks"
                  hint="Off — this app has no mask source yet, so there is nothing to export."
                >
                  <Switch
                    checked={draft.rc.colmap.export_masks}
                    onCheckedChange={(v) => patchColmap('export_masks', v)}
                  />
                </Row>
                {draft.rc.colmap.export_masks && (
                  <Row label="Mask extension">
                    <Choice
                      value={draft.rc.colmap.mask_extension}
                      onChange={(v) => patchColmap('mask_extension', v)}
                      options={[
                        { value: 'mask_ext', label: '.mask.ext' },
                        { value: 'ext', label: '.ext' },
                      ]}
                    />
                  </Row>
                )}
                <Row
                  label="Scene rotation X (deg)"
                  hint="180 keeps a COLMAP-trained splat the same way up as a transforms.json-trained one: RealityScan's COLMAP template rotates the scene Rx+90, and LichtFeld's COLMAP loader — unlike its NeRF loader — does not compensate. Set 0 only where RS's +Z was never the true vertical."
                >
                  <NumField
                    value={draft.rc.colmap.scene_rotate_x_deg}
                    step={90}
                    onChange={(v) => patchColmap('scene_rotate_x_deg', v)}
                  />
                </Row>

                <SubHeading
                  title="Undistortion settings"
                  note="Not really optional for COLMAP: RealityScan refuses to write a COLMAP camera for its own division distortion model, and the camera-model id it falls back to is not one LichtFeld Studio accepts."
                />
                <Row label="Undistort images">
                  <Switch
                    checked={draft.rc.colmap.undistort.enabled}
                    onCheckedChange={(v) => patchUndistort('enabled', v)}
                  />
                </Row>
                <Row label="Export images">
                  <Switch
                    checked={draft.rc.colmap.undistort.export_images}
                    onCheckedChange={(v) => patchUndistort('export_images', v)}
                  />
                </Row>
                <Row label="Fit">
                  <Choice
                    value={draft.rc.colmap.undistort.fit}
                    onChange={(v) => patchUndistort('fit', v)}
                    options={[
                      { value: 'inner_region', label: 'Inner region' },
                      { value: 'outer_boundary', label: 'Outer boundary' },
                      { value: 'in_between', label: 'In between' },
                    ]}
                  />
                </Row>
                <Row label="Resolution">
                  <Choice
                    value={draft.rc.colmap.undistort.resolution}
                    onChange={(v) => patchUndistort('resolution', v)}
                    options={[
                      { value: 'fit', label: 'Fit' },
                      { value: 'preserve', label: 'Preserve' },
                      { value: 'custom', label: 'Custom' },
                    ]}
                  />
                </Row>
                {draft.rc.colmap.undistort.resolution === 'custom' && (
                  <>
                    <Row label="Custom width">
                      <NumField
                        value={draft.rc.colmap.undistort.custom_width}
                        min={0}
                        onChange={(v) => patchUndistort('custom_width', v)}
                      />
                    </Row>
                    <Row label="Custom height">
                      <NumField
                        value={draft.rc.colmap.undistort.custom_height}
                        min={0}
                        onChange={(v) => patchUndistort('custom_height', v)}
                      />
                    </Row>
                  </>
                )}
                <Row label="Downscale">
                  <NumField
                    value={draft.rc.colmap.undistort.downscale}
                    min={1}
                    onChange={(v) => patchUndistort('downscale', v)}
                  />
                </Row>
                <Row
                  label="Undistort principal point"
                  hint="Undistorts for a principal point of (0, 0)."
                >
                  <Switch
                    checked={draft.rc.colmap.undistort.undistort_principal_point}
                    onCheckedChange={(v) => patchUndistort('undistort_principal_point', v)}
                  />
                </Row>
                <Row label="Image cut-out">
                  <NumField
                    value={draft.rc.colmap.undistort.image_cutout}
                    step={0.05}
                    min={0}
                    onChange={(v) => patchUndistort('image_cutout', v)}
                  />
                </Row>
                <Row
                  label="Max count of pixels"
                  hint="0 = no resampling. Anything else rescales the intrinsics along with the image."
                >
                  <NumField
                    value={draft.rc.colmap.undistort.max_pixels}
                    step={1000000}
                    min={0}
                    onChange={(v) => patchUndistort('max_pixels', v)}
                  />
                </Row>
                <Row label="Image format">
                  <Choice
                    value={draft.rc.colmap.undistort.image_format}
                    onChange={(v) => patchUndistort('image_format', v)}
                    options={[
                      { value: 'png', label: 'PNG' },
                      { value: 'jpg', label: 'JPG' },
                      { value: 'tiff', label: 'TIFF' },
                    ]}
                  />
                </Row>
                <Row label="Pixel format">
                  <TextField
                    value={draft.rc.colmap.undistort.pixel_format}
                    placeholder="24-bit BGR"
                    onChange={(v) => patchUndistort('pixel_format', v)}
                  />
                </Row>
                <Row label="Naming convention">
                  <Choice
                    value={draft.rc.colmap.undistort.naming_convention}
                    onChange={(v) => patchUndistort('naming_convention', v)}
                    options={[
                      { value: 'sequential', label: '00000...' },
                      { value: 'original', label: 'Original file name' },
                    ]}
                  />
                </Row>
                <Row label="Background colour">
                  <TextField
                    value={draft.rc.colmap.undistort.background_color}
                    placeholder="#000000"
                    onChange={(v) => patchUndistort('background_color', v)}
                  />
                </Row>
              </div>
            )}

            {draft && section === 'lfs' && (
              <div className="divide-y divide-slate-800">
                <Row label="Iterations">
                  <NumField
                    value={draft.lfs.iterations}
                    step={1000}
                    min={100}
                    onChange={(v) => patch('lfs', 'iterations', v)}
                  />
                </Row>
                <Row label="Strategy">
                  <Choice
                    value={draft.lfs.strategy}
                    onChange={(v) => patch('lfs', 'strategy', v)}
                    options={[
                      { value: 'default', label: 'Default (build choice)' },
                      { value: 'mrnf', label: 'MRNF' },
                      { value: 'mcmc', label: 'MCMC' },
                      { value: 'igs+', label: 'IGS+' },
                    ]}
                  />
                </Row>
                <Row label="Evaluation pass">
                  <Switch checked={draft.lfs.eval} onCheckedChange={(v) => patch('lfs', 'eval', v)} />
                </Row>
                <Row label="Save eval images">
                  <Switch
                    checked={draft.lfs.save_eval_images}
                    onCheckedChange={(v) => patch('lfs', 'save_eval_images', v)}
                  />
                </Row>
                <Row label="Background colour">
                  <TextField
                    value={draft.lfs.background_color}
                    placeholder="#000000"
                    onChange={(v) => patch('lfs', 'background_color', v)}
                  />
                </Row>
              </div>
            )}

            {draft && section === 'export' && (
              <div className="divide-y divide-slate-800">
                <Row label="Format">
                  <Choice
                    value={draft.export.format}
                    onChange={(v) => patch('export', 'format', v)}
                    options={[
                      { value: 'ply', label: 'PLY' },
                      { value: 'splat', label: 'SPLAT' },
                    ]}
                  />
                </Row>
                <Row
                  label="Naming pattern"
                  hint="Tokens: {project}, {seq}, {index:05d}, {fps}"
                >
                  <TextField
                    value={draft.export.pattern}
                    onChange={(v) => patch('export', 'pattern', v)}
                  />
                </Row>
              </div>
            )}

            {draft && section === 'blender' && (
              <div className="divide-y divide-slate-800">
                <Row label="Scene scale">
                  <NumField
                    value={draft.blender.scene_scale}
                    step={0.1}
                    min={0.01}
                    onChange={(v) => patch('blender', 'scene_scale', v)}
                  />
                </Row>
                <Row label="Import mode">
                  <TextField
                    value={draft.blender.import_mode}
                    onChange={(v) => patch('blender', 'import_mode', v)}
                  />
                </Row>
              </div>
            )}

            {draft && section === 'viewer' && (
              <div className="divide-y divide-slate-800">
                <p className="text-xs text-slate-500 pb-3">
                  The 3D preview in steps 3, 4 and 5. It never loads the step output
                  directly — a trained splat runs to gigabytes — but a decimated copy
                  built next to it.
                </p>
                <Row
                  label="Open at"
                  hint="Points or gaussians loaded when the viewer opens. 0 opens at full
                        quality. The Full button always loads the whole file, whatever
                        this says."
                >
                  <NumField
                    value={draft.viewer.preview_max_points}
                    step={100000}
                    min={0}
                    onChange={(v) => patch('viewer', 'preview_max_points', Math.max(0, v))}
                  />
                </Row>
                <Row label="Point size" hint="Pixels, sparse clouds only.">
                  <NumField
                    value={draft.viewer.point_size}
                    step={0.1}
                    min={0.5}
                    onChange={(v) => patch('viewer', 'point_size', v)}
                  />
                </Row>
                <Row
                  label="Show cameras"
                  hint="The registered camera frustums, coloured per sequence, amber where
                        a neighbouring frame failed to align."
                >
                  <div className="flex justify-end">
                    <Switch
                      checked={draft.viewer.show_cameras}
                      onCheckedChange={(v) => patch('viewer', 'show_cameras', v)}
                    />
                  </div>
                </Row>
                <Row label="Show camera path" hint="The line joining the cameras, cut by cut.">
                  <div className="flex justify-end">
                    <Switch
                      checked={draft.viewer.show_camera_path}
                      onCheckedChange={(v) => patch('viewer', 'show_camera_path', v)}
                    />
                  </div>
                </Row>
                <Row label="Background">
                  <TextField
                    value={draft.viewer.background}
                    onChange={(v) => patch('viewer', 'background', v)}
                  />
                </Row>
              </div>
            )}

            {section === 'tools' && settings && (
              <div className="divide-y divide-slate-800">
                <p className="text-xs text-slate-500 pb-3">
                  Installation settings — stored in config.json. Type or paste a full path,
                  then press Enter or click away to save. Escape cancels.
                </p>
                <Row
                  label="RealityScan executable"
                  wide
                  hint="Full path to RealityScan.exe."
                >
                  <PathField
                    value={settings.tools.rc_exe_path ?? ''}
                    placeholder="C:\Program Files\Epic Games\RealityScan\RealityScan.exe"
                    onCommit={(v) =>
                      updateSettings({ tools: { ...settings.tools, rc_exe_path: v || null } })
                    }
                  />
                </Row>
                <Row label="LichtFeld Studio executable" wide>
                  <PathField
                    value={settings.tools.lfs_exe_path ?? ''}
                    placeholder="C:\Tools\LichtFeldStudio\lichtfeld.exe"
                    onCommit={(v) =>
                      updateSettings({ tools: { ...settings.tools, lfs_exe_path: v || null } })
                    }
                  />
                </Row>
                <Row label="FFmpeg executable" wide hint="ffprobe is looked up next to it.">
                  <PathField
                    value={settings.tools.ffmpeg_path ?? ''}
                    placeholder="C:\ffmpeg\bin\ffmpeg.exe"
                    onCommit={(v) =>
                      updateSettings({ tools: { ...settings.tools, ffmpeg_path: v } })
                    }
                  />
                </Row>
                <Row label="Blender executable" wide>
                  <PathField
                    value={settings.tools.blender_exe_path ?? ''}
                    placeholder="C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
                    onCommit={(v) =>
                      updateSettings({ tools: { ...settings.tools, blender_exe_path: v || null } })
                    }
                  />
                </Row>
                <Row label="SuperSplat URL" wide>
                  <PathField
                    value={settings.tools.supersplat_url ?? ''}
                    placeholder="https://superspl.at/editor"
                    onCommit={(v) =>
                      updateSettings({ tools: { ...settings.tools, supersplat_url: v } })
                    }
                  />
                </Row>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <Separator className="bg-slate-700" />
        <div className="flex items-center justify-between px-6 py-3">
          <div className="text-xs">
            {error && <span className="text-red-400">{error}</span>}
            {!error && dirty && <span className="text-amber-400">Unsaved changes</span>}
            {!error && !dirty && <span className="text-slate-600">Saved</span>}
          </div>
          <div className="flex items-center gap-2">
            {section !== 'tools' && (
              <Button
                variant="outline"
                size="sm"
                onClick={handleResetSection}
                className="border-slate-600 text-slate-400 hover:text-slate-100 hover:bg-slate-800 gap-1"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Reset this section
              </Button>
            )}
            <Button
              size="sm"
              disabled={!dirty || saving}
              onClick={handleSave}
              className="bg-cyan-600 hover:bg-cyan-500 text-white"
            >
              {saving ? 'Saving…' : 'Save defaults'}
            </Button>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default AppSetupPanel;
