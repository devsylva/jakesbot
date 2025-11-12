import logging
import datetime
from typing import List, Dict, Optional, Any
from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import os

logger = logging.getLogger(__name__)


SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    "https://www.googleapis.com/auth/drive.file"
    ]

class WorkoutDietTool:
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
        self.sheet_id = settings.GOOGLE_SHEET_ID
        # Tab names used in this project
        self.workout_tab = "Workout Plan"
        self.diet_tab = "Diet Plan"
        self.service = None

        if not self.sheet_id:
            logger.warning("GOOGLE_SHEET_ID not set in settings. Tool will not access Sheets until configured.")

        self.creds = None
        try:
            # Check if required modules are available"
            from googleapiclient.discovery import build
            from google.oauth2.credentials import Credentials
            self.creds = self._load_credentials()
        except ImportError:
            logger.warning("googleapiclient or google.oauth2 not available. Install 'google-api-python-client' and 'google-auth' to enable Sheets access.")

    # def _load_credentials(self):
    #     token_file = f"token_{self.user_id or 'default'}.json"
    #     token_path = os.path.join(settings.BASE_DIR, "tokens", token_file)

    #     # load existing token if available
    #     if os.path.exists(token_path):
    #         self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    #     # Refresh or request new credentials
    #     if not self.creds or not self.creds.valid:
    #         if self.creds and self.creds.expired and self.creds.refresh_token:
    #             self.creds.refresh(Request())
    #         else:
    #             flow = InstalledAppFlow.from_client_secrets_file(
    #                 os.path.join(settings.BASE_DIR, "credentials.json"), SCOPES
    #             )
    #             self.creds = flow.run_local_server(port=0)

    #         os.makedirs(os.path.dirname(token_path), exist_ok=True)
    #         with open(token_path, "w") as token:
    #             token.write(self.creds.to_json())

    #     # Build the Sheets API service
    #     self.service = build("sheets", "v4", credentials=self.creds)

    def _load_credentials(self):
        token_path = os.path.join(settings.BASE_DIR, f'tokens/token_{self.user_id}.json')
        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                os.path.join(settings.BASE_DIR, "credentials.json"), SCOPES
            )
            self.creds = flow.run_local_server(port=0)
            os.makedirs(os.path.dirname(token_path), exist_ok=True)
            with open(token_path, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("sheets", "v4", credentials=self.creds)

    def _sheets_service(self):
        if not self.service:
            raise RuntimeError("Google Sheets OAuth credentials not configured. Run the authorization flow to create a token file.")

        return self.service

    # ------------------ Helpers ------------------
    def _read_tab(self, tab_name: str) -> List[List[str]]:
        """Return raw values (list of rows) from the given tab."""
        if not self.sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID not configured in settings.")
        service = self._sheets_service()
        range_name = f"'{tab_name}'"
        result = service.spreadsheets().values().get(spreadsheetId=self.sheet_id, range=range_name).execute()
        values = result.get('values', [])
        return values

    def _write_range(self, range_name: str, values: List[List[Any]]):
        if not self.sheet_id:
            raise RuntimeError("GOOGLE_SHEET_ID not configured in settings.")
        service = self._sheets_service()
        body = {"values": values}
        resp = service.spreadsheets().values().update(spreadsheetId=self.sheet_id, range=range_name, valueInputOption="RAW", body=body).execute()
        return resp

    # ------------------ Workout Methods ------------------
    def list_workouts(self) -> List[Dict[str, Any]]:
        """Return the workout sheet as a list of dicts (one dict per day row).
        Assumes first row is header.
        """
        rows = self._read_tab(self.workout_tab)
        if not rows:
            return []
        headers = [h.strip() for h in rows[0]]
        out = []
        for row in rows[1:]:
            item = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            out.append(item)
        return out

    def get_workout(self, day: str) -> Dict[str, Any]:
        """Return the workout for any specified day."""
        # Support both full day names and flexible formats
        target = self._normalize_day(day)
        workouts = self.list_workouts()
        for r in workouts:
            if self._normalize_day(r.get('Day', '')) == target:
                return r
        return {"Day": day, "Exercises": "Rest", "Notes": "No entry found"}
    
    def get_today_workout(self, day: Optional[str] = None) -> Dict[str, Any]:
        """Return the workout for a given day (defaults to today)."""
        target = day or datetime.datetime.now().strftime("%A")
        return self.get_workout(target)

    def update_workout(self, day: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update any workout fields for any day dynamically.
        day: any day (Monday, Tue, tomorrow, etc.)
        updates: dict of field updates e.g., {'Exercises': 'Push day', 'Sets': '3x12', 'Notes': 'Focus on form'}
        Returns the updated row dict.
        """
        target = self._normalize_day(day)
        rows = self._read_tab(self.workout_tab)
        if not rows or len(rows) < 2:
            raise RuntimeError("Workout sheet seems empty or missing headers")
        headers = [h.strip() for h in rows[0]]
        day_col = self._find_column(headers, ['day'])
        
        if day_col is None:
            raise RuntimeError("Workout sheet must have a 'Day' column")

        # Try to find existing row
        for idx, row in enumerate(rows[1:], start=2):
            cell_day = (row[day_col] if day_col < len(row) else '').strip()
            if self._normalize_day(cell_day) == target:
                # Update multiple fields in this row
                for field, value in updates.items():
                    col_idx = self._find_column(headers, [field.lower()])
                    if col_idx is not None:
                        range_a1 = f"'{self.workout_tab}'!{self._a1_notation(idx, col_idx+1)}"
                        self._write_range(range_a1, [[value]])
                
                # Return updated row
                updated = {headers[j]: (row[j] if j < len(row) else '') for j in range(len(headers))}
                updated.update(updates)
                return updated
        
        # If not found, create new row
        new_row = ["" for _ in headers]
        new_row[day_col] = day  # Use original day format
        for field, value in updates.items():
            col_idx = self._find_column(headers, [field.lower()])
            if col_idx is not None:
                new_row[col_idx] = value
        
        append_range = f"'{self.workout_tab}'"
        self._sheets_service().spreadsheets().values().append(
            spreadsheetId=self.sheet_id, 
            range=append_range, 
            valueInputOption='RAW', 
            body={'values': [new_row]}
        ).execute()
        return {headers[i]: new_row[i] for i in range(len(headers))}

    def update_today_workout(self, new_value: str, day: Optional[str] = None) -> Dict[str, Any]:
        """Legacy method for backward compatibility."""
        target = day or datetime.datetime.now().strftime("%A")
        return self.update_workout(target, {'Exercises': new_value})

    def set_rest_day(self, day: str) -> Dict[str, Any]:
        """Set the Exercises for the provided day to 'Rest' and clear sets/reps/notes where applicable."""
        return self.update_workout(day, {'Exercises': 'Rest', 'Notes': 'Rest Day'})
    
    def add_workout_note(self, day: str, note: str) -> Dict[str, Any]:
        """Add a note to a specific day's workout."""
        return self.update_workout(day, {'Notes': note})
    
    def set_workout_focus(self, day: str, focus: str, exercises: str = None) -> Dict[str, Any]:
        """Set workout focus and optionally specific exercises for a day."""
        updates = {'Exercises': focus}
        if exercises:
            updates['Specific Exercises'] = exercises
        return self.update_workout(day, updates)

    # ------------------ Diet Methods ------------------
    def list_diets(self) -> List[Dict[str, Any]]:
        rows = self._read_tab(self.diet_tab)
        if not rows:
            return []
        headers = [h.strip() for h in rows[0]]
        out = []
        for row in rows[1:]:
            item = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
            out.append(item)
        return out

    def get_diet(self, day: str) -> Dict[str, Any]:
        """Return the diet for any specified day."""
        target = self._normalize_day(day)
        diets = self.list_diets()
        # Support multiple meals per day
        entries = [r for r in diets if self._normalize_day(r.get('Day', '')) == target]
        if not entries:
            return {"Day": day, "Meals": [], "Notes": "No diet entry found"}
        
        # Build a compact representation
        meals = []
        for e in entries:
            meal = {k: v for k, v in e.items() if k.lower() not in ('day',)}
            meals.append(meal)
        return {"Day": day, "Meals": meals}
    
    def get_today_diet(self, day: Optional[str] = None) -> Dict[str, Any]:
        """Return the diet for a given day (defaults to today)."""
        target = day or datetime.datetime.now().strftime("%A")
        return self.get_diet(target)

    def update_diet(self, day: str, meal_data: Dict[str, Any], meal_time: Optional[str] = None) -> Dict[str, Any]:
        """Update diet for any day and any meal dynamically.
        day: any day (Monday, tomorrow, etc.)
        meal_data: dict of meal info e.g., {'Meal Name': 'Oatmeal', 'Food Items': 'Oats, Banana', 'Calories': '350'}
        meal_time: specific meal to update (Breakfast, Lunch, Dinner, Snack) - if None, adds new meal
        Returns the updated row dict.
        """
        target = self._normalize_day(day)
        rows = self._read_tab(self.diet_tab)
        if not rows or len(rows) < 2:
            raise RuntimeError("Diet sheet seems empty or missing headers")
        headers = [h.strip() for h in rows[0]]
        
        day_col = self._find_column(headers, ['day'])
        meal_time_col = self._find_column(headers, ['meal time', 'time', 'meal'])
        
        if day_col is None:
            raise RuntimeError("Diet sheet must have a 'Day' column")
        
        # Determine meal time - from parameter or meal_data
        target_meal_time = meal_time or meal_data.get('Meal Time')
        
        # Try to find existing row with same day and meal time
        for idx, row in enumerate(rows[1:], start=2):
            cell_day = (row[day_col] if day_col < len(row) else '').strip()
            cell_meal = (row[meal_time_col] if meal_time_col is not None and meal_time_col < len(row) else '').strip()
            
            day_match = self._normalize_day(cell_day) == target
            meal_match = not target_meal_time or self._normalize_text(cell_meal) == self._normalize_text(target_meal_time)
            
            if day_match and meal_match:
                # Update this row
                update_data = meal_data.copy()
                if target_meal_time and 'Meal Time' not in update_data:
                    update_data['Meal Time'] = target_meal_time
                
                for field, value in update_data.items():
                    col_idx = self._find_column(headers, [field.lower()])
                    if col_idx is not None:
                        range_a1 = f"'{self.diet_tab}'!{self._a1_notation(idx, col_idx+1)}"
                        self._write_range(range_a1, [[value]])
                
                # Return updated row
                merged = {headers[i]: (row[i] if i < len(row) else '') for i in range(len(headers))}
                merged.update(update_data)
                return merged
        
        # If not found, create new row
        new_row = ["" for _ in headers]
        new_row[day_col] = day  # Use original day format
        
        # Add meal data
        update_data = meal_data.copy()
        if target_meal_time and 'Meal Time' not in update_data:
            update_data['Meal Time'] = target_meal_time
            
        for field, value in update_data.items():
            col_idx = self._find_column(headers, [field.lower()])
            if col_idx is not None:
                new_row[col_idx] = value
        
        append_range = f"'{self.diet_tab}'"
        self._sheets_service().spreadsheets().values().append(
            spreadsheetId=self.sheet_id, 
            range=append_range, 
            valueInputOption='RAW', 
            body={'values': [new_row]}
        ).execute()
        return {headers[i]: new_row[i] for i in range(len(headers))}

    def update_today_diet(self, new_value: Dict[str, Any], day: Optional[str] = None) -> Dict[str, Any]:
        """Legacy method for backward compatibility."""
        target = day or datetime.datetime.now().strftime("%A")
        return self.update_diet(target, new_value)
    
    def add_meal(self, day: str, meal_time: str, meal_name: str, food_items: str = None, calories: str = None) -> Dict[str, Any]:
        """Add a specific meal to any day."""
        meal_data = {'Meal Time': meal_time, 'Meal Name': meal_name}
        if food_items:
            meal_data['Food Items'] = food_items
        if calories:
            meal_data['Calories'] = calories
        return self.update_diet(day, meal_data, meal_time)
    
    def update_meal_calories(self, day: str, meal_time: str, calories: str) -> Dict[str, Any]:
        """Update calories for a specific meal on any day."""
        return self.update_diet(day, {'Calories': calories}, meal_time)
    
    def replace_meal(self, day: str, meal_time: str, new_meal_name: str, food_items: str = None) -> Dict[str, Any]:
        """Replace a meal entirely for any day."""
        meal_data = {'Meal Name': new_meal_name}
        if food_items:
            meal_data['Food Items'] = food_items
        return self.update_diet(day, meal_data, meal_time)

    # ------------------ Utilities ------------------
    def _normalize_day(self, day: str) -> str:
        """Normalize day input to handle various formats."""
        if not day:
            return ""
        
        day = day.strip().lower()
        
        # Handle relative days
        today = datetime.datetime.now()
        if day in ['today']:
            return today.strftime("%A").lower()
        elif day in ['tomorrow']:
            return (today + datetime.timedelta(days=1)).strftime("%A").lower()
        elif day in ['yesterday']:
            return (today - datetime.timedelta(days=1)).strftime("%A").lower()
        
        # Handle day abbreviations
        day_mapping = {
            'mon': 'monday', 'tue': 'tuesday', 'wed': 'wednesday', 'thu': 'thursday',
            'fri': 'friday', 'sat': 'saturday', 'sun': 'sunday',
            'tues': 'tuesday', 'thurs': 'thursday'
        }
        
        return day_mapping.get(day, day)
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        return text.strip().lower() if text else ""
    
    def _find_column(self, headers: List[str], possible_names: List[str]) -> Optional[int]:
        """Find column index by checking multiple possible names."""
        for i, header in enumerate(headers):
            if header.lower().strip() in possible_names:
                return i
        return None
    
    def _a1_notation(self, row: int, col: int) -> str:
        """Convert row, col (1-indexed) to A1 notation (simple version)."""
        # col -> letters
        result = ""
        while col > 0:
            col, rem = divmod(col-1, 26)
            result = chr(65 + rem) + result
        return f"{result}{row}"

    # ------------------ Natural Language Wrappers for Telegram Bot ------------------
    def get_workout_summary(self, day: str = None) -> str:
        """Get workout summary in natural language for chatbot responses"""
        try:
            workout = self.get_today_workout(day) if not day else self.get_workout(day)
            day_name = workout.get('Day', day or 'today')
            
            if workout.get('Exercises') in ['Rest', 'No entry found']:
                return f"You have a rest day planned for {day_name}. Perfect time to recover! 💪"
            
            exercises = workout.get('Exercises', 'No exercises planned')
            sets = workout.get('Sets', '')
            notes = workout.get('Notes', '')
            
            response = f"🏋️ Your workout for {day_name}:\n"
            response += f"• Exercises: {exercises}\n"
            
            if sets:
                response += f"• Sets/Reps: {sets}\n"
            if notes:
                response += f"• Notes: {notes}\n"
                
            response += "\nLet's crush it! 💪"
            return response
            
        except Exception as e:
            return f"Sorry, I couldn't retrieve your workout data right now. Error: {str(e)}"

    def get_diet_summary(self, day: str = None) -> str:
        """Get diet summary in natural language for chatbot responses"""
        try:
            diet = self.get_today_diet(day) if not day else self.get_diet(day)
            day_name = diet.get('Day', day or 'today')
            meals = diet.get('Meals', [])
            
            if not meals:
                return f"No meals are planned for {day_name}. Time to plan some healthy options! 🍽️"
            
            response = f"🍽️ Your meal plan for {day_name}:\n\n"
            
            total_calories = 0
            for i, meal in enumerate(meals, 1):
                meal_time = meal.get('Meal Time', 'Unknown')
                meal_name = meal.get('Meal Name', 'Unknown meal')
                food_items = meal.get('Food Items', '')
                calories = meal.get('Calories', '')
                
                response += f"{i}. {meal_time}: {meal_name}\n"
                if food_items:
                    response += f"   Items: {food_items}\n"
                if calories:
                    try:
                        cal_num = int(''.join(filter(str.isdigit, calories)))
                        total_calories += cal_num
                        response += f"   Calories: {calories}\n"
                    except:
                        response += f"   Calories: {calories}\n"
                response += "\n"
            
            if total_calories > 0:
                response += f"📊 Total calories planned: {total_calories}"
            
            return response
            
        except Exception as e:
            return f"Sorry, I couldn't retrieve your diet data right now. Error: {str(e)}"

    def add_workout_naturally(self, day: str, workout_description: str, sets: str = None, notes: str = None) -> str:
        """Add/update workout with natural language response"""
        try:
            updates = {'Exercises': workout_description}
            if sets:
                updates['Sets'] = sets
            if notes:
                updates['Notes'] = notes
                
            result = self.update_workout(day, updates)
            
            return f"✅ Updated your {day} workout!\n🏋️ Exercises: {workout_description}" + \
                   (f"\n📊 Sets: {sets}" if sets else "") + \
                   (f"\n📝 Notes: {notes}" if notes else "")
                   
        except Exception as e:
            return f"Sorry, I couldn't update your workout. Error: {str(e)}"

    def add_meal_naturally(self, day: str, meal_time: str, meal_name: str, food_items: str = None, calories: str = None) -> str:
        """Add meal with natural language response"""
        try:
            result = self.add_meal(day, meal_time, meal_name, food_items, calories)
            
            response = f"✅ Added {meal_time.lower()} to your {day} plan!\n"
            response += f"🍽️ Meal: {meal_name}\n"
            if food_items:
                response += f"📋 Items: {food_items}\n"
            if calories:
                response += f"📊 Calories: {calories}"
                
            return response
            
        except Exception as e:
            return f"Sorry, I couldn't add your meal. Error: {str(e)}"
    
    # ------------------ JSON Schemas for OpenAI Function Calling ------------------
    @staticmethod
    def json_schema_get_workout_summary() -> Dict[str, Any]:
        return {
            "name": "get_workout_summary",
            "description": "Get Jackson's workout plan in natural, conversational language for Telegram chat",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Optional: specific day (Monday, Tuesday, today, tomorrow, etc.). Defaults to today if not specified."
                    }
                }
            }
        }

    @staticmethod
    def json_schema_get_diet_summary() -> Dict[str, Any]:
        return {
            "name": "get_diet_summary",
            "description": "Get Jackson's diet/meal plan in natural, conversational language for Telegram chat",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Optional: specific day (Monday, Tuesday, today, tomorrow, etc.). Defaults to today if not specified."
                    }
                }
            }
        }

    @staticmethod
    def json_schema_add_workout_naturally() -> Dict[str, Any]:
        return {
            "name": "add_workout_naturally",
            "description": "Add or update Jackson's workout with natural language response",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day for the workout (Monday, Tuesday, today, tomorrow, etc.)"
                    },
                    "workout_description": {
                        "type": "string",
                        "description": "Description of the workout/exercises"
                    },
                    "sets": {
                        "type": "string",
                        "description": "Optional: Sets and reps information"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional: Additional notes"
                    }
                },
                "required": ["day", "workout_description"]
            }
        }

    @staticmethod
    def json_schema_update_workout() -> Dict[str, Any]:
        return {
            "name": "update_workout",
            "description": "Update Jackson's workout details for any day",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day to update (Monday, Tuesday, today, tomorrow, etc.)"
                    },
                    "updates": {
                        "type": "object",
                        "description": "Fields to update (e.g., {'Exercises': 'Push day', 'Sets': '3x12', 'Notes': 'Focus on form'})",
                        "additionalProperties": {"type": "string"}
                    }
                },
                "required": ["day", "updates"]
            }
        }

    @staticmethod
    def json_schema_set_rest_day() -> Dict[str, Any]:
        return {
            "name": "set_rest_day",
            "description": "Set a specific day as a rest day for Jackson",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day to set as rest day"
                    }
                },
                "required": ["day"]
            }
        }

    @staticmethod
    def json_schema_add_meal_naturally() -> Dict[str, Any]:
        return {
            "name": "add_meal_naturally",
            "description": "Add a meal to Jackson's diet plan with natural language response",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day to add meal to"
                    },
                    "meal_time": {
                        "type": "string",
                        "description": "Meal time (Breakfast, Lunch, Dinner, Snack)"
                    },
                    "meal_name": {
                        "type": "string",
                        "description": "Name of the meal"
                    },
                    "food_items": {
                        "type": "string",
                        "description": "Food items in the meal"
                    },
                    "calories": {
                        "type": "string",
                        "description": "Calorie count"
                    }
                },
                "required": ["day", "meal_time", "meal_name"]
            }
        }

    @staticmethod
    def json_schema_add_meal() -> Dict[str, Any]:
        return {
            "name": "add_meal", 
            "description": "Add a meal to Jackson's diet plan (basic version)",
            "parameters": {
                "type": "object",
                "properties": {
                    "day": {
                        "type": "string",
                        "description": "Day to add meal to"
                    },
                    "meal_time": {
                        "type": "string",
                        "description": "Meal time (Breakfast, Lunch, Dinner, Snack)"
                    },
                    "meal_name": {
                        "type": "string",
                        "description": "Name of the meal"
                    },
                    "food_items": {
                        "type": "string",
                        "description": "Food items in the meal"
                    },
                    "calories": {
                        "type": "string",
                        "description": "Calorie count"
                    }
                },
                "required": ["day", "meal_time", "meal_name"]
            }
        }
