import React, { useEffect, useState } from "react";
import axios from "axios";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";
import { Line } from "react-chartjs-2";
import { useAuthStore } from "../store/authStore";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
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

  useEffect(() => {
    const fetchStats = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await axios.get("http://127.0.0.1:8000/app/ai/monitoring", {
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

    if (accessToken && activeWorkspaceId) {
      fetchStats();
    }
  }, [accessToken, activeWorkspaceId]);

  if (loading) {
    return <div className="p-8 text-center text-gray-500">Loading metrics...</div>;
  }

  if (error) {
    return (
      <div className="p-8 text-center text-red-500">
        <p>Error: {error}</p>
        <p className="text-sm mt-2">Only Admins and Editors can view monitoring stats.</p>
      </div>
    );
  }

  if (!stats) return null;

  const chartOptions = {
    responsive: true,
    plugins: {
      legend: { position: "top" as const },
      title: { display: true, text: "Predictions (Last 7 Days)" },
    },
  };

  const chartData = {
    labels: stats.chart_data.map((d) => d.date),
    datasets: [
      {
        label: "Queries",
        data: stats.chart_data.map((d) => d.count),
        borderColor: "rgb(53, 162, 235)",
        backgroundColor: "rgba(53, 162, 235, 0.5)",
      },
    ],
  };

  return (
    <div className="max-w-6xl mx-auto p-6 mt-8 space-y-6">
      <h1 className="text-3xl font-bold text-gray-800">AI Observability Dashboard</h1>
      <p className="text-gray-500">
        Monitoring metrics for Workspace ID: {activeWorkspaceId}
      </p>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <span className="text-sm text-gray-500 uppercase font-semibold tracking-wider">
            Total Queries
          </span>
          <span className="text-3xl font-bold text-gray-800 mt-2">
            {stats.total_predictions}
          </span>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <span className="text-sm text-gray-500 uppercase font-semibold tracking-wider">
            Avg Latency
          </span>
          <span className="text-3xl font-bold text-indigo-600 mt-2">
            {stats.avg_latency} ms
          </span>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <span className="text-sm text-gray-500 uppercase font-semibold tracking-wider">
            Avg Confidence
          </span>
          <span className="text-3xl font-bold text-emerald-600 mt-2">
            {(stats.avg_confidence * 100).toFixed(1)}%
          </span>
        </div>
        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col items-center">
          <span className="text-sm text-gray-500 uppercase font-semibold tracking-wider">
            Errors
          </span>
          <span className="text-3xl font-bold text-red-500 mt-2">
            {stats.error_count}
          </span>
        </div>
      </div>

      {/* Charts & Drift Logs */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white p-6 rounded-xl shadow-sm border border-gray-100">
          <Line options={chartOptions} data={chartData} />
        </div>

        <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-100 flex flex-col">
          <h2 className="text-xl font-bold text-gray-800 mb-4">Recent Drift Events</h2>
          {stats.recent_drifts.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              No drift detected recently.
            </div>
          ) : (
            <ul className="space-y-4">
              {stats.recent_drifts.map((drift) => (
                <li key={drift.id} className="p-4 bg-orange-50 border border-orange-100 rounded-lg">
                  <div className="flex justify-between items-center mb-2">
                    <span className="font-semibold text-orange-800">Alert #{drift.id}</span>
                    <span className="text-xs text-orange-600">
                      {new Date(drift.timestamp).toLocaleString()}
                    </span>
                  </div>
                  <div className="text-sm text-orange-700">
                    Similarity Score dropped to: <strong>{(drift.drift_score * 100).toFixed(1)}%</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
