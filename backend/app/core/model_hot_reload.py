"""
Model hot-reload utility for agents.
Call reload_all_agents() after retraining to refresh models in memory.
"""
from app.agents.profiling_agent import ProfilingAgent
from app.agents.schedule_agent import ScheduleAgent
from app.agents.progress_agent import ProgressAgent
from app.agents.reschedule_agent import RescheduleAgent
from app.agents.motivation_agent import MotivationAgent
from app.agents.community_agent import CommunityAgent
from app.agents.group_agent import GroupAgent

# Singleton agent instances
profiling_agent = ProfilingAgent()
schedule_agent = ScheduleAgent()
progress_agent = ProgressAgent()
reschedule_agent = RescheduleAgent()
motivation_agent = MotivationAgent()
community_agent = CommunityAgent()
group_agent = GroupAgent()

def reload_all_agents():
    global profiling_agent, schedule_agent, progress_agent, reschedule_agent, motivation_agent, community_agent, group_agent
    profiling_agent = ProfilingAgent()
    schedule_agent = ScheduleAgent()
    progress_agent = ProgressAgent()
    reschedule_agent = RescheduleAgent()
    motivation_agent = MotivationAgent()
    community_agent = CommunityAgent()
    group_agent = GroupAgent()
    print('All agent models hot-reloaded.')
