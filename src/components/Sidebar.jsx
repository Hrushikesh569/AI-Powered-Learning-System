import { Link, useLocation } from 'react-router-dom';
import { Home, BarChart3, Users, Bell, User, LogOut } from 'lucide-react';

const Sidebar = () => {
    const location = useLocation();

    const menuItems = [
        { path: '/dashboard', icon: Home, label: 'Dashboard' },
        { path: '/analytics', icon: BarChart3, label: 'Analytics' },
        { path: '/community', icon: Users, label: 'Community' },
        { path: '/profile', icon: User, label: 'Profile' },
    ];

    const isActive = (path) => location.pathname === path;

    return (
        <div className="fixed left-0 top-0 h-screen w-64 bg-white shadow-lg z-50">
            <div className="p-6 border-b">
                <h1 className="text-2xl font-bold text-primary-600">AI Scheduler</h1>
                <p className="text-sm text-gray-500 mt-1">Your Study Mentor</p>
            </div>

            <nav className="p-4 space-y-2">
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

            <div className="absolute bottom-0 w-full p-4 border-t">
                <Link
                    to="/"
                    className="flex items-center space-x-3 px-4 py-3 text-red-600 hover:bg-red-50 rounded-lg transition-all duration-200"
                >
                    <LogOut className="w-5 h-5" />
                    <span>Logout</span>
                </Link>
            </div>
        </div>
    );
};

export default Sidebar;
