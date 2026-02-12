"use client";

import { type ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  getMarketStatus,
  getSchedulerStatus,
  getTrader,
  getTraders,
  resetTraders,
  startScheduler,
  stopScheduler,
  type MarketStatus,
  type SchedulerStatus,
  type TraderDetail,
  type TraderSummary,
} from "../lib/api";

type TradeFilter = "all" | "buy" | "sell";
type ChartRange = "1d" | "1w" | "1m" | "all";
type TxSortKey = "timestamp" | "action" | "symbol" | "qty" | "price";

type TransactionPoint = {
  symbol: string;
  quantity: number;
  price: number;
  timestamp: string;
  rationale: string;
};

const TRADER_PERSONALITY_BLURBS: Record<string, string> = {
  Warren: "Disciplined value investor focused on durable businesses and patient compounding.",
  George: "Aggressive macro trader who makes bold contrarian bets when markets misprice risk.",
  Ray: "Systematic allocator balancing risk across cycles through diversification and macro signals.",
  Cathie: "High-conviction innovation investor chasing asymmetric upside in disruptive themes.",
};

function toDateInputValue(value: Date): string {
  const shifted = new Date(value.getTime() - value.getTimezoneOffset() * 60000);
  return shifted.toISOString().slice(0, 10);
}

function todayInputValue(): string {
  return toDateInputValue(new Date());
}

function monthStartInputValue(): string {
  const date = new Date();
  date.setDate(1);
  date.setHours(0, 0, 0, 0);
  return toDateInputValue(date);
}

function parseTimestampMs(timestamp: string): number | null {
  const trimmed = timestamp.trim();
  if (!trimmed) return null;

  const normalized = trimmed.includes("T") ? trimmed : trimmed.replace(" ", "T");
  const hasZone = /([zZ]|[+-]\d{2}:\d{2})$/.test(normalized);
  if (hasZone) {
    const parsed = Date.parse(normalized);
    return Number.isNaN(parsed) ? null : parsed;
  }

  const match = trimmed.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (match) {
    const [, y, m, d, hh, mm, ss = "0"] = match;
    return Date.UTC(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm), Number(ss));
  }

  const fallback = Date.parse(normalized);
  return Number.isNaN(fallback) ? null : fallback;
}

function formatDateLabel(timestampMs: number, includeTime: boolean): string {
  const options: Intl.DateTimeFormatOptions = includeTime
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { month: "short", day: "numeric" };
  return new Date(timestampMs).toLocaleString(undefined, options);
}

