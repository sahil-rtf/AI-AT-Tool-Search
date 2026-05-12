"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Constants ────────────────────────────────────────────────────────────────

const CATEGORIES = [
  "Vision",
  "Reading",
  "Cognitive",
  "Physical",
  "Hearing",
  "Speech/ Communication",
  "Training/ Therapy",
  "Executive Function",
] as const;

const PLATFORMS = [
  "Windows",
  "macOS",
  "iOS",
  "Android",
  "Web",
  "Chrome OS",
  "Linux",
] as const;

const FREQUENCIES = ["daily", "weekly", "monthly"] as const;

type Frequency = typeof FREQUENCIES[number];
type Platform  = typeof PLATFORMS[number];

const STEPS = [
  "Load Google Sheets database",
  "Gemini AI web search",
  "Verify categories & descriptions",
  "Check website URLs",
  "Fill missing data fields",
  "Score & push to AI_LEADS",
  "Clean up files",
] as const;

// ── Types ─────────────────────────────────────────────────────────────────────

type Status    = "idle" | "running" | "done" | "error";
type StepState = "pending" | "active" | "done";

interface LogLine {
  text: string;
  kind: "normal" | "error" | "step" | "ok" | "warn";
}

interface ScheduledSearch {
  id: string;
  name: string;
  date: string;
  categories: string[];
  platforms: Platform[];
  frequency: Frequency;
  createdAt: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function classifyLog(text: string): LogLine["kind"] {
  const lower = text.toLowerCase();
  if (lower.includes("[error]") || lower.includes("[fatal]")) return "error";
  if (text.startsWith("  Step ") || text.startsWith("=")) return "step";
  if (lower.includes("complete") || lower.includes("success") || lower.includes("pushed")) return "ok";
  if (lower.includes("warn") || lower.includes("skip")) return "warn";
  return "normal";
}

const logColorClass: Record<LogLine["kind"], string> = {
  normal: "text-slate-400",
  error:  "text-red-400",
  step:   "text-indigo-400 font-semibold",
  ok:     "text-green-400",
  warn:   "text-amber-400",
};

// ── Badge ─────────────────────────────────────────────────────────────────────

const badgeStyles: Record<Status, { pill: string; dot: string; label: string }> = {
  idle:    { pill: "bg-slate-800 text-slate-500 border border-slate-700",    dot: "",                      label: "Idle"     },
  running: { pill: "bg-blue-950  text-blue-400  border border-blue-700",     dot: "animate-pulse-dot",     label: "Running"  },
  done:    { pill: "bg-green-950 text-green-400 border border-green-800",    dot: "",                      label: "Complete" },
  error:   { pill: "bg-red-950   text-red-400   border border-red-900",      dot: "",                      label: "Error"    },
};

// ── Main component ────────────────────────────────────────────────────────────

export default function Dashboard() {
  const [counts, setCounts] = useState<Record<string, number>>(
    Object.fromEntries(CATEGORIES.map((c) => [c, 0]))
  );
  const [status, setStatus]       = useState<Status>("idle");
  const [steps, setSteps]         = useState<StepState[]>(STEPS.map(() => "pending"));
  const [logs, setLogs]           = useState<LogLine[]>([]);
  const [elapsed, setElapsed]     = useState("");
  const [sheetUrl, setSheetUrl]   = useState<string | null>(null);
  const [running, setRunning]     = useState(false);

  // ── Scheduler state ───────────────────────────────────────────────────────
  const todayStr = new Date().toISOString().split("T")[0];
  const [schedName,       setSchedName]       = useState("");
  const [schedDate,       setSchedDate]       = useState(todayStr);
  const [schedCategories, setSchedCategories] = useState<string[]>([]);
  const [schedPlatforms,  setSchedPlatforms]  = useState<Platform[]>([]);
  const [schedFrequency,  setSchedFrequency]  = useState<Frequency>("weekly");
  const [schedules,       setSchedules]       = useState<ScheduledSearch[]>([]);
  const [schedError,      setSchedError]      = useState("");

  const toggleSchedCategory = (cat: string) =>
    setSchedCategories((prev) =>
      prev.includes(cat) ? prev.filter((c) => c !== cat) : [...prev, cat]
    );

  const toggleSchedPlatform = (p: Platform) =>
    setSchedPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );

  const validateSched = () => {
    if (!schedName.trim())          return "Please enter a search name.";
    if (!schedDate)                 return "Please select a date.";
    if (schedCategories.length === 0) return "Select at least one category.";
    if (schedPlatforms.length === 0)  return "Select at least one platform.";
    return "";
  };

