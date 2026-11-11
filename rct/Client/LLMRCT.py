"""
LLM Agent for RollerCoaster Tycoon 2 using OpenAI's tool calling.

This agent uses the Bridge to interact with the game via actions, controlled by an LLM.
The LLM can call tools to perform actions, get information, and decide when to advance to the next month.
After advancing a month, a comprehensive park overview is provided.
Chat history is saved to a JSON file.
"""

import os
import json
from typing import Dict, Any, List
from bridge import Bridge
from openai import OpenAI
from dotenv import load_dotenv
import time

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an AI agent managing a RollerCoaster Tycoon 2 park. Your goal is to build and maintain a successful amusement park focused on maximizing guest happiness and park rating.

Game Overview:
This is a modified version of RollerCoaster Tycoon 2 with special economic rules that change the focus from money management to guest satisfaction and park quality.

Key Elements:
- Rides: Attractions for guests to enjoy. All rides are FREE for guests to use.
- Paths: Walkways for guests. Can be regular or queue paths.
- Guests: Visitors whose happiness and satisfaction are your primary concern.
- Park Rating: Overall score based on rides, cleanliness, guest satisfaction, and park design.
- Months: Time progresses monthly. Each month, guests come and experience your park.

IMPORTANT ECONOMIC RULES:
- INFINITE MONEY: You have unlimited funds - money is not a constraint.
- FREE RIDES: All rides are automatically free for guests. Ride pricing is not available.
- FOCUS ON QUALITY: Since money isn't a factor, focus entirely on guest happiness, park rating, and creating an amazing experience.

🔥 STARTUP STRATEGY - INITIAL PATH SETUP 🔥
At the beginning of the game, build a basic path network using the place_line_of_paths tool:

1. START by calling get_paths to see existing paths
2. Use place_line_of_paths to create main pathways connecting key areas
3. Build a simple grid or branching network for ride accessibility
4. THEN start placing rides adjacent to these paths

The place_line_of_paths tool allows you to:
- Connect two points with horizontal or vertical lines of paths
- Quickly build main arteries and connections
- All paths are automatically placed at ground level (z=0)
- Use queue=false for regular paths, queue=true for queue paths near ride entrances

Basic path strategy:
- Create main horizontal and vertical pathways across your owned area
- Connect these with cross-paths for accessibility
- Don't over-build - focus on functional connectivity for rides

Actions Available:
You can call tools to:
- Get information: guests, ratings, happiness, etc.
- Build: place rides, place_line_of_paths for initial path setup.
- Manage: pause, set speed, save/load.
- Advance time: run_until_month to advance to next month.

Important:
- The game is paused while you perform actions.
- After actions, call run_until_month to advance time and get monthly overview.
- Errors may occur if actions are invalid (e.g., invalid positions, water-only rides on land).
- Action results: 0 typically means success, non-zero values (e.g., 2) indicate errors.
- CRITICAL: Changes you make (placing rides, etc.) will NOT take effect until the NEXT MONTH.
- Do NOT repeatedly call the same info tools within the same month expecting different results.
- Make all your changes for the month, then call run_until_month to see the effects.
- Tool response formats:
  - get_paths: "owned tiles rectangle: X,Y to X,Y. path from: X,Y to X,Y. ..." - simplified path layout description
  - get_available_rides: "Available rides (use the ride_type number for placing):\n- Name (ride_type: TYPE, entry_index: INDEX)\n..."
  - get_ride_stats: "Ride stats:\n- Ride INDEX: Name - Income: X, Profit: Y, Guests: Z\n..." or detailed performance stats
- Use get_ tools to gather info before deciding actions.
- IMPORTANT: When placing rides, use the "ride_type" number from get_available_rides (this is the game type ID).
- Do NOT place rides with water-related names (boats, water rides, logs, etc.) as they require water and will fail.

Ride Placement Rules:
CRITICAL - RIDES ARE 3x3 AND MUST BE OFFSET FROM PATHS:

Understanding Ride Size and Placement:
- ALL rides occupy a 3x3 tile area and are CENTERED on their placement coordinates
- When you place a ride at coordinates (x, y), the ride occupies:
  * Top-left corner: (x-1, y-1)
  * Center: (x, y) 
  * Bottom-right corner: (x+1, y+1)

Path Connection Requirements:
- Rides MUST connect to paths to be accessible to guests
- Connection happens when ONE EDGE of the 3x3 ride area is ADJACENT to (touches) a path tile
- DO NOT place rides directly ON path coordinates - this destroys the paths
- Instead, place rides OFFSET from paths so they touch but don't overlap

CONCRETE EXAMPLES FOR RIDE PLACEMENT:

Example 1 - Horizontal Path:
If you have a path running horizontally at y=20 from x=10 to x=30:
✅ CORRECT: Place ride at (12, 18) - ride covers (11,17) to (13,19), bottom edge at y=19 is adjacent to path at y=20
✅ CORRECT: Place ride at (25, 22) - ride covers (24,21) to (26,23), top edge at y=21 is adjacent to path at y=20
❌ WRONG: Place ride at (15, 20) - this puts the ride directly ON the path, destroying it

Example 2 - Vertical Path:
If you have a path running vertically at x=15 from y=5 to y=25:
✅ CORRECT: Place ride at (13, 10) - ride covers (12,9) to (14,11), right edge at x=14 is adjacent to path at x=15
✅ CORRECT: Place ride at (17, 20) - ride covers (16,19) to (18,21), left edge at x=16 is adjacent to path at x=15
❌ WRONG: Place ride at (15, 15) - this puts the ride directly ON the path

Key Rules for Placement:
1. NEVER place rides at the same coordinates as existing paths
2. Place rides 2 tiles away from path centers so ONE EDGE touches
3. For horizontal paths: place rides at (path_y ± 2) to connect via top/bottom edge
4. For vertical paths: place rides at (path_x ± 2) to connect via left/right edge
5. Ensure the full 3x3 area is clear of other paths and obstacles
6. ALL rides are placed at Z=0 (ground level)

Planning Strategy:
1. First, build basic paths using place_line_of_paths if needed
2. Identify good spots where a 3x3 area can touch a path edge
3. Check that the entire 3x3 area is clear
4. Place ride at the CENTER of that 3x3 area
5. The ride entrance will automatically connect to the adjacent path

