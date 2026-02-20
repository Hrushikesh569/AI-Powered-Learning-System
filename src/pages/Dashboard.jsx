import { useState } from 'react';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import Modal from '../components/Modal';
import AchievementCard from '../components/AchievementCard';
import MotivationTips from '../components/MotivationTips';
import { scheduleData, weeklyProgress, aiSuggestions, motivationalQuotes, achievements } from '../data/mockData';
import { CheckCircle, Clock, AlertCircle, TrendingUp, Calendar, Sparkles, Trophy } from 'lucide-react';

const Dashboard = () => {
    const [showRescheduleModal, setShowRescheduleModal] = useState(false);
    const [tasks, setTasks] = useState(scheduleData);
    const randomQuote = motivationalQuotes[Math.floor(Math.random() * motivationalQuotes.length)];

    const markComplete = (id) => {
        setTasks(tasks.map((task) => (task.id === id ? { ...task, status: 'completed' } : task)));
    };

    const getStatusBadge = (status) => {
        const badges = {
            completed: 'badge-completed',
            pending: 'badge-pending',
            missed: 'badge-missed',
        };
        return badges[status] || 'badge-pending';
    };

    const getStatusIcon = (status) => {
        const icons = {
            completed: <CheckCircle className="w-4 h-4" />,
            pending: <Clock className="w-4 h-4" />,
            missed: <AlertCircle className="w-4 h-4" />,
        };
        return icons[status] || <Clock className="w-4 h-4" />;
    };

    return (
        <DashboardLayout>
            <div className="space-y-6">
                {/* Header */}
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Dashboard</h1>
                    <p className="text-gray-600 mt-1">Track your learning progress</p>
                </motion.div>

                {/* Main Grid */}
                <div className="grid lg:grid-cols-3 gap-6">
                    {/* Today's Schedule */}
                    <div className="lg:col-span-2 space-y-4">
                        <div className="card">
                            <div className="flex items-center justify-between mb-6">
                                <h2 className="text-xl font-bold text-gray-800">Today's Schedule</h2>
                                <Calendar className="w-6 h-6 text-primary-600" />
                            </div>
                            <div className="space-y-3">
                                {tasks.map((task, index) => (
                                    <motion.div
                                        key={task.id}
                                        initial={{ opacity: 0, x: -20 }}
                                        animate={{ opacity: 1, x: 0 }}
                                        transition={{ delay: index * 0.1 }}
                                        className="flex items-center justify-between p-4 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                                    >
                                        <div className="flex items-center space-x-4">
                                            <div className="text-center">
                                                <p className="text-sm font-semibold text-gray-800">{task.time}</p>
                                            </div>
                                            <div>
                                                <h3 className="font-semibold text-gray-800">{task.subject}</h3>
                                                <p className="text-sm text-gray-600">{task.topic}</p>
                                                <p className="text-xs text-gray-500">{task.duration}</p>
                                            </div>
                                        </div>
                                        <div className="flex items-center space-x-3">
                                            <span className={`${getStatusBadge(task.status)} flex items-center space-x-1`}>
                                                {getStatusIcon(task.status)}
                                                <span className="capitalize">{task.status}</span>
                                            </span>
                                            {task.status === 'pending' && (
                                                <button
                                                    onClick={() => markComplete(task.id)}
                                                    className="px-3 py-1 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 transition-colors"
                                                >
                                                    Complete
                                                </button>
                                            )}
                                        </div>
                                    </motion.div>
                                ))}
                            </div>
                        </div>

                        {/* AI Suggestions */}
                        <div className="card">
                            <div className="flex items-center space-x-2 mb-4">
                                <Sparkles className="w-6 h-6 text-primary-600" />
                                <h2 className="text-xl font-bold text-gray-800">AI Suggestions</h2>
                            </div>
                            <div className="space-y-3">
                                {aiSuggestions.map((suggestion) => (
                                    <div
                                        key={suggestion.id}
                                        className="flex items-center justify-between p-4 bg-gradient-to-r from-primary-50 to-blue-50 rounded-lg"
                                    >
                                        <p className="text-sm text-gray-700">{suggestion.message}</p>
                                        <button
                                            onClick={() => suggestion.id === 1 && setShowRescheduleModal(true)}
                                            className="px-3 py-1 bg-white text-primary-600 text-sm rounded-lg hover:bg-primary-50 transition-colors whitespace-nowrap ml-4"
                                        >
                                            {suggestion.action}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>

                    {/* Right Sidebar */}
                    <div className="space-y-4">
                        {/* Weekly Progress */}
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="card"
                        >
                            <h2 className="text-xl font-bold text-gray-800 mb-4">Weekly Progress</h2>
                            <div className="flex items-center justify-center mb-4">
                                <div className="relative w-32 h-32">
                                    <svg className="transform -rotate-90 w-32 h-32">
                                        <circle
                                            cx="64"
                                            cy="64"
                                            r="56"
                                            stroke="#e5e7eb"
                                            strokeWidth="8"
                                            fill="transparent"
                                        />
                                        <circle
                                            cx="64"
                                            cy="64"
                                            r="56"
                                            stroke="#22c55e"
                                            strokeWidth="8"
                                            fill="transparent"
                                            strokeDasharray={`${2 * Math.PI * 56}`}
                                            strokeDashoffset={`${2 * Math.PI * 56 * (1 - weeklyProgress.percentage / 100)}`}
                                            className="transition-all duration-1000"
                                        />
                                    </svg>
                                    <div className="absolute inset-0 flex items-center justify-center">
                                        <span className="text-2xl font-bold text-gray-800">
                                            {weeklyProgress.percentage}%
                                        </span>
                                    </div>
                                </div>
                            </div>
                            <div className="space-y-2">
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Completed</span>
                                    <span className="font-semibold">{weeklyProgress.completedHours}h</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Total Goal</span>
                                    <span className="font-semibold">{weeklyProgress.totalHours}h</span>
                                </div>
                                <div className="flex justify-between text-sm">
                                    <span className="text-gray-600">Study Streak</span>
                                    <span className="font-semibold text-primary-600">
                                        {weeklyProgress.streak} days 🔥
                                    </span>
                                </div>
                            </div>
                        </motion.div>

                        {/* Motivation Card */}
                        <motion.div
                            initial={{ opacity: 0, scale: 0.95 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ delay: 0.2 }}
                            className="card bg-gradient-to-br from-primary-500 to-blue-600 text-white"
                        >
                            <div className="flex items-start space-x-3">
                                <TrendingUp className="w-6 h-6 flex-shrink-0 mt-1" />
                                <div>
                                    <h3 className="font-semibold mb-2">Daily Motivation</h3>
                                    <p className="text-sm italic">"{randomQuote}"</p>
                                </div>
                            </div>
                        </motion.div>
                    </div>
                </div>

                {/* Achievements Section */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.3 }}
                >
                    <div className="card">
                        <div className="flex items-center space-x-2 mb-6">
                            <Trophy className="w-6 h-6 text-yellow-600" />
                            <h2 className="text-xl font-bold text-gray-800">Achievements</h2>
                        </div>
                        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
                            {achievements.map((achievement) => (
                                <AchievementCard key={achievement.id} achievement={achievement} />
                            ))}
                        </div>
                    </div>
                </motion.div>

                {/* Motivation Tips */}
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.4 }}
                >
                    <MotivationTips />
                </motion.div>
            </div>

            {/* Reschedule Modal */}
            <Modal
                isOpen={showRescheduleModal}
                onClose={() => setShowRescheduleModal(false)}
                title="Adaptive Rescheduling"
            >
                <div className="space-y-4">
                    <p className="text-gray-700">You missed 2 sessions today. Let AI reschedule?</p>
                    <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
                        <p className="text-sm text-yellow-800">
                            <strong>Missed:</strong> English (6:00 PM), Chemistry (1:00 PM)
                        </p>
                    </div>
                    <div className="flex space-x-3">
                        <button
                            onClick={() => {
                                setShowRescheduleModal(false);
                                alert('AI has optimized your schedule!');
                            }}
                            className="btn-primary flex-1"
                        >
                            Auto Adjust
                        </button>
                        <button className="btn-secondary flex-1">Manual Adjust</button>
                    </div>
                </div>
            </Modal>
        </DashboardLayout>
    );
};

export default Dashboard;
