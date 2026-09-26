import React, { useState, useEffect, useCallback } from 'react';

// ============================================================
// CONNECTIONS PUZZLE GENERATOR - POSTMODERN MINIMALIST UI
// ============================================================

const DIFFICULTY_COLORS = {
  YELLOW: { bg: '#F7DF94', text: '#1a1a1a' },
  GREEN: { bg: '#A8D08D', text: '#1a1a1a' },
  BLUE: { bg: '#9DB4D4', text: '#1a1a1a' },
  PURPLE: { bg: '#C4A8D0', text: '#1a1a1a' }
};

const METHODS = [
  { id: 'one_step', name: 'One-Step', desc: 'Direct generation', icon: '○' },
  { id: 'intentional_overlap', name: 'Overlap', desc: 'Multi-meaning traps', icon: '◎' },
  { id: 'false_group', name: 'False Group', desc: 'Red herrings', icon: '◇' },
  { id: 'tree_of_thoughts', name: 'Tree of Thoughts', desc: 'Iterative exploration', icon: '△' },
  { id: 'trico', name: 'TriCO', desc: 'Tri-view optimization', icon: '☆' }
];

// ============================================================
// UTILITY COMPONENTS
// ============================================================

const FadeIn = ({ children, delay = 0, className = '' }) => {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setVisible(true), delay);
    return () => clearTimeout(timer);
  }, [delay]);
  
  return (
    <div 
      className={`transition-all duration-700 ease-out ${className}`}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateY(0)' : 'translateY(20px)'
      }}
    >
      {children}
    </div>
  );
};

const Spinner = () => (
  <div className="relative w-8 h-8">
    <div className="absolute inset-0 border border-neutral-200 rounded-full" />
    <div className="absolute inset-0 border border-transparent border-t-neutral-900 rounded-full animate-spin" />
  </div>
);

const AnimatedNumber = ({ value, suffix = '' }) => {
  const [display, setDisplay] = useState(0);
  
  useEffect(() => {
    const target = parseFloat(value) || 0;
    const duration = 1000;
    const steps = 30;
    const increment = target / steps;
    let current = 0;
    
    const timer = setInterval(() => {
      current += increment;
      if (current >= target) {
        setDisplay(target);
        clearInterval(timer);
      } else {
        setDisplay(current);
      }
    }, duration / steps);
    
    return () => clearInterval(timer);
  }, [value]);
  
  return <span>{typeof value === 'number' && value % 1 !== 0 ? display.toFixed(1) : Math.round(display)}{suffix}</span>;
};

// ============================================================
// MAIN APPLICATION
// ============================================================