KIOSKS AND STALLS:
- Kiosks and stalls don't follow the 3x3 size rule - they are 1x1 and can be placed directly adjacent to paths.
- They should not be placed on path tiles either.
- It is important to distinguish these from rides when planning placement.
- restrooms are stalls, not rides.
- Food/drink stalls are kiosks, not rides.

CONCRETE EXAMPLE FOR KIOSKS/STALLS:

Example 1 - Horizontal Path:
If you have a path running horizontally at y=20 from x=10 to x=30:
✅ CORRECT: Place stall at (15, 19) - stall is 1x1, adjacent to path at y=20
✅ CORRECT: Place stall at (25, 21) - stall is 1x1, adjacent to path at y=20
❌ WRONG: Place stall at (20, 20) - this puts the stall directly ON the path, destroying it

example 2 - Vertical Path:
If you have a path running vertically at x=15 from y=5 to y=25:
✅ CORRECT: Place stall at (14, 10) - stall is 1x1, adjacent to path at x=15
✅ CORRECT: Place stall at (16, 20) - stall is 1x1, adjacent to path at x=15
❌ WRONG: Place stall at (15, 15) - this puts the stall directly ON the path

Key Rules for Placement:
1. NEVER place stalls/kiosks at the same coordinates as existing paths
2. Place stalls/kiosks 1 tile away from path centers so they are adjacent
3. Ensure the stall/kiosk tile is clear of other paths and obstacles
4. Stalls/kiosks are placed at Z=0 (ground level)

planning strategy for stalls/kiosks:
1. Ensure basic path network exists (use place_line_of_paths if needed)
2. Identify guest needs for food, drinks, restrooms, etc.
3. Find clear tiles adjacent to paths
4. Place stalls/kiosks at those tiles

Strategy Tips:
- Set up basic path connectivity at the start with place_line_of_paths as needed
- Focus on guest happiness and park rating rather than finances.
- Build diverse, exciting rides to keep guests entertained.
- Create efficient path networks for easy guest movement.
- Monitor guest thoughts and satisfaction levels. THIS IS VERY IMPORTANT. 
- Try to satisfy guest needs with service buildings.
- Ensure rides have path access before placing them.
- MONTHLY PLANNING: Make all changes for a month at once, then advance time to see results.
- Don't check stats repeatedly within the same month - they won't change until you advance time.

Think carefully about each action. Use the tools wisely to gather information and make informed decisions.

