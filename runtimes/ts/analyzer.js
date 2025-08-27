#!/usr/bin/env node
/**
 * TypeScript/JavaScript AST Analyzer for MCP Orchestrator
 * Analyzes TypeScript/JavaScript code using built-in Node.js capabilities
 * No external dependencies required
 */

const fs = require('fs');
const path = require('path');

class TypeScriptAnalyzer {
    constructor() {
        this.functions = [];
        this.totalBranches = 0;
        this.complexity = 0;
        this.sideEffects = new Set();
        this.currentFunction = null;
    }

    analyze(code) {
        try {
            // Simple regex-based parsing for basic function detection
            // This is a simplified approach that works without external dependencies
            this.parseCode(code);
            
            return {
                functions: this.functions,
                inputs: this.collectAllInputs(),
                outputs: this.collectAllOutputs(),
                complexity: this.complexity,
                branches: this.totalBranches,
                side_effects: Array.from(this.sideEffects)
            };
        } catch (error) {
            return { error: `Analysis error: ${error.message}` };
        }
    }

    parseCode(code) {
        const lines = code.split('\n');
        let currentLineNum = 0;
        let inFunction = false;
        let braceCount = 0;
        let functionStartLine = 0;

        // Patterns for different function types
        const functionPatterns = [
            // function declaration: function name(params) { }
            /^\s*function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{/,
            // arrow function: const name = (params) => { } or const name = params => expr
            /^\s*(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:\(([^)]*)\)|([a-zA-Z_$][a-zA-Z0-9_$]*))?\s*=>\s*(.*)/,
            // method: methodName(params) { } or async methodName(params) { }
            /^\s*(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{/,
            // class method: public/private methodName(params) { }
            /^\s*(?:public|private|protected|static)?\s*(?:async\s+)?([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(([^)]*)\)\s*(?::\s*([^{]+))?\s*\{/
        ];

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            currentLineNum = i + 1;

            // Skip comments and empty lines
            if (line.trim().startsWith('//') || line.trim().startsWith('/*') || line.trim() === '') {
                continue;
            }

            // Try to match function patterns
            if (!inFunction) {
                for (const pattern of functionPatterns) {
                    const match = line.match(pattern);
                    if (match) {
                        inFunction = true;
                        functionStartLine = currentLineNum;
                        braceCount = 1;
                        
                        const funcInfo = this.extractFunctionInfo(match, currentLineNum);
                        this.currentFunction = funcInfo;
                        
                        // Check if it's a single-line arrow function
                        if (pattern.source.includes('=>') && !line.includes('{')) {
                            // Single expression arrow function
                            inFunction = false;
                            funcInfo.line_end = currentLineNum;
                            this.functions.push(funcInfo);
                            this.totalBranches += funcInfo.branches;
                            this.complexity += funcInfo.local_complexity;
                            this.currentFunction = null;
                        }
                        break;
                    }
                }
            }

            if (inFunction) {
                // Count braces to track function scope
                const openBraces = (line.match(/\{/g) || []).length;
                const closeBraces = (line.match(/\}/g) || []).length;
                braceCount += openBraces - closeBraces;

                // Analyze function content
                this.analyzeLine(line);

                // Function ended
                if (braceCount === 0) {
                    inFunction = false;
                    if (this.currentFunction) {
                        this.currentFunction.line_end = currentLineNum;
                        this.functions.push(this.currentFunction);
                        this.totalBranches += this.currentFunction.branches;
                        this.complexity += this.currentFunction.local_complexity;
                        this.currentFunction = null;
                    }
                }
            } else {
                // Global scope analysis for side effects
                this.analyzeLine(line);
            }
        }
    }

    extractFunctionInfo(match, lineNum) {
        let name = 'anonymous';
        let params = '';
        let returnType = 'any';

        if (match[1]) {
            name = match[1];
        }

        // Extract parameters (match[2] for regular functions, match[3] for single param arrow functions)
        if (match[2] !== undefined) {
            params = match[2];
        } else if (match[3] !== undefined) {
            params = match[3];
        }

        // Extract return type if available
        if (match[3] && match[0].includes(':')) {
            returnType = match[3].trim();
        }

        return {
            name: name,
            inputs: this.parseParameters(params),
            outputs: returnType !== 'any' ? [returnType] : ['inferred'],
            line_start: lineNum,
            line_end: lineNum,
            branches: 0,
            local_complexity: 1
        };
    }

    parseParameters(paramString) {
        if (!paramString || paramString.trim() === '') {
            return [];
        }

        const inputs = [];
        const params = paramString.split(',');

        for (const param of params) {
            const trimmedParam = param.trim();
            if (trimmedParam) {
                // Parse parameter with optional type annotation
                const match = trimmedParam.match(/^\s*([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?::\s*([^=]+))?\s*(?:=.*)?/);
                if (match) {
                    inputs.push({
                        name: match[1],
                        type: match[2] ? match[2].trim() : 'any',
                        kind: 'parameter',
                        optional: trimmedParam.includes('?') || trimmedParam.includes('=')
                    });
                }
            }
        }

        return inputs;
    }

    analyzeLine(line) {
        // Count control flow statements (branches)
        const controlFlowPatterns = [
            /\bif\s*\(/g,
            /\belse\s+if\s*\(/g,
            /\belse\b/g,
            /\bswitch\s*\(/g,
            /\bcase\s+/g,
            /\bfor\s*\(/g,
            /\bwhile\s*\(/g,
            /\bdo\s*\{/g,
            /\btry\s*\{/g,
            /\bcatch\s*\(/g,
            /\bfinally\s*\{/g,
            /\?.*:/g // ternary operator
        ];

        for (const pattern of controlFlowPatterns) {
            const matches = line.match(pattern);
            if (matches) {
                const count = matches.length;
                if (this.currentFunction) {
                    this.currentFunction.branches += count;
                    this.currentFunction.local_complexity += count;
                } else {
                    this.totalBranches += count;
                    this.complexity += count;
                }
            }
        }

        // Detect side effects
        this.detectSideEffectsInLine(line);
    }

    detectSideEffectsInLine(line) {
        const sideEffectPatterns = [
            // Console operations
            { pattern: /console\.(log|error|warn|info|debug)/g, effect: 'io_operations' },
            // DOM operations
            { pattern: /document\.|window\.|getElementById|querySelector/g, effect: 'dom_operations' },
            // Network operations
            { pattern: /fetch\s*\(|XMLHttpRequest|axios\.|\.get\(|\.post\(|\.put\(|\.delete\(/g, effect: 'network_operations' },
            // Storage operations
            { pattern: /localStorage|sessionStorage|indexedDB/g, effect: 'storage_operations' },
            // File operations (Node.js)
            { pattern: /fs\.|require\s*\(\s*['"]fs['"]|readFile|writeFile/g, effect: 'file_operations' },
            // Timer operations
            { pattern: /setTimeout|setInterval|requestAnimationFrame/g, effect: 'timer_operations' },
            // Global state modification
            { pattern: /global\.|process\.|window\.[a-zA-Z]/g, effect: 'global_state' },
            // Async operations
            { pattern: /\bawait\b|\.then\s*\(|\.catch\s*\(|new Promise/g, effect: 'async_operations' },
            // Error throwing
            { pattern: /throw\s+/g, effect: 'exception_throwing' }
        ];

        for (const { pattern, effect } of sideEffectPatterns) {
            if (pattern.test(line)) {
                this.sideEffects.add(effect);
            }
        }

        // Detect imports/requires
        if (/\bimport\b|\brequire\s*\(/g.test(line)) {
            this.sideEffects.add('module_loading');
        }

        // Detect class instantiation
        if (/\bnew\s+[A-Z]/g.test(line)) {
            this.sideEffects.add('object_creation');
        }
    }

    collectAllInputs() {
        const allInputs = [];
        for (const func of this.functions) {
            for (const input of func.inputs) {
                const inputStr = `${input.name}: ${input.type}`;
                if (!allInputs.includes(inputStr)) {
                    allInputs.push(inputStr);
                }
            }
        }
        return allInputs;
    }

    collectAllOutputs() {
        const allOutputs = [];
        for (const func of this.functions) {
            for (const output of func.outputs) {
                if (!allOutputs.includes(output)) {
                    allOutputs.push(output);
                }
            }
        }
        return allOutputs.length > 0 ? allOutputs : ['void'];
    }
}

// Main execution
if (require.main === module) {
    let input = '';
    
    process.stdin.setEncoding('utf8');
    process.stdin.on('readable', () => {
        const chunk = process.stdin.read();
        if (chunk !== null) {
            input += chunk;
        }
    });
    
    process.stdin.on('end', () => {
        try {
            if (!input.trim()) {
                console.log(JSON.stringify({ error: "No code provided" }));
                process.exit(1);
                return;
            }

            const analyzer = new TypeScriptAnalyzer();
            const result = analyzer.analyze(input);
            console.log(JSON.stringify(result));
        } catch (error) {
            console.log(JSON.stringify({ error: `Analyzer failure: ${error.message}` }));
            process.exit(1);
        }
    });

    // Handle timeout
    setTimeout(() => {
        console.log(JSON.stringify({ error: "Analysis timeout" }));
        process.exit(1);
    }, 10000);
}

module.exports = TypeScriptAnalyzer;