import { useEffect, useMemo, useState } from "react";
import { getJson, postJson, type AskTurn, type Card, type Overview } from "./api";

const PAGES = [
  "Overview",
  "Attrition risk",
  "Unit shortage",
  "Actions & what-if",
  "Ask Genie",
  "Policy",
] as const;

type Page = (typeof PAGES)[number];

const NAV: { id: Page; label: string }[] = [
  { id: "Overview", label: "Command" },
  { id: "Attrition risk", label: "Risk queue" },
  { id: "Unit shortage", label: "Floor" },
  { id: "Actions & what-if", label: "Playbook" },
  { id: "Ask Genie", label: "Genie" },
  { id: "Policy", label: "Policy" },
];

function Table({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows.length) return <p className="cite">No rows.</p>;
  const cols = Object.keys(rows[0]);
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c}>{formatCell(row[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3);
  return String(value);
}

function cardBy(cards: Card[], column: string): Card | undefined {
  return cards.find((c) => c.column === column);
}

function QueueRow({
  i,
  name,
  sub,
  p,
  onClick,
}: {
  i: number;
  name: string;
  sub: string;
  p: number;
  onClick?: () => void;
}) {
  const inner = (
    <>
      <span className="rk">{String(i + 1).padStart(2, "0")}</span>
      <span>
        <div className="nm">{name}</div>
        <div className="sb">{sub}</div>
      </span>
      <span className="pv">{p.toFixed(3)}</span>
      <span className="bar">
        <i style={{ width: `${Math.max(4, Math.min(100, p * 100))}%` }} />
      </span>
    </>
  );
  if (onClick) {
    return (
      <button type="button" className="qrow" onClick={onClick}>
        {inner}
      </button>
    );
  }
  return <div className="qrow">{inner}</div>;
}

function OverviewPage({ data, onOpen }: { data: Overview; onOpen: (page: Page) => void }) {
  const coverage = cardBy(data.cards, "coverage_ratio_7d");
  const high = cardBy(data.cards, "high_risk_headcount");
  const dollars = cardBy(data.cards, "planning_attrition_exposure_usd");
  const vacancy = cardBy(data.cards, "vacancy_rate");
  const flagged = cardBy(data.cards, "predicted_shortage_units_14d");
  const head = cardBy(data.cards, "active_headcount");
  return (
    <div className="wall">
      <div className="strip">
        <div className="kpi ok">
          <div className="lbl">Coverage 7d</div>
          <div className="val">{coverage?.value ?? "—"}</div>
          <div className="sub">threshold 0.90</div>
        </div>
        <div className="kpi">
          <div className="lbl">Headcount</div>
          <div className="val">{head?.value ?? "—"}</div>
          <div className="sub">active roster</div>
        </div>
        <div className="kpi alert">
          <div className="lbl">High-risk</div>
          <div className="val">{high?.value ?? "—"}</div>
          <div className="sub">top {data.high_risk_percentile}%</div>
        </div>
        <div className="kpi hot">
          <div className="lbl">Units flagged</div>
          <div className="val">{flagged?.value ?? "—"}</div>
          <div className="sub">14-day shortage</div>
        </div>
        <div className="kpi">
          <div className="lbl">Vacancy</div>
          <div className="val">{vacancy?.value ?? "—"}</div>
          <div className="sub">open FTE share</div>
        </div>
        <div className="kpi alert">
          <div className="lbl">Exposure</div>
          <div className="val">{dollars?.value ?? "—"}</div>
          <div className="sub">planning $, not savings</div>
        </div>
      </div>
      <div className="panel">
        <div className="head">
          Floor status <b>{data.preview_units?.length || 0} units</b>
        </div>
        <div className="body">
          <div className="floor">
            {(data.preview_units || []).map((row) => {
              const flag = Boolean(row.predicted_shortage_flag);
              return (
                <button
                  type="button"
                  className={flag ? "cell flag" : "cell"}
                  key={String(row.department_id)}
                  onClick={() => onOpen("Unit shortage")}
                >
                  <span className="id">{String(row.department_id)}</span>
                  <span className="p">{Number(row.p_shortage_14d || 0).toFixed(2)}</span>
                  <span className="st">{flag ? "shortage" : "stable"}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
      <div className="stack">
        <div className="panel">
          <div className="head">
            Risk queue <b>{data.preview_risk?.length || 0} shown</b>
          </div>
          <div className="body queue">
            {(data.preview_risk || []).map((row, i) => (
              <QueueRow
                key={String(row.employee_id)}
                i={i}
                name={String(row.display_name)}
                sub={`${row.role_code} · ${row.department_id}`}
                p={Number(row.p_voluntary_90d) || 0}
                onClick={() => onOpen("Attrition risk")}
              />
            ))}
          </div>
          <button type="button" className="link" onClick={() => onOpen("Attrition risk")}>
            Open full queue →
          </button>
        </div>
        <div className="panel">
          <div className="head">Playbook</div>
          <div className="body strip" style={{ gridTemplateColumns: "1fr 1fr 1fr", minHeight: 0 }}>
            <div className="kpi">
              <div className="lbl">Recommended</div>
              <div className="val">{String(data.summary.recommended_action_count)}</div>
            </div>
            <div className="kpi alert">
              <div className="lbl">Pending</div>
              <div className="val">{String(data.summary.pending_human_review_count)}</div>
            </div>
            <div className="kpi">
              <div className="lbl">Applied</div>
              <div className="val">{String(data.summary.applied_count)}</div>
            </div>
          </div>
          <button type="button" className="link" onClick={() => onOpen("Actions & what-if")}>
            Open playbook →
          </button>
        </div>
      </div>
    </div>
  );
}

function AttritionPage() {
  const [list, setList] = useState<any>(null);
  const [eid, setEid] = useState("");
  const [detail, setDetail] = useState<any>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getJson<any>("/api/attrition")
      .then((d) => {
        setList(d);
        const first = d.high_risk?.[0]?.employee_id || d.employees?.[0]?.employee_id;
        if (first) setEid(first);
      })
      .catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!eid) return;
    getJson<any>(`/api/attrition/${eid}`).then(setDetail).catch((e) => setErr(e.message));
  }, [eid]);

  if (!list) return err ? <div className="err">{err}</div> : <p className="lede">Loading queue…</p>;
  const goldP = detail?.score?.p_voluntary_90d;
  const predP = detail?.predict?.rows?.[0]?.p_voluntary_90d;
  return (
    <div className="split">
      <div className="panel">
        <div className="head">
          Risk queue <b>{list.n_high}</b> / {list.n_active}
        </div>
        <div className="body queue">
          {(list.high_risk || []).map((row: Record<string, unknown>, i: number) => (
            <QueueRow
              key={String(row.employee_id)}
              i={i}
              name={String(row.display_name)}
              sub={`${row.role_code} · ${row.department_id}`}
              p={Number(row.p_voluntary_90d) || 0}
              onClick={() => setEid(String(row.employee_id))}
            />
          ))}
        </div>
      </div>
      <div className="panel">
        <div className="head">
          Inspect <b>{detail?.score?.display_name || eid}</b>
        </div>
        <div className="body">
          {err && <div className="err">{err}</div>}
          {detail && (
            <>
              <div className="split">
                <div>
                  <div className="lbl" style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.12em" }}>
                    GOLD P(LEAVE 90D)
                  </div>
                  <p className="big">{Number(goldP).toFixed(3)}</p>
                </div>
                <div>
                  <div className="lbl" style={{ color: "var(--muted)", fontFamily: "var(--mono)", fontSize: 10, letterSpacing: "0.12em" }}>
                    MODEL SCORE
                  </div>
                  <p className="big">{predP != null ? Number(predP).toFixed(3) : "—"}</p>
                </div>
              </div>
              <p className="cite">gold.employee_risk_scores</p>
              <p>{detail.score.drivers}</p>
              <div className="controls">
                <div>
                  <label>Employee</label>
                  <select value={eid} onChange={(e) => setEid(e.target.value)}>
                    {(list.employees || []).map((e: any) => (
                      <option key={e.employee_id} value={e.employee_id}>
                        {e.display_name} · {e.employee_id}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              {detail.actions?.length ? <Table rows={detail.actions} /> : <p className="lede">No playbook row.</p>}
            </>
          )}
          <details>
            <summary>Oracle labels</summary>
            <Table rows={detail?.oracle || []} />
          </details>
          <details>
            <summary>Fairness flags</summary>
            <Table rows={detail?.fairness || []} />
          </details>
        </div>
      </div>
    </div>
  );
}

function ShortagePage() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJson("/api/shortage").then(setData).catch((e) => setErr(e.message));
  }, []);
  if (!data) return err ? <div className="err">{err}</div> : <p className="lede">Loading floor…</p>;
  return (
    <div className="stack">
      <div className="panel">
        <div className="head">
          Floor <b>{data.n_flagged} flagged</b> / {data.n_units}
        </div>
        <div className="body">
          <div className="floor">
            {(data.units || []).map((row: Record<string, unknown>) => {
              const flag = Boolean(row.predicted_shortage_flag);
              return (
                <div key={String(row.department_id)} className={flag ? "cell flag" : "cell"}>
                  <span className="id">{String(row.department_id)}</span>
                  <span className="p">{Number(row.p_shortage_14d || 0).toFixed(2)}</span>
                  <span className="st">{flag ? "shortage" : "stable"}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
      <div className="panel">
        <div className="head">Unit playbook</div>
        <div className="body">
          <Table rows={data.actions} />
        </div>
      </div>
    </div>
  );
}

function ActionsPage() {
  const [playbook, setPlaybook] = useState("(all)");
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJson(`/api/actions?playbook=${encodeURIComponent(playbook)}`)
      .then(setData)
      .catch((e) => setErr(e.message));
  }, [playbook]);
  if (!data) return err ? <div className="err">{err}</div> : <p className="lede">Loading playbook…</p>;
  return (
    <div className="stack">
      <div className="strip">
        <div className="kpi">
          <div className="lbl">Recommended</div>
          <div className="val">{String(data.summary.recommended_action_count)}</div>
        </div>
        <div className="kpi alert">
          <div className="lbl">Pending review</div>
          <div className="val">{String(data.summary.pending_human_review_count)}</div>
        </div>
        <div className="kpi">
          <div className="lbl">Applied</div>
          <div className="val">{String(data.summary.applied_count)}</div>
        </div>
      </div>
      <div className="panel">
        <div className="head">Closed playbook</div>
        <div className="body">
          <div className="controls">
            <div>
              <label>Playbook action</label>
              <select value={playbook} onChange={(e) => setPlaybook(e.target.value)}>
                {data.playbooks.map((p: string) => (
                  <option key={p}>{p}</option>
                ))}
              </select>
            </div>
            <button
              type="button"
              className="ghost"
              disabled={!data.apply_enabled}
              title="Blocked. Status is always pending_human_review. Gold is not written."
            >
              Apply selected action
            </button>
          </div>
          <div className="warn">Apply is disabled. Nothing in this app writes to gold, silver, or the schedule.</div>
          <Table rows={data.actions} />
        </div>
      </div>
      <div className="panel">
        <div className="head">What-if · assumed, not savings</div>
        <div className="body">
          <Table rows={data.scenarios} />
        </div>
      </div>
    </div>
  );
}

function AskPage() {
  const [samples, setSamples] = useState<string[]>([]);
  const [question, setQuestion] = useState("What is 7-day coverage and vacancy?");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<{ role: "user" | "bot"; text: string; turn?: AskTurn }[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJson<{ sample_questions: string[] }>("/api/policy").then((d) => setSamples(d.sample_questions));
  }, []);

  async function send(q: string) {
    const text = q.trim();
    if (!text || busy) return;
    setErr("");
    setBusy(true);
    setMsgs((m) => [...m, { role: "user", text }]);
    try {
      const turn = await postJson<AskTurn>("/api/ask", { question: text, conversation_id: conversationId });
      if (turn.conversation_id) setConversationId(turn.conversation_id);
      setMsgs((m) => [...m, { role: "bot", text: turn.answer, turn }]);
    } catch (e: any) {
      setErr(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="panel">
      <div className="head">
        Genie
      </div>
      <div className="body">
        <div className="chips">
          {samples
            .filter((s) => s !== "Break down attrition risk by race.")
            .slice(0, 5)
            .map((s) => (
              <button type="button" key={s} onClick={() => send(s)}>
                {s}
              </button>
            ))}
        </div>
        <div className="thread">
          {msgs.map((m, i) =>
            m.role === "user" ? (
              <div className="q" key={i}>
                ▸ {m.text}
              </div>
            ) : (
              <div key={i}>
                <p className="a">{m.text}</p>
                {m.turn?.sql?.map((s, j) => (
                  <pre className="sql" key={j}>
                    {s.sql}
                  </pre>
                ))}
                {m.turn?.rows?.length ? <Table rows={m.turn.rows} /> : null}
                {m.turn ? <p className="a-meta">{m.turn.intent}</p> : null}
              </div>
            ),
          )}
          {busy && <p className="lede">Query running…</p>}
        </div>
        {err && <div className="err">{err}</div>}
        <div className="controls">
          <div style={{ flex: 1 }}>
            <label>Query</label>
            <input
              style={{ width: "100%" }}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") send(question);
              }}
            />
          </div>
          <button type="button" className="primary" disabled={busy} onClick={() => send(question)}>
            Ask
          </button>
          <button
            type="button"
            className="ghost"
            onClick={() => {
              setMsgs([]);
              setConversationId(null);
            }}
          >
            New conversation
          </button>
        </div>
      </div>
    </div>
  );
}

function PolicyPage() {
  const [data, setData] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    getJson("/api/policy").then(setData).catch((e) => setErr(e.message));
  }, []);
  if (!data) return err ? <div className="err">{err}</div> : <p className="lede">Loading policy…</p>;
  return (
    <div className="stack">
      <div className="panel">
        <div className="head">Locked policy</div>
        <div className="body">
          <Table rows={[data.policy]} />
        </div>
      </div>
      <div className="panel">
        <div className="head">Metric catalog</div>
        <div className="body">
          <Table rows={data.metrics} />
        </div>
      </div>
      <div className="panel">
        <div className="head">Valid-split metrics</div>
        <div className="body">
          <Table rows={data.valid_metrics} />
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("Overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    getJson<Overview>("/api/overview")
      .then(setOverview)
      .catch((e) => setErr(e.message));
  }, []);

  const body = useMemo(() => {
    if (err) return <div className="err">{err}</div>;
    if (page === "Overview") return overview ? <OverviewPage data={overview} onOpen={setPage} /> : <p className="lede">Bringing gold online…</p>;
    if (page === "Attrition risk") return <AttritionPage />;
    if (page === "Unit shortage") return <ShortagePage />;
    if (page === "Actions & what-if") return <ActionsPage />;
    if (page === "Ask Genie") return <AskPage />;
    return <PolicyPage />;
  }, [page, overview, err]);

  return (
    <div className="cc">
      <header className="top">
        <div className="brand">
          <i />
          CARESTAFF INSIGHT
        </div>
        <div className="leds">
          <span className="led">
            AS OF <b>{overview?.as_of || "2026-09-01"}</b>
          </span>
        </div>
      </header>
      <nav className="rail">
        {NAV.map((item) => (
          <button
            type="button"
            key={item.id}
            className={item.id === page ? "active" : ""}
            onClick={() => setPage(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
      <main className="viewport">{body}</main>
    </div>
  );
}
