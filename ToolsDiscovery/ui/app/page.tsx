"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORIES = [
  "Vision", "Reading", "Writing", "Cognitive", "Physical", "Hearing",
  "Braille", "Speech/ Communication", "Training/ Therapy", "Executive Function",
] as const;

const PLATFORMS = [
  "Windows", "Macintosh/Mac", "Chromebook", "iPad", "iPhone", "Android",
] as const;

const ACCESS_TYPES = ["Built-in", "Online", "Installable", "Works w/o internet"] as const;
const ACCESS_TYPES_COMING_SOON: readonly string[] = [];

const PRICING_OPTIONS = ["Free", "Free Trial", "Subscription", "One-time purchase"] as const;

const FREQUENCIES = ["daily", "weekly", "monthly"] as const;

type Frequency   = typeof FREQUENCIES[number];
type Platform    = typeof PLATFORMS[number];
type AccessType  = typeof ACCESS_TYPES[number];
type PricingOpt  = typeof PRICING_OPTIONS[number];

const STEPS = [
  "Load Google Sheets database",
  "Gemini AI web search",
  "Verify categories & descriptions",
  "Check website URLs",
  "Fill missing data fields",
  "Score & push to AI_LEADS",
  "Clean up files",
] as const;

// ── Types ──────────────────────────────────────────────────────────────────────

type Status    = "idle" | "running" | "done" | "error";
type StepState = "pending" | "active" | "done";

interface LogLine { text: string; kind: "normal"|"error"|"step"|"ok"|"warn"; }

interface ScheduledSearch {
  id: string; name: string; date: string;
  type: "schedule" | "config";
  categories: string[]; counts: Record<string,number>;
  platforms: Platform[]; accessType: AccessType[];
  pricing: PricingOpt[]; frequency: Frequency;
  createdAt: string; lastRunAt: string | null; nextRunAt: string | null;
}

