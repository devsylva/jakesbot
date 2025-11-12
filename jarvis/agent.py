import json
import os
import logging
from typing import Any, Dict, List, Optional
import openai
from django.conf import settings
from django.utils import timezone

from jarvis.models import AgentMemory
from jarvis.tools.calendar_tool import CalendarTool
from jarvis.tools.reminder_tool import ReminderTool
from jarvis.tools.workout_diet_tool import WorkoutDietTool

logger = logging.getLogger(__name__)

openai.api_key = settings.OPENAI_API_KEY


SYSTEM_PROMPT = """
    You are Jarvis — Jackson's personal AI assistant.
    Jackson is a busy software engineer and creator who uses you to manage his schedules, reminders,
    workouts, diet plans, and conversations. You always know that the user you are talking to is Jackson — no one else.

    Core traits:
    - Loyal, warm, concise, and proactive.
    - Always reason based on Jackson's actual calendar, reminders, workout plans, and diet data before suggesting anything.
    - If Jackson has no free time, event, workout, or meal planned, simply say so; never invent suggestions.
    - Use natural conversation style — you can chat casually, but keep replies purposeful.
    - Always remember context from previous conversations unless explicitly told to forget.
    - Do not ask who the user is; it's always Jackson.
    - When unsure, clarify briefly and logically.
    - For fitness queries, check Jackson's actual workout and diet plans from Google Sheets.
    - Help Jackson stay consistent with his fitness goals by tracking and updating his progress.
    - When presenting workout or diet data, use natural, conversational language instead of raw data dumps.
    
    IMPORTANT: When creating reminders or calendar events, ALWAYS use the timezone provided in the context.
    If the user says "in 20 minutes" or gives a relative time, calculate it based on the current time and timezone shown.
    Always include timezone information in ISO datetime strings (e.g., "2025-11-12T10:48:00+01:00" for Africa/Lagos timezone).
"""

MAX_MEMORY_MESSAGES = 100  # limit short-term memory to last N messages


