import { useState } from 'react';
import { Bell } from 'lucide-react';
import { notifications } from '../data/mockData';

const Navbar = () => {
    const [showNotifications, setShowNotifications] = useState(false);
    const unreadCount = notifications.filter((n) => !n.read).length;

    return (
        <div className="fixed top-0 left-64 right-0 h-16 bg-white shadow-sm z-40 flex items-center justify-between px-8">
            <div>
                <h2 className="text-xl font-semibold text-gray-800">Welcome back, Alex!</h2>
                <p className="text-sm text-gray-500">Let's make today productive</p>
            </div>

            <div className="relative">
                <button
                    onClick={() => setShowNotifications(!showNotifications)}
                    className="relative p-2 hover:bg-gray-100 rounded-lg transition-colors"
                >
                    <Bell className="w-6 h-6 text-gray-600" />
                    {unreadCount > 0 && (
                        <span className="absolute top-1 right-1 w-5 h-5 bg-red-500 text-white text-xs rounded-full flex items-center justify-center">
                            {unreadCount}
                        </span>
                    )}
                </button>

                {showNotifications && (
                    <div className="absolute right-0 mt-2 w-80 bg-white rounded-xl shadow-xl border overflow-hidden">
                        <div className="p-4 border-b bg-gray-50">
                            <h3 className="font-semibold text-gray-800">Notifications</h3>
                        </div>
                        <div className="max-h-96 overflow-y-auto">
                            {notifications.map((notification) => (
                                <div
                                    key={notification.id}
                                    className={`p-4 border-b hover:bg-gray-50 transition-colors ${!notification.read ? 'bg-blue-50' : ''
                                        }`}
                                >
                                    <p className="text-sm text-gray-800">{notification.message}</p>
                                    <p className="text-xs text-gray-500 mt-1">{notification.time}</p>
                                </div>
                            ))}
                        </div>
                        <div className="p-3 bg-gray-50 text-center">
                            <button className="text-sm text-primary-600 hover:text-primary-700 font-medium">
                                View All Notifications
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default Navbar;
