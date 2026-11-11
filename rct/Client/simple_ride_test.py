#!/usr/bin/env python3
"""
Simple test script to list available rides and place one
"""
import sys
from LLMRCT import LLMAgent
from bridge import Bridge

def main():
    print("=== RCT2 Ride Placement Test ===")

    try:
        # Connect to game
        bridge = Bridge(11753)
        bridge.connect()
        agent = LLMAgent(bridge)

        # Get available rides
        print("\nGetting available rides...")
        rides = agent.get_and_cache_available_rides()

        if not rides:
            print("ERROR: No available rides found or failed to get rides")
            return False

        # Display rides
        print(f"\nAvailable rides ({len(rides)}):")
        for i, ride in enumerate(rides):
            name = ride.get('name', 'Unknown')
            ride_id = ride.get('entry_index', 'N/A')
            ride_type = ride.get('type', 'N/A')
            print(f"  {i+1:2d}. {name} (ID: {ride_id}, Type: {ride_type})")

        # Get user choice
        while True:
            try:
                choice = input(f"\nEnter ride number (1-{len(rides)}) or 'q' to quit: ").strip()
                if choice.lower() == 'q':
                    print("Goodbye!")
                    return True

                idx = int(choice) - 1
                if 0 <= idx < len(rides):
                    break
                else:
                    print(f"Please enter a number between 1 and {len(rides)}")
            except ValueError:
                print("Please enter a valid number or 'q' to quit")

        selected_ride = rides[idx]
        print(f"\nSelected: {selected_ride['name']} (ID: {selected_ride['entry_index']})")

        # Get placement coordinates
        print("\nEnter placement coordinates:")
        while True:
            try:
                x = int(input("X coordinate (0-127): "))
                y = int(input("Y coordinate (0-127): "))
                z = int(input("Z height (0-15): "))
                if 0 <= x <= 127 and 0 <= y <= 127 and 0 <= z <= 15:
                    break
                else:
                    print("Coordinates out of range!")
            except ValueError:
                print("Please enter valid numbers")

        # Place the ride
        print(f"\nPlacing {selected_ride['name']} at ({x}, {y}, {z})...")

        # Simulate tool call
        from types import SimpleNamespace
        tool_call = SimpleNamespace()
        tool_call.function = SimpleNamespace()
        tool_call.function.name = "place_ride"
        tool_call.function.arguments = f'{{"ride_type": {selected_ride["entry_index"]}, "x": {x}, "y": {y}, "z": {z}}}'

        result = agent.execute_tool(tool_call)

        print(f"\nResult: {result}")

        if isinstance(result, dict):
            if "error" in result:
                print("❌ Placement failed!")
                error = result.get("error")
                if "Bridge returned map data" in str(error):
                    print("🚨 CRITICAL: Bridge communication issue detected!")
                    print("   The game returned map data instead of placement result")
                    print("   This may indicate a serious bug in the bridge/game interface")
                elif "Ride placement failed with code" in str(error):
                    print("\n💡 Common placement error codes:")
                    print("   - Code 1: Often insufficient funds or invalid location")
                    print("   - Try different coordinates (near paths/on flat ground)")
                    print("   - Check if you have enough money for this ride type")
                elif "Validation failed" in str(error):
                    print("💡 Validation error - check coordinates and ride ID")
                    details = result.get("details", [])
                    for detail in details:
                        print(f"   - {detail}")
            elif "success" in result:
                print("🎉 Ride placed successfully!")
            else:
                print(f"⚠️  Unexpected result format: {result}")
        else:
            print("✅ Ride placement command sent successfully!")
            if result == 0:
                print("🎉 Ride placed successfully!")
            else:
                print(f"⚠️  Placement returned code: {result}")

        return True

    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)
