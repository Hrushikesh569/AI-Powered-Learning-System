# AI Learning Scheduler - Personalized Learning Platform

A modern, production-ready frontend web application built with React (Vite) and Tailwind CSS for personalized learning scheduling powered by AI.

## 🚀 Features

### Core Functionality
- **Intelligent Profiling** - AI analyzes learning style and creates personalized study profiles
- **Smart Scheduling** - Automatically generates optimal study schedules based on goals
- **Adaptive Rescheduling** - Dynamically adjusts schedule when sessions are missed
- **Community Learning** - Connect with study groups and peers for collaborative learning
- **Analytics Dashboard** - Track performance with interactive charts and visualizations
- **Progress Tracking** - Monitor weekly progress, study streaks, and achievements

### Pages
1. **Landing Page** - Hero section, features showcase, and how it works
2. **Authentication** - Login and registration with Google sign-in UI
3. **Profiling** - Comprehensive questionnaire for learner categorization
4. **Dashboard** - Main hub with today's schedule, progress, and AI suggestions
5. **Analytics** - Performance charts (bar, line, pie) with Recharts
6. **Community** - Study groups, discussion forum, and peer matching
7. **Profile** - User settings and account management

## 🛠️ Tech Stack

- **React 18** - Modern React with hooks
- **Vite** - Fast build tool and dev server
- **Tailwind CSS** - Utility-first CSS framework
- **React Router** - Client-side routing
- **Recharts** - Beautiful, composable charts
- **Framer Motion** - Smooth animations and transitions
- **Lucide React** - Modern icon library

## 📦 Installation

1. Navigate to the project directory:
```bash
cd learning-scheduler
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

4. Open your browser and visit:
```
http://localhost:5173
```

## 🏗️ Project Structure

```
learning-scheduler/
├── src/
│   ├── components/         # Reusable components
│   │   ├── Sidebar.jsx
│   │   ├── Navbar.jsx
│   │   └── Modal.jsx
│   ├── layouts/           # Layout components
│   │   └── DashboardLayout.jsx
│   ├── pages/             # Page components
│   │   ├── LandingPage.jsx
│   │   ├── Login.jsx
│   │   ├── Register.jsx
│   │   ├── Profiling.jsx
│   │   ├── Dashboard.jsx
│   │   ├── Analytics.jsx
│   │   ├── Community.jsx
│   │   └── Profile.jsx
│   ├── data/              # Mock data
│   │   └── mockData.js
│   ├── App.jsx            # Main app with routing
│   ├── main.jsx           # Entry point
│   └── index.css          # Global styles
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

## 🎨 Design Features

- **Modern SaaS Dashboard** - Clean, professional interface
- **Gradient Backgrounds** - Beautiful color transitions
- **Smooth Animations** - Framer Motion powered transitions
- **Responsive Design** - Mobile-first approach
- **Custom Components** - Reusable card, button, and input styles
- **Status Badges** - Color-coded (green/yellow/red) for task states
- **Interactive Charts** - Real-time data visualization

## 🔄 Available Scripts

- `npm run dev` - Start development server
- `npm run build` - Build for production
- `npm run preview` - Preview production build

## 📱 Responsive Design

The application is fully responsive and works seamlessly on:
- Desktop (1920px+)
- Laptop (1024px - 1919px)
- Tablet (768px - 1023px)
- Mobile (320px - 767px)

## 🎯 Key Components

### Sidebar Navigation
- Fixed left sidebar with navigation links
- Active route highlighting
- Logout functionality

### Notifications Dropdown
- Bell icon with unread count badge
- Dropdown with notification list
- Different notification types (reminder, achievement, group, system)

### Adaptive Rescheduling Modal
- Triggered when sessions are missed
- Auto-adjust and manual adjust options
- Shows missed sessions

### Analytics Charts
- Bar chart for subject performance
- Line chart for daily study time
- Pie chart for time distribution

## 🔐 Mock Authentication

Currently uses mock authentication. Login/Register forms navigate to dashboard without backend validation. This is intentional for frontend demonstration purposes.

## 📊 Mock Data

All data is currently mocked in `src/data/mockData.js` including:
- Schedule data
- Weekly progress
- AI suggestions
- Analytics data
- Study groups
- Forum posts
- User profile

## 🚧 Future Enhancements

- Backend API integration
- Real authentication system
- Database connectivity
- Real-time notifications
- Video call integration for study groups
- AI-powered recommendations
- Mobile app version

## 📄 License

This project is created for educational and demonstration purposes.

## 👨‍💻 Author

Built with ❤️ for the Personalized Learning Scheduler & Community Platform project.
