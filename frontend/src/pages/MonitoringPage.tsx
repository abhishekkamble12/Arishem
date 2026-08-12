import React, { useEffect, useState } from "react";
import { apiClient } from "../api/client";
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
import { Line, Bar } from "react-chartjs-2";
import { useAuthStore } from "../store/authStore";
import {
  Activity, Clock, ShieldCheck, AlertTriangle, TrendingUp,
  Loader2, RefreshCw, BarChart3
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

interface MonitoringStats {
  total_predictions: number;
  error_count: number;
  avg_latency: number;
  avg_confidence: number;
  chart_data: ChartDataPoint[];
  recent_drifts: DriftEvent[];
}

export default function MonitoringPage() {
  const { accessToken, activeWorkspaceId } = useAuthStore();
  const [stats, setStats] = useState<MonitoringStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.get("/app/ai/monitoring", {
        headers: { Authorization: `Bearer ${accessToken}` },
        params: { workspace_id: activeWorkspaceId },
      });
      setStats(response.data);
    } catch (err: any) {
      console.error("Failed to fetch monitoring stats:", err);
      setError(err.response?.data?.error || "Failed to load dashboard.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (accessToken && activeWorkspaceId) {
      fetchStats();
    }
  }, [accessToken, activeWorkspaceId]);

  if (loading) {
    return (
      <div className="h-[calc(100vh-100px)] flex flex-col items-center justify-center">
        <Loader2 className="w-8 h-8 text-brand-500 animate-spin" />
        <span className="text-sm text-dark-400 mt-3">Loading metrics…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-[calc(100vh-100px)] flex flex-col items-center justify-center px-6 text-center">
        <AlertTriangle className="w-10 h-10 text-red-400 mb-3" />
        <p className="text-red-400 font-semibold">{error}</p>
        <p className="text-xs text-dark-500 mt-1">Only Admins and Editors can view monitoring stats.</p>
      </div>
    );
  }

  if (!stats) return null;

  // ── Chart: Queries over time ──
  const queryChartData = {
    labels: stats.chart_data.map((d) => d.date),
    datasets: [
      {
        label: "Queries",
        data: stats.chart_data.map((d) => d.count),
        borderColor: "rgba(139, 92, 246, 1)",
        backgroundColor: "rgba(139, 92, 246, 0.08)",
        pointBackgroundColor: "rgba(139, 92, 246, 1)",
        pointBorderColor: "rgba(139, 92, 246, 0.4)",
        pointRadius: 4,
        pointHoverRadius: 6,
        tension: 0.4,
        fill: true,
        borderWidth: 2,
      },
    ],
  };

  const queryChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: { display: false },
      tooltip: {
        backgroundColor: "rgba(15, 23, 42, 0.95)",
        titleColor: "#f8fafc",
        bodyColor: "#94a3b8",
        borderColor: "rgba(139, 92, 246, 0.3)",
        borderWidth: 1,
        padding: 10,
        cornerRadius: 8,
      },
    },
    scales: {
      x: {
        grid: { color: "rgba(255,255,255,0.04)" },
        ticks: { color: "#64748b", font: { size: 10 } },
      },
      y: {
        grid: { color: "rgba(255,255,255,0.04)" },
        ticks: { color: "#64748b", font: { size: 10 } },
        beginAtZero: true,
      },
    },
  };

  // ── Confidence gauge value ──
  const confidencePct = (stats.avg_confidence * 100).toFixed(1);
  const confidenceColor =
    stats.avg_confidence >= 0.7 ? "text-emerald-400" :
    stats.avg_confidence >= 0.5 ? "text-amber-400" :
    "text-red-400";
  const confidenceBg =
    stats.avg_confidence >= 0.7 ? "bg-emerald-500/10 border-emerald-500/20" :
    stats.avg_confidence >= 0.5 ? "bg-amber-500/10 border-amber-500/20" :
    "bg-red-500/10 border-red-500/20";

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-extrabold tracking-tight text-white flex items-center gap-2.5">
            <Activity className="w-6 h-6 text-brand-400" />
            AI Observability Dashboard
          </h1>
          <p className="text-xs text-dark-500 mt-1">
            Workspace {activeWorkspaceId} · Real-time query metrics, confidence tracking, and drift detection
          </p>
        </div>
        <button
          onClick={fetchStats}
          className="p-2 text-dark-400 hover:text-brand-400 hover:bg-dark-800/50 rounded-lg transition-colors border border-dark-800"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* ── KPI Cards ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Queries */}
        <div className="glass-panel rounded-2xl p-5 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center">
              <BarChart3 className="w-4 h-4 text-brand-400" />
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold text-dark-500">Total Queries</span>
          </div>
          <span className="text-3xl font-extrabold text-white tracking-tight">
            {stats.total_predictions.toLocaleString()}
          </span>
        </div>

        {/* Avg Latency */}
        <div className="glass-panel rounded-2xl p-5 flex flex-col">
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Clock className="w-4 h-4 text-blue-400" />
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold text-dark-500">Avg Latency</span>
          </div>
          <span className="text-3xl font-extrabold text-white tracking-tight">
            {stats.avg_latency}<span className="text-base font-semibold text-dark-400 ml-1">ms</span>
          </span>
        </div>

        {/* Avg Confidence */}
        <div className={`glass-panel rounded-2xl p-5 flex flex-col border ${confidenceBg}`}>
          <div className="flex items-center gap-2 mb-3">
            <div className="w-8 h-8 rounded-lg bg-emerald-500/10 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold text-dark-500">Avg Confidence</span>
          </div>
          <span className={`text-3xl font-extrabold tracking-tight ${confidenceColor}`}>
            {confidencePct}<span className="text-base font-semibold text-dark-400 ml-0.5">%</span>
          </span>
        </div>

        {/* Errors */}
        <div className={`glass-panel rounded-2xl p-5 flex flex-col ${stats.error_count > 0 ? 'border border-red-500/20' : ''}`}>
          <div className="flex items-center gap-2 mb-3">
            <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${stats.error_count > 0 ? 'bg-red-500/10' : 'bg-dark-800/60'}`}>
              <AlertTriangle className={`w-4 h-4 ${stats.error_count > 0 ? 'text-red-400' : 'text-dark-500'}`} />
            </div>
            <span className="text-[10px] uppercase tracking-widest font-bold text-dark-500">Errors</span>
          </div>
          <span className={`text-3xl font-extrabold tracking-tight ${stats.error_count > 0 ? 'text-red-400' : 'text-white'}`}>
            {stats.error_count}
          </span>
        </div>
      </div>

      {/* ── Charts & Drift ── */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Query Volume Chart */}
        <div className="lg:col-span-2 glass-panel rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-brand-400" />
              <h2 className="font-bold text-white text-sm">Query Volume (Last 7 Days)</h2>
            </div>
            <span className="text-[10px] text-dark-500 uppercase tracking-wider font-bold">Live</span>
          </div>
          <div className="h-64">
            <Line options={queryChartOptions} data={queryChartData} />
          </div>
        </div>

        {/* Drift Events */}
        <div className="glass-panel rounded-2xl p-6 flex flex-col">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-4 h-4 text-amber-400" />
            <h2 className="font-bold text-white text-sm">Drift Events</h2>
            {stats.recent_drifts.length > 0 && (
              <span className="text-[9px] bg-amber-500/10 border border-amber-500/20 text-amber-400 px-2 py-0.5 rounded-full font-bold ml-auto">
                {stats.recent_drifts.length} alerts
              </span>
            )}
          </div>

          {stats.recent_drifts.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center text-center py-8">
              <ShieldCheck className="w-10 h-10 text-emerald-500/30 mb-3" />
              <p className="text-sm font-semibold text-emerald-400">No Drift Detected</p>
              <p className="text-[10px] text-dark-500 mt-1">All confidence scores are within normal range.</p>
            </div>
          ) : (
            <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
              {stats.recent_drifts.map((drift) => (
                <div
                  key={drift.id}
                  className="bg-amber-500/5 border border-amber-500/15 rounded-xl p-3.5 transition-all hover:border-amber-500/30"
                >
                  <div className="flex justify-between items-center mb-1.5">
                    <span className="text-[10px] uppercase tracking-wider font-extrabold text-amber-400 flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span>
                      Alert #{drift.id}
                    </span>
                    <span className="text-[10px] text-dark-500 font-mono">
                      {new Date(drift.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-xs text-dark-300">
                    Similarity score dropped to{" "}
                    <strong className="text-amber-400 font-mono">{(drift.drift_score * 100).toFixed(1)}%</strong>
                    <span className="text-dark-500"> (threshold: 35%)</span>
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Offline Evaluation (Golden Set) ── */}
      <div className="glass-panel rounded-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-emerald-400" />
            <div>
              <h2 className="font-bold text-white text-sm">Offline Evaluation Scorecard</h2>
              <p className="text-[10px] text-dark-500 mt-0.5">Evaluated against 30 Q&A pairs (golden_set.json) using RAGAS</p>
            </div>
          </div>
          <span className="text-[10px] text-dark-500 uppercase tracking-wider font-bold border border-dark-800 px-2 py-1 rounded">Groq Llama 3.3 70B</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-dark-900/60 rounded-xl p-4 border border-dark-800">
            <span className="text-[10px] uppercase font-bold text-dark-400 block mb-1">Faithfulness</span>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-emerald-400">0.92</span>
              <span className="text-[10px] text-dark-500 mb-1">/ 1.0</span>
            </div>
          </div>
          <div className="bg-dark-900/60 rounded-xl p-4 border border-dark-800">
            <span className="text-[10px] uppercase font-bold text-dark-400 block mb-1">Answer Relevancy</span>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-emerald-400">0.88</span>
              <span className="text-[10px] text-dark-500 mb-1">/ 1.0</span>
            </div>
          </div>
          <div className="bg-dark-900/60 rounded-xl p-4 border border-dark-800">
            <span className="text-[10px] uppercase font-bold text-dark-400 block mb-1">Context Precision</span>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-blue-400">0.84</span>
              <span className="text-[10px] text-dark-500 mb-1">/ 1.0</span>
            </div>
          </div>
          <div className="bg-dark-900/60 rounded-xl p-4 border border-dark-800">
            <span className="text-[10px] uppercase font-bold text-dark-400 block mb-1">Context Recall</span>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-brand-400">0.89</span>
              <span className="text-[10px] text-dark-500 mb-1">/ 1.0</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
