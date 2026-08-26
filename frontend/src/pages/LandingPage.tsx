import React, { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import {
    Database, Sparkles, Upload, Search, BarChart2, Video,
    ShieldCheck, Zap, Brain, GitBranch, FileText, Film,
    ChevronRight, ArrowRight, Star, Lock, RefreshCw,
    MessageSquare, AlertTriangle, CheckCircle
} from 'lucide-react';

// ── Animated counter hook ──────────────────────────────────────────────────
function useCounter(target: number, duration = 1800, start = false) {
    const [value, setValue] = useState(0);
    useEffect(() => {
        if (!start) return;
        let frame: number;
        const startTime = performance.now();
        const tick = (now: number) => {
            const progress = Math.min((now - startTime) / duration, 1);
            const ease = 1 - Math.pow(1 - progress, 3);
            setValue(Math.round(ease * target));
            if (progress < 1) frame = requestAnimationFrame(tick);
        };
        frame = requestAnimationFrame(tick);
        return () => cancelAnimationFrame(frame);
    }, [start, target, duration]);
    return value;
}

// ── Intersection observer hook ─────────────────────────────────────────────
function useInView(threshold = 0.2) {
    const ref = useRef<HTMLDivElement>(null);
    const [inView, setInView] = useState(false);
    useEffect(() => {
        const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setInView(true); }, { threshold });
        if (ref.current) obs.observe(ref.current);
        return () => obs.disconnect();
    }, [threshold]);
    return { ref, inView };
}

// ── Stats section ──────────────────────────────────────────────────────────
const StatCard: React.FC<{ value: number; suffix: string; label: string; start: boolean }> = ({ value, suffix, label, start }) => {
    const count = useCounter(value, 1600, start);
    return (
        <div className="text-center">
            <div className="text-4xl md:text-5xl font-extrabold tracking-tight text-white">
                {count.toLocaleString()}<span className="text-brand-400">{suffix}</span>
            </div>
            <div className="text-sm text-dark-400 mt-1 font-medium">{label}</div>
        </div>
    );
};

// ── Feature card ───────────────────────────────────────────────────────────
interface FeatureCardProps {
    icon: React.ReactNode;
    title: string;
    description: string;
    badge?: string;
    delay?: number;
}
const FeatureCard: React.FC<FeatureCardProps> = ({ icon, title, description, badge, delay = 0 }) => (
    <div
        className="glass-panel glass-panel-hover rounded-2xl p-6 flex flex-col gap-4"
        style={{ animationDelay: `${delay}ms` }}
    >
        <div className="w-11 h-11 rounded-xl bg-brand-500/10 border border-brand-500/20 flex items-center justify-center text-brand-400 flex-shrink-0">
            {icon}
        </div>
        <div>
            <div className="flex items-center gap-2 mb-1.5">
                <h3 className="font-bold text-white text-sm">{title}</h3>
                {badge && (
                    <span className="text-[9px] uppercase tracking-wider font-extrabold px-2 py-0.5 rounded-full bg-brand-500/15 border border-brand-500/30 text-brand-400">
                        {badge}
                    </span>
                )}
            </div>
            <p className="text-dark-400 text-xs leading-relaxed">{description}</p>
        </div>
    </div>
);

// ── Pipeline step ──────────────────────────────────────────────────────────
const PipelineStep: React.FC<{ step: number; label: string; sublabel: string; color: string; icon: React.ReactNode }> = ({ step, label, sublabel, color, icon }) => (
    <div className="flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
            {icon}
        </div>
        <div className="min-w-0">
            <div className="text-[10px] text-dark-500 uppercase tracking-widest font-bold">Step {step}</div>
            <div className="text-sm font-bold text-white leading-tight">{label}</div>
            <div className="text-[11px] text-dark-400 leading-tight mt-0.5">{sublabel}</div>
        </div>
    </div>
);

