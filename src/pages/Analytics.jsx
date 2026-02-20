import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { analyticsData } from '../data/mockData';
import { BarChart, Bar, LineChart, Line, PieChart, Pie, Cell, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { TrendingUp, Clock, Target } from 'lucide-react';

const Analytics = () => {
    const COLORS = ['#22c55e', '#3b82f6', '#f59e0b', '#ef4444', '#8b5cf6'];

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
                                <p className="text-sm text-gray-600">Average Score</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">83.6%</p>
                                <p className="text-sm text-green-600 mt-1">↑ 5.2% from last week</p>
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
                                <p className="text-sm text-gray-600">Total Study Time</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">34 hrs</p>
                                <p className="text-sm text-green-600 mt-1">This week</p>
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
                                <p className="text-sm text-gray-600">Goals Achieved</p>
                                <p className="text-3xl font-bold text-gray-900 mt-1">12/15</p>
                                <p className="text-sm text-green-600 mt-1">80% completion</p>
                            </div>
                            <div className="w-12 h-12 bg-yellow-100 rounded-full flex items-center justify-center">
                                <Target className="w-6 h-6 text-yellow-600" />
                            </div>
                        </div>
                    </motion.div>
                </div>

                {/* Charts Grid */}
                <div className="grid lg:grid-cols-2 gap-6">
                    {/* Subject Performance */}
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="card"
                    >
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Subject Performance</h2>
                        <ResponsiveContainer width="100%" height={300}>
                            <BarChart data={analyticsData.subjectPerformance}>
                                <CartesianGrid strokeDasharray="3 3" />
                                <XAxis dataKey="subject" />
                                <YAxis />
                                <Tooltip />
                                <Bar dataKey="score" fill="#22c55e" radius={[8, 8, 0, 0]} />
                            </BarChart>
                        </ResponsiveContainer>
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
                        <h2 className="text-xl font-bold text-gray-800 mb-4">Time Distribution by Subject</h2>
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
                                    <Tooltip />
                                </PieChart>
                            </ResponsiveContainer>
                        </div>
                    </motion.div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Analytics;
