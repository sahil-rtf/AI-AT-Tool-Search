"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ── Constants ─────────────────────────────────────────────────────────────────

const CATEGORIES = [
  "Vision", "Reading", "Cognitive", "Physical", "Hearing",
  "Speech/ Communication", "Training/ Therapy", "Executive Function",
] as const;

const PLATFORMS = [
  "Windows", "Macintosh/Mac", "Chromebook", "iPad", "iPhone", "Android",
] as const;

const ACCESS_TYPES = ["Built-in", "Installable"] as const;

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
  categories: string[]; platforms: Platform[];
  accessType: AccessType[]; pricing: PricingOpt[];
  frequency: Frequency; createdAt: string;
}

interface RunRecord {
  id: string; startedAt: string; finishedAt: string;
  status: "done"|"error"; params: Record<string,unknown>;
  toolsFound: number; sheetUrl: string;
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
  normal:"text-slate-400", error:"text-red-400",
  step:"text-indigo-400 font-semibold", ok:"text-green-400", warn:"text-amber-400",
};

const badgeStyles: Record<Status,{pill:string;dot:string;label:string}> = {
  idle:    { pill:"bg-slate-800 text-slate-500 border border-slate-700", dot:"",                   label:"Idle"     },
  running: { pill:"bg-blue-950  text-blue-400  border border-blue-700",  dot:"animate-pulse-dot",  label:"Running"  },
  done:    { pill:"bg-green-950 text-green-400 border border-green-800", dot:"",                   label:"Complete" },
  error:   { pill:"bg-red-950   text-red-400   border border-red-900",   dot:"",                   label:"Error"    },
};

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
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
            if (st==="done")  { setStatus("done");  finalizeSteps(true);  stopTimer(); setRunning(false); setHistory(h=>[...h]); }
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

    // Refresh history after run
    fetch("/api/history").then(r=>r.json()).then(setHistory).catch(()=>{});
  }, [startTimer, stopTimer, activateStep, finalizeSteps]);

  // ── Scheduler helpers ─────────────────────────────────────────────────────

  const toggle = <T extends string>(arr: T[], val: T): T[] =>
    arr.includes(val) ? arr.filter(x=>x!==val) : [...arr, val];

  const validateSched = () => {
    if (!schedName.trim())           return "Please enter a search name.";
    if (!schedDate)                  return "Please select a date.";
    if (schedTotal === 0)            return "Enter at least one category count greater than 0.";
    if (schedPlatforms.length===0)   return "Select at least one platform.";
    return "";
  };

  const saveSchedule = async () => {
    const err = validateSched();
    if (err) { setSchedError(err); return; }
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
      setSchedName(""); setSchedDate(todayStr);
      setSchedCounts(Object.fromEntries(CATEGORIES.map(c=>[c,0])));
      setSchedPlatforms([]); setSchedAccessType([...ACCESS_TYPES]);
      setSchedPricing([]); setSchedFrequency("weekly");
    }
  };

  const deleteSchedule = async (id: string) => {
    await fetch(`/api/schedules?id=${id}`,{method:"DELETE"});
    setSchedules(prev=>prev.filter(s=>s.id!==id));
  };

  const runScheduleNow = (s: ScheduledSearch) => {
    const c = (s as ScheduledSearch & {counts?: Record<string,number>}).counts
      ?? Object.fromEntries(CATEGORIES.map(cat=>[cat, s.categories.includes(cat)?1:0]));
    startPipelineWith({
      tools_per_category: c,
      platforms_filter: s.platforms,
      access_type_filter: s.accessType,
      pricing_filter: s.pricing,
    });
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const badge = badgeStyles[status];

  return (
    <main className="flex flex-col items-center px-4 py-10 pb-16 min-h-screen bg-[#0f1117]">

      {/* Header */}
      <header className="text-center mb-10">
        <h1 className="text-3xl font-bold" style={{background:"linear-gradient(135deg,#6366f1 0%,#8b5cf6 50%,#06b6d4 100%)",WebkitBackgroundClip:"text",WebkitTextFillColor:"transparent",backgroundClip:"text"}}>
          AT Tool Discovery
        </h1>
        <p className="text-slate-500 text-sm mt-1">Pipeline Dashboard — configure, run, and monitor from your browser</p>
      </header>

      {/* ── Configure + Schedule (merged) ── */}
      <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8 mb-5">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-5">
          <CalendarIcon />
          Schedule a Search
        </div>
        <div className="flex flex-col gap-5">

          {/* Name + Date */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="flex flex-col gap-1">
              <label className="text-slate-400 text-xs font-medium">Search Name</label>
              <input type="text" placeholder="e.g. Weekly Vision Scan" value={schedName}
                onChange={e=>setSchedName(e.target.value)}
                className="bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-lg text-slate-100 text-sm px-3 py-2 outline-none transition-colors placeholder:text-slate-600"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-slate-400 text-xs font-medium">Start Date</label>
              <input type="date" value={schedDate} onChange={e=>setSchedDate(e.target.value)}
                className="bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-lg text-slate-100 text-sm px-3 py-2 outline-none transition-colors"
                style={{colorScheme:"dark"}}
              />
            </div>
          </div>

          {/* Categories with counts */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">
              Tools to find per category
              <span className="ml-2 text-slate-600 normal-case font-normal">— set to 0 to skip a category</span>
            </label>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(240px,1fr))] gap-3">
              {CATEGORIES.map(cat=>(
                <div key={cat} className={`flex items-center justify-between bg-[#262b40] border rounded-xl px-3 py-2 gap-3 focus-within:border-indigo-500 transition-colors ${schedCounts[cat]>0?"border-indigo-600":"border-[#343a54]"}`}>
                  <label className="text-slate-300 text-sm flex-1 truncate">{cat}</label>
                  <input type="number" min={0} max={999} value={schedCounts[cat]}
                    onChange={e=>setSchedCounts(prev=>({...prev,[cat]:Math.max(0,parseInt(e.target.value)||0)}))}
                    className="w-16 bg-[#0f1117] border border-[#3d4466] focus:border-indigo-500 rounded-md text-slate-100 text-sm text-center px-2 py-1 outline-none transition-colors"
                  />
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between px-4 py-3 bg-[#1a1f33] border border-[#2d3148] rounded-xl">
              <span className="text-slate-500 text-sm">Total tools to discover</span>
              <span className="text-indigo-400 text-xl font-bold">{schedTotal}</span>
            </div>
          </div>

          {/* Platforms */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">Platforms <span className="ml-1 text-slate-600 normal-case font-normal">(select one or more)</span></label>
            <div className="flex flex-wrap gap-2">
              {PLATFORMS.map(p=>(
                <button key={p} type="button" onClick={()=>setSchedPlatforms(prev=>toggle(prev,p))}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${schedPlatforms.includes(p)?"bg-cyan-700 border-cyan-500 text-white":"bg-[#262b40] border-[#343a54] text-slate-400 hover:border-cyan-600"}`}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Access Type */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">Access Type <span className="ml-1 text-slate-600 normal-case font-normal">(built-in OS feature vs separately installable)</span></label>
            <div className="flex gap-3">
              {ACCESS_TYPES.map(a=>(
                <button key={a} type="button" onClick={()=>setSchedAccessType(p=>toggle(p,a))}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold border transition-colors ${schedAccessType.includes(a)?"bg-emerald-700 border-emerald-500 text-white":"bg-[#262b40] border-[#343a54] text-slate-400 hover:border-emerald-600"}`}>
                  {a}
                </button>
              ))}
            </div>
          </div>

          {/* Pricing */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">Pricing Filter <span className="ml-1 text-slate-600 normal-case font-normal">(leave blank for any pricing)</span></label>
            <div className="flex flex-wrap gap-2">
              {PRICING_OPTIONS.map(p=>(
                <button key={p} type="button" onClick={()=>setSchedPricing(prev=>toggle(prev,p))}
                  className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${schedPricing.includes(p)?"bg-amber-600 border-amber-500 text-white":"bg-[#262b40] border-[#343a54] text-slate-400 hover:border-amber-600"}`}>
                  {p}
                </button>
              ))}
            </div>
          </div>

          {/* Frequency */}
          <div className="flex flex-col gap-2">
            <label className="text-slate-400 text-xs font-medium">Frequency</label>
            <div className="flex gap-3">
              {FREQUENCIES.map(f=>(
                <button key={f} type="button" onClick={()=>setSchedFrequency(f)}
                  className={`flex-1 py-2 rounded-lg text-xs font-semibold uppercase tracking-wider border transition-colors ${schedFrequency===f?"bg-violet-700 border-violet-500 text-white":"bg-[#262b40] border-[#343a54] text-slate-400 hover:border-violet-600"}`}>
                  {f}
                </button>
              ))}
            </div>
          </div>

          {schedError && <p className="text-red-400 text-xs">{schedError}</p>}

          <div className="flex gap-3">
            <button type="button" onClick={saveSchedule}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold border border-indigo-600 text-indigo-400 hover:bg-indigo-600 hover:text-white transition-colors">
              <CalendarIcon small />Schedule
            </button>
            <button type="button"
              onClick={()=>{
                const err=validateSched(); if(err){setSchedError(err);return;} setSchedError("");
                startPipelineWith({tools_per_category:schedCounts,platforms_filter:schedPlatforms,access_type_filter:schedAccessType,pricing_filter:schedPricing});
              }}
              disabled={running}
              className="flex-1 flex items-center justify-center gap-2 py-2.5 rounded-xl text-sm font-semibold text-white disabled:opacity-40 disabled:cursor-not-allowed transition-all hover:opacity-90"
              style={{background:"linear-gradient(135deg,#0891b2,#6366f1)"}}>
              <PlayIcon />Run Now
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
            <span className="ml-auto bg-indigo-900 text-indigo-300 text-xs font-bold px-2 py-0.5 rounded-full">{schedules.length}</span>
          </div>
          <div className="flex flex-col gap-3">
            {schedules.map(s=>(
              <div key={s.id} className="bg-[#262b40] border border-[#343a54] rounded-xl px-4 py-3 flex items-start justify-between gap-3">
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <span className="text-slate-200 text-sm font-semibold truncate">{s.name}</span>
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    <span className="text-xs bg-violet-900/60 text-violet-300 border border-violet-700 px-2 py-0.5 rounded-full capitalize">{s.frequency}</span>
                    <span className="text-xs bg-[#1a1f33] text-slate-400 border border-[#343a54] px-2 py-0.5 rounded-full">📅 {s.date}</span>
                    {/* show per-category counts if stored, otherwise fall back to category name pills */}
                    {(s as ScheduledSearch & {counts?: Record<string,number>}).counts
                      ? Object.entries((s as ScheduledSearch & {counts: Record<string,number>}).counts)
                          .filter(([,v])=>v>0)
                          .map(([cat,n])=><span key={cat} className="text-xs bg-indigo-900/50 text-indigo-300 border border-indigo-800 px-2 py-0.5 rounded-full">{cat}: {n}</span>)
                      : s.categories.map(c=><span key={c} className="text-xs bg-indigo-900/50 text-indigo-300 border border-indigo-800 px-2 py-0.5 rounded-full">{c}</span>)
                    }
                    {s.platforms.map(p=><span key={p} className="text-xs bg-cyan-900/40 text-cyan-300 border border-cyan-800 px-2 py-0.5 rounded-full">{p}</span>)}
                    {s.accessType?.map(a=><span key={a} className="text-xs bg-emerald-900/40 text-emerald-300 border border-emerald-800 px-2 py-0.5 rounded-full">{a}</span>)}
                    {s.pricing?.map(p=><span key={p} className="text-xs bg-amber-900/40 text-amber-300 border border-amber-800 px-2 py-0.5 rounded-full">{p}</span>)}
                  </div>
                </div>
                <div className="flex gap-2 flex-shrink-0 mt-0.5">
                  <button onClick={()=>runScheduleNow(s)} disabled={running} title="Run this schedule now"
                    className="text-indigo-500 hover:text-indigo-300 disabled:opacity-30 transition-colors">
                    <PlayIcon />
                  </button>
                  <button onClick={()=>deleteSchedule(s.id)} title="Remove schedule"
                    className="text-slate-600 hover:text-red-400 transition-colors">
                    <TrashIcon />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ── Progress card ── */}
      <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8 mb-5">
        <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-5">
          <TableIcon />Pipeline Progress
        </div>
        <div className="flex items-center gap-3 mb-5">
          <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${badge.pill}`}>
            <span className={badge.dot}>●</span>{badge.label}
          </span>
          {elapsed && <span className="text-slate-500 text-xs">{elapsed}</span>}
        </div>
        <div className="flex flex-col gap-2 mb-5">
          {STEPS.map((label,i)=>{
            const state=steps[i];
            return (
              <div key={i} className={`flex items-center gap-3 text-sm transition-colors ${state==="active"?"text-blue-300":state==="done"?"text-green-400":"text-slate-600"}`}>
                <span className={`w-2.5 h-2.5 rounded-full border-2 border-current flex-shrink-0 ${state==="active"?"bg-blue-400 animate-pulse-dot":state==="done"?"bg-green-400":""}`}/>
                Step {i+1} — {label}
              </div>
            );
          })}
        </div>
        <div className="bg-[#0a0d14] border border-[#1e2435] rounded-xl p-4 h-80 overflow-y-auto font-mono text-xs leading-relaxed">
          {logs.length===0
            ? <span className="text-slate-700">Waiting for pipeline to start…</span>
            : logs.map((line,i)=><div key={i} className={logColor[line.kind]}>{line.text}</div>)
          }
          <div ref={logEndRef}/>
        </div>
        {sheetUrl && (
          <a href={sheetUrl} target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-2 mt-4 px-4 py-3 bg-green-950 border border-green-800 rounded-xl text-green-400 text-sm font-medium hover:bg-green-900 transition-colors">
            <ExternalLinkIcon />Open AI_LEADS in Google Sheets
          </a>
        )}
      </section>

      {/* ── Run History ── */}
      {dataLoaded && (
        <section className="w-full max-w-3xl bg-[#1e2130] border border-[#2d3148] rounded-2xl p-8">
          <div className="flex items-center gap-2 text-slate-400 text-xs font-semibold uppercase tracking-widest mb-4">
            <HistoryIcon />
            Run History
            {history.length>0 && <span className="ml-auto bg-slate-800 text-slate-400 text-xs font-bold px-2 py-0.5 rounded-full">{history.length}</span>}
          </div>
          {history.length===0
            ? <p className="text-slate-600 text-sm">No runs yet. Run the pipeline to see history here.</p>
            : (
              <div className="flex flex-col gap-3">
                {history.map(run=>(
                  <div key={run.id} className="bg-[#262b40] border border-[#343a54] rounded-xl px-4 py-3">
                    <div className="flex items-center justify-between gap-3 flex-wrap">
                      <div className="flex items-center gap-2">
                        <span className={`w-2 h-2 rounded-full flex-shrink-0 ${run.status==="done"?"bg-green-400":"bg-red-400"}`}/>
                        <span className="text-slate-200 text-sm font-medium">{fmtDate(run.startedAt)}</span>
                      </div>
                      <div className="flex items-center gap-3">
                        {run.toolsFound>0 && (
                          <span className="text-xs text-emerald-400 font-semibold">{run.toolsFound} tools found</span>
                        )}
                        <span className={`text-xs font-semibold uppercase px-2 py-0.5 rounded-full border ${run.status==="done"?"bg-green-950 text-green-400 border-green-800":"bg-red-950 text-red-400 border-red-900"}`}>
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
                            <span key={cat} className="text-xs bg-indigo-900/40 text-indigo-300 border border-indigo-800 px-2 py-0.5 rounded-full">{cat}: {count}</span>
                          ))}
                        {(run.params.platforms_filter as string[]||[]).map(p=>(
                          <span key={p} className="text-xs bg-cyan-900/30 text-cyan-300 border border-cyan-800 px-2 py-0.5 rounded-full">{p}</span>
                        ))}
                        {(run.params.pricing_filter as string[]||[]).map(p=>(
                          <span key={p} className="text-xs bg-amber-900/30 text-amber-300 border border-amber-800 px-2 py-0.5 rounded-full">{p}</span>
                        ))}
                      </div>
                    )}
                    {run.sheetUrl && (
                      <a href={run.sheetUrl} target="_blank" rel="noopener noreferrer"
                        className="inline-flex items-center gap-1.5 mt-2 text-xs text-green-400 hover:text-green-300 transition-colors">
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
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
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
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
      <rect x="3" y="4" width="18" height="18" rx="2"/>
      <line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/>
      <line x1="3" y1="10" x2="21" y2="10"/>
    </svg>
  );
}
function ClockIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  );
}
function HistoryIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#6366f1" strokeWidth="2">
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