class JarvisAgent:
    """Personalized, memory-persistent Jarvis agent for Jackson."""

    def __init__(self, user):
        self.user = user
        self.user_id = user.id
        self.model = "gpt-4o-mini"

        self.calendar = CalendarTool(user_id=self.user_id)
        self.reminder = ReminderTool(user_id=self.user_id)
        self.workout_diet = WorkoutDietTool(user_id=self.user_id)

        self.tools = {
            # Calendar tools
            "create_calendar_event": self.calendar.create_calendar_event,
            "list_calendar_events": self.calendar.list_calendar_events,
            "update_calendar_event": self.calendar.update_calendar_event,
            "delete_calendar_event": self.calendar.delete_calendar_event,
            # Reminder tools
            "create_reminder": self.reminder.create_reminder,
            "list_reminders": self.reminder.list_reminders,
            "update_reminder": self.reminder.update_reminder,
            # Workout & Diet tools
            "get_workout_summary": self.workout_diet.get_workout_summary,
            "get_diet_summary": self.workout_diet.get_diet_summary,
            "add_workout_naturally": self.workout_diet.add_workout_naturally,
            "add_meal_naturally": self.workout_diet.add_meal_naturally,
            "set_rest_day": self.workout_diet.set_rest_day,
            "update_workout": self.workout_diet.update_workout,
            "add_meal": self.workout_diet.add_meal,
        }

        # Load or create memory
        self.memory, _ = AgentMemory.objects.get_or_create(user=user)

    def _get_function_schemas(self):
        schemas = []
        for tool in [self.calendar, self.reminder, self.workout_diet]:
            for attr in dir(tool):
                if attr.startswith("json_schema_"):
                    schema = getattr(tool, attr)()
                    if isinstance(schema, dict) and "name" in schema:
                        # Wrap in the new OpenAI tools format
                        tool_def = {
                            "type": "function",
                            "function": schema
                        }
                        schemas.append(tool_def)
        return schemas

    def _save_to_memory(self, role: str, content: str):
        history = self.memory.conversation_history
        history.append({"role": role, "content": content})
        if len(history) > MAX_MEMORY_MESSAGES:
            history = history[-MAX_MEMORY_MESSAGES:]
        self.memory.conversation_history = history
        self.memory.save(update_fields=["conversation_history", "updated_at"])

    def _load_memory_context(self) -> List[Dict[str, Any]]:
        return self.memory.conversation_history or []

    def _inject_realtime_context(self) -> str:
        """Pulls real calendar, reminders, workout & diet data and formats it as context text."""
        logger.info(f"AI Agent gathering context for user {self.user_id}")
        
        events = self.calendar.list_calendar_events()
        reminders = self.reminder.list_reminders()
        
        # Get fitness context in natural language
        try:
            today_workout = self.workout_diet.get_today_workout()
            today_diet = self.workout_diet.get_today_diet()
            
            # Format workout naturally
            workout_text = self._format_workout_naturally(today_workout)
            diet_text = self._format_diet_naturally(today_diet)
            
        except Exception as e:
            logger.warning(f"Failed to get workout/diet data: {e}")
            workout_text = "Workout data is currently unavailable."
            diet_text = "Diet data is currently unavailable."

        logger.info(f"AI Agent context data for user {self.user_id}:")
        logger.info(f"  - Events response: {type(events)} - {str(events)[:200]}{'...' if len(str(events)) > 200 else ''}")
        logger.info(f"  - Reminders response: {type(reminders)} - {str(reminders)[:200]}{'...' if len(str(reminders)) > 200 else ''}")

        context = f"Today is {timezone.now().strftime('%A, %B %d, %Y at %H:%M %Z')} (timezone: {timezone.get_current_timezone()})\n"
        context += f"\nCalendar Events:\n{events}\n"
        context += f"\nReminders:\n{reminders}\n"
        context += f"\nToday's Workout:\n{workout_text}\n"
        context += f"\nToday's Diet Plan:\n{diet_text}\n"

        logger.info(f"AI Agent final context for user {self.user_id}: {len(context)} chars")
        logger.debug(f"AI Agent context content for user {self.user_id}: {context}")
        return context

    def _format_workout_naturally(self, workout_data: Dict[str, Any]) -> str:
        """Convert workout data to natural language"""
        if not workout_data or workout_data.get('Exercises') in ['Rest', 'No entry found']:
            return f"Jackson has a rest day planned for {workout_data.get('Day', 'today')}."
        
        day = workout_data.get('Day', 'today')
        exercises = workout_data.get('Exercises', 'No exercises planned')
        sets = workout_data.get('Sets', '')
        notes = workout_data.get('Notes', '')
        
        text = f"For {day}, Jackson's workout is: {exercises}"
        if sets:
            text += f" ({sets})"
        if notes:
            text += f". Notes: {notes}"
        
        return text

    def _format_diet_naturally(self, diet_data: Dict[str, Any]) -> str:
        """Convert diet data to natural language"""
        if not diet_data or not diet_data.get('Meals'):
            return f"No meals are planned for {diet_data.get('Day', 'today')}."
        
        day = diet_data.get('Day', 'today')
        meals = diet_data.get('Meals', [])
        
        if not meals:
            return f"No meals are planned for {day}."
        
        text = f"For {day}, Jackson's meals include: "
        meal_descriptions = []
        
        for meal in meals:
            meal_time = meal.get('Meal Time', 'Unknown time')
            meal_name = meal.get('Meal Name', 'Unknown meal')
            calories = meal.get('Calories', '')
            food_items = meal.get('Food Items', '')
            
            description = f"{meal_time}: {meal_name}"
            if food_items:
                description += f" ({food_items})"
            if calories:
                description += f" - {calories} calories"
                
            meal_descriptions.append(description)
        
        return text + "; ".join(meal_descriptions)

    def chat(self, message: str) -> str:
        """Main entrypoint — memory-based chat."""
        logger.info(f"AI Agent received message from user {self.user_id}: '{message}'")
        
        user_context = self._inject_realtime_context()
        short_term = self._load_memory_context()

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "system", "content": f"Current real-world data:\n{user_context}"},
        ] + short_term + [{"role": "user", "content": message}]

        logger.info(f"AI Agent decision context for user {self.user_id}:")
        logger.info(f"  - Available tools: {list(self.tools.keys())}")
        logger.info(f"  - User context length: {len(user_context)} chars")
        logger.info(f"  - Short-term memory: {len(short_term)} messages")

        response = openai.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=self._get_function_schemas(),
            tool_choice="auto",
            temperature=0.4,
        )

        msg = response.choices[0].message
        logger.info(f"AI Agent response type for user {self.user_id}: tool_calls={hasattr(msg, 'tool_calls') and bool(msg.tool_calls)}")

        # Function call?
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            logger.info(f"AI Agent DECISION: Chose to use {len(msg.tool_calls)} tool(s) for user {self.user_id}")
            outputs = []
            for i, tool_call in enumerate(msg.tool_calls):
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                fn = self.tools.get(fn_name)

                logger.info(f"  Tool #{i+1}: {fn_name} with args: {args}")

                if not fn:
                    logger.error(f"AI Agent ERROR: Tool '{fn_name}' not found for user {self.user_id}")
                    outputs.append(f"Sorry Jackson, I can't find the function `{fn_name}`.")
                else:
                    logger.info(f"AI Agent EXECUTING: {fn_name} for user {self.user_id}")
                    result = fn(**args)
                    logger.info(f"AI Agent RESULT: {fn_name} completed for user {self.user_id}")
                    outputs.append(result)
            
            # If tools were called, return the results
            if outputs:
                logger.info(f"AI Agent DECISION OUTCOME: Returned {len(outputs)} tool result(s) for user {self.user_id}")
                return outputs
        else:
            logger.info(f"AI Agent DECISION: Chose to respond with chat message (no tools) for user {self.user_id}")
        
        # Otherwise, return the chat message
        reply = msg.content or ""

        # Save memory
        self._save_to_memory("user", message)
        self._save_to_memory("assistant", reply)

        logger.info(f"AI Agent FINAL RESPONSE for user {self.user_id}: '{reply[:100]}{'...' if len(reply) > 100 else ''}'")
        return reply
