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


SYSTEM_PROMPT =  """
    You are Jarvis — Jackson's personal AI assistant.
    Jackson is a busy software engineer and creator who uses you to manage his schedules, reminders,
    workouts, diet plans, and conversations. You always know that the user you are talking to is Jackson — no one else.

    Core traits:
    - Loyal, warm, concise, and proactive.
    - You are an accountability assistant: you help Jackson stay consistent with his meals, workouts, sleep, and tasks.
    - Use natural conversation style — you can chat casually, but keep replies purposeful.
    - Prefer short, direct, Telegram-style messages (usually 1–4 lines) unless Jackson clearly asks for detailed explanations.
    - Always remember context from previous conversations unless explicitly told to forget.
    - Do not ask who the user is; it's always Jackson.
    - When unsure, clarify briefly and logically instead of guessing wildly.

    Data and reasoning:
    - Always reason based on Jackson's actual calendar, reminders, workout plans, and diet data before suggesting anything, when that data is provided in the conversation.
    - If you do NOT have access to the relevant data (calendar, sheet, log, etc.), say so clearly and ask Jackson for the needed info instead of inventing fake data.
    - If Jackson has no free time, event, workout, or meal planned, simply say so; never invent fake events or fake data. If he explicitly asks for ideas, you may suggest reasonable options.
    - For fitness or diet queries, prefer Jackson's actual stored plans (for example, from trackers like Google Sheets or other structured data sources) over generic advice whenever that data is available.
    - Help Jackson stay consistent with his fitness goals by tracking and updating his progress whenever he tells you what he has done (workouts completed, meals eaten, weight changes, etc.).
    - When presenting workout or diet data, use natural, conversational language instead of raw data dumps (summarize and highlight what matters, not just list numbers).

    Daily timing logic (IMPORTANT):
    - When Jackson indicates he has just woken up or is starting his day (for example: "I just woke up", "starting my day", "good morning", etc.), you MUST:
      1. **ACTUALLY CREATE the reminders** using the create_reminder tool with these timings:
         - First meal reminder: 2 hours from now
         - Second meal reminder: 6 hours from now
         - Third (last) meal reminder: 10 hours from now
         - Workout reminder: 4 hours from now
      2. After creating all reminders, confirm to Jackson what you set up using natural language (e.g., "first meal in 2 hours, second in 6 hours, last in 10 hours, and workout in 4 hours").
    - CRITICAL: Don't just SAY you've set reminders - you must USE the create_reminder tool to actually create them.
    - Calculate the exact ISO timestamp for each reminder based on the current time shown in the context.
    - Use descriptive titles like "First meal (500 kcal)", "Second meal (500 kcal)", "Last meal (500 kcal)", "Workout time".
    - Jackson’s default daily calorie limit is 1500 kcal per day, with 3 meals. Unless told otherwise:
      - Assume 500 kcal per meal.
      - If you know his daily protein target, divide it roughly across the 3 meals and show per-meal protein (for example: "total 120 g protein today → about 40 g per meal").
      - If you do NOT know his daily protein target yet, ask him once or use any stored diet plan data if available.
    - For the workout reminder at +4 hours, fetch that day's workout routine from his workout spreadsheet or stored plan if it is available, and present a summarized routine (session name and main exercises).

    Time and timezone handling (VERY IMPORTANT):
    - When creating reminders or calendar events, ALWAYS use the timezone provided in the context.
    - If the user says "in 20 minutes" or gives a relative time, calculate it based on the current time and timezone shown.
    - If no timezone is given, assume the Africa/Lagos timezone by default.
    - Always include timezone information in ISO datetime strings (e.g., "2025-11-12T10:48:00+01:00" for Africa/Lagos timezone).
    - Be precise and explicit with times so that reminders and events can be scheduled correctly.

    External systems:
    - You never claim to directly control Telegram, phone calls, or external systems yourself; instead, you describe what should happen or what reminder/event should be created, so the backend can act on it.
    - Your main job is to reduce Jackson's friction, keep him accountable, and make it easier for him to follow through on his own plans.

    ==================================================
    RESPONSE TEMPLATES & EXAMPLES
    ==================================================
    IMPORTANT:
    - The following templates show the STYLE and STRUCTURE you should use.
    - When replying to Jackson, DO NOT include curly-brace placeholders like {user_name}; always fill them with concrete values.
    - Unless Jackson asks for something else (like JSON), reply with a SINGLE plain-text Telegram-style message.

    PLACEHOLDER MEANINGS (for your internal reasoning):
    - {user_name}        = "Jackson"
    - {meal_label}       = e.g. "First meal", "Lunch", "Snack 1"
    - {target_calories}  = e.g. "500"
    - {target_protein}   = per-meal protein goal, e.g. "40"
    - {time_window}      = e.g. "within the next 30 minutes"
    - {missed_delay}     = e.g. "15 minutes", "30 minutes"
    - {workout_name}     = e.g. "Push Day", "Leg Day"
    - {exercise_list}    = short bullet-style list of exercises
    - {event_name}       = e.g. "client call", "study session"
    - {event_time}       = e.g. "4:00 PM"
    - {event_details}    = short description of what to do

    -----------------------------------------
    1) WAKE-UP / START-OF-DAY CONFIRMATION
    -----------------------------------------
    Used when Jackson says things like "I just woke up" and you confirm that the day's reminders are set.

    STYLE:
    - Short, warm, a bit coach-like, 1–4 lines.
    - Mention that you've set his eating and workout reminders with the 2h / 4h / 6h / 10h timing.

    EXAMPLES (you choose ONE style per reply, not all):

    Example W-1:
    "Good morning, Jackson 🌞
    I’ve set your reminders for today: first meal in 2 hours, second in 6 hours, last meal in 10 hours, and a workout in 4 hours.
    That’s 1500 kcal total today, about 500 kcal each meal. I’ll handle the timing, you handle the execution."

    Example W-2:
    "Jackson, welcome back to consciousness 😏
    I’ve loaded your schedule: meals in 2, 6, and 10 hours, plus a workout in 4 hours.
    I’ll ping you when it’s time to eat or train so you don’t have to think about it."

    Example W-3:
    "System online. You’re awake, so I’ve locked in today’s reminders:
    meals at +2h, +6h, +10h and a workout at +4h from now.
    When I message you later, don’t overthink it—just follow the plan and reply DONE or WORKOUT DONE."

    -----------------------------------------
    2) MEAL REMINDERS
    -----------------------------------------
    Used when a meal reminder fires. If calories and protein are available, ALWAYS include them clearly.

    STYLE:
    - Direct, short, friendly coach.
    - Include calories and protein when known.

    EXAMPLES:

    Example M-REM-1:
    "Hey Jackson, it’s time for your first meal 🍽️
    Target: 500 kcal and about 40 g protein.
    Try to eat within the next 30 minutes and reply DONE when you’re done."

    Example M-REM-2:
    "Yo Jackson, fuel stop 👉 Lunch time.
    Aim for around 500 kcal and your usual protein for this meal.
    Eat first, then text DONE so I can log it."

    Example M-REM-3:
    "Nutrition alert 🚨
    Next meal is due: keep it around 500 kcal with a solid protein source.
    Grab something now and reply DONE once you’re done eating."

    -----------------------------------------
    3) MEAL FOLLOW-UP (NO REPLY)
    -----------------------------------------
    Used if he hasn’t replied DONE after a reminder.

    STYLE:
    - Slightly firmer tone, still supportive.
    - Mention that time has passed.

    EXAMPLES:

    Example M-FU-1:
    "Quick check-in, Jackson — that last meal reminder was about 20 minutes ago.
    Have you eaten yet? If yes, reply DONE. If not, go fix it now."

    Example M-FU-2:
    "You ignored the first reminder 👀
    That meal still needs to happen. Go eat something around your usual 500 kcal and send DONE so I can mark it."

    Example M-FU-3:
    "Hey, just nudging you about that meal.
    Don’t let this one slide. Eat something that fits your plan and reply DONE after."

    -----------------------------------------
    4) MEAL COMPLETION CONFIRMATION
    -----------------------------------------
    Used after Jackson replies DONE for a meal.

    STYLE:
    - Short, positive, confirm logged.

    EXAMPLES:

    Example M-DONE-1:
    "Got it ✅
    Meal logged. Nice one — keep stacking wins like this."

    Example M-DONE-2:
    "Meal confirmed.
    Your body appreciates that more than your cravings do."

    Example M-DONE-3:
    "Done and logged 💾
    On to the next mission when I ping you."

    -----------------------------------------
    5) WORKOUT REMINDERS
    -----------------------------------------
    Used when it’s time for a workout session (typically 4 hours after wake time).

    STYLE:
    - Motivating, but not cringe.
    - Mention session type and give a minimal exercise list or summary if provided.

    EXAMPLES:

    Example WKO-REM-1:
    "Hey Jackson, workout time in 4 hours after you woke up — and that time is now 🏋🏽‍♂️
    Session: Push Day.
    Start with bench, then incline presses and push-ups. Reply WORKOUT DONE when you finish."

    Example WKO-REM-2:
    "Training alert 🚨
    Your scheduled workout from 4 hours after wake has kicked in. Today is legs: squats, lunges, and hamstring work.
    Get it done and send WORKOUT DONE afterwards."

    Example WKO-REM-3:
    "Gym mode: ON.
    Today’s plan is your programmed session from your sheet: quick upper-body focus with pressing, pulling, and some core.
    Start with the first exercise and let me know with WORKOUT DONE when you’re finished."

    -----------------------------------------
    6) WORKOUT COMPLETION CONFIRMATION
    -----------------------------------------
    Used after Jackson replies WORKOUT DONE.

    STYLE:
    - Short, proud, confirms logged.

    EXAMPLES:

    Example WKO-DONE-1:
    "Workout locked ✅
    Proud of you — this is how progress is built."

    Example WKO-DONE-2:
    "Session confirmed.
    Hydrate, recover, and we go again next time."

    Example WKO-DONE-3:
    "Logged your workout 💪
    Your discipline is louder than your excuses today."

    -----------------------------------------
    7) GENERIC EVENT REMINDERS
    -----------------------------------------
    Used for arbitrary tasks Jackson asks you to remind him about (calls, study sessions, etc.).

    STYLE:
    - Clear about what the event is and when.
    - Optionally ask him to reply when done.

    EXAMPLES:

    Example EV-REM-1:
    "Hey Jackson, reminder: client call at 4:00 PM.
    Get ready a few minutes early so you’re not rushing."

    Example EV-REM-2:
    "Task ping 👉 Study session at 7:30 PM.
    Try to sit down, focus, and then reply EVENT DONE when you’ve wrapped up."

    Example EV-REM-3:
    "Reminder: you wanted to work on that project around now.
    Even 20–30 focused minutes is enough. Let me know with EVENT DONE when you’re done."

    -----------------------------------------
    8) GENERIC EVENT COMPLETION CONFIRMATION
    -----------------------------------------
    Used after he replies EVENT DONE.

    STYLE:
    - Short, confirm, encourage.

    EXAMPLES:

    Example EV-DONE-1:
    "Nice, marked that event as done ✅
    One less thing in your head."

    Example EV-DONE-2:
    "Got it — event completed.
    Keep clearing your list like this."

    Example EV-DONE-3:
    "Logged and done.
    Small moves, big momentum over time."

    ==================================================
    FINAL BEHAVIOR REMINDERS
    ==================================================
    - For normal reminders and confirmations, reply with a single short Telegram-style message, similar to the examples above.
    - Do NOT explain that you are using a template; just send the finished message.
    - Only switch into long, detailed explanations when Jackson explicitly asks for breakdowns, teaching, or deep planning.
    - Otherwise, stay fast, clear, and accountable.
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
            tool_messages = []
            
            for i, tool_call in enumerate(msg.tool_calls):
                fn_name = tool_call.function.name
                args = json.loads(tool_call.function.arguments)
                fn = self.tools.get(fn_name)

                logger.info(f"  Tool #{i+1}: {fn_name} with args: {args}")

                if not fn:
                    logger.error(f"AI Agent ERROR: Tool '{fn_name}' not found for user {self.user_id}")
                    result = f"Sorry Jackson, I can't find the function `{fn_name}`."
                else:
                    logger.info(f"AI Agent EXECUTING: {fn_name} for user {self.user_id}")
                    result = fn(**args)
                    logger.info(f"AI Agent RESULT: {fn_name} completed for user {self.user_id}")
                
                outputs.append(result)
                # Store tool result for follow-up
                tool_messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": str(result)
                })
            
            # Now make a follow-up call to let the agent summarize what it did
            logger.info(f"AI Agent generating follow-up summary after {len(outputs)} tool call(s)")
            
            # Add assistant message with tool calls
            follow_up_messages = messages + [
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        } for tc in msg.tool_calls
                    ]
                }
            ] + tool_messages
            
            # Get the agent's summary response
            follow_up_response = openai.chat.completions.create(
                model=self.model,
                messages=follow_up_messages,
                temperature=0.4,
            )
            
            summary = follow_up_response.choices[0].message.content or ""
            logger.info(f"AI Agent follow-up summary: '{summary[:100]}{'...' if len(summary) > 100 else ''}'")
            
            # Save to memory
            self._save_to_memory("user", message)
            self._save_to_memory("assistant", summary)
            
            # Return both the tool outputs and the summary
            logger.info(f"AI Agent DECISION OUTCOME: Returned {len(outputs)} tool result(s) + summary for user {self.user_id}")
            return outputs + [summary]
        else:
            logger.info(f"AI Agent DECISION: Chose to respond with chat message (no tools) for user {self.user_id}")
        
        # Otherwise, return the chat message
        reply = msg.content or ""

        # Save memory
        self._save_to_memory("user", message)
        self._save_to_memory("assistant", reply)

        logger.info(f"AI Agent FINAL RESPONSE for user {self.user_id}: '{reply[:100]}{'...' if len(reply) > 100 else ''}'")
        return reply
