import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion } from 'framer-motion';
import DashboardLayout from '../layouts/DashboardLayout';
import { userProfile } from '../data/mockData';
import { User, Mail, Clock, Target, Award, Calendar, LogOut } from 'lucide-react';

const Profile = () => {
    const navigate = useNavigate();
    const [formData, setFormData] = useState({
        name: userProfile.name,
        email: userProfile.email,
        studyHoursPerDay: userProfile.studyHoursPerDay,
        learningGoal: userProfile.learningGoal,
    });

    const handleSubmit = (e) => {
        e.preventDefault();
        alert('Profile updated successfully!');
    };

    const handleLogout = () => {
        navigate('/');
    };

    return (
        <DashboardLayout>
            <div className="space-y-6">
                <motion.div initial={{ opacity: 0, y: -20 }} animate={{ opacity: 1, y: 0 }}>
                    <h1 className="text-3xl font-bold text-gray-900">Profile</h1>
                    <p className="text-gray-600 mt-1">Manage your account settings</p>
                </motion.div>

                <div className="grid lg:grid-cols-3 gap-6">
                    {/* Profile Summary */}
                    <motion.div
                        initial={{ opacity: 0, x: -20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-1 space-y-4"
                    >
                        <div className="card text-center">
                            <div className="w-24 h-24 bg-gradient-to-br from-primary-500 to-blue-600 rounded-full flex items-center justify-center mx-auto mb-4">
                                <span className="text-3xl font-bold text-white">
                                    {userProfile.name.split(' ').map((n) => n[0]).join('')}
                                </span>
                            </div>
                            <h2 className="text-xl font-bold text-gray-800">{userProfile.name}</h2>
                            <p className="text-gray-600">{userProfile.email}</p>
                            <div className="mt-4 inline-flex items-center space-x-2 px-4 py-2 bg-primary-100 text-primary-800 rounded-full">
                                <Award className="w-4 h-4" />
                                <span className="font-semibold">{userProfile.learnerType}</span>
                            </div>
                        </div>

                        <div className="card">
                            <h3 className="font-semibold text-gray-800 mb-4">Statistics</h3>
                            <div className="space-y-3">
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-600">Member Since</span>
                                    <span className="font-semibold text-gray-800">
                                        {new Date(userProfile.joinedDate).toLocaleDateString()}
                                    </span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-600">Total Hours</span>
                                    <span className="font-semibold text-gray-800">{userProfile.totalStudyHours}h</span>
                                </div>
                                <div className="flex items-center justify-between">
                                    <span className="text-sm text-gray-600">Sessions</span>
                                    <span className="font-semibold text-gray-800">{userProfile.completedSessions}</span>
                                </div>
                            </div>
                        </div>
                    </motion.div>

                    {/* Edit Form */}
                    <motion.div
                        initial={{ opacity: 0, x: 20 }}
                        animate={{ opacity: 1, x: 0 }}
                        className="lg:col-span-2"
                    >
                        <div className="card">
                            <h2 className="text-xl font-bold text-gray-800 mb-6">Edit Profile</h2>
                            <form onSubmit={handleSubmit} className="space-y-6">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Full Name</label>
                                    <div className="relative">
                                        <User className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                                        <input
                                            type="text"
                                            value={formData.name}
                                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                            className="input-field pl-10"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">Email</label>
                                    <div className="relative">
                                        <Mail className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
                                        <input
                                            type="email"
                                            value={formData.email}
                                            onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                                            className="input-field pl-10"
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Study Hours Per Day: {formData.studyHoursPerDay}
                                    </label>
                                    <input
                                        type="range"
                                        min="1"
                                        max="12"
                                        value={formData.studyHoursPerDay}
                                        onChange={(e) =>
                                            setFormData({ ...formData, studyHoursPerDay: e.target.value })
                                        }
                                        className="w-full"
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-2">
                                        Learning Goal
                                    </label>
                                    <div className="relative">
                                        <Target className="absolute left-3 top-3 w-5 h-5 text-gray-400" />
                                        <textarea
                                            value={formData.learningGoal}
                                            onChange={(e) => setFormData({ ...formData, learningGoal: e.target.value })}
                                            className="input-field pl-10 min-h-[100px]"
                                        />
                                    </div>
                                </div>

                                <div className="flex space-x-4">
                                    <button type="submit" className="btn-primary flex-1">
                                        Save Changes
                                    </button>
                                    <button type="button" className="btn-secondary flex-1">
                                        Cancel
                                    </button>
                                </div>
                            </form>
                        </div>

                        <div className="card mt-6 border-2 border-red-200">
                            <h3 className="text-lg font-semibold text-gray-800 mb-4">Danger Zone</h3>
                            <div className="flex items-center justify-between">
                                <div>
                                    <p className="font-medium text-gray-800">Logout from your account</p>
                                    <p className="text-sm text-gray-600">You can sign back in anytime</p>
                                </div>
                                <button
                                    onClick={handleLogout}
                                    className="flex items-center space-x-2 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
                                >
                                    <LogOut className="w-4 h-4" />
                                    <span>Logout</span>
                                </button>
                            </div>
                        </div>
                    </motion.div>
                </div>
            </div>
        </DashboardLayout>
    );
};

export default Profile;
