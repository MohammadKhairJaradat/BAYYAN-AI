/* ============================================================
   BAYYAN — Strategic Analysis · Stepper + live panel.

   A horizontal stepper rail advances node-by-node while a synced panel
   reveals what the active node is reading, calling, and producing — the
   branch (completeness router), the parallel scenario fan-out, and the
   risk gate are rendered inline instead of hidden. Faithful port of the
   design handoff (pipeline/v3-stepper.jsx + stepper-screen.jsx), wired
   to the real AdvisorReport via buildNodes / useStepperRun.
   ============================================================ */
import { Fragment, useMemo, useState, type CSSProperties } from "react";
import { Icon } from "../brand";
import type { AdvisorLang, AdvisorReport } from "../../types/api";
import {
  buildNodes,
  fmtJD,
  useStepperRun,
  COMPLETENESS_INDEX,
  NODE_COUNT,
  STEPPER_T,
  type StepperNode,
} from "./analysisPipeline";

interface Props {
  report: AdvisorReport | null;
  lang: AdvisorLang;
  live: boolean;
  onUpload?: () => void;
  onViewPlan?: () => void;
}

export default function AnalysisStepper({ report, lang, live, onUpload, onViewPlan }: Props) {
  const t = STEPPER_T[lang];
  const nodes = useMemo(() => buildNodes(report, lang), [report, lang]);
  const outcome = report ? report.status : null;
  const stopIndex = COMPLETENESS_INDEX + 1; // completed-node count when an incomplete run settles

  const [replayNonce, setReplayNonce] = useState(0);
  const [sel, setSel] = useState<number | null>(null);
  const { active, progress, paused } = useStepperRun(
    nodes.map((nd) => nd.dur),
    { live, outcome, stopIndex, replayNonce },
  );

  const n = NODE_COUNT;
  const done = active >= n && !paused;

  const status = (i: number): "pending" | "running" | "done" => {
    if (paused) return i < active ? "done" : "pending";
    if (active >= n) return "done";
    return active > i ? "done" : active === i ? "running" : "pending";
  };

  const auto = done ? n - 1 : paused ? Math.max(0, active - 1) : Math.max(0, Math.min(active, n - 1));
  const viewing = sel != null ? sel : auto;
  const inspecting = sel != null;
  const node = nodes[viewing];
  const st = status(viewing);

  const pickNode = (i: number) => {
    if (status(i) !== "pending") setSel(i);
  };
  const replay = () => {
    setSel(null);
    setReplayNonce((x) => x + 1);
  };

  const refund = report?.baseline?.refund_due ?? 0;
  const net = report?.baseline?.net_tax_due ?? 0;
  const actionCount = report?.action_plan?.length ?? 0;

  /* status chip: Running (gold, pulsing) · Needs input (clay) · Complete (green) */
  const chip = done
    ? { bg: "var(--green-tint)", fg: "var(--green)", pip: "var(--green)", label: t.complete, pulse: false }
    : paused
      ? { bg: "var(--clay-tint)", fg: "var(--clay)", pip: "var(--clay)", label: t.needsInput, pulse: false }
      : { bg: "var(--gold-tint)", fg: "var(--gold)", pip: "var(--gold)", label: t.running, pulse: true };

  /* ---- rail node indicator ---- */
  const Dot = ({ i }: { i: number }) => {
    const s = status(i);
    const isSel = viewing === i;
    const ring: CSSProperties | undefined = isSel
      ? { boxShadow: "0 0 0 3px var(--paper), 0 0 0 5px var(--green)" }
      : undefined;
    const base: CSSProperties = {
      width: 38,
      height: 38,
      borderRadius: 999,
      display: "grid",
      placeItems: "center",
      flex: "none",
      transition: "all .3s ease",
    };
    if (s === "done") {
      return (
        <div style={{ ...base, background: "var(--green)", ...(ring ?? { boxShadow: "var(--shadow-glow)" }) }}>
          <Icon name="check" size={18} stroke={3} color="#FFFCF5" />
        </div>
      );
    }
    if (s === "running") {
      return (
        <div style={{ ...base, background: "var(--gold-tint)", border: "2px solid var(--gold)", position: "relative", ...ring }}>
          <span
            className="pl-spin"
            style={{ position: "absolute", inset: -2, borderRadius: 999, border: "2px solid transparent", borderTopColor: "var(--gold)" }}
          />
          <Icon name={nodes[i].icon} size={16} color="var(--gold)" />
        </div>
      );
    }
    return (
      <div style={{ ...base, background: "var(--paper-2)", border: "1.5px solid var(--line-strong)" }}>
        <span className="num" style={{ fontSize: 13, color: "var(--ink-faint)", fontWeight: 600 }}>
          {i + 1}
        </span>
      </div>
    );
  };

  return (
    <div
      className="card"
      style={{
        background: "var(--sand)",
        border: "1px solid var(--line)",
        borderRadius: 22,
        boxShadow: "var(--shadow-md)",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        minHeight: 560,
      }}
    >
      <div style={{ display: "flex", flexDirection: "column", flex: 1, padding: "30px 34px 34px", minHeight: 0 }}>
        {/* header */}
        <div className="row-between" style={{ marginBottom: 26 }}>
          <div>
            <div className="t-eyebrow" style={{ marginBottom: 7 }}>
              {t.eyebrow}
            </div>
            <h2 className="display" style={{ fontSize: 26, color: "var(--ink)" }}>
              {t.title}
            </h2>
          </div>
          <div className="row" style={{ gap: 12 }}>
            <span className="chip" style={{ background: chip.bg, color: chip.fg, fontSize: 12.5 }}>
              <span
                className={chip.pulse ? "pl-pulse" : undefined}
                style={{ width: 7, height: 7, borderRadius: 999, background: chip.pip }}
              />
              {chip.label}
            </span>
            <button className="btn btn-ghost btn-sm" onClick={replay}>
              <Icon name="refresh" size={15} />
              {t.replay}
            </button>
          </div>
        </div>

        {/* rail */}
        <div className="row" style={{ gap: 0, alignItems: "flex-start", marginBottom: 26 }}>
          {nodes.map((nd, i) => (
            <Fragment key={nd.id}>
              <button
                onClick={() => pickNode(i)}
                title={status(i) === "pending" ? "" : t.reviewHint}
                style={{
                  flex: "0 0 auto",
                  width: 104,
                  background: "none",
                  border: "none",
                  cursor: status(i) === "pending" ? "default" : "pointer",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: 9,
                  padding: 0,
                }}
              >
                <Dot i={i} />
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 13.5, fontWeight: 600, color: status(i) === "pending" ? "var(--ink-faint)" : "var(--ink)" }}>
                    {nd.label}
                  </div>
                  <div className="t-small faint" style={{ fontSize: 10.5, marginTop: 1, letterSpacing: ".02em" }}>
                    {nd.kindTag}
                  </div>
                </div>
              </button>
              {i < nodes.length - 1 && (
                <div style={{ flex: 1, height: 3, borderRadius: 999, marginTop: 17.5, background: "var(--line)", overflow: "hidden", minWidth: 18 }}>
                  <div
                    style={{
                      height: "100%",
                      borderRadius: 999,
                      background: "var(--green)",
                      width: status(i) === "done" ? "100%" : "0%",
                      transition: "width .45s ease",
                    }}
                  />
                </div>
              )}
            </Fragment>
          ))}
        </div>

        {/* review hint once the run settles */}
        {(done || paused) && (
          <div
            className="t-small faint"
            style={{ fontSize: 11.5, textAlign: "center", marginTop: -14, marginBottom: 18, opacity: inspecting ? 0 : 1, transition: "opacity .3s" }}
          >
            {t.reviewHint}
          </div>
        )}

        {/* live panel */}
        <div style={{ flex: 1, borderRadius: 16, border: "1px solid var(--line)", background: "var(--paper)", overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 0 }}>
          <div className="row-between" style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", background: "var(--paper-2)" }}>
            <div className="row" style={{ gap: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 11, background: "var(--green-tint)", display: "grid", placeItems: "center", flex: "none" }}>
                <Icon name={node.icon} size={20} color="var(--green)" />
              </div>
              <div>
                <div className="row" style={{ gap: 8 }}>
                  <span style={{ fontSize: 16.5, fontWeight: 700, color: "var(--ink)" }}>{node.label}</span>
                  <span className="chip" style={{ background: "var(--sand-deep)", color: "var(--ink-soft)", fontSize: 11, padding: "3px 8px" }}>
                    {node.tool}
                  </span>
                </div>
                <div className="t-small faint" style={{ fontSize: 11.5, marginTop: 2 }}>
                  {t.stepOf(viewing + 1, nodes.length)}
                </div>
              </div>
            </div>
            <span className="t-small" style={{ fontSize: 12, fontWeight: 600, color: st === "done" ? "var(--green)" : "var(--gold)" }}>
              {st === "done" ? t.done : t.working}
            </span>
          </div>

          <PanelBody node={node} st={st} progress={progress} lang={lang} onUpload={onUpload} />

          {/* final strip */}
          {done && (
            <div className="row-between fade-up" style={{ padding: "14px 22px", borderTop: "1px solid var(--line)", background: "var(--green-tint)" }}>
              <div className="row" style={{ gap: 18, flexWrap: "wrap" }}>
                <span className="row" style={{ gap: 8, fontSize: 13.5, fontWeight: 600, color: "var(--green-deep)", whiteSpace: "nowrap" }}>
                  <Icon name="check" size={16} stroke={3} color="var(--green)" />
                  {t.analysisComplete}
                </span>
                <span className="t-small" style={{ fontSize: 12.5 }}>
                  {refund > 0 ? (
                    <>
                      {lang === "ar" ? "استرداد " : "Refund "}
                      <b className="num" style={{ color: "var(--green)" }}>{fmtJD(refund, lang)} JD</b>
                    </>
                  ) : (
                    <>
                      {lang === "ar" ? "مستحق " : "Net due "}
                      <b className="num" style={{ color: "var(--ink)" }}>{fmtJD(net, lang)} JD</b>
                    </>
                  )}
                  {" · "}
                  {t.actionsReady(actionCount)}
                </span>
              </div>
              <button className="btn btn-primary btn-sm" onClick={onViewPlan}>
                {t.viewPlan}
                <Icon name="arrow" size={15} className="i-arrow" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* ---- panel body: varies by node kind ---- */
function PanelBody({
  node,
  st,
  progress,
  lang,
  onUpload,
}: {
  node: StepperNode;
  st: "pending" | "running" | "done";
  progress: number;
  lang: AdvisorLang;
  onUpload?: () => void;
}) {
  return (
    <div style={{ flex: 1, padding: "20px 22px", overflow: "auto", minHeight: 0 }}>
      {/* working line / summary */}
      {st === "running" ? (
        <div className="row" style={{ gap: 10, marginBottom: 18 }}>
          <span style={{ fontSize: 15, color: "var(--ink)", fontWeight: 500 }}>{node.verb}</span>
          <span className="pl-dots">
            <span />
            <span />
            <span />
          </span>
        </div>
      ) : (
        node.summary && (
          <div className="row" style={{ gap: 9, marginBottom: 18 }}>
            <Icon name="check" size={17} stroke={2.6} color="var(--green)" />
            <span style={{ fontSize: 15, color: "var(--ink)", fontWeight: 600 }}>{node.summary}</span>
          </div>
        )
      )}

      {/* body by kind */}
      {node.kind === "parallel" && node.lanes ? (
        <div className="stack" style={{ ["--gap"]: "10px" } as CSSProperties}>
          {node.lanes.map((l, i) => {
            const fillP = st === "done" ? 1 : Math.max(0, Math.min(1, (progress - i * 0.18) / 0.5));
            const settled = fillP > 0.85;
            const won = l.best && fillP > 0.8;
            return (
              <div
                key={i}
                style={{
                  padding: "12px 14px",
                  borderRadius: 12,
                  border: `1.5px solid ${won ? "var(--green)" : "var(--line)"}`,
                  background: won ? "var(--green-tint)" : "var(--paper-2)",
                  transition: "all .3s",
                }}
              >
                <div className="row-between" style={{ marginBottom: 8 }}>
                  <span className="row" style={{ gap: 7, fontSize: 13.5, fontWeight: 600, color: "var(--ink)" }}>
                    {won && <Icon name="star" size={13} color="var(--green)" />}
                    {l.name}
                  </span>
                  <span className="t-small faint" style={{ fontSize: 11 }}>
                    {Math.round(fillP * 100)}%
                  </span>
                </div>
                <div style={{ height: 6, borderRadius: 999, background: "var(--line)", overflow: "hidden", marginBottom: settled ? 10 : 0 }}>
                  <div style={{ height: "100%", width: `${fillP * 100}%`, background: l.best ? "var(--green)" : "var(--gold)", borderRadius: 999 }} />
                </div>
                {settled && (
                  <div className="row" style={{ gap: 20, flexWrap: "wrap" }}>
                    <span className="t-small faint" style={{ fontSize: 11.5 }}>
                      {lang === "ar" ? "الضريبة " : "Tax due "}
                      <b className="num" style={{ color: "var(--ink)", fontWeight: 600 }}>{l.tax}</b>
                    </span>
                    <span className="t-small faint" style={{ fontSize: 11.5 }}>
                      {lang === "ar" ? "الفرق " : "Δ "}
                      <b
                        className="num"
                        style={{ fontWeight: 600, color: l.delta === 0 ? "var(--ink-faint)" : l.delta < 0 ? "var(--positive)" : "var(--danger)" }}
                      >
                        {l.delta > 0 ? "+" : ""}
                        {fmtJD(l.delta, lang)}
                      </b>
                    </span>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        node.detail &&
        node.detail.length > 0 && (
          <div className="grid" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2px 28px" }}>
            {node.detail.map((d, i) => (
              <div key={i} className="row-between" style={{ padding: "10px 0", borderBottom: "1px solid var(--line)" }}>
                <span className="t-small faint" style={{ fontSize: 12.5 }}>{d[0]}</span>
                <span className="num" style={{ fontSize: 13.5, fontWeight: 600, color: "var(--ink)", textAlign: "end" }}>{d[1]}</span>
              </div>
            ))}
          </div>
        )
      )}

      {/* branch callout (the completeness router) */}
      {node.kind === "decision" && node.branch && (
        <div
          className="row-between"
          style={{
            marginTop: 16,
            padding: "13px 15px",
            borderRadius: 12,
            background: "var(--clay-tint)",
            border: "1px solid color-mix(in srgb, var(--clay) 35%, transparent)",
            gap: 12,
          }}
        >
          <div className="row" style={{ gap: 11 }}>
            <Icon name="bell" size={17} color="var(--clay)" />
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: "var(--clay)" }}>{node.branch.title}</div>
              <div className="t-small" style={{ fontSize: 12, color: "var(--ink-soft)" }}>{node.branch.line}</div>
            </div>
          </div>
          <button className="btn btn-clay btn-sm" onClick={onUpload}>
            <Icon name="upload" size={14} />
            {node.branch.cta}
          </button>
        </div>
      )}

      {/* gate pass / caution */}
      {node.kind === "gate" && st === "done" && node.gateText && (
        <div
          className="row"
          style={{
            marginTop: 16,
            gap: 10,
            padding: "12px 15px",
            borderRadius: 12,
            background: node.gatePass ? "var(--green-tint)" : "var(--clay-tint)",
            border: `1px solid ${node.gatePass ? "var(--green-tint2)" : "color-mix(in srgb, var(--clay) 35%, transparent)"}`,
          }}
        >
          <Icon name="shield" size={17} color={node.gatePass ? "var(--green)" : "var(--clay)"} />
          <span style={{ fontSize: 13.5, fontWeight: 600, color: node.gatePass ? "var(--green-deep)" : "var(--clay)" }}>
            {node.gateText}
          </span>
        </div>
      )}
    </div>
  );
}
