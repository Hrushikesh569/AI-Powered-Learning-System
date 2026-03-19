
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { agentAPI, getAuthToken } from '../api';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, Clock, Target } from 'lucide-react';

const Analytics = () => {
    const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];
    const [analyticsData, setAnalyticsData] = useState({ subjectCompletion: [], dailyStudyTime: [], timeDistribution: [], weeklyProgress: {} });
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchAnalytics = async () => {
            setLoading(true);
            setError('');
            try {
                const token = getAuthToken();
                const [dashRes, subjectRes] = await Promise.all([
                    agentAPI.getProgressDashboard(token),
                    agentAPI.listSubjects(token).catch(() => ({ subjects: [] })),
                ]);
                const wp = dashRes.weeklyProgress || {};
                const subjects = subjectRes.subjects || [];

                // Subject completion: tasks completed per subject
                const completedSubjects = JSON.parse(localStorage.getItem('completedSubjects') || '{}');
                const onlineSubjects = new Set();
                subjects.forEach(s => onlineSubjects.add(s.name));
                // Include all uploaded subjects + any completed subjects from the tracker
                const allSubjectNames = new Set([
                    ...subjects.map(s => s.name),
                    ...Object.keys(completedSubjects)
                ]);
                const subjectCompletion = Array.from(allSubjectNames).map((name) => ({
                    subject: name,
                    completed: completedSubjects[name] || 0,
                    uploaded: onlineSubjects.has(name) ? 1 : 0,
                })).sort((a, b) => b.completed - a.completed);

                // Weekly time: single data point from progress logs
                const dailyStudyTime = [
                    { day: 'This Week', hours: wp.completedHours || 0 },
                ];

                // Time distribution: subjects by file count
                const timeDistribution = subjects.map((s) => ({
                    name: s.name,
                    value: s.fileCount || 1,
                }));

                setAnalyticsData({ subjectCompletion, dailyStudyTime, timeDistribution, weeklyProgress: wp });
            } catch (err) {
                setError('Failed to load analytics data.');
            } finally {
                setLoading(false);
            }
        };
        fetchAnalytics();
    }, []);

    const totalTasksCompleted = analyticsData.subjectCompletion.reduce((sum, s) => sum + (s.completed || 0), 0);
    const totalStudyHours = analyticsData.weeklyProgress?.completedHours || 0;
    const streak = analyticsData.weeklyProgress?.streak || 0;

    if (loading) return (
        <DashboardLayout>
            <div className="flex items-center justify-center h-64">
                <div className="flex flex-col items-center space-y-3">
                    <div className="animate-spin w-10 h-10 rounded-full border-4 border-primary-200 border-t-primary-600" />
                    <p className="text-sm text-gray-500">Loading analytics...</p>
                </div>
            </div>
        </DashboardLayout>
    );
    if (error) return (
        <DashboardLayout>
            <div className="flex flex-col items-center justify-center h-64 space-y-3">
                <p className="text-red-500 font-medium">{error}</p>
                <p className="text-sm text-gray-500">Try refreshing the page.</p>
            </div>
        </DashboardLayout>
    );

    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Analytics</h1>
                    <p className="text-gray-600 mt-1">Track your learning performance</p>
                </motion.div>

                {/* Stats Cards */}
                <div className="grid md:grid-cols-3 gap-6">
                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        className="card"
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-600">Tasks Completed</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">{totalTasksCompleted}</p>
                                <p className="text-sm text-gray-500 mt-1">Across all subjects</p>
                            </div>
                            <div className="w-12 h-12 bg-primary-100 rounded-full flex items-center justify-center">
                                <TrendingUp className="w-6 h-6 text-primary-600" />
                            </div>
                        </div>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.1 }}
                        className="card"
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-600">Study Hours (Week)</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">{totalStudyHours} hrs</p>
                                <p className="text-sm text-gray-500 mt-1">Logged this week</p>
                            </div>
                            <div className="w-12 h-12 bg-blue-100 rounded-full flex items-center justify-center">
                                <Clock className="w-6 h-6 text-blue-600" />
                            </div>
                        </div>
                    </motion.div>

                    <motion.div
                        initial={{ opacity: 0, scale: 0.95 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={{ delay: 0.2 }}
                        className="card"
                    >
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-600">Current Streak</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">{streak} days</p>
                                <p className="text-sm text-gray-500 mt-1">Keep it going!</p>
                            </div>
                            <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
                                <Target className="w-6 h-6 text-yellow-600" />
                            </div>
                        </div>
                    </motion.div>
                </div>

                {/* Charts Grid */}
                <div className="grid lg:grid-cols-2 gap-6">
                    {/* Task Completion per Subject */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="card"
                    >
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Tasks Completed per Subject</h2>
                        {analyticsData.subjectCompletion.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-48 text-gray-400 space-y-2">
                                <TrendingUp className="w-10 h-10 opacity-30" />
                                <p className="text-sm">Complete tasks to see your progress here</p>
                            </div>
                        ) : (
                            <ResponsiveContainer width="100%" height={300}>
                                <BarChart data={analyticsData.subjectCompletion}>
                                    <CartesianGrid strokeDasharray="3 3" />
                                    <XAxis dataKey="subject" tick={{ fontSize: 12 }} />
                                    <YAxis />
                                    <Tooltip formatter={(v) => [`${v} tasks`, 'Completed']} />
                                    <Legend />
                                    <Bar dataKey="completed" fill="#22c55e" radius={[8, 8, 0, 0]} name="Completed" />
                                </BarChart>
                            </ResponsiveContainer>
                        )}
                    </motion.div>

                    {/* Daily Study Time */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="card"
                    >
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Daily Study Time</h2>
                        <ResponsiveContainer width="100%" height={300}>
                            <LineChart data={analyticsData.dailyStudyTime}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="day" />
                                <YAxis />
                                <Tooltip />
                                <Line type="monotone" dataKey="hours" stroke="#3b82f6" strokeWidth={3} />
                            </LineChart>
                        </ResponsiveContainer>
                    </motion.div>

                    {/* Time Distribution */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="card lg:col-span-2"
                    >
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Materials by Subject</h2>
                        {analyticsData.timeDistribution.length === 0 ? (
                            <div className="flex flex-col items-center justify-center h-48 text-gray-400 space-y-2">
                                <Target className="w-10 h-10 opacity-30" />
                                <p className="text-sm">No materials uploaded yet</p>
                            </div>
                        ) : (
                            <div className="flex items-center justify-center">
                                <ResponsiveContainer width="100%" height={350}>
                                    <PieChart>
                                        <Pie
                                            data={analyticsData.timeDistribution}
                                            cx="50%"
                                            cy="50%"
                                            labelLine={false}
                                            label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
                                            outerRadius={120}
                                            fill="#8884d8"
                                            dataKey="value"
                                        >
                                            {analyticsData.timeDistribution.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                                            ))}
                                        </Pie>
                                        <Tooltip formatter={(v) => [`${v} file(s)`, 'Files']} />
                                    </PieChart>
                                </ResponsiveContainer>
                            </div>
                        )}
                    </motion.div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Analytics;
