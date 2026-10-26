import { useCallback, useEffect, useState } from "react";
import { apiClient, apiErrorMessage } from "../api/client";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { useAuthStore } from "../store/authStore";
import {
  Activity, AlertTriangle, TrendingUp, Loader2, RefreshCw, Coins, MessageSquare,
} from "lucide-react";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

interface ChartDataPoint {
  date: string;
  count: number;
}

interface DriftEvent {
  id: number;
  drift_score: number;
  timestamp: string;
}

// Mirrors app/metrics_service.get_workspace_monitoring_stats.
interface MonitoringStats {
  total_predictions: number;
  error_count: number;
  avg_latency: number;       // milliseconds
  avg_confidence: number;    // mean retrieval similarity, not a probability
  chart_data: ChartDataPoint[];
  recent_drifts: DriftEvent[];
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  refused_queries: number;
  estimated_cost_usd: number;
  cost_rates_configured: boolean;
}

// Every number on this page comes from the API. An earlier version showed invented
// metrics whenever the workspace was empty or the request failed, which made an
// outage look healthy - the opposite of what a monitoring page is for.
export default function MonitoringPage() {
  const { activeWorkspaceId } = useAuthStore();
  const [stats, setStats] = useState<MonitoringStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    if (!activeWorkspaceId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.get<MonitoringStats>("/ai/monitoring", {
        params: { workspace_id: activeWorkspaceId },
      });
      setStats(response.data);
    } catch (err) {
      setStats(null);
      setError(apiErrorMessage(err, "Could not load monitoring data."));
    } finally {
      setLoading(false);
    }
  }, [activeWorkspaceId]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const header = (
    <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-dark-800/60 pb-5">
      <div>
        <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-brand-500/10 border border-brand-500/25 text-brand-400">
          Observability
        </span>
        <h1 className="text-2xl font-bold tracking-tight text-white mt-1 flex items-center gap-2">
          <Activity className="w-5 h-5 text-brand-400" />
          <span>Workspace monitoring</span>
        </h1>
      </div>
      <button
        onClick={fetchStats}
        className="p-2 text-dark-400 hover:text-brand-400 hover:bg-dark-800/50 rounded-lg transition-colors border border-dark-800 self-start sm:self-auto"
        title="Refresh"
      >
        <RefreshCw className="w-4 h-4" />
      </button>
    </div>
  );

  if (loading) {
    return (
      <div className="h-[calc(100vh-80px)] flex flex-col items-center justify-center bg-dark-950">
        <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
        <span className="text-xs text-dark-400 mt-3 font-semibold">Loading monitoring data...</span>
      </div>
    );
  }

  if (error || !stats) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {header}
        <div className="glass-panel rounded-2xl p-8 border border-rose-500/20 text-center">
          <AlertTriangle className="w-8 h-8 text-rose-400 mx-auto" />
          <h3 className="text-sm font-bold text-white mt-3">Monitoring data is unavailable</h3>
          <p className="text-xs text-dark-400 mt-1">{error}</p>
          <button
            onClick={fetchStats}
            className="mt-4 px-3 py-1.5 text-xs text-white bg-brand-600 hover:bg-brand-500 rounded-lg font-semibold"
          >
            Try again
          </button>
        </div>
      </div>
    );
  }

  if (stats.total_predictions === 0) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-8 space-y-6">
        {header}
        <div className="glass-panel rounded-2xl p-8 border border-dark-850 text-center">
          <MessageSquare className="w-8 h-8 text-dark-500 mx-auto" />
          <h3 className="text-sm font-bold text-white mt-3">No queries in this workspace yet</h3>
          <p className="text-xs text-dark-400 mt-1">
            Latency, retrieval similarity, token usage and drift appear here once questions are asked in Chat.
          </p>
        </div>
      </div>
    );
  }

  const queryChartData = {
    labels: stats.chart_data.map((d) => d.date),
    datasets: [
      {
        label: "Queries",
        data: stats.chart_data.map((d) => d.count),
        borderColor: "rgba(139, 92, 246, 1)",
        backgroundColor: "rgba(139, 92, 246, 0.05)",
        pointBackgroundColor: "rgba(139, 92, 246, 1)",
        pointBorderColor: "rgba(255, 255, 255, 0.1)",
        pointRadius: 4,
        tension: 0.4,
        fill: true,
        borderWidth: 2.5,
      },
    ],
  };

  const queryChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        titleColor: "#f8fafc",
        bodyColor: "#94a3b8",
        borderColor: "rgba(139, 92, 246, 0.2)",
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(255, 255, 255, 0.03)" },
        ticks: { color: "#64748b", font: { size: 10, family: "JetBrains Mono" } },
      },
      y: {
        grid: { color: "rgba(255, 255, 255, 0.03)" },
        ticks: { color: "#64748b", font: { size: 10, family: "JetBrains Mono" }, precision: 0 },
        beginAtZero: true,
      },
    },
  };

  const answered = stats.total_predictions - stats.refused_queries;
  const tokensPerQuery =
    stats.total_predictions > 0
      ? Math.round((stats.prompt_tokens + stats.completion_tokens) / stats.total_predictions)
      : 0;

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6 animate-slide-up">
      {header}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Queries" value={stats.total_predictions.toLocaleString()}
                  note={`${answered} answered · ${stats.refused_queries} refused`} />
        <StatCard label="Avg latency" value={`${(stats.avg_latency / 1000).toFixed(2)} s`}
                  note="including every LLM call" />
        {/* Mean cosine similarity of the retrieved chunks. Shown as a plain number:
            it is not a probability, and typical values here are 0.2-0.5. */}
        <StatCard label="Avg retrieval similarity" value={stats.avg_confidence.toFixed(3)}
                  note="mean of the top-k chunks" />
        <StatCard label="Errors" value={String(stats.error_count)}
                  note="failed queries" valueClass={stats.error_count > 0 ? "text-rose-400" : "text-white"} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-8 glass-panel rounded-2xl p-5 border border-dark-850 flex flex-col">
          <h3 className="text-sm font-bold text-white flex items-center space-x-2 mb-4">
            <TrendingUp className="w-4 h-4 text-brand-400" />
            <span>Queries, last 7 days</span>
          </h3>
          <div className="h-64 relative">
            <Line options={queryChartOptions} data={queryChartData} />
          </div>
        </div>

        <div className="lg:col-span-4 glass-panel rounded-2xl p-5 border border-dark-850 flex flex-col">
          <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <span>Drift alerts</span>
          </h3>
          {stats.recent_drifts.length === 0 ? (
            <p className="text-xs text-dark-400">
              None. An alert is raised when the rolling mean similarity of the last 50
              queries falls below the refusal threshold.
            </p>
          ) : (
            <div className="space-y-3 overflow-y-auto max-h-64 pr-1">
              {stats.recent_drifts.map((d) => (
                <div key={d.id} className="p-3 bg-dark-950/60 rounded-xl border border-dark-800 flex items-center justify-between">
                  <div>
                    <span className="text-[10px] text-dark-500 font-mono block">
                      {new Date(d.timestamp).toLocaleString([], { dateStyle: "short", timeStyle: "short" })}
                    </span>
                    <span className="text-xs font-semibold text-white mt-1 block">Low retrieval similarity</span>
                  </div>
                  <span className="text-xs font-mono font-bold px-2 py-0.5 rounded border bg-rose-500/10 border-rose-500/20 text-rose-400">
                    {d.drift_score.toFixed(3)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="glass-panel rounded-2xl p-5 border border-dark-850">
        <h3 className="text-sm font-bold text-white mb-4 flex items-center space-x-2">
          <Coins className="w-4 h-4 text-emerald-400" />
          <span>LLM usage and cost</span>
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <MiniStat label="LLM calls" value={stats.llm_calls.toLocaleString()} />
          <MiniStat label="Prompt tokens" value={stats.prompt_tokens.toLocaleString()} />
          <MiniStat label="Completion tokens" value={stats.completion_tokens.toLocaleString()} />
          <MiniStat label="Tokens per query" value={tokensPerQuery.toLocaleString()} />
        </div>
        <p className="text-[11px] text-dark-400 mt-4">
          {stats.cost_rates_configured ? (
            <>Estimated cost: <span className="font-mono text-white">${stats.estimated_cost_usd.toFixed(4)}</span> at the configured per-token rates.</>
          ) : (
            <>No cost shown: set <span className="font-mono">LLM_INPUT_COST_PER_MTOK</span> and{" "}
            <span className="font-mono">LLM_OUTPUT_COST_PER_MTOK</span> on the server to turn these token counts into a price.</>
          )}{" "}
          A refused query skips synthesis and self-critique, so it costs a fraction of an answered one.
        </p>
      </div>
    </div>
  );
}

function StatCard({ label, value, note, valueClass = "text-white" }: {
  label: string; value: string; note: string; valueClass?: string;
}) {
  return (
    <div className="glass-panel rounded-2xl p-5 border border-dark-850 flex flex-col justify-between">
      <span className="text-[10px] uppercase tracking-wider font-bold text-dark-500">{label}</span>
      <span className={`text-2xl font-extrabold tracking-tight mt-2 font-mono ${valueClass}`}>{value}</span>
      <span className="text-[10px] text-dark-500 mt-1">{note}</span>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-dark-950/60 rounded-xl p-3.5 border border-dark-800">
      <span className="text-[10px] font-bold text-dark-400 block uppercase tracking-wider mb-1">{label}</span>
      <span className="text-xl font-bold text-white font-mono">{value}</span>
    </div>
  );
}