interface RunRecord {
  id: string; startedAt: string; finishedAt: string;
  status: "done"|"error"; params: Record<string,unknown>;
  toolsFound: number; sheetUrl: string;
  source?: "manual"|"cron"; scheduleName?: string;
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function classifyLog(text: string): LogLine["kind"] {
  const l = text.toLowerCase();
  if (l.includes("[error]") || l.includes("[fatal]")) return "error";
  if (text.startsWith("  Step ") || text.startsWith("=")) return "step";
  if (l.includes("complete") || l.includes("success") || l.includes("pushed")) return "ok";
  if (l.includes("warn") || l.includes("skip")) return "warn";
  return "normal";
}

const logColor: Record<LogLine["kind"],string> = {
  normal:"text-black", error:"text-red-600",
  step:"text-black font-semibold", ok:"text-black font-medium", warn:"text-black",
};

const badgeStyles: Record<Status,{pill:string;dot:string;label:string}> = {
  idle:    { pill:"bg-slate-100 text-slate-500 border border-slate-300", dot:"",                   label:"Idle"     },
  running: { pill:"bg-blue-50   text-blue-600  border border-blue-300",  dot:"animate-pulse-dot",  label:"Running"  },
  done:    { pill:"bg-green-50  text-green-600 border border-green-300", dot:"",                   label:"Complete" },
  error:   { pill:"bg-red-50    text-red-600   border border-red-300",   dot:"",                   label:"Error"    },
};

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

function computeNextRun(startDate: string, frequency: Frequency): Date {
  const base = new Date(`${startDate}T09:00:00Z`);
  const now   = new Date();
  if (base > now) return base;
  // advance until future
  const d = new Date(base);
  while (d <= now) {
    if (frequency === "daily")   d.setUTCDate(d.getUTCDate() + 1);
    else if (frequency === "weekly")  d.setUTCDate(d.getUTCDate() + 7);
    else                              d.setUTCMonth(d.getUTCMonth() + 1);
  }
  return d;
}

function fmtNextRun(d: Date): string {
  return d.toLocaleString(undefined, {
    weekday:"long", year:"numeric", month:"long", day:"numeric",
    hour:"2-digit", minute:"2-digit", timeZoneName:"short",
  });
}

// ── Main component ─────────────────────────────────────────────────────────────

export default function Dashboard() {
  const todayStr = new Date().toISOString().split("T")[0];

  // Pipeline state
  const [status,   setStatus]   = useState<Status>("idle");
  const [steps,    setSteps]    = useState<StepState[]>(STEPS.map(()=>"pending"));
  const [logs,     setLogs]     = useState<LogLine[]>([]);
  const [elapsed,  setElapsed]  = useState("");
  const [sheetUrl, setSheetUrl] = useState<string|null>(null);
  const [running,  setRunning]  = useState(false);

  // Scheduler form state
  const [schedName,       setSchedName]       = useState("");
  const [schedDate,       setSchedDate]       = useState(todayStr);
  const [schedCounts,     setSchedCounts]     = useState<Record<string,number>>(Object.fromEntries(CATEGORIES.map(c=>[c,0])));
  const [schedPlatforms,  setSchedPlatforms]  = useState<Platform[]>([]);
  const [schedAccessType, setSchedAccessType] = useState<AccessType[]>([...ACCESS_TYPES]);
  const [schedPricing,    setSchedPricing]    = useState<PricingOpt[]>([]);
  const [schedFrequency,  setSchedFrequency]  = useState<Frequency>("weekly");
  const [schedError,      setSchedError]      = useState("");
  const [conflictWarning, setConflictWarning] = useState("");

  // Auto-schedule staging state
  const [showAutoStaging,  setShowAutoStaging]  = useState(false);
  const [autoRunNow,       setAutoRunNow]       = useState<boolean|null>(null);
  const [autoConfirming,   setAutoConfirming]   = useState(false);

  const schedTotal = Object.values(schedCounts).reduce((s,v)=>s+v,0);

  // Persisted data
  const [schedules, setSchedules] = useState<ScheduledSearch[]>([]);
  const [history,   setHistory]   = useState<RunRecord[]>([]);
  const [dataLoaded, setDataLoaded] = useState(false);

  // Refs
  const logEndRef    = useRef<HTMLDivElement>(null);
  const readerRef    = useRef<ReadableStreamDefaultReader|null>(null);
  const timerRef     = useRef<ReturnType<typeof setInterval>|null>(null);
  const startTimeRef = useRef<number>(0);
  const currentStep  = useRef<number>(0);

  // ── Load schedules + history from API on mount ────────────────────────────

  useEffect(() => {
    Promise.all([
      fetch("/api/schedules").then(r=>r.json()).catch(()=>[]),
      fetch("/api/history").then(r=>r.json()).catch(()=>[]),
    ]).then(([scheds, hist]) => {
      setSchedules(scheds);
      setHistory(hist);
      setDataLoaded(true);
    });
  }, []);

  // Auto-scroll log
  useEffect(() => { logEndRef.current?.scrollIntoView({behavior:"smooth"}); }, [logs]);

  // ── Timer ──────────────────────────────────────────────────────────────────

  const startTimer = useCallback(() => {
    startTimeRef.current = Date.now();
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now()-startTimeRef.current)/1000);
      setElapsed(`${Math.floor(s/60)}m ${s%60}s elapsed`);
    }, 1000);
  }, []);

  const stopTimer = useCallback(() => {
    if (timerRef.current) { clearInterval(timerRef.current); timerRef.current=null; }
  }, []);

  // ── Step helpers ───────────────────────────────────────────────────────────

  const activateStep = useCallback((num: number) => {
    currentStep.current = num;
    setSteps(STEPS.map((_,i) => i+1<num?"done":i+1===num?"active":"pending"));
  }, []);

  const finalizeSteps = useCallback((success: boolean) => {
    setSteps(STEPS.map((_,i) => success?"done":i+1<=currentStep.current?"done":"pending"));
  }, []);

  // ── Pipeline runner (reads streaming response) ────────────────────────────

  const startPipelineWith = useCallback(async (payload: Record<string,unknown>) => {
    const payloadTotal = Object.values(payload.tools_per_category as Record<string,number>).reduce((s,v)=>s+v,0);
    if (payloadTotal===0) { alert("Please enter at least one category count greater than 0."); return; }

    setRunning(true); setStatus("idle"); setLogs([]); setElapsed(""); setSheetUrl(null);
    setSteps(STEPS.map(()=>"pending")); currentStep.current=0;
    startTimer(); setStatus("running");

    try {
      const res = await fetch("/api/run", {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify(payload),
      });

      if (!res.ok || !res.body) throw new Error("Pipeline request failed");

      const reader = res.body.getReader();
      readerRef.current = reader;
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream:true});
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const msg = line.slice(5).trim();
          if (!msg) continue;

          if (msg.startsWith("STATUS:")) {
            const st = msg.split(":")[1];
            if (st==="done")  { setStatus("done");  finalizeSteps(true);  stopTimer(); setRunning(false); }
            if (st==="error") { setStatus("error"); finalizeSteps(false); stopTimer(); setRunning(false); }
            continue;
          }
          if (msg.startsWith("SHEET_URL:")) { setSheetUrl(msg.slice(10)); continue; }
          const sm = msg.match(/Step\s+(\d+)\s+\|/);
          if (sm) activateStep(parseInt(sm[1],10));
          setLogs(prev=>[...prev,{text:msg, kind:classifyLog(msg)}]);
        }
      }
    } catch (e) {
      setLogs(prev=>[...prev,{text:`[ERROR] ${(e as Error).message}`, kind:"error"}]);
      setStatus("error"); stopTimer(); setRunning(false);
    }

    // Refresh history + schedules after run (schedules get lastRunAt/nextRunAt updated server-side)
    Promise.all([
      fetch("/api/history").then(r=>r.json()).catch(()=>null),
      fetch("/api/schedules").then(r=>r.json()).catch(()=>null),
    ]).then(([hist, scheds]) => {
      if (hist)   setHistory(hist);
      if (scheds) setSchedules(scheds);
    });
  }, [startTimer, stopTimer, activateStep, finalizeSteps]);

  // ── Scheduler helpers ─────────────────────────────────────────────────────

  const toggle = <T extends string>(arr: T[], val: T): T[] =>
    arr.includes(val) ? arr.filter(x=>x!==val) : [...arr, val];

  const validateSched = () => {
    if (!schedName.trim())           return "Please enter a search name.";
    if (schedTotal === 0)            return "Enter at least one category count greater than 0.";
    if (schedPlatforms.length===0)   return "Select at least one platform.";
    return "";
  };

  const validateSchedule = () => {
    const base = validateSched();
    if (base) return base;
    if (!schedDate)                  return "Please select a start date for the auto-schedule.";
    return "";
  };

  const _checkConflict = (date: string) => {
    const sameDay = schedules.filter(
      s => s.type === "schedule" && s.nextRunAt && s.nextRunAt.startsWith(date)
    );
    if (sameDay.length > 0) {
      setConflictWarning(
        `⚠ Another auto-schedule ("${sameDay[0].name}") already runs on ${date}. ` +
        `Vercel Cron runs once per day — both will execute, but total runtime may approach the 300 s limit. ` +
        `Consider changing the date.`
      );
    } else {
      setConflictWarning("");
    }
  };

  const resetForm = () => {
    setSchedName(""); setSchedDate(todayStr);
    setSchedCounts(Object.fromEntries(CATEGORIES.map(c=>[c,0])));
    setSchedPlatforms([]); setSchedAccessType([...ACCESS_TYPES]);
    setSchedPricing([]); setSchedFrequency("weekly");
    setConflictWarning("");
  };

  const saveConfigOnly = async () => {
    const err = validateSched();
    if (err) { setSchedError(err); return; }
    setSchedError("");
    const body = {
      name: schedName.trim(), date: "", frequency: "",
      categories: CATEGORIES.filter(c => schedCounts[c] > 0),
      counts: schedCounts, platforms: schedPlatforms,
      accessType: schedAccessType, pricing: schedPricing,
    };
    const res = await fetch("/api/schedules",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    if (res.ok) {
      const entry = await res.json();
      setSchedules(prev=>[entry,...prev]);
      resetForm();
    }
  };

  const saveSchedule = async (): Promise<ScheduledSearch|null> => {
    const err = validateSchedule();
    if (err) { setSchedError(err); return null; }
    setSchedError("");
    const body = {
      name: schedName.trim(), date: schedDate,
      categories: CATEGORIES.filter(c => schedCounts[c] > 0),
      counts: schedCounts,
      platforms: schedPlatforms, accessType: schedAccessType,
      pricing: schedPricing, frequency: schedFrequency,
    };
    const res = await fetch("/api/schedules",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    if (res.ok) {
      const entry = await res.json();
      setSchedules(prev=>[entry,...prev]);
      return entry;
    }
    return null;
  };

  const runScheduleNow = (s: ScheduledSearch) => {
    const c = s.counts ?? Object.fromEntries(CATEGORIES.map(cat=>[cat, s.categories.includes(cat)?1:0]));
    startPipelineWith({
      tools_per_category: c,
      platforms_filter: s.platforms,
      access_type_filter: s.accessType,
      pricing_filter: s.pricing,
      schedule_id: s.id,
    });
  };

  const openAutoStaging = () => {
    const err = validateSchedule();
    if (err) { setSchedError(err); return; }
    setSchedError("");
    _checkConflict(schedDate);
    setAutoRunNow(null);
    setShowAutoStaging(true);
  };

  const confirmAutoSchedule = async () => {
    setAutoConfirming(true);
    const entry = await saveSchedule();
    if (entry) {
      if (autoRunNow) {
        runScheduleNow(entry);
      }
      // Re-fetch schedules from server to ensure the saved entry is authoritative
      fetch("/api/schedules").then(r=>r.json()).then(setSchedules).catch(()=>{});
      setShowAutoStaging(false);
      setAutoConfirming(false);
      resetForm();
    } else {
      setAutoConfirming(false);
    }
  };

  const deleteSchedule = async (id: string) => {
    await fetch(`/api/schedules?id=${id}`,{method:"DELETE"});
    setSchedules(prev=>prev.filter(s=>s.id!==id));
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const badge = badgeStyles[status];

  return (
    <main className="flex flex-col items-center px-4 py-10 pb-16 min-h-screen bg-white">

      {/* Header */}
      <header className="text-center mb-10">
        <h1 className="text-3xl font-bold text-black tracking-tight">
          AT Tool Discovery
        </h1>
        <p className="text-black text-sm mt-1.5">Pipeline Dashboard — configure, run, and monitor from your browser</p>
      </header>

      {/* ── Configure + Schedule (merged) ── */}
      <section className="w-full max-w-3xl bg-white border border-slate-200 rounded-xl p-8 mb-5">
          <div className="flex items-center gap-2 text-black text-xs font-semibold uppercase tracking-widest mb-6">
          <CalendarIcon />
          Schedule a Search
        </div>
        <div className="flex flex-col gap-5">

          {/* Name + Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-black text-xs font-medium">Search Name</label>
              <input type="text" placeholder="e.g. Weekly Vision Scan" value={schedName}
                onChange={e=>setSchedName(e.target.value)}
                className="bg-white border border-slate-300 focus:border-indigo-500 rounded-lg text-black text-sm px-3 py-2 outline-none transition-colors placeholder:text-black/30"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-black text-xs font-medium">Start Date</label>
              <input type="date" value={schedDate} onChange={e=>setSchedDate(e.target.value)}
                className="bg-white border border-slate-300 focus:border-indigo-500 rounded-lg text-black text-sm px-3 py-2 outline-none transition-colors"
                style={{colorScheme:"light"}}
              />
            </div>
          </div>

          {/* Categories with counts */}
          <div className="flex flex-col gap-2">
            <label className="text-black text-xs font-medium">
              Tools to find per category
              <span className="ml-2 text-black normal-case font-normal">— set to 0 to skip a category</span>
            </label>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
              {CATEGORIES.map(cat=>(
                <div key={cat} className={`flex items-center justify-between bg-slate-50 border rounded-lg px-3 py-2 gap-3 focus-within:border-indigo-500 transition-colors ${schedCounts[cat]>0?"border-indigo-400":"border-slate-200"}`}>
                  <label className="text-black text-sm flex-1 truncate">{cat}</label>
                  <input type="number" min={0} max={10}
                    value={schedCounts[cat] === 0 ? "" : schedCounts[cat]}
                    placeholder="0"
                    onChange={e=>setSchedCounts(prev=>({...prev,[cat]:Math.min(10,Math.max(0,parseInt(e.target.value)||0))}))}
                    onBlur={e=>{ if(e.target.value==="") setSchedCounts(prev=>({...prev,[cat]:0})); }}
                    className="w-16 bg-white border border-slate-300 focus:border-indigo-500 rounded text-black text-sm text-center px-2 py-1 outline-none transition-colors placeholder:text-black/30"
                  />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg">
              <span className="text-black text-sm">Total tools to search for across all categories</span>
              <span className="text-black text-xl font-bold">{schedTotal}</span>
            </div>
          </div>

          {/* Platforms */}
          <div className="flex flex-col gap-2">
            <label className="text-black text-xs font-medium">Platforms <span className="ml-1 text-black normal-case font-normal">(select one or more)</span></label>
            <div className="flex flex-wrap gap-2">
              {PLATFORMS.map(p=>(
                <button key={p} type="button" onClick={()=>setSchedPlatforms(prev=>toggle(prev,p))}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${schedPlatforms.includes(p)?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Access Type */}
          <div className="flex flex-col gap-2">
            <label className="text-black text-xs font-medium">Access Type <span className="ml-1 text-black normal-case font-normal">(built-in OS feature, online/web-based, separately installable, or works without internet)</span></label>
            <div className="flex gap-3 flex-wrap">
              {ACCESS_TYPES.map(a=>(
                <button key={a} type="button" onClick={()=>setSchedAccessType(p=>toggle(p,a))}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold border transition-colors ${schedAccessType.includes(a)?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                  {a}
                </button>
              ))}
              {ACCESS_TYPES_COMING_SOON.map(a=>(
                <button key={a} type="button" disabled
                  title="Coming soon — letter not yet assigned"
                  className="flex-1 py-2 rounded-lg text-xs font-semibold border border-dashed border-slate-300 text-black/40 bg-slate-50 cursor-not-allowed select-none">
                  {a}
                  <span className="ml-1.5 text-[10px] font-normal text-black/40">soon</span>
                </button>
              ))}
            </div>
            {schedAccessType.includes("Works w/o internet") && (
              <p className="text-black/50 text-xs px-1">
                ℹ Note: the &ldquo;Works w/o internet&rdquo; filter is not yet active — selecting it will not affect the search results at this time.
              </p>
            )}
          </div>

          {/* Pricing */}
          <div className="flex flex-col gap-2">
            <label className="text-black text-xs font-medium">Pricing Filter <span className="ml-1 text-black normal-case font-normal">(leave blank for any pricing)</span></label>
            <div className="flex flex-wrap gap-2">
              {PRICING_OPTIONS.map(p=>(
                <button key={p} type="button" onClick={()=>setSchedPricing(prev=>toggle(prev,p))}
                  className={`px-3 py-1.5 rounded-md text-xs font-medium border transition-colors ${schedPricing.includes(p)?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                  {p}
                </button>
              ))}
            </div>
          </div>


          {schedError && <p className="text-red-400 text-xs">{schedError}</p>}
          {conflictWarning && (
            <div className="flex gap-2 px-3 py-2.5 bg-amber-50 border border-amber-300 rounded-lg text-amber-700 text-xs leading-relaxed">
              <WarningIcon /><span>{conflictWarning}</span>
            </div>
          )}

          {/* ── Auto-Schedule Staging Panel ── */}
          {showAutoStaging && (() => {
            const nextRun = computeNextRun(schedDate, schedFrequency);
            const activeCats = CATEGORIES.filter(c => schedCounts[c] > 0);
            return (
              <div className="flex flex-col gap-4 bg-slate-50 border border-indigo-200 rounded-xl p-5">
                {/* Header */}
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 text-black text-xs font-semibold uppercase tracking-widest">
                    <CalendarIcon small />Auto-Schedule Staging
                  </div>
                  <button type="button" onClick={()=>setShowAutoStaging(false)}
                    className="text-black/40 hover:text-black text-xs transition-colors">✕ Cancel</button>
                </div>

                {/* Frequency selector */}
                <div className="flex flex-col gap-2">
                  <label className="text-black text-xs font-medium">Repeat Frequency</label>
                  <div className="flex gap-3">
                    {FREQUENCIES.map(f=>(
                      <button key={f} type="button" onClick={()=>setSchedFrequency(f)}
                        className={`flex-1 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider border transition-colors ${schedFrequency===f?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                        {f}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Config summary */}
                <div className="flex flex-col gap-2">
                  <p className="text-black text-xs font-medium uppercase tracking-wider">Configuration</p>
                  <div className="bg-white border border-slate-200 rounded-lg px-4 py-3 flex flex-col gap-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-black/60">Name</span>
                      <span className="text-black font-medium">{schedName.trim()}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-black/60">Frequency</span>
                      <span className="text-black font-semibold capitalize">{schedFrequency}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-black/60">Start date</span>
                      <span className="text-black">{schedDate}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-black/60">Platforms</span>
                      <span className="text-black">{schedPlatforms.join(", ") || "—"}</span>
                    </div>
                    <div className="flex justify-between text-xs">
                      <span className="text-black/60">Categories</span>
                      <span className="text-black">{activeCats.map(c=>`${c}: ${schedCounts[c]}`).join(", ")}</span>
                    </div>
                    {schedPricing.length > 0 && (
                      <div className="flex justify-between text-xs">
                        <span className="text-black/60">Pricing</span>
                        <span className="text-black">{schedPricing.join(", ")}</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Schedule info */}
                <div className="flex flex-col gap-1.5 bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
                  <p className="text-black text-xs font-semibold flex items-center gap-1.5">
                    <ClockIcon />Auto-schedule runs every job at <span className="text-black font-bold">9:00 AM UTC</span>
                  </p>
                  <p className="text-black text-xs">
                    Next scheduled run: <span className="text-black font-medium">{fmtNextRun(nextRun)}</span>
                  </p>
                </div>

                {/* Run-now choice */}
                <div className="flex flex-col gap-2">
                  <p className="text-black text-xs font-medium">Would you like to run now, or wait for the scheduled time?</p>
                  <div className="flex gap-3">
                    <button type="button" onClick={()=>setAutoRunNow(true)}
                      className={`flex-1 py-2.5 rounded-lg text-xs font-semibold border transition-colors flex items-center justify-center gap-1.5 ${autoRunNow===true?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                      <PlayIcon />Run now &amp; schedule
                    </button>
                    <button type="button" onClick={()=>setAutoRunNow(false)}
                      className={`flex-1 py-2.5 rounded-lg text-xs font-semibold border transition-colors ${autoRunNow===false?"bg-indigo-600 border-indigo-500 text-white":"bg-white border-slate-300 text-black hover:border-slate-500"}`}>
                      Let it run automatically
                    </button>
                  </div>
                  {autoRunNow !== null && (
                    <p className="text-black/60 text-xs">
                      {autoRunNow
                        ? "The pipeline will start immediately and also be saved for automatic runs."
                        : `The pipeline will start automatically at ${fmtNextRun(nextRun)}.`}
                    </p>
                  )}
                </div>

                {/* Confirm button */}
                <button type="button"
                  onClick={confirmAutoSchedule}
                  disabled={autoRunNow === null || autoConfirming}
                  className="w-full py-3 rounded-lg text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2">
                  {autoConfirming
                    ? "Saving…"
                    : autoRunNow
                      ? <><PlayIcon />Confirm &amp; Run Now</>
                      : <><CalendarIcon small />Confirm Auto-Schedule</>}
                </button>
              </div>
            );
          })()}

          <div className="flex gap-3 flex-wrap">
            <button type="button" onClick={saveConfigOnly}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold border border-slate-300 text-black hover:border-slate-500 transition-colors bg-white"
              title="Save this search config to run manually later (appears in Saved Searches)">
              <BookmarkIcon />Save Search
            </button>
            {!showAutoStaging && (
            <button type="button"
              onClick={openAutoStaging}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold border border-slate-300 text-black hover:border-slate-500 transition-colors bg-white"
              title="Save and auto-run on start date, then repeat at chosen frequency">
              <CalendarIcon small />Auto-Schedule
            </button>
            )}
            <button type="button"
              onClick={()=>{
                const err=validateSched(); if(err){setSchedError(err);return;} setSchedError("");
                startPipelineWith({tools_per_category:schedCounts,platforms_filter:schedPlatforms,access_type_filter:schedAccessType,pricing_filter:schedPricing});
              }}
              disabled={running}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm font-semibold bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
              <PlayIcon />Run Now
            </button>
          </div>
        </div>
      </section>

      {/* ── Scheduled searches list ── */}
      {schedules.length > 0 && (
        <section className="w-full max-w-3xl bg-white border border-slate-200 rounded-xl p-8 mb-5">
          <div className="flex items-center gap-2 text-black text-xs font-semibold uppercase tracking-widest mb-4">
            <ClockIcon />
            Saved Searches
            <span className="ml-auto bg-slate-100 text-black text-xs font-bold px-2 py-0.5 rounded border border-slate-200">{schedules.length}</span>
          </div>
          <div className="flex flex-col gap-3">
            {schedules.map(s=>(
              <div key={s.id} className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 flex items-start justify-between gap-3">
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-black text-sm font-semibold truncate">{s.name}</span>
                    {s.type === "schedule"
                      ? <span className="text-xs bg-indigo-50 text-black border border-indigo-200 px-2 py-0.5 rounded font-medium">Auto</span>
                      : <span className="text-xs bg-slate-100 text-black border border-slate-200 px-2 py-0.5 rounded font-medium">Config</span>
                    }
                  </div>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {s.type === "schedule" && s.frequency && (
                      <span className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded capitalize">{s.frequency}</span>
                    )}
                    {s.nextRunAt && s.type === "schedule" && (
                      <span className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">
                        Next: {new Date(s.nextRunAt).toLocaleDateString()}
                      </span>
                    )}
                    {s.lastRunAt && (
                      <span className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">
                        Last: {new Date(s.lastRunAt).toLocaleDateString()}
                      </span>
                    )}
                    {s.counts
                      ? Object.entries(s.counts).filter(([,v])=>v>0)
                          .map(([cat,n])=><span key={cat} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{cat}: {n}</span>)
                      : s.categories.map(c=><span key={c} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{c}</span>)
                    }
                    {s.platforms.map(p=><span key={p} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{p}</span>)}
                    {s.accessType?.map(a=><span key={a} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{a}</span>)}
                    {s.pricing?.map(p=><span key={p} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{p}</span>)}
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0 mt-0.5">
                  <button onClick={()=>runScheduleNow(s)} disabled={running} title="Run this search now"
                    className="text-black/50 hover:text-black disabled:opacity-30 transition-colors">
                    <PlayIcon />
                  </button>
                  <button onClick={()=>deleteSchedule(s.id)} title="Remove"
                    className="text-black/50 hover:text-black transition-colors">
                    <TrashIcon />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Progress card ── */}
      <section className="w-full max-w-3xl bg-white border border-slate-200 rounded-xl p-8 mb-5">
          <div className="flex items-center gap-2 text-black text-xs font-semibold uppercase tracking-widest mb-6">
          <TableIcon />Pipeline Progress
        </div>
        <div className="flex items-center gap-3 mb-5">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider ${badge.pill}`}>
            <span className={badge.dot}>●</span>{badge.label}
          </span>
          {elapsed && <span className="text-black text-xs">{elapsed}</span>}
        </div>
        <div className="flex flex-col gap-2 mb-5">
          {STEPS.map((label,i)=>{
            const state=steps[i];
            return (
              <div key={i} className={`flex items-center gap-3 text-sm transition-colors ${state==="active"?"text-black font-semibold":state==="done"?"text-black":"text-black/40"}`}>
                <span className={`w-2.5 h-2.5 rounded-full border-2 border-current flex-shrink-0 ${state==="active"?"bg-black animate-pulse-dot":state==="done"?"bg-black":""}`}/>
                Step {i+1} — {label}
              </div>
            );
          })}
        </div>
        <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 h-80 overflow-y-auto font-mono text-xs leading-relaxed">
          {logs.length===0
            ? <span className="text-black/40">Waiting for pipeline to start…</span>
            : logs.map((line,i)=><div key={i} className={logColor[line.kind]}>{line.text}</div>)
          }
          <div ref={logEndRef}/>
        </div>
        {sheetUrl && (
          <a href={sheetUrl} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 mt-4 px-4 py-3 bg-slate-50 border border-slate-200 rounded-lg text-black text-sm font-medium hover:bg-slate-100 transition-colors">
            <ExternalLinkIcon />Open AI_LEADS in Google Sheets
          </a>
        )}
      </section>

      {/* ── Run History ── */}
      {dataLoaded && (
        <section className="w-full max-w-3xl bg-white border border-slate-200 rounded-xl p-8">
          <div className="flex items-center gap-2 text-black text-xs font-semibold uppercase tracking-widest mb-4">
            <HistoryIcon />
            Run History
            {history.length>0 && <span className="ml-auto bg-slate-100 text-black text-xs font-bold px-2 py-0.5 rounded border border-slate-200">{history.length}</span>}
          </div>
          {history.length===0
            ? <p className="text-black/40 text-sm">No runs yet. Run the pipeline to see history here.</p>
            : (
              <div className="flex flex-col gap-3">
                {history.map(run=>(
                  <div key={run.id} className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${run.status==="done"?"bg-green-500":"bg-red-500"}`}/>
                        <span className="text-black text-sm font-medium">{fmtDate(run.startedAt)}</span>
                        {run.scheduleName && <span className="text-xs text-black/60">— {run.scheduleName}</span>}
                      </div>
                      <div className="flex items-center gap-3">
                        {run.source === "cron" && (
                          <span className="text-xs bg-indigo-50 text-black border border-indigo-200 px-2 py-0.5 rounded font-medium">Auto</span>
                        )}
                        {run.toolsFound>0 && (
                          <span className="text-xs text-black font-semibold">{run.toolsFound} tools found</span>
                        )}
                        <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded border ${run.status==="done"?"bg-green-50 text-green-700 border-green-300":"bg-red-50 text-red-700 border-red-300"}`}>
                          {run.status}
                        </span>
                      </div>
                    </div>
                    {/* Search params summary */}
                    {run.params && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {Object.entries((run.params.tools_per_category as Record<string,number>)||{})
                          .filter(([,v])=>v>0)
                          .map(([cat,count])=>(
                            <span key={cat} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{cat}: {count}</span>
                          ))}
                        {(run.params.platforms_filter as string[]||[]).map(p=>(
                          <span key={p} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{p}</span>
                        ))}
                        {(run.params.pricing_filter as string[]||[]).map(p=>(
                          <span key={p} className="text-xs bg-white text-black border border-slate-200 px-2 py-0.5 rounded">{p}</span>
                        ))}
                      </div>
                    )}
                    {run.sheetUrl && (
                      <a href={run.sheetUrl} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 mt-2 text-xs text-black hover:text-black/70 transition-colors">
                        <ExternalLinkIcon />View in Google Sheets
                      </a>
                    )}
                  </div>
                ))}
              </div>
            )
          }
        </section>
      )}

    </main>
  );
}

// ── Inline SVG icons ───────────────────────────────────────────────────────────

function PlayIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
  );
}
function TableIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>
    </svg>
  );
}
function ExternalLinkIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
      <polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
    </svg>
  );
}
function CalendarIcon({small}:{small?:boolean}) {
  const s=small?14:15;
  return (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  );
}
function ClockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}
function HistoryIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.95"/>
    </svg>
  );
}
function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="3 6 5 6 21 6"/>
      <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>
      <path d="M10 11v6M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>
    </svg>
  );
}
function WarningIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{flexShrink:0,marginTop:1}}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
      <line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/>
    </svg>
  );
}
function BookmarkIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/>
    </svg>
  );
}