  const saveSchedule = () => {
    const err = validateSched();
    if (err) { setSchedError(err); return; }
    setSchedError("");
    const entry: ScheduledSearch = {
      id: crypto.randomUUID(),
      name: schedName.trim(),
      date: schedDate,
      categories: schedCategories,
      platforms: schedPlatforms,
      frequency: schedFrequency,
      createdAt: new Date().toISOString(),
    };
    setSchedules((prev) => [entry, ...prev]);
    setSchedName("");
    setSchedDate(todayStr);
    setSchedCategories([]);
    setSchedPlatforms([]);
    setSchedFrequency("weekly");
  };

  const runNow = () => {
    const err = validateSched();
    if (err) { setSchedError(err); return; }
    setSchedError("");
    // Map selected categories to counts (1 each) and kick off the pipeline
    const nowCounts = Object.fromEntries(
      CATEGORIES.map((c) => [c, schedCategories.includes(c) ? 1 : 0])
    );
    setCounts(nowCounts);
    // Small delay so the count state propagates before startPipeline reads it
    setTimeout(() => startPipelineWith(nowCounts), 50);
  };

  const deleteSchedule = (id: string) =>
    setSchedules((prev) => prev.filter((s) => s.id !== id));

  const logEndRef    = useRef<HTMLDivElement>(null);
  const evtSourceRef = useRef<EventSource | null>(null);
  const timerRef     = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  const currentStep  = useRef<number>(0);

  const total = Object.values(counts).reduce((s, v) => s + v, 0);