function money(value: number, digits = 0): string {
  return value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatDateTimeLocal(timestamp: string): string {
  const timestampMs = parseTimestampMs(timestamp);
  if (timestampMs === null) return timestamp;
  return new Date(timestampMs).toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function HelpTip({
  text,
  label,
  placement = "up",
  align = "center",
}: {
  text: string;
  label: string;
  placement?: "up" | "down" | "right";
  align?: "center" | "right";
}) {
  return (
    <span
      className={`helpTip ${placement === "down" ? "down" : ""} ${placement === "right" ? "right" : ""} ${align === "right" ? "alignRight" : ""}`}
      tabIndex={0}
      role="note"
      aria-label={label}
      data-tip={text}
    >
      ?
    </span>
  );
}

function RichHelpTip({
  label,
  placement = "down",
  children,
  className = "",
}: {
  label: string;
  placement?: "up" | "down" | "right";
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={`helpTip richHelpTip ${className} ${placement === "down" ? "down" : ""} ${placement === "right" ? "right" : ""}`} tabIndex={0} role="note" aria-label={label}>
      Details
      <span className="richHelpBubble">
        {children}
      </span>
    </span>
  );
}

function getRangeStart(maxTs: number, range: ChartRange): number {
  const day = 1000 * 60 * 60 * 24;
  if (range === "1d") return maxTs - day;
  if (range === "1w") return maxTs - day * 7;
  if (range === "1m") return maxTs - day * 30;
  return Number.MIN_SAFE_INTEGER;
}

function logTypeClass(type: string): string {
  if (type === "account") return "logTypeAccount";
  if (type === "trace") return "logTypeTrace";
  if (type === "agent") return "logTypeAgent";
  if (type === "function") return "logTypeFunction";
  if (type === "generation") return "logTypeGen";
  return "logTypeNeutral";
}

function logTradeClass(type: string, message: string): string {
  if (type.trim().toLowerCase() !== "account") return "";
  const text = message.trim().toLowerCase();
  if (text.startsWith("bought ")) return "logTradeBuy";
  if (text.startsWith("sold ")) return "logTradeSell";
  return "";
}

function PortfolioLineChart({
  series,
  transactions,
  txFilter,
  chartRange,
}: {
  series?: Array<[string, number]>;
  transactions?: TransactionPoint[];
  txFilter: TradeFilter;
  chartRange: ChartRange;
}) {
  const points = (series || [])
    .map((entry) => {
      const timestamp = String(entry[0]);
      const value = Number(entry[1]);
      const timestampMs = parseTimestampMs(timestamp);
      return { timestamp, timestampMs, value };
    })
    .filter((entry) => entry.timestampMs !== null && Number.isFinite(entry.value))
    .map((entry) => ({ ...entry, timestampMs: entry.timestampMs as number }))
    .sort((a, b) => a.timestampMs - b.timestampMs);

  const [zoomStep, setZoomStep] = useState<number>(0);
  const [panOffsetMs, setPanOffsetMs] = useState<number>(0);
  const [hoveredMarkerId, setHoveredMarkerId] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const dragStartXRef = useRef<number | null>(null);
  const dragStartPanRef = useRef<number>(0);

  useEffect(() => {
    setZoomStep(0);
    setPanOffsetMs(0);
    setIsDragging(false);
    dragStartXRef.current = null;
  }, [chartRange]);

  if (points.length < 2) {
    return <p className="muted">Not enough history yet.</p>;
  }

  const maxTs = points[points.length - 1].timestampMs;
  const minVisibleTs = getRangeStart(maxTs, chartRange);
  const rangeFilteredPoints = points.filter((entry) => entry.timestampMs >= minVisibleTs);
  const basePoints = rangeFilteredPoints.length >= 2 ? rangeFilteredPoints : points.slice(-2);

  const baseMinTs = basePoints[0].timestampMs;
  const baseMaxTs = basePoints[basePoints.length - 1].timestampMs;
  const baseRange = Math.max(1, baseMaxTs - baseMinTs);
  const zoomFactor = Math.pow(1.6, zoomStep);
  const visibleDuration = Math.max(baseRange / zoomFactor, baseRange * 0.02);
  const maxPanOffset = Math.max(0, baseRange - visibleDuration);
  const safePanOffset = Math.min(panOffsetMs, maxPanOffset);
  const visibleMinTs = baseMinTs + safePanOffset;
  const visibleMaxTs = visibleMinTs + visibleDuration;

  let plottedPoints = basePoints.filter(
    (entry) => entry.timestampMs >= visibleMinTs && entry.timestampMs <= visibleMaxTs,
  );
  if (plottedPoints.length < 2) {
    const rightIdx = basePoints.findIndex((entry) => entry.timestampMs >= visibleMinTs);
    if (rightIdx <= 0) {
      plottedPoints = basePoints.slice(0, 2);
    } else if (rightIdx >= basePoints.length - 1) {
      plottedPoints = basePoints.slice(-2);
    } else {
      plottedPoints = basePoints.slice(rightIdx - 1, rightIdx + 1);
    }
  }

  const values = plottedPoints.map((entry) => entry.value);
  const minYRaw = Math.min(...values);
  const maxYRaw = Math.max(...values);
  const yPadding = Math.max(25, (maxYRaw - minYRaw) * 0.1);
  const minY = minYRaw - yPadding;
  const maxY = maxYRaw + yPadding;

  const minX = plottedPoints[0].timestampMs;
  const maxX = plottedPoints[plottedPoints.length - 1].timestampMs;
  const xRange = Math.max(1, maxX - minX);
  const yRange = Math.max(1, maxY - minY);

  const width = 980;
  const height = 390;
  const margin = { top: 18, right: 22, bottom: 72, left: 92 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  const xScale = (timestampMs: number) => margin.left + ((timestampMs - minX) / xRange) * plotWidth;
  const yScale = (value: number) => margin.top + (1 - (value - minY) / yRange) * plotHeight;

  const linePath = plottedPoints
    .map((entry, idx) => `${idx === 0 ? "M" : "L"}${xScale(entry.timestampMs)},${yScale(entry.value)}`)
    .join(" ");

  const yTicks = Array.from({ length: 5 }).map((_, idx) => minY + (idx / 4) * yRange);
  const xTicks = Array.from({ length: 6 }).map((_, idx) => minX + (idx / 5) * xRange);
  const includeTime = xRange <= 1000 * 60 * 60 * 24 * 3;

  function nearestValueAt(timestampMs: number): number {
    let best = plottedPoints[0].value;
    let bestDistance = Math.abs(plottedPoints[0].timestampMs - timestampMs);
    for (const point of plottedPoints) {
      const distance = Math.abs(point.timestampMs - timestampMs);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = point.value;
      }
    }
    return best;
  }

  const markers = (transactions || [])
    .map((tx, idx) => {
      const timestampMs = parseTimestampMs(tx.timestamp);
      if (timestampMs === null || timestampMs < visibleMinTs || timestampMs > visibleMaxTs) {
        return null;
      }
      const side: TradeFilter = tx.quantity >= 0 ? "buy" : "sell";
      if (txFilter !== "all" && txFilter !== side) {
        return null;
      }
      const action = side === "buy" ? "BUY" : "SELL";
      const color = side === "buy" ? "#0c9b52" : "#d03b2f";
      const valueAtTime = nearestValueAt(timestampMs);
      const notional = Math.abs(tx.quantity * tx.price);
      return {
        ...tx,
        id: `${tx.timestamp}-${tx.symbol}-${idx}`,
        timestampMs,
        side,
        action,
        color,
        notional,
        x: xScale(timestampMs),
        y: yScale(valueAtTime),
      };
    })
    .filter((marker): marker is NonNullable<typeof marker> => marker !== null)
    .sort((a, b) => a.timestampMs - b.timestampMs);

  const hoveredMarker = markers.find((marker) => marker.id === hoveredMarkerId) ?? null;
  const hoveredPlacement = hoveredMarker
    ? {
        textAnchor: hoveredMarker.x < width * 0.72 ? "start" : "end",
        dominantBaseline: hoveredMarker.y < height * 0.28 ? "hanging" : "alphabetic",
        labelX: hoveredMarker.x + (hoveredMarker.x < width * 0.72 ? 10 : -10),
        labelY: hoveredMarker.y + (hoveredMarker.y < height * 0.28 ? 12 : -10),
        sideClass: hoveredMarker.x < width * 0.72 ? "tooltipRight" : "tooltipLeft",
        verticalClass: hoveredMarker.y < height * 0.28 ? "tooltipDown" : "tooltipUp",
      }
    : null;

  const firstValue = plottedPoints[0].value;
  const lastValue = plottedPoints[plottedPoints.length - 1].value;
  const change = lastValue - firstValue;
  const panStepMs = visibleDuration * 0.35;
  const canPanBack = safePanOffset > 0;
  const canPanForward = safePanOffset < maxPanOffset - 1;
  const canDrag = maxPanOffset > 1;

  function clampPan(value: number): number {
    return Math.min(maxPanOffset, Math.max(0, value));
  }

  function startDrag(clientX: number) {
    if (!canDrag) return;
    dragStartXRef.current = clientX;
    dragStartPanRef.current = safePanOffset;
    setIsDragging(true);
    setHoveredMarkerId(null);
  }

  function updateDrag(clientX: number) {
    if (!isDragging || dragStartXRef.current === null) return;
    const deltaX = clientX - dragStartXRef.current;
    const deltaMs = (deltaX / plotWidth) * visibleDuration;
    setPanOffsetMs(clampPan(dragStartPanRef.current - deltaMs));
  }

  function endDrag() {
    if (!isDragging) return;
    setIsDragging(false);
    dragStartXRef.current = null;
  }

  return (
    <div className="portfolioTimeline">
      <div className="timelineChartPanel">
        <div className="chartZoomControls">
          <button
            type="button"
            className="chartZoomBtn"
            onClick={() => setZoomStep((value) => Math.min(8, value + 1))}
          >
            Zoom In
          </button>
          <button
            type="button"
            className="chartZoomBtn"
            disabled={zoomStep === 0}
            onClick={() => setZoomStep((value) => Math.max(0, value - 1))}
          >
            Zoom Out
          </button>
          <button
            type="button"
            className="chartZoomBtn"
            disabled={!canPanBack}
            onClick={() => setPanOffsetMs((value) => Math.max(0, value - panStepMs))}
          >
            Backward
          </button>
          <button
            type="button"
            className="chartZoomBtn"
            disabled={!canPanForward}
            onClick={() => setPanOffsetMs((value) => Math.min(maxPanOffset, value + panStepMs))}
          >
            Forward
          </button>
        </div>
        <div
          className={`chartSurface ${canDrag ? "draggable" : ""} ${isDragging ? "dragging" : ""}`}
          onMouseLeave={() => {
            if (!isDragging) setHoveredMarkerId(null);
          }}
          onPointerDown={(event) => {
            if (event.button !== 0) return;
            if (!canDrag) return;
            event.currentTarget.setPointerCapture(event.pointerId);
            startDrag(event.clientX);
          }}
          onPointerMove={(event) => updateDrag(event.clientX)}
          onPointerUp={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
            endDrag();
          }}
          onPointerCancel={(event) => {
            if (event.currentTarget.hasPointerCapture(event.pointerId)) {
              event.currentTarget.releasePointerCapture(event.pointerId);
            }
            endDrag();
          }}
        >
          <svg className="lineChart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Portfolio value chart">
          {yTicks.map((value) => {
            const y = yScale(value);
            return (
              <g key={`y-${value}`}>
                <line x1={margin.left} y1={y} x2={width - margin.right} y2={y} className="chartGridLine" />
                <text x={margin.left - 10} y={y + 4} textAnchor="end" className="chartTickLabel">
                  ${money(Math.round(value), 0)}
                </text>
              </g>
            );
          })}

          {xTicks.map((value) => {
            const x = xScale(value);
            return (
              <g key={`x-${value}`}>
                <line x1={x} y1={margin.top} x2={x} y2={height - margin.bottom} className="chartGridLineX" />
                <text x={x} y={height - margin.bottom + 22} textAnchor="middle" className="chartTickLabel">
                  {formatDateLabel(value, includeTime)}
                </text>
              </g>
            );
          })}

          <line
            x1={margin.left}
            y1={height - margin.bottom}
            x2={width - margin.right}
            y2={height - margin.bottom}
            className="chartAxisLine"
          />
          <line
            x1={margin.left}
            y1={margin.top}
            x2={margin.left}
            y2={height - margin.bottom}
            className="chartAxisLine"
          />

          <text
            x={(margin.left + (width - margin.right)) / 2}
            y={height - 12}
            textAnchor="middle"
            className="chartAxisTitle"
          >
            Date
          </text>
          <text
            x={24}
            y={(margin.top + (height - margin.bottom)) / 2}
            transform={`rotate(-90 24 ${(margin.top + (height - margin.bottom)) / 2})`}
            textAnchor="middle"
            className="chartAxisTitle"
          >
            Amount ($)
          </text>

          <path d={linePath} className="lineChartStroke" />

          {markers.map((marker) => (
            <g
              key={marker.id}
              className="txMarkerGroup"
              onMouseEnter={() => {
                if (!isDragging) setHoveredMarkerId(marker.id);
              }}
              onMouseLeave={() => {
                if (!isDragging) setHoveredMarkerId((current) => (current === marker.id ? null : current));
              }}
            >
              <circle
                cx={marker.x}
                cy={marker.y}
                r={hoveredMarkerId === marker.id ? 5.2 : 4.5}
                fill={marker.color}
                className={`txDot ${hoveredMarkerId === marker.id ? "txDotActive" : ""}`}
              />
            </g>
          ))}

          {hoveredMarker && hoveredPlacement && !isDragging ? (
            <text
              x={hoveredPlacement.labelX}
              y={hoveredPlacement.labelY}
              textAnchor={hoveredPlacement.textAnchor}
              dominantBaseline={hoveredPlacement.dominantBaseline}
              className="txHoverLabel"
            >
              {hoveredMarker.action} {hoveredMarker.symbol}
            </text>
          ) : null}
          </svg>

          {hoveredMarker && hoveredPlacement && !isDragging ? (
            <div
              className={`markerTooltip ${hoveredPlacement.sideClass} ${hoveredPlacement.verticalClass}`}
              style={{
                left: `${(hoveredMarker.x / width) * 100}%`,
                top: `${(hoveredMarker.y / height) * 100}%`,
              }}
            >
              <p>
                <strong>{hoveredMarker.symbol}</strong> <span className={hoveredMarker.side === "buy" ? "txBuy" : "txSell"}>{hoveredMarker.action}</span>
              </p>
              <p>Qty: {Math.abs(hoveredMarker.quantity)}</p>
              <p>Price: ${money(hoveredMarker.price, 2)}</p>
              <p>Time: {formatDateTimeLocal(hoveredMarker.timestamp)}</p>
              <p className="markerTooltipRationale">{hoveredMarker.rationale || "No rationale"}</p>
            </div>
          ) : null}
        </div>
      </div>

      <div className="timelineLedgerPanel">
        <div className="chartMeta">
          <span>Start: ${money(firstValue, 0)}</span>
          <span>Latest: ${money(lastValue, 0)}</span>
          <span className={change >= 0 ? "pnlUp" : "pnlDown"}>
            Change: {change >= 0 ? "+" : "-"}${money(Math.abs(change), 0)}
          </span>
        </div>
        <div className="txLedger">
          {(markers.length > 0 ? markers.slice(-12).reverse() : []).map((marker) => (
            <p key={marker.id}>
              <span className="txLedgerCol txLedgerTime">{formatDateLabel(marker.timestampMs, true)}</span>
              <span className={`txLedgerCol ${marker.side === "buy" ? "txBuy" : "txSell"}`}>{marker.action}</span>
              <span className="txLedgerCol">{marker.symbol}</span>
              <span className="txLedgerCol txLedgerPrice">@ ${money(marker.price, 2)}</span>
              <span className="txLedgerCol txLedgerNotional">${money(marker.notional, 0)}</span>
            </p>
          ))}
          {markers.length === 0 ? <p className="muted">No matching buy/sell points for this filter.</p> : null}
        </div>
      </div>
    </div>
  );
}

export default function HomePage() {
  const [traders, setTraders] = useState<TraderSummary[]>([]);
  const [selectedTrader, setSelectedTrader] = useState<string>("Warren");
  const selectedTraderRef = useRef<string>("Warren");
  const leftRailRef = useRef<HTMLDivElement | null>(null);
  const runInProgressRef = useRef<boolean>(false);
  const [leftRailHeight, setLeftRailHeight] = useState<number | null>(null);
  const [stackedDeskLayout, setStackedDeskLayout] = useState<boolean>(false);
  const [detail, setDetail] = useState<TraderDetail | null>(null);
  const [market, setMarket] = useState<MarketStatus>({ status: "unknown", is_open: null, detail: null });
  const [scheduler, setScheduler] = useState<SchedulerStatus>({
    running: false,
    pid: null,
    started_at: null,
    run_in_progress: false,
    last_run_started_at: null,
    last_run_ended_at: null,
    read_only_mode: false,
  });
  const [txFilter, setTxFilter] = useState<TradeFilter>("all");
  const [chartRange, setChartRange] = useState<ChartRange>("1w");
  const [runEveryNMinutes, setRunEveryNMinutes] = useState<number>(60);
  const [txSort, setTxSort] = useState<{ key: TxSortKey; direction: "asc" | "desc" }>({
    key: "timestamp",
    direction: "desc",
  });
  const [txSearch, setTxSearch] = useState<string>("");
  const [txActionFilter, setTxActionFilter] = useState<"all" | "buy" | "sell">("all");
  const [txDateFrom, setTxDateFrom] = useState<string>(monthStartInputValue);
  const [txDateTo, setTxDateTo] = useState<string>(todayInputValue);
  const [txPage, setTxPage] = useState<number>(1);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [allowClosedMarketTrading, setAllowClosedMarketTrading] = useState<boolean>(false);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  const syncLeftRailHeight = useCallback(() => {
    if (stackedDeskLayout) {
      setLeftRailHeight((prev) => (prev === null ? prev : null));
      return;
    }
    const node = leftRailRef.current;
    if (!node) {
      return;
    }
    const nextHeight = Math.round(node.getBoundingClientRect().height);
    setLeftRailHeight((prev) => (prev === nextHeight ? prev : nextHeight));
  }, [stackedDeskLayout]);

  async function refreshDashboard() {
    try {
      const [nextTraders, nextScheduler, nextMarket] = await Promise.all([
        getTraders(),
        getSchedulerStatus(),
        getMarketStatus(),
      ]);
      setTraders(nextTraders);
      setScheduler(nextScheduler);
      setMarket(nextMarket);

      const activeName =
        nextTraders.find((entry) => entry.name === selectedTraderRef.current)?.name ?? nextTraders[0]?.name ?? "";
      if (activeName) {
        if (activeName !== selectedTraderRef.current) {
          selectedTraderRef.current = activeName;
          setSelectedTrader(activeName);
        }
        const nextDetail = await getTrader(activeName);
        setDetail(nextDetail);
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard data.");
    } finally {
      setLoading(false);
    }
  }

  async function runAction(key: string, fn: () => Promise<void>) {
    try {
      setActionBusy(key);
      await fn();
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : `Action failed: ${key}`);
    } finally {
      setActionBusy(null);
    }
  }

  useEffect(() => {
    void refreshDashboard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!scheduler.running) {
      return;
    }
    const statusTimer = window.setInterval(() => {
      void getSchedulerStatus()
        .then((nextStatus) => setScheduler(nextStatus))
        .catch(() => {
          // keep existing scheduler state; full refresh/error path handles broader failures
        });
    }, 3000);
    return () => window.clearInterval(statusTimer);
  }, [scheduler.running]);

  useEffect(() => {
    if (!scheduler.run_in_progress) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshDashboard();
    }, 10000);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scheduler.run_in_progress]);

  useEffect(() => {
    if (runInProgressRef.current !== scheduler.run_in_progress) {
      runInProgressRef.current = scheduler.run_in_progress;
      void refreshDashboard();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scheduler.run_in_progress]);

  useEffect(() => {
    if (!selectedTrader) {
      return;
    }
    selectedTraderRef.current = selectedTrader;
    void getTrader(selectedTrader)
      .then((nextDetail) => setDetail(nextDetail))
      .catch((err) => setError(err instanceof Error ? err.message : "Unable to load trader details."));
  }, [selectedTrader]);

  useEffect(() => {
    if (market.status === "open") {
      setAllowClosedMarketTrading(false);
    }
  }, [market.status]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1320px)");
    const applyLayout = () => setStackedDeskLayout(media.matches);
    applyLayout();
    const onChange = () => {
      applyLayout();
      window.requestAnimationFrame(syncLeftRailHeight);
    };
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    }
    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, [syncLeftRailHeight]);

  useEffect(() => {
    const rafId = window.requestAnimationFrame(syncLeftRailHeight);
    const timeoutId = window.setTimeout(syncLeftRailHeight, 140);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
    };
  }, [syncLeftRailHeight]);

  useEffect(() => {
    const node = leftRailRef.current;
    if (!node) {
      return;
    }
    let timeoutId: number | null = null;
    const handleResize = () => {
      syncLeftRailHeight();
      window.requestAnimationFrame(syncLeftRailHeight);
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
      timeoutId = window.setTimeout(syncLeftRailHeight, 140);
    };
    syncLeftRailHeight();
    const observer = new ResizeObserver(syncLeftRailHeight);
    observer.observe(node);
    window.addEventListener("resize", handleResize);
    window.addEventListener("load", handleResize);
    return () => {
      observer.disconnect();
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("load", handleResize);
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [syncLeftRailHeight]);

  useLayoutEffect(() => {
    syncLeftRailHeight();
    const rafId = window.requestAnimationFrame(syncLeftRailHeight);
    const timeoutId = window.setTimeout(syncLeftRailHeight, 120);
    return () => {
      window.cancelAnimationFrame(rafId);
      window.clearTimeout(timeoutId);
    };
  }, [
    syncLeftRailHeight,
    selectedTrader,
    detail,
    traders.length,
    market.status,
    scheduler.running,
    scheduler.run_in_progress,
    allowClosedMarketTrading,
    actionBusy,
    loading,
    stackedDeskLayout,
  ]);

  const totalCashValue = useMemo(
    () => traders.reduce((acc, trader) => acc + (trader.cash_balance ?? trader.balance), 0),
    [traders],
  );
  const totalMarketValue = useMemo(
    () =>
      traders.reduce(
        (acc, trader) =>
          acc +
          (trader.holdings_market_value ??
            Math.max(0, (trader.total_equity ?? trader.total_portfolio_value) - (trader.cash_balance ?? trader.balance))),
        0,
      ),
    [traders],
  );
  const totalValue = useMemo(
    () => traders.reduce((acc, trader) => acc + (trader.total_equity ?? trader.total_portfolio_value), 0),
    [traders],
  );
  const totalPnL = useMemo(
    () => traders.reduce((acc, trader) => acc + trader.total_profit_loss, 0),
    [traders],
  );
  const totalPnLLabel = totalPnL >= 0 ? "Profit" : "Loss";

  const selectedSummary = traders.find((entry) => entry.name === selectedTrader) ?? null;
  const selectedCash = selectedSummary?.cash_balance ?? selectedSummary?.balance ?? 0;
  const selectedMarketValue =
    selectedSummary?.holdings_market_value ??
    Math.max(0, (selectedSummary?.total_equity ?? selectedSummary?.total_portfolio_value ?? 0) - selectedCash);
  const selectedTotalEquity = selectedSummary?.total_equity ?? selectedSummary?.total_portfolio_value ?? 0;
  const selectedPnl = selectedSummary?.total_profit_loss ?? 0;
  const selectedPnlLabel = selectedPnl >= 0 ? "Profit" : "Loss";
  const visibleLogs = useMemo(
    () =>
      (detail?.logs || []).filter((log) => {
        const logType = log.type.trim().toLowerCase();
        const message = log.message.trim().toLowerCase();
        if (logType === "mcp_tools" || logType === "mcp-tools") return false;
        if (logType === "account" && message === "retrieved account details") return false;
        return true;
      }),
    [detail?.logs],
  );
  const sortedTransactions = useMemo(() => {
    const items = [...(detail?.account.transactions || [])];
    const sign = txSort.direction === "asc" ? 1 : -1;
    items.sort((a, b) => {
      if (txSort.key === "timestamp") {
        const aTs = parseTimestampMs(a.timestamp) ?? 0;
        const bTs = parseTimestampMs(b.timestamp) ?? 0;
        return (aTs - bTs) * sign;
      }
      if (txSort.key === "action") {
        const aAction = a.quantity >= 0 ? "BUY" : "SELL";
        const bAction = b.quantity >= 0 ? "BUY" : "SELL";
        return aAction.localeCompare(bAction) * sign;
      }
      if (txSort.key === "symbol") {
        return a.symbol.localeCompare(b.symbol) * sign;
      }
      if (txSort.key === "qty") {
        return (Math.abs(a.quantity) - Math.abs(b.quantity)) * sign;
      }
      return (a.price - b.price) * sign;
    });
    return items;
  }, [detail?.account.transactions, txSort]);
  const visibleTransactions = useMemo(() => {
    const query = txSearch.trim().toLowerCase();
    const fromMs = txDateFrom ? Date.parse(`${txDateFrom}T00:00:00Z`) : null;
    const toMs = txDateTo ? Date.parse(`${txDateTo}T23:59:59Z`) : null;
    return sortedTransactions.filter((tx) => {
      const side = tx.quantity >= 0 ? "buy" : "sell";
      if (txActionFilter !== "all" && side !== txActionFilter) {
        return false;
      }

      const tsMs = parseTimestampMs(tx.timestamp);
      if (fromMs !== null && (tsMs === null || tsMs < fromMs)) {
        return false;
      }
      if (toMs !== null && (tsMs === null || tsMs > toMs)) {
        return false;
      }

      if (!query) {
        return true;
      }
      const haystack = `${tx.timestamp} ${side} ${tx.symbol} ${Math.abs(tx.quantity)} ${tx.price} ${tx.rationale || ""}`
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [sortedTransactions, txSearch, txActionFilter, txDateFrom, txDateTo]);
  const txPageSize = 12;
  const totalTxPages = Math.max(1, Math.ceil(visibleTransactions.length / txPageSize));
  const currentTxPage = Math.min(txPage, totalTxPages);
  const pagedTransactions = useMemo(() => {
    const start = (currentTxPage - 1) * txPageSize;
    return visibleTransactions.slice(start, start + txPageSize);
  }, [currentTxPage, txPageSize, visibleTransactions]);
  const txRowStart = visibleTransactions.length === 0 ? 0 : (currentTxPage - 1) * txPageSize + 1;
  const txRowEnd = Math.min(currentTxPage * txPageSize, visibleTransactions.length);

  useEffect(() => {
    setTxPage(1);
  }, [selectedTrader, txSearch, txActionFilter, txDateFrom, txDateTo, txSort]);

  useEffect(() => {
    if (txPage > totalTxPages) {
      setTxPage(totalTxPages);
    }
  }, [txPage, totalTxPages]);

  const marketLabel =
    market.status === "open" ? "OPEN" : market.status === "closed" ? "CLOSED" : "UNKNOWN";
  const marketClass =
    market.status === "open" ? "marketOpen" : market.status === "closed" ? "marketClosed" : "marketUnknown";
  const startBlockedByClosedMarket = market.status === "closed" && !allowClosedMarketTrading;
  const readOnlyMode = Boolean(scheduler.read_only_mode);
  const traderThemeClass = `theme-${selectedTrader.toLowerCase()}`;
  const rightPanelHeightStyle = !stackedDeskLayout && leftRailHeight ? { height: `${leftRailHeight}px` } : undefined;
  const toggleTxSort = (key: TxSortKey) => {
    setTxSort((prev) =>
      prev.key === key
        ? { key, direction: prev.direction === "asc" ? "desc" : "asc" }
        : { key, direction: key === "timestamp" ? "desc" : "asc" },
    );
  };
  const sortLabel = (key: TxSortKey) => {
    if (txSort.key !== key) return "↕";
    return txSort.direction === "asc" ? "▲" : "▼";
  };

  return (
    <main className={`controlDesk ${traderThemeClass}`}>
      <header className="topHero">
        <div className="brandBlock">
          <p className="brandKicker">
            <span className="brandTitleText">Autonomous Agentic Trader</span>
            <RichHelpTip label="How autonomous trading works" placement="down" className="heroPillSup">
              <p className="richHelpTitle">How autonomous trading works</p>
              <p className="richHelpText">Key components:</p>
              <ul className="richHelpList">
                <li>Dashboard web app for monitoring, controls, and live logs.</li>
                <li>FastAPI backend for data APIs and trading runtime control.</li>
                <li>Autonomous trading engine where trader agents make decisions.</li>
              </ul>
              <p className="richHelpText">
                The system can use internet research tools to gather current market news and context before taking action.
              </p>
              <p className="richHelpText">
                Market price lookup order:
              </p>
              <ol className="richHelpList">
                <li>Try Polygon first (preferred source).</li>
                <li>If Polygon fails, use the latest cached price for that symbol (if available).</li>
                <li>If cache is empty, query Brave web search and extract a previous-close style price.</li>
                <li>If all sources fail, mark the symbol as unavailable (price = 0.00) and skip execution for that trade.</li>
              </ol>
              <p className="richHelpText">
                Trades are strategy-driven per trader, and each trader can run on a different LLM model (OpenAI, DeepSeek, Gemini, Grok in multi-model mode).
              </p>
            </RichHelpTip>
          </p>
          <p className="brandSubtitle">Live portfolio intelligence, trading control, and strategy execution in one view.</p>
        </div>
        <div className="heroStats">
          <article className="statCard statCardCentered">
            <span className="statLabel">
              Market{" "}
              <RichHelpTip label="Market status help" placement="down">
                <p className="richHelpTitle">Market status + price lookup</p>
                <p className="richHelpText">
                  This card shows whether the US market session is open or closed based on backend market-hours checks.
                </p>
                <p className="richHelpText">When a trade needs a price, lookup runs in this order:</p>
                <ol className="richHelpList">
                  <li>Polygon API (preferred).</li>
                  <li>Cached last-known price for the symbol.</li>
                  <li>Brave web search fallback price extraction.</li>
                  <li>If all fail: mark as unavailable (`0.00`) and skip the trade.</li>
                </ol>
                <p className="richHelpText">Live logs show which source was used: POLYGON, CACHE, WEB, or UNAVAILABLE.</p>
              </RichHelpTip>
            </span>
            <span className={`statValue marketBadge ${marketClass}`} title={market.detail || undefined}>
              {marketLabel}
            </span>
            <small className="statHint marketHours">US Market 9:30 AM – 4:00 PM ET</small>
          </article>
          <article className="statCard statCardCentered">
            <span className="statLabel">
              Trading{" "}
              <HelpTip
                placement="down"
                label="Trading status help"
                text="Indicates whether the trading loop process is running. PID appears when active."
              />
            </span>
            <span className={`statValue tradingStatusPill ${scheduler.running ? "tradingRunning" : "tradingStopped"}`}>
              {scheduler.running ? "Running" : "Stopped"}
            </span>
            <small className="statHint">{scheduler.pid ? `PID ${scheduler.pid}` : "No active trading process"}</small>
          </article>
          <article className="statCard statCardCentered">
            <span className="statLabel">
              Total Portfolio{" "}
              <HelpTip
                placement="down"
                label="Total portfolio help"
                text="Combined total equity across all traders, broken into cash balance and holdings market value, plus net profit or loss."
              />
            </span>
            <span className="statValue">
              <span className={`totalValuePill ${totalPnL >= 0 ? "totalValuePillUp" : "totalValuePillDown"}`}>
                <span className="pillPrimary">${money(totalValue, 0)}</span>
                <span className="pillDivider">|</span>
                <span className={`pillSecondary ${totalPnL >= 0 ? "pnlUp" : "pnlDown"}`}>
                  {totalPnL >= 0 ? "+" : "-"}${money(Math.abs(totalPnL), 0)}
                </span>
              </span>
            </span>
            <small className="statHint">Cash ${money(totalCashValue, 0)} + Market ${money(totalMarketValue, 0)}</small>
          </article>
        </div>
      </header>

      <section className="traderStrip" aria-label="Trader selector">
        {traders.map((trader) => {
          const isActive = trader.name === selectedTrader;
          const blurb = TRADER_PERSONALITY_BLURBS[trader.name] || "Adaptive trader with a distinct investing style.";
          return (
            <button
              key={trader.name}
              className={`traderChip ${isActive ? "active" : ""}`}
              onClick={() => {
                selectedTraderRef.current = trader.name;
                setSelectedTrader(trader.name);
              }}
            >
              <strong>{trader.name}</strong>
              <span className="traderRole">
                {trader.lastname} ({trader.model_name})
              </span>
              <small className="traderBlurb">{blurb}</small>
            </button>
          );
        })}
      </section>

      <p className="marketDisclaimer">
        Disclaimer: Market prices shown in this dashboard are based on the previous trading day&apos;s market close.
      </p>

      <section className="deskGrid">
        <div className="leftRail" ref={leftRailRef}>
          <aside className="panel controlPanel">
            <h2 className="titleWithHelp">
              Trade Controls
              <HelpTip
                label="Trade controls help"
                text="Central command panel for trading operations. Start or stop automated trading, manually refresh live portfolio snapshots, reset all traders for clean development runs, and optionally allow trading while market status is closed."
              />
            </h2>
            <div className="controlActions">
              <div className="frequencyControl">
                <label className="frequencyLabel" htmlFor="run-frequency-input">
                  Run Every N Minutes
                  <HelpTip
                    label="Trading frequency help"
                    text="Sets RUN_EVERY_N_MINUTES for the trading process. Initial value is 60 minutes. Changes apply on the next Start Trading."
                  />
                </label>
                <input
                  id="run-frequency-input"
                  className="frequencyInput"
                  type="number"
                  min={1}
                  step={1}
                  value={runEveryNMinutes}
                  disabled={actionBusy !== null || readOnlyMode}
                  onChange={(event) => {
                    const parsed = Number(event.target.value);
                    if (!Number.isFinite(parsed)) {
                      return;
                    }
                    setRunEveryNMinutes(Math.max(1, Math.floor(parsed)));
                  }}
                />
              </div>
              <button
                className={`deskBtn ${market.status !== "open" ? (allowClosedMarketTrading ? "warnActive" : "warn") : "muted"}`}
                disabled={actionBusy !== null || scheduler.running || market.status === "open" || readOnlyMode}
                onClick={() => {
                  if (market.status !== "open") {
                    setAllowClosedMarketTrading((prev) => !prev);
                  }
                }}
              >
                <span className="btnWithHelp">
                  {market.status !== "open"
                    ? allowClosedMarketTrading
                      ? "Disable Closed-Market Override"
                      : "Enable Trading While Market Closed"
                    : "Market Open (Override Not Needed)"}
                  <HelpTip
                    label="Closed market override help"
                    text="Enables trading start even when market status reports CLOSED. Use only for paper simulation, testing, or non-market-hour strategy validation."
                  />
                </span>
              </button>
              <button
                className="deskBtn"
                disabled={actionBusy !== null || startBlockedByClosedMarket || scheduler.running || readOnlyMode}
                onClick={() =>
                  runAction("start", async () => {
                    setScheduler(
                      await startScheduler({
                        runEvenWhenMarketIsClosed: allowClosedMarketTrading ? true : undefined,
                        runEveryNMinutes,
                      }),
                    );
                    await refreshDashboard();
                  })
                }
              >
                {actionBusy === "start" ? (
                  "Starting..."
                ) : (
                  <span className="btnWithHelp">
                    {startBlockedByClosedMarket ? "Start Trading (Market Closed)" : "Start Trading"}
                    <HelpTip
                      label="Start trading help"
                      text="Launches the trading process so trader agents execute on schedule."
                    />
                  </span>
                )}
              </button>
              <button
                className="deskBtn"
                disabled={actionBusy !== null || readOnlyMode}
                onClick={() =>
                  runAction("stop", async () => {
                    setScheduler(await stopScheduler());
                    await refreshDashboard();
                  })
                }
              >
                {actionBusy === "stop" ? (
                  "Stopping..."
                ) : (
                  <span className="btnWithHelp">
                    Stop Trading
                    <HelpTip
                      label="Stop trading help"
                      text="Stops the active trading process and halts automatic trading runs."
                    />
                  </span>
                )}
              </button>
              <button
                className="deskBtn"
                disabled={actionBusy !== null}
                onClick={() => runAction("refresh", refreshDashboard)}
              >
                {actionBusy === "refresh" ? (
                  "Refreshing..."
                ) : (
                  <span className="btnWithHelp">
                    Refresh Traders Portfolio
                    <HelpTip
                      label="Refresh traders portfolio help"
                      text="Reloads all trader summaries, market status, trading status, and currently selected trader detail."
                    />
                  </span>
                )}
              </button>
              <button
                className="deskBtn danger"
                disabled={actionBusy !== null || readOnlyMode}
                onClick={() =>
                  runAction("reset", async () => {
                    await resetTraders();
                    await refreshDashboard();
                  })
                }
              >
                {actionBusy === "reset" ? (
                  "Resetting..."
                ) : (
                  <span className="btnWithHelp">
                    Reset Traders Portfolio
                    <HelpTip
                      label="Reset traders portfolio help"
                      text="Clears trader account state and rebuilds fresh starter portfolios. Intended for development resets."
                    />
                  </span>
                )}
              </button>
            </div>
            {readOnlyMode ? (
              <p className="controlNotice">
                READ_ONLY_MODE is enabled. Trade controls are disabled and trading is managed automatically by market status.
              </p>
            ) : null}
            {!readOnlyMode && startBlockedByClosedMarket ? (
              <p className="controlNotice">
                Market is closed. Enable the closed-market override button above if you want to run trading anyway.
              </p>
            ) : null}
          </aside>

          <aside className="panel holdingsPanel">
            <h2 className="titleWithHelp">
              Holdings
              <HelpTip
                label="Holdings help"
                text="Position snapshot for the selected trader. Cash is available buying power, Market Value is holdings value at current pricing, and Total Equity is Cash + Market Value."
                placement="right"
              />
            </h2>
            <div className="controlMeta holdingsMeta">
              <p>
                <span>Selected Trader</span>
                <strong>{selectedSummary?.name || "-"}</strong>
              </p>
              <p>
                <span>Cash</span>
                <strong>${money(selectedCash, 0)}</strong>
              </p>
              <p>
                <span>Market Value</span>
                <strong>${money(selectedMarketValue, 0)}</strong>
              </p>
              <p>
                <span>Total Equity</span>
                <strong>${money(selectedTotalEquity, 0)}</strong>
              </p>
              <p>
                <span className={selectedPnl >= 0 ? "pnlUp" : "pnlDown"}>{selectedPnlLabel}</span>
                <strong className={selectedPnl >= 0 ? "pnlUp" : "pnlDown"}>
                  ${money(Math.abs(selectedPnl), 0)}
                </strong>
              </p>
            </div>

            <div className="tableWrap holdingsTableWrap">
              <table className="holdingsTable">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(detail?.account.holdings || {}).map(([symbol, qty]) => (
                    <tr key={symbol}>
                      <td>{symbol}</td>
                      <td>{qty}</td>
                    </tr>
                  ))}
                  {Object.keys(detail?.account.holdings || {}).length === 0 ? (
                    <tr>
                      <td colSpan={2}>No holdings.</td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </aside>
        </div>

        <section className="panel chartPanel" style={rightPanelHeightStyle}>
          <div className="panelHeaderRow">
            <h2 className="titleWithHelp">
              {selectedTrader} Portfolio Timeline
              <HelpTip
                label="Portfolio timeline help"
                text="Performance chart of the selected trader over time. X-axis is date/time, Y-axis is portfolio amount. BUY/SELL markers highlight executed trades, while filters narrow by side and date window."
              />
            </h2>
            <div className="chartToolbar">
              <div className="filterGroup" aria-label="Trade filter">
                {(["all", "buy", "sell"] as TradeFilter[]).map((filter) => (
                  <button
                    key={filter}
                    className={`filterBtn ${txFilter === filter ? "active" : ""}`}
                    onClick={() => setTxFilter(filter)}
                  >
                    {filter.toUpperCase()}
                  </button>
                ))}
              </div>
              <div className="filterGroup" aria-label="Date range filter">
                {(["1d", "1w", "1m", "all"] as ChartRange[]).map((range) => (
                  <button
                    key={range}
                    className={`filterBtn ${chartRange === range ? "active" : ""}`}
                    onClick={() => setChartRange(range)}
                  >
                    {range.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {detail ? (
            <PortfolioLineChart
              series={detail.account.portfolio_value_time_series}
              transactions={detail.account.transactions}
              txFilter={txFilter}
              chartRange={chartRange}
            />
          ) : (
            <p className="muted">{loading ? "Loading chart..." : "No trader data available."}</p>
          )}
        </section>

        <aside className="panel logPanel" style={rightPanelHeightStyle}>
          <div className="panelHeaderRow">
            <h2 className="titleWithHelp">
              Live Logs
              <HelpTip
                label="Live logs help"
                text="Operational event stream from backend services. Includes model interactions, function calls, account updates, traces, and execution diagnostics to help troubleshoot behavior."
              />
            </h2>
            <span className="panelHint">{visibleLogs.length} entries</span>
          </div>
          <div className="logStream">
            {visibleLogs.map((log, idx) => {
              const tradeClass = logTradeClass(log.type, log.message);
              return (
              <article key={`${log.timestamp}-${idx}`} className={`logItem ${tradeClass}`}>
                <div className="logHead">
                  <span className="logTime">{formatDateTimeLocal(log.timestamp)}</span>
                  <span className={`logType ${logTypeClass(log.type)}`}>{log.type}</span>
                </div>
                <p className="logText">{log.message}</p>
              </article>
              );
            })}
            {visibleLogs.length === 0 ? <p className="muted">No logs yet.</p> : null}
          </div>
        </aside>
      </section>

      {error ? <p className="error">{error}</p> : null}

      <section className="panel detailWorkspace">
        <h2 className="titleWithHelp">
          Transactions
          <HelpTip
            placement="down"
            label="Transactions table help"
            text="Detailed trade ledger for the selected trader in chronological order. Each row shows timestamp, action side, symbol, quantity, fill price, and full trade rationale generated at execution."
          />
        </h2>
        <div className="txTableControls">
          <input
            type="text"
            className="txSearchInput"
            placeholder="Search symbol, rationale, qty, price..."
            value={txSearch}
            onChange={(event) => setTxSearch(event.target.value)}
          />
          <div className="txActionFilterGroup">
            {(["all", "buy", "sell"] as const).map((action) => (
              <button
                key={action}
                type="button"
                className={`txActionFilterBtn ${txActionFilter === action ? "active" : ""}`}
                onClick={() => setTxActionFilter(action)}
              >
                {action.toUpperCase()}
              </button>
            ))}
          </div>
          <div className="txDateRange">
            <label>
              From
              <input type="date" value={txDateFrom} onChange={(event) => setTxDateFrom(event.target.value)} />
            </label>
            <label>
              To
              <input type="date" value={txDateTo} onChange={(event) => setTxDateTo(event.target.value)} />
            </label>
          </div>
        </div>
        <div className="tableWrap transactionsTableWrap">
          <table>
            <thead>
              <tr>
                <th>
                  <button type="button" className="thSortBtn" onClick={() => toggleTxSort("timestamp")}>
                    Timestamp <span className="sortArrow">{sortLabel("timestamp")}</span>
                  </button>
                </th>
                <th>
                  <button type="button" className="thSortBtn" onClick={() => toggleTxSort("action")}>
                    Action <span className="sortArrow">{sortLabel("action")}</span>
                  </button>
                </th>
                <th>
                  <button type="button" className="thSortBtn" onClick={() => toggleTxSort("symbol")}>
                    Symbol <span className="sortArrow">{sortLabel("symbol")}</span>
                  </button>
                </th>
                <th>
                  <button type="button" className="thSortBtn" onClick={() => toggleTxSort("qty")}>
                    Qty <span className="sortArrow">{sortLabel("qty")}</span>
                  </button>
                </th>
                <th>
                  <button type="button" className="thSortBtn" onClick={() => toggleTxSort("price")}>
                    Price <span className="sortArrow">{sortLabel("price")}</span>
                  </button>
                </th>
                <th>Rationale</th>
              </tr>
            </thead>
            <tbody>
              {pagedTransactions.map((tx, idx) => {
                const side = tx.quantity >= 0 ? "BUY" : "SELL";
                return (
                  <tr key={`${tx.timestamp}-${idx}`}>
                    <td className="colTimestamp">{formatDateTimeLocal(tx.timestamp)}</td>
                    <td className={`colAction ${tx.quantity >= 0 ? "txBuy" : "txSell"}`}>{side}</td>
                    <td className="colSymbol">{tx.symbol}</td>
                    <td className="colQty">{Math.abs(tx.quantity)}</td>
                    <td className="colPrice">${money(tx.price, 2)}</td>
                    <td className="txRationale" title={tx.rationale || "No rationale"}>
                      {tx.rationale || "No rationale"}
                    </td>
                  </tr>
                );
              })}
              {visibleTransactions.length === 0 ? (
                <tr>
                  <td colSpan={6}>No transactions match the current filters.</td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="txPagination">
          <span className="txPaginationInfo">
            Showing {txRowStart}-{txRowEnd} of {visibleTransactions.length}
          </span>
          <div className="txPaginationActions">
            <button
              type="button"
              className="txPageBtn"
              disabled={currentTxPage <= 1}
              onClick={() => setTxPage((page) => Math.max(1, page - 1))}
            >
              Previous
            </button>
            <span className="txPageCurrent">
              Page {currentTxPage} / {totalTxPages}
            </span>
            <button
              type="button"
              className="txPageBtn"
              disabled={currentTxPage >= totalTxPages}
              onClick={() => setTxPage((page) => Math.min(totalTxPages, page + 1))}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </main>
  );
}
