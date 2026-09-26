import os, sys
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

# Note: Requires 'openai' package: pip install openai
from openai import OpenAI
from Simulation.config import OPINION_AXIS, LLM_CONFIG

# Initialize OpenAI client (configured via LLM_CONFIG in config.py)
client = OpenAI(
    base_url=LLM_CONFIG["base_url"],
    api_key=LLM_CONFIG["api_key"]
)

def format_opinion_value(opinion_value):
    """
    Format an opinion value with context about what it represents.
    
    Args:
        opinion_value: Float between -1.0 and 1.0
        
    Returns:
        String describing the opinion value in context
    """
    if opinion_value is None:
        return ""
    
    min_label = OPINION_AXIS.get("min_label", "Left")
    max_label = OPINION_AXIS.get("max_label", "Right")
    
    # Determine which side of the spectrum
    if opinion_value < -0.33:
        strength = "strongly" if abs(opinion_value) > 0.66 else "somewhat"
        return f"{strength} {min_label} ({opinion_value:.3f})"
    elif opinion_value > 0.33:
        strength = "strongly" if abs(opinion_value) > 0.66 else "somewhat"
        return f"{strength} {max_label} ({opinion_value:.3f})"
    else:
        return f"centrist/neutral ({opinion_value:.3f})"

def generate_conversation_with_llm(events, topic):
    """
    Generate natural language conversation from events using LLM.
    
    Args:
        events: List of conversation event dictionaries
        topic: The topic being discussed
        
    Returns:
        Formatted conversation text
    """
    from collections import defaultdict
    
    # Group events by conversation_id
    conversations = defaultdict(list)
    for event in events:
        conv_id = event.get('conversation_id', 0)
        conversations[conv_id].append(event)
    
    # Sort events within each conversation by turn
    for conv_id in conversations:
        conversations[conv_id].sort(key=lambda x: x.get('turn', 0))
    
    min_label = OPINION_AXIS.get("min_label", "Left")
    max_label = OPINION_AXIS.get("max_label", "Right")
    
    formatted_conversations = {}
    
    for conv_id, conv_events in conversations.items():
        # Check if this is just research (all events are research)
        all_research = all(ev.get('type') == 'research' for ev in conv_events)
        
        # If all events are research, just show the research (no conversation)
        if all_research:
            lines = []
            for event in conv_events:
                speaker = event.get('speaker', 'Unknown')
                source = event.get('source', 'an article')
                # Handle source being a dict or string
                if isinstance(source, dict):
                    source_name = source.get('name', 'an article')
                else:
                    source_name = source if source else 'an article'
                # Make research sound natural
                lines.append(f"{speaker}: [Researches '{source_name}']")
            formatted_conversations[conv_id] = f"\n=== Conversation {conv_id} ===\n\n" + "\n".join(lines) + "\n"
            continue
        
        # Build context for the LLM
        system_prompt = f"""You are converting structured conversation data into natural, realistic dialogue between people discussing {topic}.

CRITICAL RULES:
- Use the EXACT agent IDs as speaker names (e.g., Max, Lewis, Sebastian) - DO NOT make up names
- Output ONLY the dialogue lines, no meta-commentary, no explanations, no "Here's a dialogue" text
- Start directly with the first speaker's line
- End with the last speaker's line
- NEVER have an agent refer to themselves by their own name - use "I", "me", "my" instead
- When an agent agrees/disagrees with someone, they should refer to the OTHER person by name, not themselves

DIALOGUE QUALITY REQUIREMENTS:
- Make conversations flow naturally - each line should build on or respond to previous statements
- Avoid generic phrases like "I support that" or "I disagree with that" - be specific about what you're supporting/disagreeing with
- Vary your language - don't repeat the same phrases
- Make questions and responses feel connected to the ongoing discussion
- When challenging someone, be specific about what aspect you're challenging
- When agreeing, reference what specifically you agree with
- Use natural conversation patterns - people don't always directly state their opinion, they discuss implications, examples, concerns

Context:
- Topic: {topic}
- Opinion scale: {min_label} (-1.0) to {max_label} (1.0)
- Values closer to -1.0 = {min_label} positions
- Values closer to 1.0 = {max_label} positions  
- Values near 0.0 = centrist/neutral positions

Interaction types (use these to guide the tone, but make dialogue natural):
- "statement": Making an initial statement or sharing a view - be specific and substantive
- "agreement": Agreeing with what someone said - reference what you agree with specifically
- "disagreement": Disagreeing with what someone said - explain your different perspective
- "support": Supporting someone's position with additional arguments - add new points or examples
- "challenge": Challenging or questioning someone's view - raise specific concerns or counterpoints
- "question": Asking a question - make it relevant to the discussion
- "response": Answering a question - address what was actually asked
- "research": Researching/looking up information - make it sound natural like "researches [source]" or "reads up about [source]"

Your task: Convert the events into natural, flowing dialogue that reads like a real conversation. Use opinion values to inform the substance of what they say, but express it naturally without mentioning numbers. Make each line feel like it belongs in an ongoing discussion."""

        # Build the conversation history for context
        conversation_context = []
        for event in conv_events:
            speaker = event.get('speaker', 'Unknown')
            target = event.get('target')
            event_type = event.get('type', 'unknown')
            statement_opinion = event.get('statement_opinion')
            source = event.get('source')
            
            event_desc = f"Turn {event.get('turn', 0)}: {speaker}"
            if target:
                event_desc += f" (to {target})"
            event_desc += f" - {event_type}"
            if statement_opinion is not None:
                if statement_opinion < -0.33:
                    opinion_desc = f"{min_label} leaning"
                elif statement_opinion > 0.33:
                    opinion_desc = f"{max_label} leaning"
                else:
                    opinion_desc = "centrist/neutral"
                event_desc += f" - opinion: {statement_opinion:.3f} ({opinion_desc})"
            if source:
                event_desc += f" - researching: '{source}'"
            
            conversation_context.append(event_desc)
        
        # Check if there are any non-research events (actual conversation)
        has_conversation = any(ev.get('type') != 'research' for ev in conv_events)
        
        if not has_conversation:
            # Only research events - make them sound natural
            lines = []
            for event in conv_events:
                speaker = event.get('speaker', 'Unknown')
                source = event.get('source', 'an article')
                if isinstance(source, dict):
                    source_name = source.get('name', 'an article')
                else:
                    source_name = source if source else 'an article'
                # Make research sound natural
                lines.append(f"{speaker}: [Researches '{source_name}']")
            formatted_conversations[conv_id] = f"\n=== Conversation {conv_id} ===\n\n" + "\n".join(lines) + "\n"
            continue
        
        user_prompt = f"""Convert these events into natural, flowing dialogue. Use the EXACT agent IDs as names.

Events:
{chr(10).join(conversation_context)}

CRITICAL: Each event shows "speaker" and "target" (if present). 
- The SPEAKER is the person talking - they should use "I", "me", "my" when referring to themselves
- The TARGET (if present) is who they're talking TO - refer to them by their exact agent ID name
- NEVER have the speaker refer to themselves by their own name - that's a mistake
- When speaker agrees/disagrees with target, reference what specifically you agree/disagree with from their previous statement

CONVERSATION FLOW:
- Read through all events first to understand the conversation arc
- Each line should feel like a natural response to what came before
- Build on previous statements - reference specific points, ask follow-up questions, provide examples
- Avoid generic responses - be specific about what you're agreeing with, disagreeing with, or challenging
- Make questions feel relevant to the ongoing discussion
- When someone challenges a view, they should reference what aspect they're questioning

IMPORTANT: Only generate dialogue for events that involve actual conversation (statements, agreements, questions, etc.). 
If an event is just "research", make it sound natural like: "Speaker: [Researches 'article name']" or "Speaker: [Reads up about 'article name']"
Do NOT invent conversations that aren't in the events.

Output format (ONLY dialogue, no explanations):
Speaker (to Target): [dialogue]
or
Speaker: [dialogue]

Start with the first event's dialogue immediately. No meta-commentary. Make it read like a real, engaging conversation."""

        try:
            response = client.chat.completions.create(
                model=LLM_CONFIG["model_name"],
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.8,
                max_tokens=2500
            )
            
            generated_text = response.choices[0].message.content
            
            # Clean up meta-commentary and ensure we use actual agent IDs
            lines = generated_text.split('\n')
            cleaned_lines = []
            skip_until_dialogue = False
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Skip meta-commentary lines
                if any(phrase in line.lower() for phrase in [
                    "here's a natural", "okay, here's", "i understand", "now i am ready",
                    "explanation:", "**turn", "**explanation", "based on the provided"
                ]):
                    skip_until_dialogue = True
                    continue
                
                # Skip if it's still in meta-commentary mode and doesn't look like dialogue
                if skip_until_dialogue:
                    # Check if this looks like actual dialogue (has agent ID or colon format)
                    if any(agent_id in line for agent_id in [ev.get('speaker', '') for ev in conv_events]):
                        skip_until_dialogue = False
                    elif ':' in line and not line.startswith('**'):
                        skip_until_dialogue = False
                    else:
                        continue
                
                # Only include lines that look like dialogue
                if ':' in line or any(ev.get('speaker', '') in line for ev in conv_events):
                    # Fix cases where an agent refers to themselves by name
                    # Extract the speaker from the line (format: "Speaker: dialogue")
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            speaker_name = parts[0].strip()
                            dialogue = parts[1].strip()
                            # Replace self-references (e.g., "I agree with Jenson" when Jenson is speaking)
                            if speaker_name in dialogue:
                                # Replace "I agree with [speaker_name]" with "I agree with you" or similar
                                dialogue = dialogue.replace(f"with {speaker_name}", "with you")
                                dialogue = dialogue.replace(f"{speaker_name} said", "you said")
                                dialogue = dialogue.replace(f"{speaker_name}'s", "your")
                                line = f"{speaker_name}: {dialogue}"
                    cleaned_lines.append(line)
            
            # If we got nothing useful, fall back to simple format
            if not cleaned_lines:
                cleaned_lines = []
                for event in conv_events:
                    speaker = event.get('speaker', 'Unknown')
                    target = event.get('target')
                    event_type = event.get('type', 'unknown')
                    if target:
                        cleaned_lines.append(f"{speaker} (to {target}): [{event_type}]")
                    else:
                        cleaned_lines.append(f"{speaker}: [{event_type}]")
            
            formatted_conversations[conv_id] = f"\n=== Conversation {conv_id} ===\n\n" + "\n".join(cleaned_lines) + "\n"
            
        except Exception as e:
            # Fallback to template if LLM fails
            print(f"Warning: LLM generation failed for conversation {conv_id}: {e}")
            print(f"Make sure your LLM service is running at {LLM_CONFIG['base_url']} with model '{LLM_CONFIG['model_name']}' loaded")
            # Generate a simple fallback
            fallback_lines = [f"\n=== Conversation {conv_id} ===\n"]
            for event in conv_events:
                speaker = event.get('speaker', 'Unknown')
                target = event.get('target')
                event_type = event.get('type', 'unknown')
                statement_opinion = event.get('statement_opinion')
                if target:
                    fallback_lines.append(f"{speaker} (to {target}): [{event_type}]")
                else:
                    fallback_lines.append(f"{speaker}: [{event_type}]")
                if statement_opinion is not None:
                    fallback_lines[-1] += f" (opinion: {statement_opinion:.3f})"
            formatted_conversations[conv_id] = "\n".join(fallback_lines) + "\n"
    
    return formatted_conversations

