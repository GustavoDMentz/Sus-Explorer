"use client";

import { useEffect, useState } from "react";
import { Activity, ArrowUpRight, BookOpen, ChartNoAxesCombined, Database, LoaderCircle, Search, ShieldCheck } from "lucide-react";
import { ResponsiveContainer, CartesianGrid, XAxis, YAxis, Tooltip, LineChart, Line, BarChart, Bar } from "recharts";

type Mode = "scientific" | "dashboard";
type Observation = { period?: string; doses?: number | string | null; value?: number | string | null; observation_status?: string; metrics?: Record<string, { value?: number | string | null; interpretation?: string; unavailable_reasons?: unknown }> };
type ApiResult = { needs_clarification: boolean; clarification_question?: string | null; answer?: string | null; result?: { operation?: string; data?: { rows?: Observation[] }; provenance?: Record<string, unknown> } | null };
const suggestions = [
  "A vacinação contra influenza no RS está acelerando de janeiro a junho de 2026?",
  "Qual foi a variação mensal das doses no RS de janeiro a junho de 2026?",
  "Quantas doses foram aplicadas no RS em maio de 2026?"
];
const demo: Observation[] = [
  { period: "2026-01", value: 100, metrics: { delta_2: { value: null } } },
  { period: "2026-02", value: 145, metrics: { delta_2: { value: null } } },
  { period: "2026-03", value: 180, metrics: { delta_2: { value: -10 } } },
  { period: "2026-04", value: 205, metrics: { delta_2: { value: -10 } } },
  { period: "2026-05", value: 220, metrics: { delta_2: { value: -10 } } },
  { period: "2026-06", value: 225, metrics: { delta_2: { value: -10 } } }
];
function fmt(value: unknown) {
  if (value === null || value === undefined) return "Indisponível";
  if (typeof value === "number") return value.toLocaleString("pt-BR");
  return String(value);
}
function numeric(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && /^-?\d+(\.\d+)?$/.test(value)) {
    const n = Number(value);
    return Number.isSafeInteger(n) || (Math.abs(n) < 1e15 && Number.isFinite(n)) ? n : null;
  }
  return null;
}
export default function Home() {
  const [mode, setMode] = useState<Mode>("scientific");
  const [question, setQuestion] = useState(suggestions[0]);
  const [response, setResponse] = useState<ApiResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [method, setMethod] = useState(false);
  useEffect(() => {
    const stored = localStorage.getItem("sus-explorer-view");
    if (stored === "scientific" || stored === "dashboard") setMode(stored);
  }, []);
  function switchMode(next: Mode) { setMode(next); localStorage.setItem("sus-explorer-view", next); }
  async function submit() {
    if (!question.trim() || busy) return;
    setBusy(true); setError(""); setResponse(null);
    try {
      const base = (process.env.NEXT_PUBLIC_SUS_API_URL || "http://localhost:8000").replace(/\/$/, "");
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 90000);
      try {
        const res = await fetch(base + "/api/ask", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: question.trim() }), signal: controller.signal });
        const json = await res.json();
        if (!res.ok) throw new Error(typeof json?.detail?.message === "string" ? json.detail.message : "Não foi possível executar a consulta.");
        setResponse(json as ApiResult);
      } finally { clearTimeout(timeout); }
    } catch (err) { setError(err instanceof Error ? err.message : "Erro de conexão."); }
    finally { setBusy(false); }
  }
  const realRows = response?.result?.data?.rows;
  const rows = realRows ?? demo;
  const demonstration = !realRows;
  const chart = rows.map((r) => ({ period: r.period?.slice(5) || "—", doses: numeric(r.value ?? r.doses), delta: numeric(Object.values(r.metrics || {})[0]?.value) }));
  const latest = [...rows].reverse().find(r => r.value !== null && r.value !== undefined || r.doses !== null && r.doses !== undefined);
  const selectedMetric = latest?.metrics ? Object.entries(latest.metrics)[0] : undefined;
  return <main className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="brandIcon"><Activity size={23}/></div><div><strong>SUS Explorer</strong><span>OpenDataSUS Intelligence</span></div></div>
      <div className="sideHeading">ESPAÇO DE TRABALHO</div>
      <div className="nav active"><Search size={17}/> Explorar dados</div>
      <div className="nav"><ChartNoAxesCombined size={17}/> Analytics</div>
      <div className="sideHeading">SOBRE OS DADOS</div>
      <div className="nav"><Database size={17}/> SI-PNI / OpenDataSUS</div>
      <div className="nav"><ShieldCheck size={17}/> Proveniência</div>
      <div className="sidebarBottom"><div className="onlineDot"/> Consultas determinísticas<br/><small>Parquet/R2 + Python</small></div>
    </aside>
    <section className="workspace">
      <header className="topbar"><div><span className="crumb">Workspace</span><span className="slash">/</span> Explorar</div><span className="version">BETA · v0.1</span></header>
      <div className="content">
        <div className="eyebrow"><span className="pulse"/> DADOS PÚBLICOS · ANÁLISE REPRODUZÍVEL</div>
        <h1>Entenda os dados.<br/><em>Explore possibilidades.</em></h1>
        <p className="intro">Faça perguntas em linguagem natural sobre a vacinação no Brasil. Obtenha resultados verificáveis, visualizações e contexto metodológico.</p>
        <div className="searchCard">
          <div className="searchLabel"><Search size={17}/> SUA PERGUNTA</div>
          <textarea aria-label="Pergunta sobre dados de saúde" value={question} onChange={e => setQuestion(e.target.value)} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") void submit(); }} placeholder="O que você quer descobrir nos dados do SUS?" maxLength={1000}/>
          <div className="searchFooter"><span>Os cálculos são realizados no backend, não pela IA.</span><button className="primary" onClick={() => void submit()} disabled={busy || question.trim().length < 3}>{busy ? <LoaderCircle className="spin" size={17}/> : <ArrowUpRight size={17}/>} {busy ? "Analisando..." : "Explorar"}</button></div>
        </div>
        <div className="examples">{suggestions.map((s, i) => <button key={i} onClick={() => setQuestion(s)}>{s}</button>)}</div>
        {error && <div role="alert" className="alert">{error}</div>}
        {response?.needs_clarification && <div className="alert info"><strong>Precisamos de mais informações.</strong><p>{response.clarification_question}</p></div>}
        <div className="sectionHeader"><div><span className="eyebrow small">RESULTADOS</span><h2>Visão analítica</h2></div><div className="modeSwitch" role="group" aria-label="Modo de visualização"><button aria-pressed={mode === "scientific"} className={mode === "scientific" ? "chosen" : ""} onClick={() => switchMode("scientific")}><BookOpen size={15}/> Científico</button><button aria-pressed={mode === "dashboard"} className={mode === "dashboard" ? "chosen" : ""} onClick={() => switchMode("dashboard")}><ChartNoAxesCombined size={15}/> Dashboard</button></div></div>
        <div className="resultPanel">
          <div className="resultTop"><div><span className="resultTitle">{response?.result?.operation === "temporal" ? "Análise temporal derivada" : "Evolução mensal de doses"}</span><p>{demonstration ? "Exemplo visual com dados sintéticos" : "Resultado da consulta ao SI-PNI"}</p></div><span className="pill">{demonstration ? "DEMONSTRAÇÃO" : response?.result?.provenance?.classification === "DERIVED" ? "DERIVED" : "DIRECT"}</span></div>
          {mode === "dashboard" && <div className="kpis"><div><span>Último volume</span><strong>{fmt(latest?.value ?? latest?.doses)}</strong><small>Doses / registros</small></div><div><span>Indicador temporal</span><strong>{selectedMetric ? fmt(selectedMetric[1].value) : "—"}</strong><small>{selectedMetric?.[0] ?? "Sem derivada selecionada"}</small></div><div><span>Meses na série</span><strong>{rows.length}</strong><small>Períodos exibidos</small></div></div>}
          <div className="chartArea"><div className="chartTitle">{mode === "scientific" ? "Série mensal · observações" : "Volume mensal"}</div><ResponsiveContainer width="100%" height={280}>{mode === "scientific" ? <LineChart data={chart}><CartesianGrid stroke="#e7edea" vertical={false}/><XAxis dataKey="period" tickLine={false} axisLine={false}/><YAxis tickLine={false} axisLine={false}/><Tooltip/><Line type="linear" dataKey="doses" stroke="#117e70" strokeWidth={3} dot={{r:4}} connectNulls={false} name="Doses"/></LineChart> : <BarChart data={chart}><CartesianGrid stroke="#e7edea" vertical={false}/><XAxis dataKey="period" tickLine={false} axisLine={false}/><YAxis tickLine={false} axisLine={false}/><Tooltip/><Bar dataKey="doses" fill="#117e70" radius={[5,5,0,0]} name="Doses"/></BarChart>}</ResponsiveContainer></div>
          {mode === "scientific" ? <div className="tableWrap"><table><thead><tr><th>Período</th><th>Doses / registros</th><th>Diferença selecionada</th><th>Disponibilidade</th></tr></thead><tbody>{rows.map((r,i) => <tr key={i}><td>{r.period ?? "—"}</td><td>{fmt(r.value ?? r.doses)}</td><td>{fmt(Object.values(r.metrics || {})[0]?.value)}</td><td>{r.observation_status ?? "OBSERVED"}</td></tr>)}</tbody></table></div> : <div className="insight"><Activity size={20}/><div><strong>Leitura do resultado</strong><p>{response?.answer || "Envie uma pergunta para receber uma interpretação baseada nos dados reais. Este gráfico é apenas demonstrativo."}</p></div></div>}
          <button className="methodToggle" onClick={() => setMethod(!method)} aria-expanded={method}><ShieldCheck size={17}/> Metodologia e proveniência <span>{method ? "−" : "+"}</span></button>
          {method && <div className="provenance"><p>{demonstration ? "Dados sintéticos, sem fonte real associada. Nenhuma consulta foi executada." : "Metadados fornecidos pelo backend. Valores ausentes não são interpretados como zero."}</p>{!demonstration && <pre>{JSON.stringify(response?.result?.provenance ?? {}, null, 2)}</pre>}</div>}
        </div>
        <footer>Fonte de referência: OpenDataSUS · SI-PNI <span>Dados públicos, análises transparentes.</span></footer>
      </div>
    </section>
  </main>;
}