When ready to advance, call run_until_month. You'll receive an overview, then continue planning.
"""

def get_comprehensive_overview(bridge: Bridge, agent: 'LLMAgent' = None) -> Dict[str, Any]:
    """Get a full overview of the park state."""
    overview = {}
    getters = [
        "get_cash", "get_num_guests", "get_park_rating", "get_company_value",
        "get_park_value", "get_loan", "get_max_loan", "get_weekly_profit",
        "get_avg_happiness", "get_num_months", "get_awards", "get_paths"
    ]
    for action in getters:
        try:
            reply = bridge.send_action(action)
            # Defensive handling for special marker replies from the bridge
            if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                overview[action] = {"error": reply.decode()}
                continue
            data = _decode(reply)  # Use local _decode

            # Prevent map data dumps in overview for simple getters
            if action in ["get_cash", "get_num_guests", "get_park_rating", "get_company_value",
                         "get_park_value", "get_loan", "get_max_loan", "get_weekly_profit",
                         "get_avg_happiness", "get_num_months", "get_awards"]:
                if isinstance(data, dict) and any(key in data for key in ['map', 'entrances', 'spawns', 'map_size']):
                    overview[action] = f"ERROR: {action} returned map data instead of expected value"
                    continue
                if isinstance(data, dict) and len(str(data)) > 1000:
                    overview[action] = f"ERROR: {action} returned unexpectedly large data"
                    continue

            if action == 'get_paths':
                # Handle various invalid responses for get_paths
                if data == "nan" or str(data).lower() == "nan":
                    overview[action] = "ERROR: get_paths returned nan"
                elif isinstance(data, str) and ("error" in data.lower() or "fail" in data.lower()):
                    overview[action] = f"ERROR: get_paths failed - {data}"
                elif isinstance(data, dict) and any(key in data for key in ['map', 'entrances', 'spawns', 'map_size']):
                    # This looks like valid map data, process it
                    overview[action] = simplify_map_data(data)
                elif data and isinstance(data, (dict, list)):
                    overview[action] = simplify_map_data(data)
                else:
                    overview[action] = "0 paths"
            else:
                overview[action] = data
        except Exception as e:
            overview[action] = f"Error: {str(e)}"

    # Add comprehensive ride stats using tracked rides
    if agent and hasattr(agent, 'get_tracked_ride_stats'):
        try:
            overview['ride_stats'] = agent.get_tracked_ride_stats()
        except Exception as e:
            overview['ride_stats'] = f"Error getting ride stats: {str(e)}"
    else:
        overview['ride_stats'] = "Ride tracking not available"

    return overview

def _decode(reply):
    """Decode bridge reply."""
    if isinstance(reply, bytes):
        try:
            return json.loads(reply.decode('utf-8'))
        except json.JSONDecodeError:
            return reply.decode('utf-8')
    return reply

def simplify_map_data(data):
    """Simplify the map data from get_paths, keeping only paths, rides, ownership, and coordinates."""
    if not isinstance(data, dict):
        return str(data)


    owned_tiles = set()
    path_tiles = []


    # Get path tiles
    if 'paths' in data:
        if isinstance(data['paths'], dict):
            # Old format: {'paths': {'index': [objects]}}
            map_size = data.get('map_size', {'x': 128, 'y': 128})
            for index_str, objects in data['paths'].items():
                index = int(index_str)
                y = index // map_size['x']
                x = index % map_size['x']
                for obj in objects:
                    obj_id = obj.get('obj_id', '')
                    owned = obj.get('owned', False)
                    if owned:
                        owned_tiles.add((x, y))
                    if 'footpath' in obj_id.lower():
                        path_tiles.append((x, y))
        elif isinstance(data['paths'], list):
            # New format: {'paths': [{'x':, 'y':, ...}]}
            for p in data['paths']:
                x = int(p['x'])
                y = int(p['y'])
                path_tiles.append((x, y))

    # Use positions data for owned tiles if available (this represents actual owned land)
    if 'positions' in data and isinstance(data['positions'], list):
        owned_tiles.clear()  # Clear any path-based owned tiles
        for pos in data['positions']:
            x = int(pos['x'])
            y = int(pos['y'])
            owned_tiles.add((x, y))
    else:
        # Fallback: if no positions data, treat path tiles as owned
        owned_tiles.update(path_tiles)

    def find_rectangles(points):
        """Find the minimum number of rectangles to cover all points using maximal rectangle decomposition."""
        if not points:
            return []

        # First, group points into connected components
        components = []
        visited = set()
        for point in points:
            if point not in visited:
                component = set()
                queue = [point]
                while queue:
                    p = queue.pop(0)
                    if p in visited:
                        continue
                    visited.add(p)
                    component.add(p)
                    x, y = p
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if (nx, ny) in points and (nx, ny) not in visited:
                            queue.append((nx, ny))
                components.append(component)

        # For each connected component, find optimal rectangle decomposition
        all_rectangles = []
        for component in components:
            if not component:
                continue
            rectangles = decompose_into_rectangles(component)
            all_rectangles.extend(rectangles)

        return all_rectangles

    def decompose_into_rectangles(points):
        """Decompose a set of points into minimal rectangles using greedy maximal rectangle algorithm."""
        if not points:
            return []

        points = set(points)  # Make a copy to modify
        rectangles = []

        while points:
            # Find the largest rectangle starting from any remaining point
            best_rect = None
            best_area = 0

            for start_point in list(points):
                rect = find_maximal_rectangle_from(start_point, points)
                area = (rect[2] - rect[0] + 1) * (rect[3] - rect[1] + 1)
                if area > best_area:
                    best_area = area
                    best_rect = rect

            if best_rect is None:
                # This shouldn't happen, but safety fallback
                point = points.pop()
                best_rect = (point[0], point[1], point[0], point[1])

            rectangles.append(best_rect)

            # Remove all points covered by this rectangle
            x1, y1, x2, y2 = best_rect
            covered_points = set()
            for x in range(x1, x2 + 1):
                for y in range(y1, y2 + 1):
                    if (x, y) in points:
                        covered_points.add((x, y))
            points -= covered_points

        return rectangles

    def find_maximal_rectangle_from(start_point, available_points):
        """Find the largest rectangle that can be formed starting from start_point."""
        start_x, start_y = start_point

        # Find maximum width at the starting row
        max_width = 1
        x = start_x + 1
        while (x, start_y) in available_points:
            max_width += 1
            x += 1

        best_rect = (start_x, start_y, start_x + max_width - 1, start_y)
        best_area = max_width

        # Try extending downward row by row
        current_width = max_width
        for height in range(2, 50):  # Reasonable height limit
            y = start_y + height - 1

            # Check if we can maintain the current width at this new row
            valid_width = 0
            for x in range(start_x, start_x + current_width):
                if (x, y) in available_points:
                    valid_width += 1
                else:
                    break

            if valid_width == 0:
                # Can't extend any further down
                break

            # Update current width to the maximum we can maintain
            current_width = min(current_width, valid_width)
            current_area = current_width * height

            if current_area > best_area:
                best_area = current_area
                best_rect = (start_x, start_y, start_x + current_width - 1, start_y + height - 1)

            # If width becomes 1, no point continuing (we won't get better area)
            if current_width == 1 and height > 1:
                break

        return best_rect

    def find_path_lines(points):
        """Find individual path lines (connected segments)."""
        if not points:
            return []

        lines = []
        points_set = set(points)
        visited = set()

        for point in points:
            if point not in visited:
                # Start a new connected component from this point
                component = set()
                queue = [point]

                while queue:
                    current = queue.pop(0)
                    if current in visited:
                        continue
                    visited.add(current)
                    component.add(current)

                    x, y = current
                    # Check 4 adjacent directions
                    for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        nx, ny = x + dx, y + dy
                        if (nx, ny) in points_set and (nx, ny) not in visited:
                            queue.append((nx, ny))

                if component:
                    # Find actual path segments within this component
                    # Look for straight lines or create multiple segments
                    component_lines = find_lines_in_component(component)
                    lines.extend(component_lines)

        return lines

    def find_lines_in_component(component):
        """Find individual lines within a connected component."""
        if not component:
            return []

        lines = []
        points = list(component)
        points.sort()  # Sort by x, then y

        # Group by rows (same y coordinate)
        from collections import defaultdict
        rows = defaultdict(list)
        cols = defaultdict(list)

        for x, y in points:
            rows[y].append(x)
            cols[x].append(y)

        # Find horizontal lines
        horizontal_lines = []
        for y, x_coords in rows.items():
            x_coords.sort()
            # Find consecutive runs
            if len(x_coords) > 1:
                start_x = x_coords[0]
                prev_x = x_coords[0]

                for i in range(1, len(x_coords)):
                    curr_x = x_coords[i]
                    if curr_x != prev_x + 1:  # Gap found
                        if prev_x > start_x:  # Line of length > 1
                            horizontal_lines.append((start_x, y, prev_x, y))
                        start_x = curr_x
                    prev_x = curr_x

                # Add the last line
                if prev_x > start_x:
                    horizontal_lines.append((start_x, y, prev_x, y))

        # Find vertical lines
        vertical_lines = []
        for x, y_coords in cols.items():
            y_coords.sort()
            if len(y_coords) > 1:
                start_y = y_coords[0]
                prev_y = y_coords[0]

                for i in range(1, len(y_coords)):
                    curr_y = y_coords[i]
                    if curr_y != prev_y + 1:  # Gap found
                        if prev_y > start_y:  # Line of length > 1
                            vertical_lines.append((x, start_y, x, prev_y))
                        start_y = curr_y
                    prev_y = curr_y

                # Add the last line
                if prev_y > start_y:
                    vertical_lines.append((x, start_y, x, prev_y))

        # Combine all lines
        lines = horizontal_lines + vertical_lines

        # If no lines found, treat as a single area
        if not lines and component:
            xs = [p[0] for p in component]
            ys = [p[1] for p in component]
            min_x, max_x = min(xs), max(xs)
            min_y, max_y = min(ys), max(ys)
            lines.append((min_x, min_y, max_x, max_y))

        return lines

    owned_rects = find_rectangles(owned_tiles) if owned_tiles else []
    path_lines = find_path_lines(path_tiles) if path_tiles else []

    # Build string summary
    summary_parts = []
    if owned_rects:
        for x1, y1, x2, y2 in owned_rects:
            summary_parts.append(f"owned tiles rectangle: {x1},{y1} to {x2},{y2}")

    if path_lines:
        for x1, y1, x2, y2 in path_lines:
            if x1 == x2 and y1 == y2:
                summary_parts.append(f"path at: {x1}, {y1}")
            else:
                summary_parts.append(f"path from: {x1}, {y1} to {x2}, {y2}")

    return '. '.join(summary_parts) if summary_parts else "No owned tiles or paths."

class LLMAgent:
    def __init__(self, bridge: Bridge):
        self.bridge = bridge
        self.chat_history = []
        self.tools = self.define_tools()
        self.available_rides_cache = None  # Cache for available rides
        self.problematic_rides = set()  # Track ride IDs that cause water/placement errors
        self.placed_rides = []  # Track coordinates and info of placed rides: [{"x": x, "y": y, "z": z, "name": name, "type": type}, ...]

    def define_tools(self) -> List[Dict[str, Any]]:
        # Define all tools based on actions
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "pause",
                    "description": "Pause the game.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_until_month",
                    "description": "Advance the game to the next month and get an overview. IMPORTANT: Changes you make (rides, prices, etc.) only take effect when you advance to the next month. Use this after making all your changes to see the results.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_cash",
                    "description": "Get current cash amount. Note: Changes from rides/prices won't show until next month.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_num_guests",
                    "description": "Get the number of guests in the park. Note: New rides won't affect guest count until next month.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_park_rating",
                    "description": "Get the park rating. Note: New rides and changes won't affect rating until next month.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_company_value",
                    "description": "Get the company value.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_park_value",
                    "description": "Get the park value.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_loan",
                    "description": "Get the current loan amount.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_max_loan",
                    "description": "Get the maximum loan amount.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_weekly_profit",
                    "description": "Get the weekly profit.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_avg_happiness",
                    "description": "Get the average guest happiness.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_num_months",
                    "description": "Get the number of months elapsed.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_awards",
                    "description": "Get the park awards.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_ride_stats",
                    "description": "Get statistics for all rides.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_detailed_ride_stats",
                    "description": "Get detailed performance stats for all tracked rides, showing top 3 and bottom 3 performers with profit, popularity, and excitement ratings.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_guest_thoughts",
                    "description": "Get guest thoughts.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_paths",
                    "description": "Get the paths in the park.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_available_rides",
                    "description": "Get available rides to build.",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "place_path",
                    "description": "Place a path tile at given coordinates. Paths are always placed at ground level (z=0).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "integer", "description": "X coordinate"},
                            "y": {"type": "integer", "description": "Y coordinate"},
                            "queue": {"type": "boolean", "description": "Is queue path"}
                        },
                        "required": ["x", "y", "queue"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "place_ride",
                    "description": "Place a ride at given coordinates. CRITICAL: Rides are 3x3 and CENTERED on placement coordinates. If you place at (x,y), the ride occupies (x-1,y-1) to (x+1,y+1). To connect to a path, place the ride so ONE EDGE of this 3x3 area touches the path. Example: path at x=22, place ride at x=20 (covers 19-21, edge 21 touches path 22) or x=24 (covers 23-25, edge 23 touches path 22). Use 'ride_type' from get_available_rides. Avoid water rides. Ensure the full 3x3 area is clear.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ride_type": {"type": "integer", "description": "Ride type ID from get_available_rides"},
                            "x": {"type": "integer", "description": "X coordinate for CENTER of the 3x3 ride (0-127). Ride will occupy x-1 to x+1."},
                            "y": {"type": "integer", "description": "Y coordinate for CENTER of the 3x3 ride (0-127). Ride will occupy y-1 to y+1."},
                            "z": {"type": "integer", "description": "Z height (0-15). Use 0 to place on ground level."}
                        },
                        "required": ["ride_type", "x", "y", "z"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "remove_ride",
                    "description": "Remove a ride by ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "ride_id": {"type": "integer", "description": "Ride ID"}
                        },
                        "required": ["ride_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "set_speed",
                    "description": "Set the game speed.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "speed": {"type": "integer", "description": "Speed level"}
                        },
                        "required": ["speed"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "save_park",
                    "description": "Save the park.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Save path"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "place_line_of_paths",
                    "description": "Place a line of path tiles between two points. The points must form a straight line (horizontal or vertical only). Automatically places all path tiles between start and end coordinates. All paths are placed at ground level (z=0).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "x1": {"type": "integer", "description": "Start X coordinate"},
                            "y1": {"type": "integer", "description": "Start Y coordinate"},
                            "x2": {"type": "integer", "description": "End X coordinate"},
                            "y2": {"type": "integer", "description": "End Y coordinate"},
                            "queue": {"type": "boolean", "description": "Are these queue paths"}
                        },
                        "required": ["x1", "y1", "x2", "y2", "queue"]
                    }
                }
            }
        ]
        return tools

    def get_and_cache_available_rides(self):
        """Get available rides and cache them for validation."""
        try:
            reply = self.bridge.send_action("get_available_rides")
            data = self._decode(reply)

            # Only process if we get a proper list of rides
            if isinstance(data, list):
                # Validate that this looks like ride data
                if data and all(isinstance(item, dict) and 'entry_index' in item and 'name' in item for item in data[:3]):
                    # Cache rides with type (game_type) as the key since that's what we use for placement
                    self.available_rides_cache = {}
                    for item in data:
                        ride_type = item['type']  # Use the 'type' field (game_type)
                        # Store with both string and int versions
                        self.available_rides_cache[ride_type] = item
                        try:
                            self.available_rides_cache[int(ride_type)] = item
                        except ValueError:
                            pass  # Skip if ride_type is not convertible to int
                    return data
                else:
                    return []
            else:
                return []

        except Exception as e:
            print(f"Error getting available rides: {e}")
            return []

    def validate_ride_placement(self, ride_type, x, y, z):
        """Validate ride placement parameters."""
        errors = []

        # Validate coordinates are reasonable
        if not (0 <= x <= 127 and 0 <= y <= 127):
            errors.append(f"Coordinates out of bounds: x={x}, y={y} (should be 0-127)")

        if not (0 <= z <= 15):
            errors.append(f"Z coordinate out of bounds: z={z} (should be 0-15)")

        # Check if ride type is available
        if self.available_rides_cache is None:
            self.get_and_cache_available_rides()

        if self.available_rides_cache and ride_type not in self.available_rides_cache:
            # Try both int and string versions
            int_ride_type = None
            str_ride_type = str(ride_type)
            try:
                int_ride_type = int(ride_type)
            except ValueError:
                pass

            if (int_ride_type is not None and int_ride_type not in self.available_rides_cache) or str_ride_type not in self.available_rides_cache:
                available_ids = [k for k in self.available_rides_cache.keys() if isinstance(k, (int, str))]
                errors.append(f"Invalid ride_type {ride_type}. Available ride IDs: {available_ids}")

        return errors

    def get_tracked_ride_stats(self):
        """Get stats for all tracked rides and return top 3 and bottom 3 performers."""
        if not self.placed_rides:
            return "No rides have been placed yet."

        print(f"DEBUG: Getting stats for {len(self.placed_rides)} tracked rides: {[r['name'] + ' at ' + str((r['x'], r['y'], r['z'])) for r in self.placed_rides]}")

        ride_stats = []

        for ride in self.placed_rides:
            try:
                # Get individual ride stats using coordinates
                act = {"action": "get_ride_stats", "x": ride["x"], "y": ride["y"]}
                reply = self.bridge.send_action_dict(act)
                data = self._decode(reply)

                print(f"DEBUG: Ride stats for {ride['name']} at ({ride['x']}, {ride['y']}): {data}")

                if isinstance(data, str):
                    if "can't find ride" in data.lower():
                        print(f"DEBUG: No ride found at {ride['name']} coordinates ({ride['x']}, {ride['y']}, {ride['z']})")
                        continue
                    else:
                        # Try to parse string response as numbers
                        print(f"DEBUG: Got string response for {ride['name']}: '{data}'")
                        continue
                elif isinstance(data, dict):
                    # Parse ride stats from dict
                    ride_stat = {
                        "name": ride["name"],
                        "coords": f"({ride['x']}, {ride['y']}, {ride['z']})",
                        "profit": data.get("profit", data.get("total_profit", 0)),
                        "popularity": data.get("popularity", data.get("rating", 0)),
                        "excitement": data.get("excitement", 0),
                        "intensity": data.get("intensity", 0),
                        "nausea": data.get("nausea", 0),
                        "guests": data.get("guests", data.get("total_customers", 0))
                    }
                    ride_stats.append(ride_stat)
                    print(f"DEBUG: Added stats for {ride['name']}: profit={ride_stat['profit']}, popularity={ride_stat['popularity']}")
                elif isinstance(data, (int, float)):
                    # Sometimes just returns a single number - assume it's profit or status
                    if data == 0:
                        print(f"DEBUG: Ride {ride['name']} returned 0 - might not be operational yet")
                        continue
                    else:
                        ride_stat = {
                            "name": ride["name"],
                            "coords": f"({ride['x']}, {ride['y']}, {ride['z']})",
                            "profit": int(data) if data > 0 else 0,
                            "popularity": 50,  # Default value
                            "excitement": 0,
                            "intensity": 0,
                            "nausea": 0,
                            "guests": 0
                        }
                        ride_stats.append(ride_stat)
                        print(f"DEBUG: Added basic stats for {ride['name']}: numeric data={data}")
                else:
                    print(f"DEBUG: Unexpected data type for {ride['name']}: {type(data)} = {data}")
                    # Still try to track the ride with default values
                    ride_stat = {
                        "name": ride["name"],
                        "coords": f"({ride['x']}, {ride['y']}, {ride['z']})",
                        "profit": 0,
                        "popularity": 0,
                        "excitement": 0,
                        "intensity": 0,
                        "nausea": 0,
                        "guests": 0
                    }
                    ride_stats.append(ride_stat)

            except Exception as e:
                print(f"Error getting stats for {ride['name']}: {e}")
                # Add ride with default stats so it still shows up
                ride_stat = {
                    "name": ride["name"],
                    "coords": f"({ride['x']}, {ride['y']}, {ride['z']})",
                    "profit": 0,
                    "popularity": 0,
                    "excitement": 0,
                    "intensity": 0,
                    "nausea": 0,
                    "guests": 0
                }
                ride_stats.append(ride_stat)
                continue

        if not ride_stats:
            return f"No ride stats could be retrieved from {len(self.placed_rides)} tracked rides. Rides may not be operational yet or coordinates may be incorrect."

        # Sort by profit (primary) and popularity (secondary)
        ride_stats.sort(key=lambda r: (r["profit"], r["popularity"]), reverse=True)

        # Get top 3 and bottom 3
        top_3 = ride_stats[:3]
        bottom_3 = ride_stats[-3:] if len(ride_stats) > 3 else []

        # Format output
        result = []

        if top_3:
            result.append("🏆 TOP 3 PERFORMING RIDES:")
            for i, ride in enumerate(top_3, 1):
                result.append(f"  {i}. {ride['name']} at {ride['coords']}")
                result.append(f"     💰 Profit: ${ride['profit']:,} | 👥 Popularity: {ride['popularity']}% | 🎫 Guests: {ride['guests']}")
                result.append(f"     🎢 Excitement: {ride['excitement']} | Intensity: {ride['intensity']} | Nausea: {ride['nausea']}")

        if bottom_3 and len(ride_stats) > 3:
            result.append("\n📉 BOTTOM 3 PERFORMING RIDES:")
            for i, ride in enumerate(bottom_3, 1):
                result.append(f"  {i}. {ride['name']} at {ride['coords']}")
                result.append(f"     💰 Profit: ${ride['profit']:,} | 👥 Popularity: {ride['popularity']}% | 🎫 Guests: {ride['guests']}")
                result.append(f"     🎢 Excitement: {ride['excitement']} | Intensity: {ride['intensity']} | Nausea: {ride['nausea']}")

        result.append(f"\n📊 Total tracked rides: {len(ride_stats)} (out of {len(self.placed_rides)} placed rides)")

        return "\n".join(result)

    def execute_tool(self, tool_call) -> Any:
        name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        try:
            if name == "run_until_month":
                # Use run_sim action with num_ticks=-1 to advance to next month
                reply = self.bridge.send_action_dict({"action": "run_sim", "num_ticks": -1})
                overview = get_comprehensive_overview(self.bridge, agent=self)
                return {"run_reply": self._decode(reply), "overview": overview}
            elif name == "get_available_rides":
                data = self.get_and_cache_available_rides()
                if isinstance(data, list) and data:
                    # Filter out problematic rides (water rides, etc.)
                    if hasattr(self, 'problematic_rides') and self.problematic_rides:
                        data = [item for item in data if int(item.get('type', -1)) not in self.problematic_rides]
                        if not data:
                            return "No suitable land-based rides available (all available rides require water or have placement issues)"

                    # Only return formatted summary if we have valid ride data
                    if all(isinstance(item, dict) and 'name' in item and 'entry_index' in item for item in data):
                        print(f"DEBUG: Available rides raw data: {data}")  # Debug logging
                        # Use the 'type' field (game_type) for ride placement, not entry_index
                        summary = "Available rides (use the ride_type number for placing):\n" + "\n".join(
                            f"- {item['name']} (ride_type: {item['type']}, entry_index: {item['entry_index']})" for item in data
                        )
                        return summary
                    else:
                        return {"error": "Invalid ride data format", "raw_data_preview": str(data)[:200]}
                elif isinstance(data, list) and not data:
                    return "No available rides found"
                else:
                    return {"error": "Failed to get available rides", "data_type": str(type(data)), "note": "Expected list of ride objects"}
            elif name == "get_ride_stats":
                reply = self.bridge.send_action(name)
                data = self._decode(reply)
                if isinstance(data, list):
                    summary = "Ride stats:\n" + "\n".join(f"- Ride {i}: {ride.get('name', 'Unknown')} - Income: {ride.get('total_income', 0)}, Profit: {ride.get('total_profit', 0)}, Guests: {ride.get('guests', 0)}" for i, ride in enumerate(data))
                    return summary
                return data
            elif name == "get_detailed_ride_stats":
                return self.get_tracked_ride_stats()
            elif name == "get_paths":
                reply = self.bridge.send_action(name)
                data = self._decode(reply)

                # Handle various invalid responses for get_paths
                if data == "nan" or str(data).lower() == "nan":
                    return "ERROR: get_paths returned nan - no path data available"
                elif isinstance(data, str) and ("error" in data.lower() or "fail" in data.lower()):
                    return f"ERROR: get_paths failed - {data}"
                elif isinstance(data, dict) and any(key in data for key in ['map', 'entrances', 'spawns', 'map_size']):
                    # This looks like valid map data, process it
                    return simplify_map_data(data)
                elif data and isinstance(data, (dict, list)):
                    return simplify_map_data(data)
                else:
                    return "No paths found in the park"
            elif name in ["pause", "get_cash", "get_num_guests", "get_park_rating", "get_company_value", "get_park_value", "get_loan", "get_max_loan", "get_weekly_profit", "get_avg_happiness", "get_num_months", "get_awards", "get_guest_thoughts"]:
                reply = self.bridge.send_action(name)
                result = self._decode(reply)

                # Validate that these actions return simple values, not map data
                if isinstance(result, dict) and any(key in result for key in ['map', 'entrances', 'spawns', 'map_size']):
                    print(f"WARNING: {name} returned map data instead of expected simple value")
                    return {"error": f"Bridge returned map data for {name}", "action_confusion": True}

                # For these simple getters, we expect numbers, strings, or small objects - not massive data
                if isinstance(result, dict) and len(str(result)) > 1000:
                    print(f"WARNING: {name} returned unexpectedly large data ({len(str(result))} chars)")
                    return {"error": f"Bridge returned unexpectedly large data for {name}", "data_size": len(str(result))}

                return result
            elif name == "place_path":
                act = {"action": "place_path", "x": args["x"], "y": args["y"], "z": 0, "queue": args["queue"]}
                reply = self.bridge.send_action_dict(act)
                # Defensive: if bridge returned a special marker, return structured error
                if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                    return {"error": reply.decode()}
                return self._decode(reply)
            elif name == "place_ride":
                # Validate parameters before attempting to place ride
                ride_type = args.get("ride_type")
                x = args.get("x")
                y = args.get("y")
                z = args.get("z")

                # Check for missing parameters
                if ride_type is None or x is None or y is None or z is None:
                    return {"error": "Missing required parameters", "required": ["ride_type", "x", "y", "z"], "received": args}

                # Convert to proper types to prevent C++ bad_any_cast exceptions
                try:
                    ride_type = int(ride_type)
                    x = int(x)
                    y = int(y)
                    z = 0  # Force all rides to be placed at ground level (z = 0)
                except (ValueError, TypeError) as e:
                    return {"error": "Type conversion failed", "message": str(e), "args": args}

                # Validate parameters
                validation_errors = self.validate_ride_placement(ride_type, x, y, z)
                if validation_errors:
                    return {"error": "Validation failed", "details": validation_errors, "action": args}

                # Additional validation: Check if this ride type seems to be a water ride or invalid
                if self.available_rides_cache and ride_type in self.available_rides_cache:
                    ride_info = self.available_rides_cache[ride_type]
                    ride_name = ride_info.get('name', 'Unknown')
                    print(f"DEBUG: Attempting to place {ride_name} (game_type: {ride_type}) at ({x}, {y}, {z})")

                    # Check if this ride has previously caused water/placement errors
                    if ride_type in self.problematic_rides:
                        return {"error": f"Cannot place ride '{ride_name}' - this ride ID has previously caused water/placement errors",
                               "ride_info": ride_info,
                               "note": "This ride type has been marked as problematic"}

                    # Check for water rides or other problematic ride types by name
                    water_keywords = ['boat', 'water', 'submarine', 'log', 'splash', 'river', 'lake']
                    if any(keyword in ride_name.lower() for keyword in water_keywords):
                        self.problematic_rides.add(ride_type)
                        return {"error": f"Cannot place water ride '{ride_name}' on land",
                               "ride_info": ride_info,
                               "note": "This appears to be a water-only ride"}
                else:
                    return {"error": f"Ride type {ride_type} not found in available rides cache", "action": args}

                try:
                    act = {"action": "place_ride", "ride_type": ride_type, "x": x, "y": y, "z": z}
                    reply = self.bridge.send_action_dict(act)

                    # Defensive: if bridge returned a special marker, return structured error
                    if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                        return {"error": reply.decode(), "action": act}

                    # Give game a brief moment to stabilize after placing an object
                    time.sleep(0.15)
                    result = self._decode(reply)

                    # Handle string responses (game sometimes returns '0\x00' for success)
                    if isinstance(result, str):
                        # Clean up null terminators and whitespace
                        cleaned_result = result.rstrip('\x00').strip()
                        try:
                            # Try to convert to integer
                            int_result = int(cleaned_result)
                            if int_result == 0:
                                return {"success": True, "message": "Ride placed successfully", "result": int_result}
                            else:
                                ride_info = self.available_rides_cache.get(ride_type, {}) if self.available_rides_cache else {}
                                return {"error": f"Ride placement failed with code {int_result}",
                                       "action": act,
                                       "ride_info": ride_info,
                                       "note": "Non-zero return codes indicate placement errors (insufficient funds, invalid location, etc.)"}
                        except ValueError:
                            # String is not a number, check if it contains error messages
                            if "error" in cleaned_result.lower() or "fail" in cleaned_result.lower():
                                return {"error": "Ride placement failed", "message": cleaned_result, "action": act}

                    # Check if result is a dict containing error information
                    if isinstance(result, dict):
                        if "error" in result or "code" in result:
                            error_msg = result.get("error", "Unknown error")
                            error_code = result.get("code", "unknown")

                            # Check for water-only error and mark this ride as problematic
                            if "water" in error_msg.lower() or "Can only build this on water" in error_msg:
                                print(f"DEBUG: Marking ride_type {ride_type} as water-only/problematic")
                                self.problematic_rides.add(ride_type)
                                if self.available_rides_cache and ride_type in self.available_rides_cache:
                                    ride_name = self.available_rides_cache[ride_type].get('name', 'Unknown')
                                    error_msg = f"Ride '{ride_name}' requires water and cannot be placed on land"

                            return {"error": f"Ride placement failed: {error_msg}",
                                   "code": error_code,
                                   "action": act,
                                   "note": "Game returned error details in dict format"}

                    # Check if placement was successful (should be 0 for success, non-zero for error)
                    if isinstance(result, (int, float)):
                        if result != 0:
                            ride_info = self.available_rides_cache.get(ride_type, {}) if self.available_rides_cache else {}
                            return {"error": f"Ride placement failed with code {result}",
                                   "action": act,
                                   "ride_info": ride_info,
                                   "note": "Non-zero return codes indicate placement errors (insufficient funds, invalid location, etc.)"}
                        else:
                            # Successfully placed ride, track its coordinates and info
                            ride_info = self.available_rides_cache.get(ride_type, {}) if self.available_rides_cache else {}
                            ride_name = ride_info.get('name', f'Ride_{ride_type}')

                            # Add to placed rides tracking
                            ride_entry = {
                                "x": x, "y": y, "z": z,
                                "name": ride_name,
                                "type": ride_type,
                                "placed_month": "current"  # Could be enhanced with actual month tracking
                            }
                            self.placed_rides.append(ride_entry)
                            print(f"DEBUG: Tracked new ride: {ride_name} at ({x}, {y}, {z})")

                            return {"success": True, "message": "Ride placed successfully", "result": result}

                    # SPECIAL CASE: Sometimes the game returns ride data instead of error codes, but ride is actually placed
                    if isinstance(result, list) and result:
                        # Check if this looks like ride data that matches what we tried to place
                        first_item = result[0] if result else {}
                        if isinstance(first_item, dict) and 'entry_index' in first_item and 'name' in first_item:
                            # Since we're using game_type (type field) for placement, compare against that
                            placed_ride_type = first_item.get('type', '')
                            # Convert both to string for comparison
                            if str(placed_ride_type) == str(ride_type):
                                # Successfully placed ride, track its coordinates if not already tracked
                                ride_name = first_item.get('name', f'Ride_{ride_type}')

                                # Check if this ride is already tracked at these coordinates
                                already_tracked = any(
                                    r["x"] == x and r["y"] == y and r["z"] == z
                                    for r in self.placed_rides
                                )

                                if not already_tracked:
                                    ride_entry = {
                                        "x": x, "y": y, "z": z,
                                        "name": ride_name,
                                        "type": ride_type,
                                        "placed_month": "current"
                                    }
                                    self.placed_rides.append(ride_entry)
                                    print(f"DEBUG: Tracked ride from response: {ride_name} at ({x}, {y}, {z})")

                                return {"success": True,
                                       "message": f"Ride placed successfully! Game returned ride data instead of status code.",
                                       "ride_info": first_item,
                                       "note": "Game communication quirk - returned ride data but placement succeeded"}

                    # Check if we got FULL map data (which would be a serious error)
                    if isinstance(result, dict) and all(key in result for key in ['map', 'entrances', 'spawns', 'map_size']):
                        return {"error": "Bridge returned FULL map data instead of placement result",
                               "action_confusion": True,
                               "data_type": "full_map_data",
                               "note": "This indicates a serious bridge communication issue - got entire map instead of placement result"}

                    # If we get here, result format is unexpected but not necessarily an error
                    return {"success": True,
                           "message": "Placement completed but returned unexpected format",
                           "result": str(result)[:100],
                           "result_type": str(type(result)),
                           "note": "Ride may have been placed successfully despite unusual response"}

                except Exception as e:
                    print(f"Exception during place_ride: {e}")
                    return {"error": "exception", "message": str(e), "action": args}
            elif name == "remove_ride":
                act = {"action": "remove_ride", "ride_id": args["ride_id"]}
                reply = self.bridge.send_action_dict(act)
                if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                    return {"error": reply.decode()}
                return self._decode(reply)
            elif name == "set_speed":
                act = {"action": "set_speed", "speed": args["speed"]}
                reply = self.bridge.send_action_dict(act)
                if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                    return {"error": reply.decode()}
                return self._decode(reply)
            elif name == "save_park":
                act = {"action": "save_park", "path": args["path"]}
                reply = self.bridge.send_action_dict(act)
                if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                    return {"error": reply.decode()}
                return self._decode(reply)
            elif name == "place_line_of_paths":
                # Get coordinates and validate they form a straight line
                x1, y1, x2, y2 = args["x1"], args["y1"], args["x2"], args["y2"]
                z = 0  # All paths are at ground level
                queue = args["queue"]

                # Check if points form a straight line (horizontal or vertical only)
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)

                if dx != 0 and dy != 0:
                    return {"error": "Points must form a straight line (horizontal or vertical only)",
                           "coordinates": f"({x1},{y1}) to ({x2},{y2})",
                           "note": "Diagonal lines are not supported"}

                # Calculate the path coordinates
                path_coords = []

                if x1 == x2:  # Vertical line
                    start_y, end_y = min(y1, y2), max(y1, y2)
                    for y in range(start_y, end_y + 1):
                        path_coords.append((x1, y))
                elif y1 == y2:  # Horizontal line
                    start_x, end_x = min(x1, x2), max(x1, x2)
                    for x in range(start_x, end_x + 1):
                        path_coords.append((x, y1))
                else:
                    # This case should not happen due to validation above
                    return {"error": "Invalid line coordinates"}

                # Place all path tiles
                results = []
                successful_placements = 0

                for x, y in path_coords:
                    try:
                        act = {"action": "place_path", "x": x, "y": y, "z": z, "queue": queue}
                        reply = self.bridge.send_action_dict(act)

                        if reply in (b"TIMEOUT", b"NO_REPLY", b"ZMQERROR"):
                            results.append(f"({x},{y}): {reply.decode()}")
                        else:
                            result = self._decode(reply)
                            if result == 0 or result == "0":  # Success
                                successful_placements += 1
                            results.append(f"({x},{y}): {result}")
                    except Exception as e:
                        results.append(f"({x},{y}): Error - {str(e)}")

                return {
                    "message": f"Line placement completed: {successful_placements}/{len(path_coords)} paths placed successfully",
                    "line": f"({x1},{y1}) to ({x2},{y2})",
                    "total_tiles": len(path_coords),
                    "successful_placements": successful_placements,
                    "results": results[:10] if len(results) > 10 else results,  # Limit output for long lines
                    "truncated": len(results) > 10
                }
            else:
                return f"Unknown tool: {name}"
        except KeyError as e:
            # Handle missing arguments more gracefully
            print(f"Missing argument while executing tool {name}: {e}")
            return {"error": "missing_argument", "message": f"Missing required argument: {str(e)}", "tool": name, "args": args}
        except json.JSONDecodeError as e:
            # Handle JSON parsing errors
            print(f"JSON decode error while executing tool {name}: {e}")
            return {"error": "json_decode_error", "message": str(e), "tool": name}
        except Exception as e:
            # Ensure the agent never crashes due to unexpected bridge/library issues
            print(f"Exception while executing tool {name}: {e}")
            import traceback
            traceback.print_exc()
            return {"error": "exception", "message": str(e), "tool": name, "args": args}

    def _decode(self, reply):
        """Decode bridge reply."""
        if isinstance(reply, bytes):
            try:
                return json.loads(reply.decode('utf-8'))
            except json.JSONDecodeError:
                return reply.decode('utf-8')
        return reply

    def run(self, parkname="RealTest-ForestFrontiers", model="gpt-4o"):
        self.bridge.connect()
        import datetime
        date = datetime.date.today().strftime("%Y-%m-%d")
        time_str = datetime.datetime.now().strftime("%H-%M-%S")
        run_folder = f"Runs/{parkname}_{date}_{time_str}_{model}"
        os.makedirs(run_folder, exist_ok=True)
        current_month = 0
        # Run indefinitely until manually stopped (removed 1 year cap)
        while True:
            print(f"\n=== Starting Month {current_month} ===")
            month_folder = f"{run_folder}/{current_month}"
            os.makedirs(month_folder, exist_ok=True)
            overview = get_comprehensive_overview(self.bridge, agent=self)
            print(f"Park overview for month {current_month}:")
            for key, value in overview.items():
                print(f"  {key}: {value}")
            # Create dense overview string
            awards = overview.get('get_awards')
            awards_count = len(awards) if isinstance(awards, list) else 0
            dense_overview = (
                f"Cash: {overview.get('get_cash', 0)}, "
                f"Guests: {overview.get('get_num_guests', 0)}, "
                f"Rating: {overview.get('get_park_rating', 0)}, "
                f"Loan: {overview.get('get_loan', 0)}, "
                f"Company Value: {overview.get('get_company_value', 0)}, "
                f"Park Value: {overview.get('get_park_value', 0)}, "
                f"Weekly Profit: {overview.get('get_weekly_profit', 0)}, "
                f"Avg Happiness: {overview.get('get_avg_happiness', 0)}, "
                f"Months: {overview.get('get_num_months', 0)}, "
                f"Awards: {awards_count} awards, "
                f"Paths: {overview.get('get_paths', 'None')}"
            )

            # Add ride stats separately for better formatting
            ride_stats = overview.get('ride_stats', 'No rides tracked')
            if isinstance(ride_stats, str) and len(ride_stats) > 100:
                # Long ride stats, add as separate section
                dense_overview += f"\n\nRide Performance:\n{ride_stats}"
            else:
                # Short or no ride stats, add inline
                dense_overview += f", Ride Stats: {ride_stats}"
            # Start new conversation for this month
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Park overview for month {current_month}: {dense_overview}. Plan your actions for this month."}
            ]
            chat_history = messages.copy()
            month_done = False
            while not month_done:
                print(f"\n--- Month {current_month}: Getting LLM response ---")
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto"
                )
                message = response.choices[0].message
                message_dict = message.to_dict() if hasattr(message, 'to_dict') else dict(message)
                messages.append(message_dict)
                chat_history.append(message_dict)
                if message.tool_calls:
                    print(f"Month {current_month}: LLM decided to call tools:")
                    tool_messages = []
                    for tool_call in message.tool_calls:
                        print(f"  - {tool_call.function.name}")
                        result = self.execute_tool(tool_call)
                        print(f"    Result: {result}")
                        tool_msg = {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": json.dumps(result)
                        }
                        tool_messages.append(tool_msg)
                        if tool_call.function.name == "run_until_month":
                            month_done = True
                            print(f"Month {current_month} advanced.")
                    # Append all tool messages
                    messages.extend(tool_messages)
                    chat_history.extend(tool_messages)
                else:
                    print(f"Month {current_month}: LLM responded with text: {message.content}")
                    month_done = True  # End the month if no tools called
            # Save chat history for this month
            chat_file = f"{month_folder}/chat_history.json"
            with open(chat_file, "w") as f:
                json.dump(chat_history, f, indent=2)
            print(f"Month {current_month} chat history saved to {chat_file}")
            current_month += 1
        print("\n--- Simulation stopped manually or scenario ended ---")
        # Unpause at the end
        print("Unpausing the game...")
        unpause_resp = self.bridge.send_action("unpause")
        print("Unpaused game:", self._decode(unpause_resp))
        print("LLM agent finished.")


if __name__ == '__main__':
    b = Bridge(11753)
    agent = LLMAgent(b)
    agent.run()
