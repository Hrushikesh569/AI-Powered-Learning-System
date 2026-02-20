// Mock data for the application

export const scheduleData = [
    {
        id: 1,
        time: '09:00 AM',
        subject: 'Mathematics',
        topic: 'Calculus - Derivatives',
        duration: '1 hour',
        status: 'completed',
    },
    {
        id: 2,
        time: '10:30 AM',
        subject: 'Physics',
        topic: 'Quantum Mechanics',
        duration: '1.5 hours',
        status: 'completed',
    },
    {
        id: 3,
        time: '01:00 PM',
        subject: 'Chemistry',
        topic: 'Organic Chemistry',
        duration: '1 hour',
        status: 'pending',
    },
    {
        id: 4,
        time: '03:00 PM',
        subject: 'Computer Science',
        topic: 'Data Structures',
        duration: '2 hours',
        status: 'pending',
    },
    {
        id: 5,
        time: '06:00 PM',
        subject: 'English',
        topic: 'Literature Analysis',
        duration: '1 hour',
        status: 'missed',
    },
];

export const weeklyProgress = {
    completedHours: 24,
    totalHours: 35,
    streak: 7,
    percentage: 68,
};

export const aiSuggestions = [
    {
        id: 1,
        type: 'warning',
        message: 'You missed 2 sessions yesterday. Consider rescheduling.',
        action: 'Reschedule',
    },
    {
        id: 2,
        type: 'info',
        message: 'Your performance in Mathematics improved by 15%!',
        action: 'View Details',
    },
    {
        id: 3,
        type: 'suggestion',
        message: 'Try studying Physics in the morning for better retention.',
        action: 'Apply',
    },
];

export const motivationalQuotes = [
    "Success is the sum of small efforts repeated day in and day out.",
    "The expert in anything was once a beginner.",
    "Education is the passport to the future.",
    "Learning never exhausts the mind.",
    "The beautiful thing about learning is that no one can take it away from you.",
];

export const analyticsData = {
    subjectPerformance: [
        { subject: 'Math', score: 85 },
        { subject: 'Physics', score: 78 },
        { subject: 'Chemistry', score: 92 },
        { subject: 'CS', score: 88 },
        { subject: 'English', score: 75 },
    ],
    dailyStudyTime: [
        { day: 'Mon', hours: 4 },
        { day: 'Tue', hours: 5 },
        { day: 'Wed', hours: 3 },
        { day: 'Thu', hours: 6 },
        { day: 'Fri', hours: 4 },
        { day: 'Sat', hours: 7 },
        { day: 'Sun', hours: 5 },
    ],
    timeDistribution: [
        { name: 'Mathematics', value: 25 },
        { name: 'Physics', value: 20 },
        { name: 'Chemistry', value: 18 },
        { name: 'Computer Science', value: 22 },
        { name: 'English', value: 15 },
    ],
};

export const studyGroups = [
    {
        id: 1,
        name: 'Advanced Calculus Study Group',
        members: 12,
        subject: 'Mathematics',
        nextSession: '2026-02-18 10:00 AM',
        description: 'Weekly sessions on advanced calculus topics',
    },
    {
        id: 2,
        name: 'Physics Problem Solvers',
        members: 8,
        subject: 'Physics',
        nextSession: '2026-02-19 02:00 PM',
        description: 'Collaborative problem-solving sessions',
    },
    {
        id: 3,
        name: 'CS Algorithms Masterclass',
        members: 15,
        subject: 'Computer Science',
        nextSession: '2026-02-20 04:00 PM',
        description: 'Deep dive into algorithms and data structures',
    },
];

export const forumPosts = [
    {
        id: 1,
        author: 'Sarah Johnson',
        avatar: 'SJ',
        title: 'Best resources for learning Quantum Mechanics?',
        content: 'Looking for recommendations on textbooks and online courses...',
        upvotes: 24,
        comments: 8,
        timeAgo: '2 hours ago',
    },
    {
        id: 2,
        author: 'Mike Chen',
        avatar: 'MC',
        title: 'Study tips for maintaining focus during long sessions',
        content: 'I struggle with maintaining concentration after 1 hour...',
        upvotes: 18,
        comments: 12,
        timeAgo: '5 hours ago',
    },
    {
        id: 3,
        author: 'Emma Davis',
        avatar: 'ED',
        title: 'Anyone interested in forming a Chemistry study group?',
        content: 'Looking for 4-5 people to study Organic Chemistry together...',
        upvotes: 31,
        comments: 15,
        timeAgo: '1 day ago',
    },
];

