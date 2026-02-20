import Sidebar from '../components/Sidebar';
import Navbar from '../components/Navbar';

const DashboardLayout = ({ children }) => {
    return (
        <div className="min-h-screen bg-gray-50">
            <Sidebar />
            <Navbar />
            <main className="ml-64 pt-16">
                <div className="p-8">{children}</div>
            </main>
        </div>
    );
};

export default DashboardLayout;