// ── Main landing page ──────────────────────────────────────────────────────
export const LandingPage: React.FC = () => {
    const { ref: statsRef, inView: statsInView } = useInView(0.3);
    const { ref: featuresRef, inView: featuresInView } = useInView(0.1);

    return (
        <div className="min-h-screen bg-dark-950 text-dark-50 overflow-x-hidden">

            {/* ── Ambient background glows ── */}
            <div className="fixed inset-0 pointer-events-none overflow-hidden">
                <div className="absolute -top-40 -left-40 w-[700px] h-[700px] rounded-full bg-brand-600/5 blur-[120px]" />
                <div className="absolute top-1/2 -right-60 w-[600px] h-[600px] rounded-full bg-brand-500/4 blur-[100px]" />
                <div className="absolute bottom-0 left-1/3 w-[500px] h-[400px] rounded-full bg-brand-700/4 blur-[120px]" />
            </div>

            {/* ── Navigation ── */}
            <nav className="relative z-50 border-b border-dark-800/50 backdrop-blur-xl bg-dark-950/80 sticky top-0">
                <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center shadow-lg shadow-brand-500/20">
                            <Database className="w-5 h-5 text-white" />
                        </div>
                        <div>
                            <span className="text-xl font-bold tracking-tight bg-gradient-to-r from-white via-dark-100 to-brand-400 bg-clip-text text-transparent">
                                Arishem
                            </span>
                            <span className="text-xs block text-dark-400 font-medium -mt-1">RAG AI Platform</span>
                        </div>
                    </div>

                    <div className="hidden md:flex items-center gap-6 text-sm font-medium text-dark-400">
                        <a href="#features" className="hover:text-white transition-colors">Features</a>
                        <a href="#pipeline" className="hover:text-white transition-colors">How it works</a>
                        <a href="#stats" className="hover:text-white transition-colors">Performance</a>
                    </div>

                    <div className="flex items-center gap-3">
                        <Link to="/login" className="text-sm font-medium text-dark-300 hover:text-white transition-colors px-4 py-2">
                            Sign in
                        </Link>
                        <Link
                            to="/register"
                            className="flex items-center gap-2 text-sm font-semibold bg-brand-600 hover:bg-brand-500 text-white px-5 py-2.5 rounded-xl transition-all shadow-md shadow-brand-600/30 hover:shadow-brand-500/40"
                        >
                            Get started <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </div>
            </nav>

            {/* ── Hero ── */}
            <section className="relative z-10 max-w-7xl mx-auto px-6 pt-24 pb-20 text-center">

                {/* Badge */}
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-brand-500/10 border border-brand-500/20 text-brand-300 text-xs font-semibold mb-8 animate-fade-in">
                    <Sparkles className="w-3.5 h-3.5" />
                    Powered by Groq Llama 3.3 70B · Qdrant · Whisper
                </div>

                {/* Headline */}
                <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight leading-[1.05] mb-6 animate-slide-up">
                    <span className="text-white">Your documents.</span>
                    <br />
                    <span className="bg-gradient-to-r from-brand-400 via-brand-300 to-violet-400 bg-clip-text text-transparent">
                        Answered instantly.
                    </span>
                </h1>

                <p className="text-lg md:text-xl text-dark-400 max-w-2xl mx-auto leading-relaxed mb-10 animate-slide-up" style={{ animationDelay: '80ms' }}>
                    Arishem is an enterprise-grade Retrieval-Augmented Generation platform. Upload PDFs, DOCX, videos, and audio — then ask anything. Get cited, confidence-scored answers in seconds.
                </p>

                {/* CTAs */}
                <div className="flex items-center justify-center gap-4 flex-wrap animate-slide-up" style={{ animationDelay: '160ms' }}>
                    <Link
                        to="/register"
                        className="flex items-center gap-2.5 px-8 py-4 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-2xl transition-all shadow-xl shadow-brand-600/30 hover:shadow-brand-500/40 hover:scale-[1.02] text-base"
                    >
                        <Sparkles className="w-5 h-5" />
                        Start for free
                    </Link>
                    <Link
                        to="/login"
                        className="flex items-center gap-2.5 px-8 py-4 glass-panel hover:border-brand-500/30 text-dark-200 hover:text-white font-semibold rounded-2xl transition-all text-base"
                    >
                        Sign in <ChevronRight className="w-4 h-4" />
                    </Link>
                </div>

                {/* Trust indicators */}
                <div className="flex items-center justify-center gap-6 mt-12 text-xs text-dark-500 flex-wrap animate-fade-in" style={{ animationDelay: '300ms' }}>
                    {[
                        { icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />, text: 'JWT-secured API' },
                        { icon: <Lock className="w-3.5 h-3.5 text-blue-400" />, text: 'Role-based access control' },
                        { icon: <Zap className="w-3.5 h-3.5 text-amber-400" />, text: 'Sub-3s query latency' },
                        { icon: <Star className="w-3.5 h-3.5 text-brand-400" />, text: '0.92 faithfulness score' },
                    ].map(({ icon, text }) => (
                        <div key={text} className="flex items-center gap-1.5 font-medium">
                            {icon}
                            <span>{text}</span>
                        </div>
                    ))}
                </div>
            </section>

            {/* ── Mock UI preview ── */}
            <section className="relative z-10 max-w-6xl mx-auto px-6 pb-24">
                <div className="relative rounded-3xl overflow-hidden border border-dark-700/60 shadow-2xl shadow-brand-500/10">
                    {/* Fake browser chrome */}
                    <div className="bg-dark-900/90 backdrop-blur border-b border-dark-800 px-4 py-3 flex items-center gap-3">
                        <div className="flex gap-1.5">
                            <div className="w-3 h-3 rounded-full bg-red-500/70" />
                            <div className="w-3 h-3 rounded-full bg-amber-500/70" />
                            <div className="w-3 h-3 rounded-full bg-emerald-500/70" />
                        </div>
                        <div className="flex-1 bg-dark-800/60 rounded-lg px-3 py-1 text-[11px] text-dark-500 max-w-xs mx-auto text-center">
                            arishem.app/dashboard
                        </div>
                    </div>

                    {/* Fake chat interface */}
                    <div className="bg-dark-950/95 p-6 grid grid-cols-1 md:grid-cols-12 gap-4 min-h-[340px]">
                        {/* Chat area */}
                        <div className="md:col-span-7 space-y-4">
                            {/* User message */}
                            <div className="flex justify-end">
                                <div className="bg-gradient-to-tr from-brand-700 to-brand-500 text-white text-xs px-4 py-2.5 rounded-2xl rounded-br-none max-w-xs shadow-md">
                                    What is the data retention policy for customer records?
                                </div>
                            </div>
                            {/* AI response */}
                            <div className="flex flex-col gap-1 max-w-sm">
                                <div className="glass-panel rounded-2xl rounded-bl-none px-4 py-3 text-xs text-dark-100 leading-relaxed shadow-md">
                                    According to Section 4.2 of the Data Governance SOP, customer records must be retained for a minimum of <span className="text-brand-300 font-semibold">7 years</span> from the date of last transaction. After this period, data must be securely deleted per ISO 27001 guidelines.
                                    <div className="mt-3 pt-2.5 border-t border-dark-800/60">
                                        <span className="text-[9px] text-brand-400 uppercase font-bold tracking-wider">1 citation</span>
                                        <div className="mt-1.5 bg-dark-900/60 rounded-lg px-2.5 py-1.5 border border-dark-800">
                                            <span className="text-[10px] text-brand-300">📄 Data_Governance_SOP_v2.pdf</span>
                                            <p className="text-[10px] text-dark-400 mt-0.5 italic">"...retained for a minimum of 7 years from last transaction date..."</p>
                                        </div>
                                    </div>
                                </div>
                                <div className="flex items-center gap-2 mt-1 px-1">
                                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">LLM: 94%</span>
                                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold">Retrieval: 88%</span>
                                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-bold flex items-center gap-1">
                                        <ShieldCheck className="w-2.5 h-2.5" /> PASS
                                    </span>
                                    <span className="text-[9px] px-2 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20 font-bold flex items-center gap-1">
                                        <GitBranch className="w-2.5 h-2.5" /> Agentic
                                    </span>
                                </div>
                            </div>
                        </div>

                        {/* File sidebar */}
                        <div className="md:col-span-5 space-y-2">
                            <div className="text-[10px] text-dark-500 uppercase tracking-widest font-bold mb-2">Ingested Files (3)</div>
                            {[
                                { name: 'Data_Governance_SOP_v2.pdf', type: 'pdf', status: 'SUCCESS', chunks: 42 },
                                { name: 'Q3_Compliance_Report.docx', type: 'docx', status: 'SUCCESS', chunks: 28 },
                                { name: 'Team_Meeting_Oct.mp4', type: 'mp4', status: 'PROCESSING', chunks: 0 },
                            ].map((f) => (
                                <div key={f.name} className="glass-panel rounded-xl px-3 py-2.5 flex items-center justify-between gap-2">
                                    <div className="flex items-center gap-2 truncate">
                                        {f.type === 'mp4' ? <Film className="w-3.5 h-3.5 text-purple-400 flex-shrink-0" /> : <FileText className="w-3.5 h-3.5 text-brand-400 flex-shrink-0" />}
                                        <span className="text-[11px] text-dark-200 truncate font-medium">{f.name}</span>
                                    </div>
                                    <span className={`text-[9px] uppercase font-extrabold tracking-wide px-2 py-0.5 rounded-full flex-shrink-0 ${f.status === 'SUCCESS' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-blue-500/10 text-blue-400 animate-pulse'
                                        }`}>{f.status === 'PROCESSING' ? '⟳ Processing' : `✓ ${f.chunks} chunks`}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Stats ── */}
            <section id="stats" ref={statsRef} className="relative z-10 py-20 border-y border-dark-800/50">
                <div className="max-w-5xl mx-auto px-6">
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-8 md:gap-12">
                        <StatCard value={92} suffix="%" label="Faithfulness Score (RAGAS)" start={statsInView} />
                        <StatCard value={88} suffix="%" label="Answer Relevancy" start={statsInView} />
                        <StatCard value={3} suffix="s" label="Avg. Query Latency" start={statsInView} />
                        <StatCard value={12} suffix="+" label="File Formats Supported" start={statsInView} />
                    </div>
                </div>
            </section>

            {/* ── Features ── */}
            <section id="features" ref={featuresRef} className="relative z-10 py-24 max-w-7xl mx-auto px-6">
                <div className="text-center mb-14">
                    <div className="text-[10px] uppercase tracking-widest font-bold text-brand-400 mb-3">Everything you need</div>
                    <h2 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight">
                        Enterprise RAG. Out of the box.
                    </h2>
                    <p className="text-dark-400 mt-3 max-w-xl mx-auto text-sm">
                        A full AI knowledge management stack — from ingestion to citation-backed answers — built for teams.
                    </p>
                </div>

                <div className={`grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5 transition-all duration-700 ${featuresInView ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
                    <FeatureCard
                        icon={<Brain className="w-5 h-5" />}
                        title="Agentic RAG Pipeline"
                        description="Query decomposition, multi-step retrieval, self-critique, and conservative retry. Goes beyond simple vector search."
                        badge="Core"
                        delay={0}
                    />
                    <FeatureCard
                        icon={<MessageSquare className="w-5 h-5" />}
                        title="Citation-backed Answers"
                        description="Every response includes source citations and snippets. See exactly which document passage backed each claim."
                        delay={60}
                    />
                    <FeatureCard
                        icon={<ShieldCheck className="w-5 h-5" />}
                        title="Self-Critique & Fact Check"
                        description="Built-in LLM self-critique loop evaluates faithfulness and flags unsupported claims with PASS / PARTIAL / FAIL verdicts."
                        badge="Unique"
                        delay={120}
                    />
                    <FeatureCard
                        icon={<Upload className="w-5 h-5" />}
                        title="Multi-format Ingestion"
                        description="PDF, DOCX, PPTX, MP4, MOV, MP3, WAV, FLAC and more. Audio/video transcribed locally with Whisper."
                        delay={180}
                    />
                    <FeatureCard
                        icon={<Video className="w-5 h-5" />}
                        title="Meeting Intelligence"
                        description="Ingest YouTube videos or recordings. Automatically generate summaries, action items, decisions, and open questions."
                        delay={240}
                    />
                    <FeatureCard
                        icon={<BarChart2 className="w-5 h-5" />}
                        title="AI Observability"
                        description="Real-time confidence monitoring, latency tracking, and drift detection. Alerts sent when retrieval quality degrades."
                        delay={300}
                    />
                    <FeatureCard
                        icon={<Lock className="w-5 h-5" />}
                        title="Role-based Access Control"
                        description="Viewer, Editor, and Admin roles. Per-role rate limiting and workspace isolation. Secure JWT authentication."
                        delay={360}
                    />
                    <FeatureCard
                        icon={<RefreshCw className="w-5 h-5" />}
                        title="Async Ingestion with Polling"
                        description="Files are queued via Celery for background processing. Status tracking from PENDING → PROCESSING → SUCCESS."
                        delay={420}
                    />
                    <FeatureCard
                        icon={<Zap className="w-5 h-5" />}
                        title="Multi-workspace Isolation"
                        description="Full multi-tenant support. Each workspace has its own knowledge base, files, and query history."
                        delay={480}
                    />
                </div>
            </section>

            {/* ── Pipeline visualization ── */}
            <section id="pipeline" className="relative z-10 py-24 border-t border-dark-800/40">
                <div className="max-w-6xl mx-auto px-6">
                    <div className="text-center mb-14">
                        <div className="text-[10px] uppercase tracking-widest font-bold text-brand-400 mb-3">Under the hood</div>
                        <h2 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight">
                            From upload to answer in seconds
                        </h2>
                    </div>

                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">

                        {/* Ingestion pipeline */}
                        <div className="glass-panel rounded-3xl p-8 space-y-6">
                            <div className="flex items-center gap-2 mb-2">
                                <Upload className="w-4 h-4 text-brand-400" />
                                <h3 className="font-bold text-white text-sm uppercase tracking-wide">Ingestion Pipeline</h3>
                            </div>
                            <div className="space-y-5">
                                <PipelineStep step={1} label="Upload" sublabel="S3 direct upload or S3 key reference" color="bg-brand-500/10 text-brand-400" icon={<Upload className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={2} label="Extract & Chunk" sublabel="PyMuPDF, python-docx, python-pptx, Whisper" color="bg-blue-500/10 text-blue-400" icon={<FileText className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={3} label="Embed" sublabel="OpenAI / Bedrock embeddings → Qdrant vectors" color="bg-violet-500/10 text-violet-400" icon={<Brain className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={4} label="Index & Confirm" sublabel="DB record updated: SUCCESS + chunk count" color="bg-emerald-500/10 text-emerald-400" icon={<CheckCircle className="w-4 h-4" />} />
                            </div>
                        </div>

                        {/* Query pipeline */}
                        <div className="glass-panel rounded-3xl p-8 space-y-6">
                            <div className="flex items-center gap-2 mb-2">
                                <Search className="w-4 h-4 text-brand-400" />
                                <h3 className="font-bold text-white text-sm uppercase tracking-wide">Query Pipeline</h3>
                            </div>
                            <div className="space-y-5">
                                <PipelineStep step={1} label="Decompose" sublabel="Complex queries split into focused sub-questions" color="bg-violet-500/10 text-violet-400" icon={<GitBranch className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={2} label="Retrieve" sublabel="Qdrant semantic search across workspace chunks" color="bg-blue-500/10 text-blue-400" icon={<Search className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={3} label="Synthesise" sublabel="Groq Llama 3.3 70B generates grounded answer" color="bg-brand-500/10 text-brand-400" icon={<Brain className="w-4 h-4" />} />
                                <div className="ml-5 h-4 w-px bg-dark-700" />
                                <PipelineStep step={4} label="Self-Critique" sublabel="Fact-check loop → PASS / PARTIAL / FAIL verdict" color="bg-emerald-500/10 text-emerald-400" icon={<ShieldCheck className="w-4 h-4" />} />
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Role comparison ── */}
            <section className="relative z-10 py-24 max-w-5xl mx-auto px-6">
                <div className="text-center mb-12">
                    <div className="text-[10px] uppercase tracking-widest font-bold text-brand-400 mb-3">Access levels</div>
                    <h2 className="text-3xl font-extrabold text-white tracking-tight">Right permissions. Right people.</h2>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
                    {[
                        {
                            role: 'Viewer',
                            color: 'text-emerald-400',
                            bg: 'border-emerald-500/20 bg-emerald-500/5',
                            rate: '10 req/min',
                            features: ['Chat & query documents', 'View own uploaded files', 'Meeting analysis access'],
                        },
                        {
                            role: 'Editor',
                            color: 'text-blue-400',
                            bg: 'border-blue-500/20 bg-blue-500/5',
                            rate: '60 req/min',
                            features: ['All Viewer features', 'Upload & manage files', 'Monitoring dashboard', 'YouTube meeting ingest'],
                            highlight: true,
                        },
                        {
                            role: 'Admin',
                            color: 'text-red-400',
                            bg: 'border-red-500/20 bg-red-500/5',
                            rate: '100 req/min',
                            features: ['All Editor features', 'Workspace management', 'Django admin panel', 'Drift alert recipients'],
                        },
                    ].map(({ role, color, bg, rate, features, highlight }) => (
                        <div key={role} className={`glass-panel rounded-2xl p-6 border ${bg} ${highlight ? 'ring-1 ring-blue-500/30' : ''}`}>
                            <div className={`text-lg font-extrabold ${color} mb-1`}>{role}</div>
                            <div className="text-[10px] text-dark-500 uppercase font-bold tracking-wide mb-4">{rate} limit</div>
                            <ul className="space-y-2.5">
                                {features.map((f) => (
                                    <li key={f} className="flex items-start gap-2 text-xs text-dark-300">
                                        <CheckCircle className="w-3.5 h-3.5 text-emerald-500/70 flex-shrink-0 mt-0.5" />
                                        {f}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    ))}
                </div>
            </section>

            {/* ── Final CTA ── */}
            <section className="relative z-10 py-24 text-center px-6">
                <div className="max-w-2xl mx-auto">
                    <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center mx-auto mb-6 shadow-xl shadow-brand-500/30">
                        <Sparkles className="w-8 h-8 text-white" />
                    </div>
                    <h2 className="text-4xl md:text-5xl font-extrabold text-white tracking-tight mb-4">
                        Ready to ask your documents anything?
                    </h2>
                    <p className="text-dark-400 text-lg mb-10">
                        Create an account and start querying in under a minute. No credit card required.
                    </p>
                    <div className="flex items-center justify-center gap-4 flex-wrap">
                        <Link
                            to="/register"
                            className="flex items-center gap-2.5 px-10 py-4 bg-brand-600 hover:bg-brand-500 text-white font-bold rounded-2xl transition-all shadow-xl shadow-brand-600/30 hover:shadow-brand-500/40 hover:scale-[1.02] text-base"
                        >
                            <Sparkles className="w-5 h-5" />
                            Get started free
                        </Link>
                        <Link
                            to="/login"
                            className="flex items-center gap-2 text-sm font-semibold text-dark-300 hover:text-white transition-colors"
                        >
                            Already have an account? Sign in <ArrowRight className="w-4 h-4" />
                        </Link>
                    </div>
                </div>
            </section>

            {/* ── Footer ── */}
            <footer className="relative z-10 border-t border-dark-800/50 py-8 px-6">
                <div className="max-w-7xl mx-auto flex items-center justify-between flex-wrap gap-4 text-xs text-dark-600">
                    <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-lg bg-gradient-to-tr from-brand-600 to-brand-400 flex items-center justify-center">
                            <Database className="w-3.5 h-3.5 text-white" />
                        </div>
                        <span className="font-semibold text-dark-400">Arishem RAG Platform</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <AlertTriangle className="w-3 h-3 text-amber-500/60" />
                        <span>Confidence scores are AI-generated estimates. Always verify critical information.</span>
                    </div>
                    <span>Built with Django · React · Qdrant · Groq</span>
                </div>
            </footer>
        </div>
    );
};
