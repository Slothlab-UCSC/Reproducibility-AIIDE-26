#!/usr/bin/env python3
"""
NYT Connections Puzzle Generator - Main Entry Point
Interactive CLI for generating, evaluating, and simulating puzzles

Usage:
    python main.py                  # Interactive mode
    python main.py --mode trico     # Direct generation
    python main.py --help           # Show options
"""

import os
import sys
import argparse

# Import from modular components
from core import (
    PuzzleMode, ModelBackend, PlayerStrategy,
    OpenSourceLLM, ConnectionsPuzzle
)
from generator import PuzzleGenerator
from player import (
    PuzzleEditor, HumanEvaluator, SmartPuzzlePlayer, PuzzleSimulator,
    print_puzzle, print_evaluation, print_simulation_results
)


def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="NYT Connections Puzzle Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py                           # Interactive mode
    python main.py --mode one_step           # Generate one-step puzzle
    python main.py --mode trico --sims 20    # TriCO with 20 simulations
    python main.py --backend openai          # Use OpenAI GPT-4
    python main.py --theme "science"         # Generate with theme
        """
    )
    
    parser.add_argument(
        '--mode', '-m',
        choices=['one_step', 'intentional_overlap', 'false_group', 
                 'tree_of_thoughts', 'trico'],
        help='Generation mode (default: interactive selection)'
    )
    
    parser.add_argument(
        '--backend', '-b',
        choices=['mock', 'openai', 'open_source'],
        default='mock',
        help='Model backend (default: mock)'
    )
    
    parser.add_argument(
        '--model',
        help='Open source model name (for --backend open_source)'
    )
    
    parser.add_argument(
        '--theme', '-t',
        help='Theme for puzzle generation'
    )
    
    parser.add_argument(
        '--sims', '-s',
        type=int,
        default=10,
        help='Number of player simulations (default: 10)'
    )
    
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Run strategy comparison after generation'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Verbose output during simulations'
    )
    
    parser.add_argument(
        '--interactive', '-i',
        action='store_true',
        help='Force interactive mode even with other arguments'
    )
    
    return parser.parse_args()


def select_mode_interactive() -> PuzzleMode:
    """Interactive mode selection"""
    print("\nSelect generation method:")
    print("1. Original One-Step")
    print("2. Intentional Overlap")
    print("3. False Group")
    print("4. Tree of Thoughts")
    print("5. TriCO (Tri-View Counterfactual)")
    
    method_choice = input("\nChoice (1-5): ").strip()
    
    mode_map = {
        "1": PuzzleMode.ONE_STEP,
        "2": PuzzleMode.INTENTIONAL_OVERLAP,
        "3": PuzzleMode.FALSE_GROUP,
        "4": PuzzleMode.TREE_OF_THOUGHTS,
        "5": PuzzleMode.TRICO
    }
    
    return mode_map.get(method_choice, PuzzleMode.ONE_STEP)


def select_backend_interactive():
    """Interactive backend selection"""
    print("\nSelect model backend:")
    print("1. Mock (no API required)")
    print("2. OpenAI GPT-4")
    print("3. Open Source Model")
    
    backend_choice = input("\nChoice (1-3): ").strip()
    
    selected_model = None
    api_key = None
    
    if backend_choice == "2":
        backend = ModelBackend.OPENAI
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            print("\nNo API key found in environment.")
            print("Enter your API key (or press Enter for mock backend):")
            api_key_input = input().strip()
            if api_key_input:
                api_key = api_key_input
            else:
                backend = ModelBackend.MOCK
                
    elif backend_choice == "3":
        backend = ModelBackend.OPEN_SOURCE
        print("\n" + "=" * 60)
        print("SELECT OPEN SOURCE MODEL")
        print("=" * 60)
        
        models = OpenSourceLLM.RECOMMENDED_MODELS
        for idx, (model_name, description) in enumerate(models, 1):
            print(f"{idx}. {description}")
        
        print(f"{len(models) + 1}. Custom model")
        
        model_choice = input(f"\nChoice (1-{len(models) + 1}): ").strip()
        
        try:
            model_idx = int(model_choice) - 1
            if 0 <= model_idx < len(models):
                selected_model = models[model_idx][0]
            elif model_idx == len(models):
                selected_model = input("Enter model name: ").strip()
            else:
                selected_model = models[0][0]
        except:
            selected_model = models[0][0]
    else:
        backend = ModelBackend.MOCK
    
    return backend, api_key, selected_model


def run_interactive():
    """Run in full interactive mode"""
    print("=" * 60)
    print("NYT Connections Puzzle Generator")
    print("Enhanced Edition with Smart Player & Simulations")
    print("=" * 60)
    
    # Select mode
    selected_mode = select_mode_interactive()
    
    # Select backend
    backend, api_key, selected_model = select_backend_interactive()
    
    # Get theme
    theme = None
    theme_input = input("\nEnter a theme (or press Enter to skip): ").strip()
    if theme_input:
        theme = theme_input
    
    # Get number of simulations
    print("\nHow many player simulations? (Enter for 10):")
    sim_input = input().strip()
    try:
        num_simulations = int(sim_input) if sim_input else 10
        num_simulations = max(1, min(num_simulations, 1000))
    except:
        num_simulations = 10
    
    # Run generation
    run_generation(
        mode=selected_mode,
        backend=backend,
        api_key=api_key,
        model=selected_model,
        theme=theme,
        num_simulations=num_simulations,
        compare_strategies=True,  # Ask interactively
        verbose=True,
        interactive_compare=True
    )


def run_generation(mode: PuzzleMode, 
                   backend: ModelBackend,
                   api_key: str = None,
                   model: str = None,
                   theme: str = None,
                   num_simulations: int = 10,
                   compare_strategies: bool = False,
                   verbose: bool = False,
                   interactive_compare: bool = False):
    """Run puzzle generation with given parameters"""
    
    print(f"\n{'=' * 60}")
    print(f"Configuration:")
    print(f"  Mode: {mode.value}")
    print(f"  Backend: {backend.value}")
    if backend == ModelBackend.OPEN_SOURCE and model:
        print(f"  Model: {model}")
    if theme:
        print(f"  Theme: {theme}")
    print(f"  Simulations: {num_simulations}")
    print(f"{'=' * 60}")
    
    # Initialize components
    print("\nInitializing...")
    generator = PuzzleGenerator(
        api_key=api_key,
        backend=backend,
        open_source_model=model,
        enable_novel_methods=True,
        enable_reinforcement=False,
        enable_ensemble=False
    )
    
    editor = PuzzleEditor(generator)
    evaluator = HumanEvaluator()
    simulator = PuzzleSimulator(generator)
    
    # Generate puzzle
    print("\nGenerating puzzle...")
    puzzle = generator.generate_puzzle(
        mode=mode,
        theme=theme
    )
    
    # Edit puzzle
    print("Refining puzzle...")
    puzzle = editor.edit_puzzle(puzzle, "balance_difficulty")
    puzzle = editor.edit_puzzle(puzzle, "verify_solvability")
    
    # Display puzzle
    print_puzzle(puzzle)
    
    # Evaluate puzzle
    metrics = evaluator.evaluate(puzzle)
    print_evaluation(metrics)
    
    # Run simulations
    sim_result = simulator.simulate(
        puzzle, 
        num_simulations=num_simulations,
        verbose=(verbose and num_simulations <= 20)
    )
    print_simulation_results(sim_result)
    
    # Single detailed play-through
    print("\n" + "=" * 60)
    print("DETAILED PLAY-THROUGH (Hybrid Strategy)")
    print("=" * 60)
    
    player = SmartPuzzlePlayer(generator, PlayerStrategy.HYBRID)
    play_result = player.play(puzzle, verbose=True)
    
    print(f"\nPlay Summary:")
    print(f"  Solved: {'✓' if play_result.solved else '✗'}")
    print(f"  Groups Found: {len(play_result.groups_found)}/4")
    print(f"  Mistakes: {play_result.mistakes}/4")
    print(f"  Time: {play_result.time_taken:.2f}s")
    
    # Show reasoning traces if available
    if play_result.reasoning_traces:
        print(f"\nReasoning Traces:")
        for i, trace in enumerate(play_result.reasoning_traces[:5], 1):
            print(f"  {i}. {trace[:80]}...")
    
    # Show metadata
    if puzzle.metadata:
        print("\n" + "=" * 60)
        print("PUZZLE METADATA")
        print("=" * 60)
        for key, value in puzzle.metadata.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.3f}")
            elif isinstance(value, bool):
                print(f"  {key}: {value}")
            elif isinstance(value, str):
                print(f"  {key}: {value}")
            elif isinstance(value, int):
                print(f"  {key}: {value}")
    
    # Special messages for TriCO
    if mode == PuzzleMode.TRICO:
        print("\n" + "=" * 60)
        print("TriCO PUZZLE INFO")
        print("=" * 60)
        
        # Show if fully dynamic
        if puzzle.metadata.get('fully_dynamic'):
            print("Generation: FULLY DYNAMIC (no hardcoded words)")
            print("  - Rhymes detected via CMU Pronouncing Dictionary")
            print("  - Semantic groups discovered via embeddings + LLM")
            print("  - Orthographic patterns analyzed from word pool")
        else:
            print("This puzzle uses pattern-based multi-view optimization:")
        print()
        
        print("Pattern Types:")
        print("- Semantic: Words that share meaning/category")
        print("- Phonetic: Words that actually rhyme (same sound)")
        print("- Orthographic: Words with visual patterns (length, prefix)")
        print()
        
        # Show view distribution if available
        if 'view_distribution' in puzzle.metadata:
            view_dist = puzzle.metadata['view_distribution']
            view_names = {'sem': 'Semantic', 'pho': 'Phonetic', 'orth': 'Orthographic'}
            print("View Distribution:")
            for view, count in view_dist.items():
                print(f"  {view_names.get(view, view)}: {count} group(s)")
            print()
        
        print("Group Details:")
        for group in puzzle.groups:
            view_name = {'sem': 'Semantic', 'pho': 'Phonetic', 'orth': 'Orthographic'}.get(
                group.primary_view, group.primary_view or 'Unknown'
            )
            print(f"  {group.difficulty.name}: {group.category} [{view_name}]")
    
    # Strategy comparison
    if interactive_compare:
        print("\n" + "=" * 60)
        compare_choice = input("Compare player strategies? (y/n): ").strip().lower()
        compare_strategies = (compare_choice == 'y')
    
    if compare_strategies:
        comparison = simulator.compare_strategies(puzzle, num_per_strategy=10)
        
        print("\n" + "=" * 60)
        print("STRATEGY COMPARISON")
        print("=" * 60)
        
        for strategy, stats in sorted(comparison.items(), 
                                     key=lambda x: x[1]['solve_rate'], 
                                     reverse=True):
            print(f"\n{strategy}:")
            print(f"  Solve Rate:    {stats['solve_rate']:.1%}")
            print(f"  Mean Mistakes: {stats['mean_mistakes']:.2f}")
            print(f"  Mean Time:     {stats['mean_time']:.3f}s")
    
    print("\n" + "=" * 60)
    print("Generation complete!")
    print("=" * 60)
    
    return puzzle, metrics, sim_result


def main():
    """Main entry point"""
    args = parse_args()
    
    # Determine if we should run interactive mode
    run_interactive_mode = args.interactive or (args.mode is None and not sys.stdin.isatty())
    
    if args.mode is None and not args.interactive:
        # No mode specified, run fully interactive
        run_interactive()
    else:
        # Parse mode
        mode_map = {
            'one_step': PuzzleMode.ONE_STEP,
            'intentional_overlap': PuzzleMode.INTENTIONAL_OVERLAP,
            'false_group': PuzzleMode.FALSE_GROUP,
            'tree_of_thoughts': PuzzleMode.TREE_OF_THOUGHTS,
            'trico': PuzzleMode.TRICO
        }
        selected_mode = mode_map.get(args.mode, PuzzleMode.ONE_STEP)
        
        # Parse backend
        backend_map = {
            'mock': ModelBackend.MOCK,
            'openai': ModelBackend.OPENAI,
            'open_source': ModelBackend.OPEN_SOURCE
        }
        backend = backend_map.get(args.backend, ModelBackend.MOCK)
        
        # Get API key for OpenAI
        api_key = None
        if backend == ModelBackend.OPENAI:
            api_key = os.environ.get('OPENAI_API_KEY')
            if not api_key:
                print("Warning: OPENAI_API_KEY not set, falling back to mock backend")
                backend = ModelBackend.MOCK
        
        # Run generation
        run_generation(
            mode=selected_mode,
            backend=backend,
            api_key=api_key,
            model=args.model,
            theme=args.theme,
            num_simulations=args.sims,
            compare_strategies=args.compare,
            verbose=args.verbose,
            interactive_compare=False
        )


if __name__ == "__main__":
    main()
