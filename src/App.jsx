import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { getAuthToken } from './api'
import LandingPage from './pages/LandingPage'
import Login from './pages/Login'
import Register from './pages/Register'
import Profiling from './pages/Profiling'
import Dashboard from './pages/Dashboard'
import Analytics from './pages/Analytics'
import Community from './pages/Community'
import Profile from './pages/Profile'
import SyllabusManager from './pages/SyllabusManager'

function PrivateRoute({ children }) {
    return getAuthToken() ? children : <Navigate to="/login" replace />
}

function App() {
    return (
        <Router future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
            <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/login" element={<Login />} />
                <Route path="/register" element={<Register />} />
                <Route path="/profiling" element={<PrivateRoute><Profiling /></PrivateRoute>} />
                <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
                <Route path="/analytics" element={<PrivateRoute><Analytics /></PrivateRoute>} />
                <Route path="/community" element={<PrivateRoute><Community /></PrivateRoute>} />
                <Route path="/profile" element={<PrivateRoute><Profile /></PrivateRoute>} />
                <Route path="/syllabus" element={<PrivateRoute><SyllabusManager /></PrivateRoute>} />
            </Routes>
        </Router>
    )
}

export default App
