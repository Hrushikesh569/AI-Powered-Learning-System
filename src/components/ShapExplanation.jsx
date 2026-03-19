import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Sparkles, TrendingUp, TrendingDown, RefreshCw, ChevronDown, ChevronUp, Brain } from 'lucide-react';
import { agentAPI, getAuthToken } from '../api';

const AGENT_CONFIG = {
    progress: {
        title: 'Learning Progress Factors',
        description: 'Discover which study habits and patterns the AI weighs most when predicting your next learning outcome.',
    },
    profile: {
        title: 'Learner Profile Factors',
        description: 'See which personal attributes (attendance, participation, study hours) shape your overall learner profile score.',
    },
};

const FEATURE_FRIENDLY = {
    difficulty:               'Question Difficulty',
    u_cum_acc:                'Cumulative Accuracy',
    u_roll5:                  'Recent 5-Question Avg',
    u_total:                  'Total Questions Attempted',
    attempt_n:                'Attempt Number',
    q_cum_acc:                'Question Avg Accuracy',
    irt_score:                'IRT Score',
    prev_correct:             'Previous Answer Correct',
    weekly_self_study_hours:  'Weekly Self-Study Hours',
    attendance_percentage:    'Attendance %',
    class_participation:      'Class Participation',
    total_score:              'Total Score',
};

function ImpactBar({ impact, max }) {
    const pct = Math.min(Math.abs(impact) / max, 1) * 100;
    const isPos = impact >= 0;
    return (
        <div className="flex items-center space-x-2 flex-1 min-w-0">
            <div className="relative h-2.5 flex-1 bg-gray-100 rounded-full overflow-hidden">
                <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${pct}%` }}
                    transition={{ duration: 0.6, ease: 'easeOut' }}
                    className={`h-full rounded-full ${isPos ? 'bg-emerald-500' : 'bg-rose-400'}`}
                />
            </div>
            <span className={`text-xs font-mono w-14 text-right shrink-0 ${isPos ? 'text-emerald-600' : 'text-rose-500'}`}>
                {isPos ? '+' : ''}{impact.toFixed(3)}
            </span>
        </div>
    );
}

export default function ShapExplanation({ agent = 'progress' }) {
    const [data, setData]         = useState(null);
    const [loading, setLoading]   = useState(false);
    const [error, setError]       = useState(null);
    const [expanded, setExpanded] = useState(false);
    const [fetched, setFetched]   = useState(false);

    const cfg = AGENT_CONFIG[agent] || AGENT_CONFIG.progress;

    const fetchData = async () => {
        setLoading(true);
        setError(null);
        setFetched(true);
        try {
            const token = getAuthToken();
            const res = agent === 'progress'
                ? await agentAPI.getProgressExplanation(token)
                : await agentAPI.getProfileExplanation(token);
            setData(res);
            setExpanded(false);
        } catch {
            setError('Could not compute explanation. Keep using the app and try again later.');
        } finally {
            setLoading(false);
        }
    };

    const shown = data?.contributions ?? [];
    const maxImpact = shown.reduce((m, c) => Math.max(m, Math.abs(c.impact)), 0.001);
    const visible = expanded ? shown : shown.slice(0, 4);

    return (
        <div className="bg-white rounded-2xl border border-gray-100 shadow-sm overflow-hidden">
            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-50">
                <div className="flex items-center space-x-2">
                    <Brain className="w-5 h-5 text-violet-500" />
                    <div>
                        <p className="text-sm font-semibold text-gray-800">{cfg.title}</p>
                        <p className="text-xs text-gray-400">AI feature importance (SHAP)</p>
                    </div>
                </div>
                {fetched && (
                    <button
                        onClick={fetchData}
                        disabled={loading}
                        className="p-1.5 rounded-lg hover:bg-gray-100 transition disabled:opacity-40"
                        title="Refresh"
                    >
                        <RefreshCw className={`w-4 h-4 text-gray-400 ${loading ? 'animate-spin' : ''}`} />
                    </button>
                )}
            </div>

            {/* Body */}
            <div className="px-5 py-4 space-y-3">
                {/* Idle state — not yet fetched */}
                {!fetched && (
                    <div className="flex flex-col items-center text-center space-y-3 py-4">
                        <p className="text-xs text-gray-500 leading-relaxed max-w-xs">{cfg.description}</p>
                        <button
                            onClick={fetchData}
                            className="flex items-center space-x-2 px-4 py-2 bg-violet-50 hover:bg-violet-100 text-violet-700 text-xs font-semibold rounded-xl transition"
                        >
                            <Sparkles className="w-4 h-4" />
                            <span>Analyze My Factors</span>
                        </button>
                    </div>
                )}

                {/* Loading skeleton */}
                {loading && (
                    <div className="space-y-2">
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="h-5 bg-gray-100 rounded animate-pulse" />
                        ))}
                    </div>
                )}

                {/* Error */}
                {error && (
                    <div className="flex flex-col items-center space-y-2 py-2">
                        <p className="text-xs text-rose-500 text-center">{error}</p>
                        <button
                            onClick={fetchData}
                            className="text-xs text-violet-500 hover:underline"
                        >
                            Try again
                        </button>
                    </div>
                )}

                {/* Results */}
                {!loading && data && (
                    <>
                        <p className="text-xs text-gray-500 bg-violet-50 rounded-xl px-3 py-2 leading-relaxed">
                            {data.summary}
                        </p>
                        <div className="space-y-2.5 mt-2">
                            {visible.map((c) => (
                                <div key={c.feature} className="flex items-center space-x-3">
                                    <div className="flex items-center space-x-1 w-5 shrink-0">
                                        {c.direction === 'positive'
                                            ? <TrendingUp className="w-3.5 h-3.5 text-emerald-500" />
                                            : <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                                        }
                                    </div>
                                    <span className="text-xs text-gray-600 w-40 shrink-0 truncate" title={c.feature}>
                                        {FEATURE_FRIENDLY[c.feature] || c.feature}
                                    </span>
                                    <ImpactBar impact={c.impact} max={maxImpact} />
                                </div>
                            ))}
                        </div>
                        {shown.length > 4 && (
                            <button
                                onClick={() => setExpanded(e => !e)}
                                className="flex items-center space-x-1 text-xs text-violet-500 hover:text-violet-700 mt-1"
                            >
                                {expanded
                                    ? <><ChevronUp className="w-3.5 h-3.5" /><span>Show less</span></>
                                    : <><ChevronDown className="w-3.5 h-3.5" /><span>Show {shown.length - 4} more</span></>
                                }
                            </button>
                        )}
                        <p className="text-[10px] text-gray-300 mt-1">Model: {data.model_used}</p>
                    </>
                )}
            </div>
        </div>
    );
}