  // Auto-scroll log console
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  // ── Timer ──────────────────────────────────────────────────────────────────

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now() - startTimeRef.current) / 1000);
      const m = Math.floor(s / 60);
      setElapsed(`${m}m ${s % 60}s elapsed`);
    }, 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; }
  }, []);

  // ── Step helpers ───────────────────────────────────────────────────────────

  const activateStep = useCallback((num: number) => {
    currentStep.current = num;
    setSteps(STEPS.map((_, i) => {
      if (i + 1 < num)  return "done";
      if (i + 1 === num) return "active";
      return "pending";
    }));
  }, []);

  const finalizeSteps = useCallback((success: boolean) => {
    setSteps(STEPS.map((_, i) => {
      if (success) return "done";
      return i + 1 <= currentStep.current ? "done" : "pending";
    }));
  }, []);

  // ── SSE connection ─────────────────────────────────────────────────────────

  const connectSSE = useCallback(() => {
    if (evtSourceRef.current) evtSourceRef.current.close();
    // /api/stream is proxied to Flask /stream by next.config.mjs
    const src = new EventSource("/api/stream");
    evtSourceRef.current = src;

    src.onmessage = (e) => {
      const msg: string = e.data;
      if (!msg) return; // keep-alive ping

      if (msg.startsWith("STATUS:")) {
        const st = msg.split(":")[1];
        if (st === "running") {
          setStatus("running");
        } else if (st === "done") {
          setStatus("done");
          finalizeSteps(true);
          stopTimer();
          setRunning(false);
        } else if (st === "error") {
          setStatus("error");
          finalizeSteps(false);
          stopTimer();
          setRunning(false);
        }
        return;
      }

      if (msg.startsWith("SHEET_URL:")) {
        setSheetUrl(msg.slice("SHEET_URL:".length));
        return;
      }

      // Detect "  Step N  |" lines
      const stepMatch = msg.match(/Step\s+(\d+)\s+\|/);
      if (stepMatch) activateStep(parseInt(stepMatch[1], 10));

      setLogs((prev) => [...prev, { text: msg, kind: classifyLog(msg) }]);
    };
  }, [activateStep, finalizeSteps, stopTimer]);

  // ── Start pipeline ─────────────────────────────────────────────────────────

  const startPipelineWith = useCallback(async (overrideCounts?: Record<string, number>) => {
    const payload = overrideCounts ?? counts;
    const payloadTotal = Object.values(payload).reduce((s, v) => s + v, 0);
    if (payloadTotal === 0) {
      alert("Please enter at least one category count greater than 0.");
      return;
    }

    setRunning(true);
    setStatus("idle");
    setLogs([]);
    setElapsed("");
    setSheetUrl(null);
    setSteps(STEPS.map(() => "pending"));
    currentStep.current = 0;

    connectSSE();
    startTimer();
    setStatus("running");

    const res = await fetch("/api/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setLogs((prev) => [...prev, {
        text: `[ERROR] ${(err as { error?: string }).error ?? "Failed to start pipeline."}`,
        kind: "error",
      }]);
      setStatus("error");
      stopTimer();
      setRunning(false);
    }
  }, [counts, connectSSE, startTimer, stopTimer]);

  const startPipeline = useCallback(() => startPipelineWith(), [startPipelineWith]);

  // ── Render ─────────────────────────────────────────────────────────────────

  const badge = badgeStyles[status];

  return (
    <main className="flex flex-col items-center px-4 py-10 pb-16 min-h-screen bg-[#0f1117]">

      {/* ── Header ── */}
      <header className="text-center mb-10">
        <h1
          className="text-3xl font-bold"
          style={{
            background: "linear-gradient(135deg,#6366f1 0%,#8b5cf6 50%,#06b6d4 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}
        >
          AT Tool Discovery
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Pipeline Dashboard — configure, run, and monitor from your browser
        </p>
      </header>

      {/* ── Category config card ── */}
      <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8 mb-5">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-5">
          <PencilIcon />
          Configure — Tools to find per category
        </div>

        <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
          {CATEGORIES.map((cat) => (
            <div
              key={cat}
              className="flex items-center justify-between bg-[#262b40] border border-[#343a54] rounded-xl px-3 py-2 gap-3 focus-within:border-indigo-500 transition-colors"
            >
              <label className="text-slate-300 text-sm flex-1 truncate">{cat}</label>
              <input
                type="number"
                min={0}
                max={999}
                value={counts[cat]}
                onChange={(e) =>
                  setCounts((prev) => ({ ...prev, [cat]: Math.max(0, parseInt(e.target.value) || 0) }))
                }
                className="w-16 bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-md text-slate-100 text-sm text-center px-2 py-1 outline-none transition-colors"
              />
            </div>
          ))}
        </div>

        <div className="flex items-center justify-between mt-5 px-4 py-3 bg-[#1a1f33] border border-[#2d3148] rounded-xl">
          <span className="text-slate-500 text-sm">Estimated tools to discover</span>
          <span className="text-indigo-400 text-xl font-bold">{total}</span>
        </div>
      </section>

      {/* ── Run button ── */}
      <button
        onClick={startPipeline}
        disabled={running}
        className="w-full max-w-3xl flex items-center justify-center gap-2 py-3 mb-5 rounded-xl text-base font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:opacity-90 hover:-translate-y-px active:translate-y-0"
        style={{ background: "linear-gradient(135deg,#6366f1,#8b5cf6)" }}
      >
        <PlayIcon />
        Run Pipeline
      </button>

      {/* ── Schedule Search card ── */}
      <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8 mb-5">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-5">
          <CalendarIcon />
          Schedule a Search
        </div>

        <div className="flex flex-col gap-4">

          {/* Name + Date row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-slate-400 text-xs font-medium">Search Name</label>
              <input
                type="text"
                placeholder="e.g. Weekly Vision Scan"
                value={schedName}
                onChange={(e) => setSchedName(e.target.value)}
                className="bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-lg text-slate-100 text-sm px-3 py-2 outline-none transition-colors placeholder:text-slate-600"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-slate-400 text-xs font-medium">Start Date</label>
              <input
                type="date"
                value={schedDate}
                onChange={(e) => setSchedDate(e.target.value)}
                className="bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-lg text-slate-100 text-sm px-3 py-2 outline-none transition-colors"
                style={{ colorScheme: "dark" }}
              />
            </div>
          </div>

          {/* Categories */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">
              Categories
              <span className="ml-2 text-slate-600 normal-case font-normal">(select one or more)</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {CATEGORIES.map((cat) => {
                const checked = schedCategories.includes(cat);
                return (
                  <button
                    key={cat}
                    type="button"
                    onClick={() => toggleSchedCategory(cat)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      checked
                        ? "bg-indigo-600 border-indigo-500 text-white"
                        : "bg-[#262b40] border-[#343a54] text-slate-400 hover:border-indigo-600"
                    }`}
                  >
                    {cat}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Platforms */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">
              Platforms
              <span className="ml-2 text-slate-600 normal-case font-normal">(select one or more)</span>
            </label>
            <div className="flex flex-wrap gap-2">
              {PLATFORMS.map((p) => {
                const checked = schedPlatforms.includes(p);
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => toggleSchedPlatform(p)}
                    className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
                      checked
                        ? "bg-cyan-700 border-cyan-500 text-white"
                        : "bg-[#262b40] border-[#343a54] text-slate-400 hover:border-cyan-600"
                    }`}
                  >
                    {p}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Frequency */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">Frequency</label>
            <div className="flex gap-3">
              {FREQUENCIES.map((f) => (
                <button
                  key={f}
                  type="button"
                  onClick={() => setSchedFrequency(f)}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider border transition-colors ${
                    schedFrequency === f
                      ? "bg-violet-700 border-violet-500 text-white"
                      : "bg-[#262b40] border-[#343a54] text-slate-400 hover:border-violet-600"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>

          {/* Error */}
          {schedError && (
            <p className="text-red-400 text-xs">{schedError}</p>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 mt-1">
            <button
              type="button"
              onClick={saveSchedule}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold border border-indigo-600 text-indigo-400 hover:bg-indigo-600 hover:text-white transition-colors"
            >
              <CalendarIcon small />
              Schedule
            </button>
            <button
              type="button"
              onClick={runNow}
              disabled={running}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:opacity-90"
              style={{ background: "linear-gradient(135deg,#0891b2,#6366f1)" }}
            >
              <PlayIcon />
              Run Now
            </button>
          </div>
        </div>
      </section>

      {/* ── Scheduled searches list ── */}
      {schedules.length > 0 && (
        <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8 mb-5">
          <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-4">
            <ClockIcon />
            Scheduled Searches
            <span className="ml-auto bg-indigo-900 text-indigo-300 text-xs font-bold px-2 py-0.5 rounded-full">
              {schedules.length}
            </span>
          </div>
          <div className="flex flex-col gap-3">
            {schedules.map((s) => (
              <div
                key={s.id}
                className="bg-[#262b40] border border-[#343a54] rounded-xl px-4 py-3 flex items-start justify-between gap-3"
              >
                <div className="flex flex-col gap-1 min-w-0">
                  <span className="text-slate-200 text-sm font-semibold truncate">{s.name}</span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    <span className="text-xs bg-violet-900/60 text-violet-300 border border-violet-700 px-2 py-0.5 rounded-full capitalize">
                      {s.frequency}
                    </span>
                    <span className="text-xs bg-[#1a1f33] text-slate-400 border border-[#343a54] px-2 py-0.5 rounded-full">
                      📅 {s.date}
                    </span>
                    {s.categories.map((c) => (
                      <span key={c} className="text-xs bg-indigo-900/50 text-indigo-300 border border-indigo-800 px-2 py-0.5 rounded-full">
                        {c}
                      </span>
                    ))}
                    {s.platforms.map((p) => (
                      <span key={p} className="text-xs bg-cyan-900/40 text-cyan-300 border border-cyan-800 px-2 py-0.5 rounded-full">
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
                <button
                  onClick={() => deleteSchedule(s.id)}
                  className="text-slate-600 hover:text-red-400 transition-colors mt-0.5 flex-shrink-0"
                  title="Remove schedule"
                >
                  <TrashIcon />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Progress card ── */}
      <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-5">
          <TableIcon />
          Pipeline Progress
        </div>

        {/* Badge + elapsed */}
        <div className="flex items-center gap-3 mb-5">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${badge.pill}`}>
            <span className={badge.dot}>●</span>
            {badge.label}
          </span>
          {elapsed && <span className="text-slate-500 text-xs">{elapsed}</span>}
        </div>

        {/* Step list */}
        <div className="flex flex-col gap-2 mb-5">
          {STEPS.map((label, i) => {
            const state = steps[i];
            const textColor =
              state === "active" ? "text-blue-300" :
              state === "done"   ? "text-green-400" :
              "text-slate-600";
            const dotBg =
              state === "active" ? "bg-blue-400 animate-pulse-dot" :
              state === "done"   ? "bg-green-400" :
              "";
            return (
              <div key={i} className={`flex items-center gap-3 text-sm ${textColor} transition-colors`}>
                <span
                  className={`w-2.5 h-2.5 rounded-full border-2 border-current flex-shrink-0 ${dotBg}`}
                />
                Step {i + 1} — {label}
              </div>
            );
          })}
        </div>

        {/* Log console */}
        <div className="bg-[#0a0d14] border border-[#1e2435] rounded-xl p-4 h-80 overflow-y-auto font-mono text-xs leading-relaxed">
          {logs.length === 0 ? (
            <span className="text-slate-700">Waiting for pipeline to start…</span>
          ) : (
            logs.map((line, i) => (
              <div key={i} className={logColorClass[line.kind]}>
                {line.text}
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>

        {/* Sheet link */}
        {sheetUrl && (
          <a
            href={sheetUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 mt-4 px-4 py-3 bg-green-950 border border-green-800 rounded-xl text-green-400 text-sm font-medium hover:bg-green-900 transition-colors"
          >
            <ExternalLinkIcon />
            Open AI_LEADS in Google Sheets
          </a>
        )}
      </section>
    </main>
  );
}

// ── Inline SVG icons ──────────────────────────────────────────────────────────

function PencilIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2" style={{ flexShrink: 0 }}>
      <path d="M12 20h9" />
      <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z" />
    </svg>
  );
}

function PlayIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  );
}

function TableIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <path d="M3 9h18M9 21V9" />
    </svg>
  );
}

function ExternalLinkIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

function CalendarIcon({ small }: { small?: boolean }) {
  const s = small ? 14 : 15;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8"  y1="2" x2="8"  y2="6" />
      <line x1="3"  y1="10" x2="21" y2="10" />
    </svg>
  );
}

function ClockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    </svg>
  );
}