export const notifications = [
    {
        id: 1,
        type: 'reminder',
        message: 'Chemistry session starts in 30 minutes',
        time: '30 min ago',
        read: false,
    },
    {
        id: 2,
        type: 'achievement',
        message: 'You completed your weekly goal! 🎉',
        time: '2 hours ago',
        read: false,
    },
    {
        id: 3,
        type: 'group',
        message: 'New message in Advanced Calculus Study Group',
        time: '4 hours ago',
        read: true,
    },
    {
        id: 4,
        type: 'system',
        message: 'Your study schedule has been optimized',
        time: '1 day ago',
        read: true,
    },
];

export const userProfile = {
    name: 'Alex Thompson',
    email: 'alex.thompson@example.com',
    studyHoursPerDay: 5,
    learningGoal: 'Master advanced mathematics and computer science',
    learnerType: 'Fast Learner',
    joinedDate: '2026-01-15',
    totalStudyHours: 156,
    completedSessions: 42,
};

export const achievements = [
    {
        id: 1,
        title: '7-Day Streak',
        description: 'Study for 7 consecutive days',
        icon: '🔥',
        unlocked: true,
        unlockedDate: '2026-02-10',
    },
    {
        id: 2,
        title: 'Early Bird',
        description: 'Complete 10 morning study sessions',
        icon: '🌅',
        unlocked: true,
        unlockedDate: '2026-02-05',
    },
    {
        id: 3,
        title: 'Night Owl',
        description: 'Complete 10 evening study sessions',
        icon: '🦉',
        unlocked: false,
        progress: 6,
        total: 10,
    },
    {
        id: 4,
        title: 'Century Club',
        description: 'Complete 100 hours of study',
        icon: '💯',
        unlocked: true,
        unlockedDate: '2026-02-12',
    },
    {
        id: 5,
        title: 'Perfect Week',
        description: 'Complete all scheduled sessions in a week',
        icon: '⭐',
        unlocked: false,
        progress: 5,
        total: 7,
    },
    {
        id: 6,
        title: 'Social Butterfly',
        description: 'Join 3 study groups',
        icon: '🦋',
        unlocked: false,
        progress: 1,
        total: 3,
    },
];

export const milestones = [
    {
        id: 1,
        title: '50 Hours Studied',
        hours: 50,
        reached: true,
        date: '2026-01-25',
    },
    {
        id: 2,
        title: '100 Hours Studied',
        hours: 100,
        reached: true,
        date: '2026-02-12',
    },
    {
        id: 3,
        title: '150 Hours Studied',
        hours: 150,
        reached: true,
        date: '2026-02-16',
    },
    {
        id: 4,
        title: '200 Hours Studied',
        hours: 200,
        reached: false,
        progress: 156,
    },
];

export const motivationTips = [
    {
        id: 1,
        category: 'Focus',
        tip: 'Use the Pomodoro Technique: 25 minutes of focused study followed by a 5-minute break.',
        icon: '🎯',
    },
    {
        id: 2,
        category: 'Health',
        tip: 'Take regular breaks to stretch and rest your eyes. Your brain needs oxygen!',
        icon: '🧘',
    },
    {
        id: 3,
        category: 'Productivity',
        tip: 'Study the hardest subjects when you have the most energy, usually in the morning.',
        icon: '⚡',
    },
    {
        id: 4,
        category: 'Memory',
        tip: 'Review material before bed. Your brain consolidates memories during sleep.',
        icon: '🧠',
    },
    {
        id: 5,
        category: 'Motivation',
        tip: 'Set small, achievable goals. Celebrate each victory, no matter how small!',
        icon: '🎉',
    },
];

