import { Link, useLocation } from 'react-router-dom';
import { Home, BarChart3, Users, User, LogOut, FileText, MessageCircle } from 'lucide-react';
import StudyChat from './StudyChat';
import { useState } from 'react';

const Sidebar = () => {
    const location = useLocation();
    const [chatOpen, setChatOpen] = useState(false);

    const menuItems = [
        { path: '/dashboard', icon: Home, label: 'Dashboard' },
        { path: '/analytics', icon: BarChart3, label: 'Analytics' },
        { path: '/community', icon: Users, label: 'Community' },
        { path: '/syllabus', icon: FileText, label: 'Syllabus & Files' },
        { path: '/profile', icon: User, label: 'Profile' },
    ];

    const isActive = (path) => location.pathname === path;

    return (
        <div className="fixed left-0 top-0 h-screen w-64 bg-white shadow-lg z-50 flex flex-col">
            <div className="p-6 border-b">
                <h1 className="text-2xl font-bold text-primary-600">AI Scheduler</h1>
                <p className="text-sm text-gray-500 mt-1">Your Study Mentor</p>
            </div>

            <nav className="p-4 space-y-2 flex-1">
                {menuItems.map((item) => (
                    <Link
                        key={item.path}
                        to={item.path}
                        className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200 ${isActive(item.path)
                                ? 'bg-primary-50 text-primary-600 font-medium'
                                : 'text-gray-600 hover:bg-gray-50'
                            }`}
                    >
                        <item.icon className="w-5 h-5" />
                        <span>{item.label}</span>
                    </Link>
                ))}
            </nav>

            <div className="w-full p-4 border-t space-y-2">
                <button
                    onClick={() => setChatOpen(o => !o)}
                    className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                        chatOpen
                            ? 'bg-primary-50 text-primary-600 font-medium'
                            : 'text-gray-600 hover:bg-gray-50'
                    }`}
                >
                    <MessageCircle className="w-5 h-5" />
                    <span>Study Chat</span>
                </button>
                <Link
                    to="/"
                    className="flex items-center space-x-3 px-4 py-3 text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200"
                >
                    <LogOut className="w-5 h-5" />
                    <span>Logout</span>
                </Link>
            </div>

            <StudyChat open={chatOpen} onClose={() => setChatOpen(false)} />
        </div>
    );
};

export default Sidebar;