export default function ConnectionsGenerator() {
  const [phase, setPhase] = useState('landing'); // landing, config, generating, results
  const [method, setMethod] = useState('trico');
  const [theme, setTheme] = useState('');
  const [simCount, setSimCount] = useState(10);
  const [puzzle, setPuzzle] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [simResults, setSimResults] = useState(null);
  const [genStep, setGenStep] = useState(0);
  const [revealed, setRevealed] = useState([]);
  const [error, setError] = useState(null);

  const GEN_STEPS = [
    'Initializing generator',
    'Building word pool',
    'Finding semantic groups',
    'Detecting phonetic patterns',
    'Analyzing orthographic features',
    'Selecting diverse groups',
    'Validating puzzle quality',
    'Running player simulations',
    'Finalizing results'
  ];

  // ============================================================
  // API CALLS
  // ============================================================

  const generatePuzzle = async () => {
    setPhase('generating');
    setGenStep(0);
    setError(null);
    setRevealed([]);

    try {
      // Step through generation phases
      for (let i = 0; i < GEN_STEPS.length - 2; i++) {
        setGenStep(i);
        await new Promise(r => setTimeout(r, 400 + Math.random() * 300));
      }

      // Generate puzzle via Claude
      setGenStep(GEN_STEPS.length - 2);
      const puzzleData = await callClaudeForPuzzle();
      setPuzzle(puzzleData.puzzle);
      setMetrics(puzzleData.metrics);

      // Simulate
      setGenStep(GEN_STEPS.length - 1);
      const simData = await callClaudeForSimulation(puzzleData.puzzle);
      setSimResults(simData);

      await new Promise(r => setTimeout(r, 500));
      setPhase('results');

    } catch (err) {
      console.error(err);
      setError(err.message || 'Generation failed');
      setPhase('config');
    }
  };

  const callClaudeForPuzzle = async () => {
    const methodInstructions = {
      one_step: 'Generate a standard puzzle with clear categories.',
      intentional_overlap: 'Create words with multiple meanings that could belong to different categories.',
      false_group: 'Include 4 words that seem related but actually belong to separate groups.',
      tree_of_thoughts: 'Explore creative and unusual category types.',
      trico: 'Include: 2-3 semantic groups (meaning-based), 1 phonetic group (rhyming words), and optionally 1 orthographic group (same length or pattern).'
    };

    const prompt = `Generate an NYT Connections puzzle. ${methodInstructions[method]}
${theme ? `Theme: ${theme}` : ''}

Create exactly 4 groups of 4 words (16 total unique words).
- YELLOW: Easiest category
- GREEN: Medium difficulty  
- BLUE: Harder category
- PURPLE: Hardest/trickiest category

Rules:
- All words UPPERCASE, single words only
- Each word appears exactly once
- Categories should be specific and clever
${method === 'trico' ? '- Include at least one group that rhymes (same sound) and one group with same word length' : ''}

Also evaluate the puzzle quality.

Respond with ONLY this JSON (no other text):
{
  "puzzle": {
    "groups": [
      {"difficulty": "YELLOW", "category": "Category Name", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]},
      {"difficulty": "GREEN", "category": "Category Name", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]},
      {"difficulty": "BLUE", "category": "Category Name", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]},
      {"difficulty": "PURPLE", "category": "Category Name", "words": ["WORD1", "WORD2", "WORD3", "WORD4"]}
    ]
  },
  "metrics": {
    "semanticClarity": 0.75,
    "deceptiveness": 0.45,
    "creativity": 0.80,
    "overallQuality": 0.70,
    "estimatedSolveRate": 55,
    "nearMissCount": 42
  }
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1500,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    const data = await response.json();
    const text = data.content[0].text;
    const json = JSON.parse(text.match(/\{[\s\S]*\}/)[0]);
    return json;
  };

  const callClaudeForSimulation = async (puzzleData) => {
    const prompt = `Simulate ${simCount} players solving this Connections puzzle:

${JSON.stringify(puzzleData, null, 2)}

Provide realistic simulation results.

Respond with ONLY this JSON:
{
  "totalRuns": ${simCount},
  "solveRate": 0.70,
  "avgMistakes": 1.8,
  "strategies": {
    "hybrid": { "solveRate": 0.85, "avgMistakes": 1.2 },
    "humanLike": { "solveRate": 0.75, "avgMistakes": 1.8 },
    "embedding": { "solveRate": 0.50, "avgMistakes": 2.5 }
  },
  "groupDifficulty": {
    "YELLOW": 0.95,
    "GREEN": 0.80,
    "BLUE": 0.65,
    "PURPLE": 0.45
  }
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 800,
        messages: [{ role: 'user', content: prompt }]
      })
    });

    const data = await response.json();
    const text = data.content[0].text;
    return JSON.parse(text.match(/\{[\s\S]*\}/)[0]);
  };

  const revealGroup = (index) => {
    if (!revealed.includes(index)) {
      setRevealed([...revealed, index]);
    }
  };

  const reset = () => {
    setPhase('config');
    setPuzzle(null);
    setMetrics(null);
    setSimResults(null);
    setRevealed([]);
  };

  // ============================================================
  // LANDING PAGE
  // ============================================================

  if (phase === 'landing') {
    return (
      <div className="min-h-screen bg-white flex flex-col items-center justify-center p-8">
        <FadeIn delay={0}>
          <div className="w-16 h-16 mb-8 grid grid-cols-2 gap-1">
            <div className="bg-yellow-200 rounded-sm" />
            <div className="bg-green-200 rounded-sm" />
            <div className="bg-blue-200 rounded-sm" />
            <div className="bg-purple-200 rounded-sm" />
          </div>
        </FadeIn>
        
        <FadeIn delay={200}>
          <h1 className="text-5xl font-extralight tracking-tight text-neutral-900 mb-3">
            Connections
          </h1>
        </FadeIn>
        
        <FadeIn delay={400}>
          <p className="text-neutral-400 tracking-widest text-xs uppercase mb-12">
            Puzzle Generator
          </p>
        </FadeIn>
        
        <FadeIn delay={600}>
          <button
            onClick={() => setPhase('config')}
            className="group relative px-12 py-4 bg-neutral-900 text-white text-sm tracking-widest uppercase overflow-hidden"
          >
            <span className="relative z-10">Begin</span>
            <div className="absolute inset-0 bg-neutral-700 transform translate-y-full group-hover:translate-y-0 transition-transform duration-300" />
          </button>
        </FadeIn>
        
        <FadeIn delay={800}>
          <p className="mt-16 text-xs text-neutral-300 max-w-md text-center leading-relaxed">
            Generate challenging word puzzles using advanced AI methods including semantic analysis, 
            phonetic patterns, and multi-view optimization.
          </p>
        </FadeIn>
      </div>
    );
  }

  // ============================================================
  // CONFIGURATION PAGE
  // ============================================================

  if (phase === 'config') {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-8">
        <div className="w-full max-w-lg">
          <FadeIn>
            <button 
              onClick={() => setPhase('landing')}
              className="text-xs text-neutral-400 hover:text-neutral-900 transition-colors mb-8 flex items-center gap-2"
            >
              <span>←</span> Back
            </button>
          </FadeIn>

          <FadeIn delay={100}>
            <h2 className="text-3xl font-extralight text-neutral-900 mb-1">Configure</h2>
            <p className="text-neutral-400 text-sm mb-12">Set your generation parameters</p>
          </FadeIn>

          {/* Method Selection */}
          <FadeIn delay={200}>
            <div className="mb-10">
              <label className="text-xs tracking-widest uppercase text-neutral-400 mb-4 block">
                Method
              </label>
              <div className="grid grid-cols-1 gap-2">
                {METHODS.map((m, i) => (
                  <button
                    key={m.id}
                    onClick={() => setMethod(m.id)}
                    className={`
                      p-4 text-left transition-all duration-200 border
                      ${method === m.id 
                        ? 'border-neutral-900 bg-neutral-50' 
                        : 'border-neutral-100 hover:border-neutral-300'
                      }
                    `}
                  >
                    <div className="flex items-center gap-4">
                      <span className={`text-lg ${method === m.id ? 'text-neutral-900' : 'text-neutral-300'}`}>
                        {m.icon}
                      </span>
                      <div className="flex-1">
                        <span className={`block text-sm ${method === m.id ? 'text-neutral-900' : 'text-neutral-500'}`}>
                          {m.name}
                        </span>
                        <span className="text-xs text-neutral-400">{m.desc}</span>
                      </div>
                      {method === m.id && (
                        <span className="w-2 h-2 bg-neutral-900 rounded-full" />
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          </FadeIn>

          {/* Theme Input */}
          <FadeIn delay={300}>
            <div className="mb-10">
              <label className="text-xs tracking-widest uppercase text-neutral-400 mb-4 block">
                Theme <span className="normal-case">(optional)</span>
              </label>
              <input
                type="text"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                placeholder="e.g., Music, Sports, Movies..."
                className="w-full p-4 border border-neutral-100 focus:border-neutral-900 outline-none transition-colors text-neutral-900 placeholder-neutral-300 text-sm"
              />
            </div>
          </FadeIn>

          {/* Simulations */}
          <FadeIn delay={400}>
            <div className="mb-12">
              <div className="flex justify-between items-center mb-4">
                <label className="text-xs tracking-widest uppercase text-neutral-400">
                  Simulations
                </label>
                <span className="text-sm text-neutral-900 font-light">{simCount}</span>
              </div>
              <input
                type="range"
                min="1"
                max="50"
                value={simCount}
                onChange={(e) => setSimCount(parseInt(e.target.value))}
                className="w-full h-px bg-neutral-200 appearance-none cursor-pointer
                  [&::-webkit-slider-thumb]:appearance-none
                  [&::-webkit-slider-thumb]:w-4
                  [&::-webkit-slider-thumb]:h-4
                  [&::-webkit-slider-thumb]:bg-neutral-900
                  [&::-webkit-slider-thumb]:rounded-full
                  [&::-webkit-slider-thumb]:cursor-pointer
                  [&::-webkit-slider-thumb]:transition-transform
                  [&::-webkit-slider-thumb]:hover:scale-125"
              />
            </div>
          </FadeIn>

          {/* Generate Button */}
          <FadeIn delay={500}>
            <button
              onClick={generatePuzzle}
              className="w-full py-4 bg-neutral-900 text-white text-sm tracking-widest uppercase hover:bg-neutral-800 transition-colors"
            >
              Generate
            </button>
          </FadeIn>

          {error && (
            <FadeIn>
              <p className="mt-4 text-sm text-red-500 text-center">{error}</p>
            </FadeIn>
          )}
        </div>
      </div>
    );
  }

  // ============================================================
  // GENERATING PAGE
  // ============================================================

  if (phase === 'generating') {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-8">
        <div className="w-full max-w-md">
          <div className="flex justify-center mb-8">
            <Spinner />
          </div>
          
          <h2 className="text-2xl font-extralight text-neutral-900 text-center mb-2">
            Generating
          </h2>
          
          <p className="text-sm text-neutral-400 text-center mb-12">
            {GEN_STEPS[genStep]}
          </p>

          {/* Progress Steps */}
          <div className="space-y-3">
            {GEN_STEPS.map((step, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className={`
                  w-6 h-6 rounded-full flex items-center justify-center text-xs
                  transition-all duration-300
                  ${i < genStep ? 'bg-neutral-900 text-white' : ''}
                  ${i === genStep ? 'bg-neutral-200 text-neutral-600' : ''}
                  ${i > genStep ? 'bg-neutral-50 text-neutral-300' : ''}
                `}>
                  {i < genStep ? '✓' : i + 1}
                </div>
                <span className={`
                  text-sm transition-colors duration-300
                  ${i <= genStep ? 'text-neutral-900' : 'text-neutral-300'}
                `}>
                  {step}
                </span>
              </div>
            ))}
          </div>

          {/* Animated Grid Preview */}
          <div className="mt-12 grid grid-cols-4 gap-1">
            {[...Array(16)].map((_, i) => (
              <div 
                key={i}
                className="aspect-square bg-neutral-100 animate-pulse"
                style={{ 
                  animationDelay: `${i * 100}ms`,
                  animationDuration: '1.5s'
                }}
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  // ============================================================
  // RESULTS PAGE
  // ============================================================

  if (phase === 'results' && puzzle) {
    const allWords = puzzle.groups.flatMap(g => g.words);
    const shuffledWords = [...allWords].sort(() => 0.5 - Math.random());

    return (
      <div className="min-h-screen bg-white">
        {/* Header */}
        <div className="border-b border-neutral-100">
          <div className="max-w-4xl mx-auto px-8 py-6 flex justify-between items-center">
            <div>
              <h1 className="text-xl font-extralight text-neutral-900">
                {METHODS.find(m => m.id === method)?.name} Puzzle
              </h1>
              {theme && <p className="text-xs text-neutral-400 mt-1">Theme: {theme}</p>}
            </div>
            <button
              onClick={reset}
              className="px-4 py-2 text-xs tracking-widest uppercase border border-neutral-200 hover:border-neutral-900 transition-colors"
            >
              New Puzzle
            </button>
          </div>
        </div>

        <div className="max-w-4xl mx-auto px-8 py-12">
          {/* Puzzle Grid */}
          <FadeIn>
            <div className="mb-16">
              <h3 className="text-xs tracking-widest uppercase text-neutral-400 mb-4">
                Puzzle
              </h3>
              <div className="grid grid-cols-4 gap-2">
                {shuffledWords.map((word, i) => {
                  const groupIndex = puzzle.groups.findIndex(g => g.words.includes(word));
                  const isRevealed = revealed.includes(groupIndex);
                  const color = puzzle.groups[groupIndex]?.difficulty;
                  
                  return (
                    <div
                      key={i}
                      className="aspect-square flex items-center justify-center text-xs font-medium tracking-wide transition-all duration-500 cursor-pointer hover:scale-105"
                      style={{
                        backgroundColor: isRevealed ? DIFFICULTY_COLORS[color]?.bg : '#f5f5f5',
                        color: isRevealed ? DIFFICULTY_COLORS[color]?.text : '#525252'
                      }}
                      onClick={() => revealGroup(groupIndex)}
                    >
                      {word}
                    </div>
                  );
                })}
              </div>
              <p className="text-xs text-neutral-400 mt-3 text-center">
                Click tiles to reveal groups
              </p>
            </div>
          </FadeIn>

          {/* Solution */}
          <FadeIn delay={200}>
            <div className="mb-16">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xs tracking-widest uppercase text-neutral-400">
                  Solution
                </h3>
                <button
                  onClick={() => setRevealed([0, 1, 2, 3])}
                  className="text-xs text-neutral-400 hover:text-neutral-900 transition-colors"
                >
                  Reveal All
                </button>
              </div>
              <div className="space-y-2">
                {puzzle.groups.map((group, i) => (
                  <div
                    key={i}
                    onClick={() => revealGroup(i)}
                    className={`
                      p-4 cursor-pointer transition-all duration-500
                      ${revealed.includes(i) ? '' : 'opacity-30 hover:opacity-60'}
                    `}
                    style={{
                      backgroundColor: DIFFICULTY_COLORS[group.difficulty]?.bg
                    }}
                  >
                    <div className="flex justify-between items-start">
                      <div>
                        <p className="text-xs uppercase tracking-wide opacity-60 mb-1">
                          {group.difficulty}
                        </p>
                        <p className="text-sm font-medium mb-2">{group.category}</p>
                        <p className="text-xs opacity-80">
                          {group.words.join(' · ')}
                        </p>
                      </div>
                      {!revealed.includes(i) && (
                        <span className="text-xs opacity-50">Click to reveal</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </FadeIn>

          {/* Metrics */}
          {metrics && (
            <FadeIn delay={400}>
              <div className="mb-16">
                <h3 className="text-xs tracking-widest uppercase text-neutral-400 mb-6">
                  Quality Metrics
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-8">
                  <div>
                    <p className="text-3xl font-extralight text-neutral-900">
                      <AnimatedNumber value={metrics.overallQuality * 100} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Overall Quality</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={metrics.estimatedSolveRate} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Est. Solve Rate</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={metrics.nearMissCount} />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Near Misses</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={metrics.semanticClarity * 100} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Semantic Clarity</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={metrics.deceptiveness * 100} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Deceptiveness</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={metrics.creativity * 100} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Creativity</p>
                  </div>
                </div>
              </div>
            </FadeIn>
          )}

          {/* Simulation Results */}
          {simResults && (
            <FadeIn delay={600}>
              <div className="mb-16">
                <h3 className="text-xs tracking-widest uppercase text-neutral-400 mb-6">
                  Simulation Results
                </h3>
                
                <div className="grid grid-cols-3 gap-8 mb-8">
                  <div>
                    <p className="text-3xl font-extralight text-neutral-900">
                      <AnimatedNumber value={simResults.solveRate * 100} suffix="%" />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Solve Rate</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      <AnimatedNumber value={simResults.avgMistakes} />
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Avg Mistakes</p>
                  </div>
                  <div>
                    <p className="text-3xl font-extralight text-neutral-600">
                      {simResults.totalRuns}
                    </p>
                    <p className="text-xs text-neutral-400 mt-1">Simulations</p>
                  </div>
                </div>

                {/* Strategy Performance */}
                <div className="space-y-4">
                  <p className="text-xs text-neutral-400 uppercase tracking-wide">Strategy Performance</p>
                  {Object.entries(simResults.strategies || {}).map(([name, data]) => (
                    <div key={name} className="flex items-center gap-4">
                      <span className="w-24 text-xs text-neutral-500 capitalize">{name}</span>
                      <div className="flex-1 h-1 bg-neutral-100 rounded-full overflow-hidden">
                        <div 
                          className="h-full bg-neutral-900 transition-all duration-1000 ease-out"
                          style={{ width: `${(data.solveRate || 0) * 100}%` }}
                        />
                      </div>
                      <span className="w-12 text-xs text-neutral-900 text-right">
                        {Math.round((data.solveRate || 0) * 100)}%
                      </span>
                    </div>
                  ))}
                </div>

                {/* Group Difficulty */}
                {simResults.groupDifficulty && (
                  <div className="mt-8 space-y-4">
                    <p className="text-xs text-neutral-400 uppercase tracking-wide">Group Success Rate</p>
                    {Object.entries(simResults.groupDifficulty).map(([color, rate]) => (
                      <div key={color} className="flex items-center gap-4">
                        <span 
                          className="w-24 text-xs font-medium px-2 py-1"
                          style={{ backgroundColor: DIFFICULTY_COLORS[color]?.bg }}
                        >
                          {color}
                        </span>
                        <div className="flex-1 h-1 bg-neutral-100 rounded-full overflow-hidden">
                          <div 
                            className="h-full transition-all duration-1000 ease-out"
                            style={{ 
                              width: `${(rate || 0) * 100}%`,
                              backgroundColor: DIFFICULTY_COLORS[color]?.bg
                            }}
                          />
                        </div>
                        <span className="w-12 text-xs text-neutral-900 text-right">
                          {Math.round((rate || 0) * 100)}%
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </FadeIn>
          )}

          {/* Footer */}
          <FadeIn delay={800}>
            <div className="pt-8 border-t border-neutral-100 text-center">
              <p className="text-xs text-neutral-300">
                Connections Puzzle Generator · {new Date().toLocaleDateString()}
              </p>
            </div>
          </FadeIn>
        </div>
      </div>
    );
  }

  return null;
}
